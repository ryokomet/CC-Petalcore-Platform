import os

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, declarative_base

_url = os.environ["DATABASE_URL"]

# Supabase gives "postgresql://"; SQLAlchemy needs the driver named
# explicitly to use psycopg (v3) instead of the default psycopg2.
if _url.startswith("postgres://"):
    _url = _url.replace("postgres://", "postgresql+psycopg://", 1)
elif _url.startswith("postgresql://"):
    _url = _url.replace("postgresql://", "postgresql+psycopg://", 1)

_parsed_url = make_url(_url)
_local_hosts = {"localhost", "127.0.0.1", "::1", "[::1]"}
if (
    _parsed_url.host
    and _parsed_url.host.lower() not in _local_hosts
    and _parsed_url.query.get("sslmode") not in {"require", "verify-ca", "verify-full"}
):
    # Managed PostgreSQL providers should use TLS; preserve an explicit mode
    # only when it validates or requires an encrypted connection.
    _parsed_url = _parsed_url.update_query_dict({"sslmode": "require"})

engine = create_engine(
    _parsed_url,
    pool_pre_ping=True,
    pool_size=1,          # serverless: keep pools tiny
    max_overflow=0,
    connect_args={"connect_timeout": 10},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()
