from __future__ import annotations

from pydantic import BaseModel, Field


class Loan(BaseModel):
    """Minimal fields for a deterministic one-loan cash-flow run."""

    loan_id: str
    current_balance: float = Field(gt=0)
    annual_rate: float = Field(ge=0, description="Decimal, e.g. 0.08781")
    remaining_term_months: int = Field(gt=0)
    loan_age_months: int = Field(ge=0, default=0)
    monthly_payment: float | None = Field(
        default=None,
        description="If None, level payment is computed from balance/rate/term",
    )
    remaining_io_months: int = Field(ge=0, default=0)
    state: str | None = None
    cohort: str | None = None
