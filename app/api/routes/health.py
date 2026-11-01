"""Liveness / readiness stubs."""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.repositories.db import db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "database": db.status(),
    }
