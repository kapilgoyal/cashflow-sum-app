"""Monthly cash-flow row covering the three CF panels + run-loan schema.

Panel 1 (performing UPB): Mo, Beg UPB, Interest, Sched Prin, CPR, CDR,
Prepay, New Default, End UPB.

Panel 2 (default roll / lag liquidation): Mo, Beg Default Bal, New Default,
Liquidated Default, Recovery, Realized Loss, End Default Bal.

Panel 3 (actual cash): Mo, Interest, Sched Prin, Prepay, Recovery, Total Cash.
Defaults themselves are not cash.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class CashFlowRow(BaseModel):
    """One projected month — performing UPB + default inventory + cash."""

    month: int = Field(ge=1, le=480)

    # Panel 1 — performing UPB
    beginning_balance: float = 0.0  # Beg UPB
    interest: float = 0.0
    scheduled_principal: float = 0.0
    cpr: float = 0.0
    cdr: float = 0.0
    prepay: float = 0.0
    new_default: float = Field(
        default=0.0,
        description="New default principal this month",
    )
    # Back-compat alias persisted as Neon default_amt / older CSV "default"
    default: float = Field(
        default=0.0,
        description="Alias of new_default for legacy writers",
    )
    ending_balance: float = 0.0  # End UPB

    # Panel 2 — default balance roll (lag liquidation)
    beginning_default_balance: float = 0.0
    liquidated_default: float = 0.0
    recovery: float = 0.0
    realized_loss: float = 0.0
    ending_default_balance: float = 0.0

    # Panel 3 — actual cash (defaults excluded)
    total_cash: float = Field(
        default=0.0,
        description="interest + scheduled_principal + prepay + recovery",
    )

    # Curve / lag metadata
    loan_age: int = 0
    smm: float = 0.0
    mdr: float = 0.0
    used_recovery_lag_months: int | None = Field(
        default=None,
        description=(
            "Lag months before liquidation/recovery (Fannie Mae state "
            "foreclosure time frame when loan.state is known)"
        ),
    )
    recovery_rate: float | None = Field(
        default=None,
        description=(
            "Recovery rate on liquidated default: Urban/Freddie "
            "1−severity when has_mi, else cohort rate"
        ),
    )

    @model_validator(mode="after")
    def _sync_default_alias(self) -> CashFlowRow:
        # Prefer new_default when set; keep default in sync for Neon/CSV.
        if self.new_default and not self.default:
            self.default = self.new_default
        elif self.default and not self.new_default:
            self.new_default = self.default
        else:
            # Both set — force equality on new_default as source of truth
            self.default = self.new_default
        return self


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
    """Documented CF response. Scaffold returns empty cash_flows."""

    loan_id: str
    scenario_id: str | None = None
    months: int = 360
    status: str = Field(default="stub", description="'stub' until engine is wired")
    message: str = "placeholder — cash-flow engine not invoked"
    cash_flows: list[CashFlowRow] = Field(
        default_factory=list,
        description="Empty in scaffold; length==months when engine runs",
    )
