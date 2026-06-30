from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from openai import OpenAI
from dotenv import load_dotenv
import models, schemas
from database import engine, get_db
from cache import get_cached, set_cached, delete_cached
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
