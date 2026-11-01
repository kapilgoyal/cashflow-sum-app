"""ABS tranche Pydantic + SQLAlchemy stubs."""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Tranche(BaseModel):
    """Securitization tranche waterfalls are out of scope; schema only."""

    tranche_id: str
    name: str
    seniority: int = Field(ge=1, description="1 = most senior")
    attachment_pct: float = Field(ge=0, le=1, default=0.0)
    detachment_pct: float = Field(ge=0, le=1, default=1.0)
    coupon: float | None = Field(default=None, description="Annual coupon decimal")
    balance: float | None = None
    note: str = ""


class TrancheORM(Base):
    __tablename__ = "tranches"

    tranche_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    seniority: Mapped[int] = mapped_column(Integer, nullable=False)
    attachment_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    detachment_pct: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    coupon: Mapped[float | None] = mapped_column(Float, nullable=True)
    balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
