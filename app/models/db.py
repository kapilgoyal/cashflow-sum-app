"""DATABASE_URL engine factory — sqlite by default, Postgres/Neon when URL is postgres."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.repositories.connect import (
    dialect_name,
    is_postgres_url,
    path_to_sqlite_url,
    provider_hint,
    resolve_database_url,
    sqlite_path_from_url,
)

DATABASE_URL_ENV = "DATABASE_URL"
NEON_DATABASE_URL_ENV = "NEON_DATABASE_URL"


@lru_cache(maxsize=1)
def get_engine(url: str | None = None) -> Engine | None:
    """Return a SQLAlchemy Engine when a URL is configured; else None (stub)."""
    resolved = url or resolve_database_url()
    if not resolved:
        return None
    connect_args: dict = {}
    sa_url = resolved
    if is_postgres_url(resolved):
        if "sslmode=" not in resolved:
            connect_args["sslmode"] = "require"
    else:
        path = sqlite_path_from_url(resolved)
        path.parent.mkdir(parents=True, exist_ok=True)
        sa_url = path_to_sqlite_url(path)
        connect_args["check_same_thread"] = False
    return create_engine(sa_url, pool_pre_ping=True, connect_args=connect_args)


def get_session_factory(url: str | None = None) -> sessionmaker[Session] | None:
    engine = get_engine(url)
    if engine is None:
        return None
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def session_status() -> dict:
    """Health/diagnostics helper — does not open a connection unless URL set."""
    url = resolve_database_url()
    hint = provider_hint(url)
    out = {
        "configured": True,
        "dialect": dialect_name(url),
        "provider_hint": hint,
        "note": (
            "postgres/Neon via DATABASE_URL"
            if is_postgres_url(url)
            else "prototype sqlite file (set DATABASE_URL=postgres://… for Neon)"
        ),
    }
    if not is_postgres_url(url):
        out["sqlite_path"] = str(sqlite_path_from_url(url))
        out["sqlite_url_examples"] = [
            "sqlite:////data/cashflow.db",
            "sqlite:///./data/cashflow.db",
        ]
    return out
