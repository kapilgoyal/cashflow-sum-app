"""Tranche repository stub (Neon / Postgres via DATABASE_URL)."""

from __future__ import annotations

from typing import Any

from app.models.tranche import Tranche
from app.repositories.db import db


class TrancheRepository:
    """No tranche waterfall yet — returns empty / not-found stubs."""

    def list(self) -> list[Tranche]:
        if db.url_configured():
            _ = db.status()  # reserved for future SELECT
        return []

    def get(self, tranche_id: str) -> Tranche | None:
        _ = tranche_id
        return None

    def neon_stub_status(self) -> dict[str, Any]:
        return {
            **db.status(),
            "table": "tranches",
            "impl": "stub — no waterfall engine",
        }
