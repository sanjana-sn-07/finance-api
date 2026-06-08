from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from openai import OpenAI
from dotenv import load_dotenv
import models, schemas
from database import engine, get_db
import os

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
def get_transactions(db: Session = Depends(get_db)):
    return db.query(models.Transaction).all()

@app.get("/transactions/{transaction_id}", response_model=schemas.TransactionResponse)
def get_transaction(transaction_id: int, db: Session = Depends(get_db)):
    transaction = db.query(models.Transaction).filter(
        models.Transaction.id == transaction_id
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction

@app.post("/transactions", response_model=schemas.TransactionResponse)
def create_transaction(transaction: schemas.TransactionCreate, db: Session = Depends(get_db)):
    if transaction.category == "uncategorized":
        transaction.category = categorize_transaction(transaction.description)
    db_transaction = models.Transaction(**transaction.model_dump())
    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)
    return db_transaction
