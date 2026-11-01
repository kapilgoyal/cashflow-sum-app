"""DATABASE_URL / Neon engine factory (stub — no eager connect)."""

from __future__ import annotations

import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

# Neon / Postgres; leave unset for offline scaffold work.
DATABASE_URL_ENV = "DATABASE_URL"
NEON_DATABASE_URL_ENV = "NEON_DATABASE_URL"


def resolve_database_url() -> str | None:
    return os.environ.get(DATABASE_URL_ENV) or os.environ.get(NEON_DATABASE_URL_ENV)


@lru_cache(maxsize=1)
def get_engine(url: str | None = None) -> Engine | None:
    """Return a SQLAlchemy Engine when a URL is configured; else None (stub)."""
    resolved = url or resolve_database_url()
    if not resolved:
        return None
    # Neon-friendly: require SSL when using postgres schemes without query params.
    connect_args: dict = {}
    if resolved.startswith("postgres") and "sslmode=" not in resolved:
        connect_args["sslmode"] = "require"
    return create_engine(resolved, pool_pre_ping=True, connect_args=connect_args)


def get_session_factory(url: str | None = None) -> sessionmaker[Session] | None:
    engine = get_engine(url)
    if engine is None:
        return None
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def session_status() -> dict:
    """Health/diagnostics helper — does not open a connection unless URL set."""
    url = resolve_database_url()
    return {
        "configured": bool(url),
        "dialect": "postgresql" if url else None,
        "provider_hint": "neon" if url and "neon.tech" in url else ("postgres" if url else None),
        "note": "stub: call repositories only when DATABASE_URL is set",
    }
