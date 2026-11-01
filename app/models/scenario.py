"""Scenario Pydantic schema + SQLAlchemy ORM stub."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Scenario(BaseModel):
    """One cell of the cohort × PSA × SDA securitization grid.

    TODO (not implemented): state-varying foreclosure / REO lag and recovery
    timing. recovery_period_months / recovery_lag_months are pool-level
    constants until state logic exists.
    """

    scenario_id: str
    cohort: str
    psa_multiple: int = Field(description="PSA speed multiple, e.g. 75/100/125")
    sda_multiple: int = Field(description="SDA speed multiple, e.g. 50/100/200")
    recovery_period_months: int = 6
    recovery_lag_months: int = 0
    recovery_rate: float = Field(
        default=0.60,
        description="Fraction of defaulted principal recovered (static)",
    )
    note: str = ""
    state_varying_recovery_todo: bool = True


class ScenarioORM(Base):
    __tablename__ = "securitization_scenarios"

    scenario_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    cohort: Mapped[str] = mapped_column(String(32), nullable=False)
    psa_multiple: Mapped[int] = mapped_column(Integer, nullable=False)
    sda_multiple: Mapped[int] = mapped_column(Integer, nullable=False)
    recovery_period_months: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    recovery_lag_months: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recovery_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.60)
    state_varying_recovery_todo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
