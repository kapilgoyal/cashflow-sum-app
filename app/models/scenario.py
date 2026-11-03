"""Scenario Pydantic schema + SQLAlchemy ORM stub."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Scenario(BaseModel):
    """One cell of the cohort × PSA × SDA securitization grid.

    recovery_rate / recovery_period_months are cohort constants (60%/12,
    55%/15, 75%/9). recovery_lag_months on the scenario is a fallback only;
    the engine applies Fannie Mae state foreclosure lag from loan.state.
    """

    scenario_id: str
    cohort: str
    psa_multiple: int = Field(description="PSA speed multiple, e.g. 75/100/125")
    sda_multiple: int = Field(description="SDA speed multiple, e.g. 50/100/200")
    recovery_period_months: int = 6
    recovery_lag_months: int = 6
    recovery_rate: float = Field(
        default=0.60,
        description="Cohort fraction of defaulted principal recovered (not one pool rate)",
    )
    note: str = ""
    state_varying_recovery_todo: bool = False


class ScenarioORM(Base):
    __tablename__ = "securitization_scenarios"

    scenario_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    cohort: Mapped[str] = mapped_column(String(128), nullable=False)
    psa_multiple: Mapped[int] = mapped_column(Integer, nullable=False)
    sda_multiple: Mapped[int] = mapped_column(Integer, nullable=False)
    recovery_period_months: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    recovery_lag_months: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    recovery_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.60)
    state_varying_recovery_todo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
