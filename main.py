from fastapi import FastAPI, Depends, HTTPException, Request
import pandas as pd
from sqlalchemy.orm import Session
from openai import OpenAI
from dotenv import load_dotenv
import models, schemas
from database import engine, get_db
from cache import get_cached, set_cached, delete_cached
from plaid_service import (
    create_link_token,
    create_sandbox_public_token,
    exchange_public_token,
    sync_transactions,
)
import os
from sqlalchemy import func
from auth import hash_password, verify_password, create_access_token, decode_token
from fastapi.security import OAuth2PasswordRequestForm


load_dotenv()

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def categorize_transaction(description: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": f"Categorize this transaction into exactly one word from this list (food/transport/shopping/utilities/entertainment/health/other): {description}"
        }]
    )
    return response.choices[0].message.content.strip().lower()


def get_current_user(current_user: str = Depends(decode_token), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == current_user).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _plaid_category(txn: dict) -> str:
    pfc = txn.get("personal_finance_category") or {}
    return (pfc.get("primary") or "uncategorized").lower()


def _save_plaid_transactions(db: Session, added: list, username: str) -> int:
    count = 0
    for txn in added:
        plaid_id = txn["transaction_id"]
        if db.query(models.Transaction).filter(
            models.Transaction.plaid_transaction_id == plaid_id
        ).first():
            continue

        description = txn.get("merchant_name") or txn.get("name") or "Plaid transaction"
        category = _plaid_category(txn)
        if category == "uncategorized":
            category = categorize_transaction(description)

        db.add(models.Transaction(
            description=description,
            amount=float(txn["amount"]),
            category=category,
            plaid_transaction_id=plaid_id,
        ))
        count += 1

    if count:
        db.commit()
        delete_cached(f"summary:{username}")
    return count


def _sync_user_transactions(user: models.User, db: Session) -> dict:
    if not user.plaid_access_token:
        raise HTTPException(status_code=400, detail="Link a Plaid account first")

    imported = 0
    cursor = user.plaid_sync_cursor
    has_more = True

    while has_more:
        result = sync_transactions(user.plaid_access_token, cursor)
        imported += _save_plaid_transactions(db, result["added"], user.username)
        cursor = result["next_cursor"]
        has_more = result["has_more"]

    user.plaid_sync_cursor = cursor
    db.commit()
    return {"imported": imported, "cursor": cursor}

@app.get("/")
def root():
    return {"message": "Finance API is running"}

@app.get("/transactions", response_model=list[schemas.TransactionResponse])
def get_transactions(current_user: str = Depends(decode_token), db: Session = Depends(get_db)):
    return db.query(models.Transaction).all()

@app.get("/transactions/{transaction_id}", response_model=schemas.TransactionResponse)
def get_transaction(transaction_id: int, current_user: str = Depends(decode_token), db: Session = Depends(get_db)):
    transaction = db.query(models.Transaction).filter(
        models.Transaction.id == transaction_id
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction

def _compute_summary(db: Session) -> dict:
    total = db.query(func.sum(models.Transaction.amount)).scalar() or 0
    count = db.query(func.count(models.Transaction.id)).scalar() or 0
    top_category = db.query(
        models.Transaction.category,
        func.sum(models.Transaction.amount).label("total")
    ).group_by(models.Transaction.category)\
     .order_by(func.sum(models.Transaction.amount).desc())\
     .first()

    return {
        "total_spent": round(total, 2),
        "transaction_count": count,
        "top_spending_category": top_category.category if top_category else None
    }


@app.post("/transactions", response_model=schemas.TransactionResponse)
def create_transaction(transaction: schemas.TransactionCreate, current_user: str = Depends(decode_token),  db: Session = Depends(get_db)):
    if transaction.category == "uncategorized":
        transaction.category = categorize_transaction(transaction.description)
    db_transaction = models.Transaction(**transaction.model_dump())
    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)
    delete_cached(f"summary:{current_user}")
    return db_transaction

