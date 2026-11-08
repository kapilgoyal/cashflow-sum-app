"""Loan Pydantic schema + SQLAlchemy ORM stub."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Loan(BaseModel):
    """Minimal fields for a deterministic one-loan cash-flow run."""

    loan_id: str
    current_balance: float = Field(gt=0)
    annual_rate: float = Field(ge=0, description="Decimal, e.g. 0.08781")
    remaining_term_months: int = Field(gt=0)
    loan_age_months: int = Field(
        ge=0,
        default=0,
        description="Seasoning at cutoff (scheduled payments before cutoff)",
    )
    monthly_payment: float | None = Field(
        default=None,
        description="If None, level payment is computed from balance/rate/term",
    )
    remaining_io_months: int = Field(ge=0, default=0)
    state: str | None = None
    cohort: str | None = None
    origination_date: date | None = Field(
        default=None,
        description="Optional; used to derive seasoning when age is unavailable",
    )
    cutoff_date: date | None = Field(
        default=None,
        description="Optional tape cutoff; pairs with origination_date",
    )
    original_fico: int | None = None
    original_ltv: float | None = Field(
        default=None,
        description="Origination LTV as fraction (0–1) or percent; severity lookup normalizes",
    )
    has_mi: bool | None = Field(
        default=None,
        description="Mortgage insurance flag; None → assumptions.csv has_mi_all (True)",
    )
    # ARM fields (tape). Engine is fixed-coupon; resets inside the horizon raise.
    arm_index: str | None = Field(
        default=None,
        description="ARM index name when present; None/blank = fixed-rate",
    )
    arm_initial_fixed_months: int | None = Field(
        default=None,
        ge=0,
        description="Months from origination until first ARM reset",
    )
    arm_reset_frequency_months: int | None = Field(
        default=None,
        ge=0,
        description="ARM reset frequency; >0 marks loan as ARM for validation",
    )


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
    cohort: Mapped[str | None] = mapped_column(String(128), nullable=True)
    original_fico: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_ltv: Mapped[float | None] = mapped_column(Float, nullable=True)
    has_mi: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
