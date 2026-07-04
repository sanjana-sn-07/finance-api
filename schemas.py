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

class UserCreate(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class PlaidPublicToken(BaseModel):
    public_token: str

class PlaidLinkTokenResponse(BaseModel):
    link_token: str
