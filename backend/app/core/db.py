# backend/app/core/db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, future=True)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)

Base = declarative_base()


def get_db():
    from sqlalchemy.orm import Session  # local import to avoid circulars

    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