@app.get("/budget")
def get_budget(current_user: str = Depends(decode_token), db: Session = Depends(get_db)):
    results = db.query(
        models.Transaction.category,
        func.sum(models.Transaction.amount).label("total"),
        func.count(models.Transaction.id).label("count")
    ).group_by(models.Transaction.category).all()
    return [
        {"category": r.category, "total": round(r.total, 2), "count": r.count}
        for r in results
    ]

@app.get("/summary")
def get_summary(current_user: str = Depends(decode_token), db: Session = Depends(get_db)):
    cache_key = f"summary:{current_user}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    result = _compute_summary(db)
    set_cached(cache_key, result)
    return result

@app.post("/register", response_model=dict)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(
        models.User.username == user.username
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    db_user = models.User(
        username=user.username,
        hashed_password=hash_password(user.password)
    )
    db.add(db_user)
    db.commit()
    return {"message": f"User {user.username} created successfully"}

@app.post("/token", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(
        models.User.username == form_data.username
    ).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = create_access_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer"}


@app.post("/plaid/link-token", response_model=schemas.PlaidLinkTokenResponse)
def plaid_link_token(user: models.User = Depends(get_current_user)):
    try:
        link_token = create_link_token(user.username)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"link_token": link_token}


@app.post("/plaid/exchange-token")
def plaid_exchange_token(
    body: schemas.PlaidPublicToken,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        access_token, item_id = exchange_public_token(body.public_token)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Plaid exchange failed: {exc}") from exc

    user.plaid_access_token = access_token
    user.plaid_item_id = item_id
    user.plaid_sync_cursor = None
    db.commit()
    return {"message": "Plaid account linked", "item_id": item_id}


@app.post("/plaid/sandbox/setup")
def plaid_sandbox_setup(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sandbox only — links a test bank without Plaid Link UI."""
    try:
        public_token = create_sandbox_public_token()
        access_token, item_id = exchange_public_token(public_token)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Plaid sandbox setup failed: {exc}") from exc

    user.plaid_access_token = access_token
    user.plaid_item_id = item_id
    user.plaid_sync_cursor = None
    db.commit()
    return {"message": "Sandbox bank linked", "item_id": item_id}


@app.post("/plaid/sync")
def plaid_sync(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return _sync_user_transactions(user, db)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Plaid sync failed: {exc}") from exc


@app.get("/report")
def get_report(current_user: str = Depends(decode_token), db: Session = Depends(get_db)):
    transactions = db.query(models.Transaction).all()
    if not transactions:
        return {"message": "No transactions found", "monthly_breakdown": [], "top_categories": []}

    df = pd.DataFrame([{
        "description": t.description,
        "amount": t.amount,
        "category": t.category,
        "date": t.created_at
    } for t in transactions])

    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M").astype(str)

    monthly = df.groupby(["month", "category"])["amount"].sum().reset_index()
    monthly["amount"] = monthly["amount"].round(2)
    monthly_breakdown = monthly.sort_values(["month", "amount"], ascending=[True, False])

    top_categories = (
        df.groupby("category")["amount"]
        .sum()
        .round(2)
        .sort_values(ascending=False)
        .reset_index()
    )

    return {
        "total_transactions": len(df),
        "total_spent": round(df["amount"].sum(), 2),
        "monthly_breakdown": monthly_breakdown.to_dict(orient="records"),
        "top_categories": top_categories.rename(columns={"amount": "total"}).to_dict(orient="records")
    }


@app.post("/plaid/webhook")
async def plaid_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    webhook_type = payload.get("webhook_type")
    webhook_code = payload.get("webhook_code")
    item_id = payload.get("item_id")

    if webhook_type != "TRANSACTIONS":
        return {"status": "ignored"}

    if webhook_code not in {"SYNC_UPDATES_AVAILABLE", "DEFAULT_UPDATE", "INITIAL_UPDATE"}:
        return {"status": "ignored"}

    user = db.query(models.User).filter(models.User.plaid_item_id == item_id).first()
    if not user:
        return {"status": "user_not_found"}

    result = _sync_user_transactions(user, db)
    return {"status": "synced", **result}
