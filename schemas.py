from pydantic import BaseModel
from datetime import datetime

class TransactionCreate(BaseModel):
    description: str
    amount: float
    category: str = "uncategorized"

class TransactionResponse(TransactionCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
