"""SQLAlchemy declarative base for Neon / Postgres ORM stubs."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared ORM metadata. Tables are stubs until migrations land."""
