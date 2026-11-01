"""Postgres / Neon repository wiring stubs via DATABASE_URL."""

from __future__ import annotations

from typing import Any

from app.models.db import get_engine, get_session_factory, resolve_database_url, session_status


class DatabaseStub:
    """Thin facade: reports config; optional session when URL is present."""

    def status(self) -> dict[str, Any]:
        return session_status()

    def url_configured(self) -> bool:
        return bool(resolve_database_url())

    def session(self):
        factory = get_session_factory()
        if factory is None:
            raise RuntimeError(
                "DATABASE_URL / NEON_DATABASE_URL not set — Neon stub offline"
            )
        return factory()

    def engine(self):
        engine = get_engine()
        if engine is None:
            raise RuntimeError(
                "DATABASE_URL / NEON_DATABASE_URL not set — Neon stub offline"
            )
        return engine


db = DatabaseStub()
