import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

_url = os.environ["DATABASE_URL"]

# Supabase gives "postgresql://"; SQLAlchemy needs the driver named
# explicitly to use psycopg (v3) instead of the default psycopg2.
if _url.startswith("postgres://"):
    _url = _url.replace("postgres://", "postgresql+psycopg://", 1)
elif _url.startswith("postgresql://"):
    _url = _url.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(
    _url,
    pool_pre_ping=True,
    pool_size=1,          # serverless: keep pools tiny
    max_overflow=0,
    connect_args={"connect_timeout": 10},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()