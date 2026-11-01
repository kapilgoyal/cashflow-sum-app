"""Loan lookup stubs: tape file today, Postgres/Neon when DATABASE_URL set."""

from __future__ import annotations

from typing import Any

from app.models.loan import Loan
from app.repositories.db import db
from app.repositories.tape_repository import TapeRepository


class LoanRepository:
    """Prefer Neon/Postgres when configured; fall back to Excel tape stub."""

    def __init__(self, tape: TapeRepository | None = None) -> None:
        self.tape = tape or TapeRepository()

    def get(self, loan_id: str) -> Loan:
        # TODO: SELECT from loans ORM when Neon is seeded.
        if db.url_configured():
            # Stub path — no engine run / no live query in scaffold.
            _ = db.status()
        return self.tape.get_loan(loan_id)

    def neon_stub_status(self) -> dict[str, Any]:
        return {
            **db.status(),
            "table": "loans",
            "impl": "stub — tape-backed until Neon seed",
        }
