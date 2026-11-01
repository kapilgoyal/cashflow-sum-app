"""Loan Pydantic schema + SQLAlchemy ORM stub."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


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


class LoanORM(Base):
    __tablename__ = "loans"

    loan_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    current_balance: Mapped[float] = mapped_column(Float, nullable=False)
    annual_rate: Mapped[float] = mapped_column(Float, nullable=False)
    remaining_term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    loan_age_months: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    monthly_payment: Mapped[float | None] = mapped_column(Float, nullable=True)
    remaining_io_months: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str | None] = mapped_column(String(8), nullable=True)
    cohort: Mapped[str | None] = mapped_column(String(32), nullable=True)
