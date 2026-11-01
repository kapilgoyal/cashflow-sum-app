"""Monthly cash-flow row + documented 360-mo run-loan response schema."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CashFlowRow(BaseModel):
    """One projected month of loan cash flows (engine or placeholder)."""

    month: int = Field(ge=1, le=480)
    beginning_balance: float = 0.0
    interest: float = 0.0
    scheduled_principal: float = 0.0
    default: float = 0.0
    prepay: float = 0.0
    recovery: float = 0.0
    ending_balance: float = 0.0
    loan_age: int = 0
    cpr: float = 0.0
    smm: float = 0.0
    cdr: float = 0.0
    mdr: float = 0.0


# Alias kept for parallel scenario-grid imports.
CashflowRow = CashFlowRow


class RunLoanRequest(BaseModel):
    """POST /api/run-loan body: loan + scenario selectors."""

    loan_id: str
    scenario_id: str | None = Field(
        default=None,
        description="Grid cell id (e.g. S05); optional if scenario payload supplied",
    )
    psa_multiple: int | None = Field(default=None, description="Override PSA multiple")
    sda_multiple: int | None = Field(default=None, description="Override SDA multiple")
    months: int = Field(default=360, ge=1, le=480, description="Projection horizon")


class RunLoanResponse(BaseModel):
    """Documented 360-month CF response. Scaffold returns empty cash_flows.

    When the engine is wired, ``cash_flows`` will contain exactly ``months``
    rows (default 360) with balances, interest, scheduled principal, default,
    prepay, and recovery under PSA/SDA + constant recovery lag.
    """

    loan_id: str
    scenario_id: str | None = None
    months: int = 360
    status: str = Field(default="stub", description="'stub' until engine is wired")
    message: str = "placeholder — cash-flow engine not invoked"
    cash_flows: list[CashFlowRow] = Field(
        default_factory=list,
        description="Empty in scaffold; length==months when engine runs",
    )
