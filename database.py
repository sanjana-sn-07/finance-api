from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv(override=False)

DATABASE_URL = (
    os.getenv("DATABASE_URL") or
    os.getenv("DATABASE_PUBLIC_URL") or
    os.getenv("POSTGRES_URL") or
    os.getenv("POSTGRESQL_URL")
)

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if not DATABASE_URL:
    raise RuntimeError(
        f"DATABASE_URL not set. Available env vars: {[k for k in os.environ.keys() if 'DATA' in k.upper() or 'PG' in k.upper() or 'POST' in k.upper()]}"
    )

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
