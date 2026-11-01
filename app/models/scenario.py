from __future__ import annotations

from pydantic import BaseModel, Field


class Scenario(BaseModel):
    """One cell of the cohort × PSA × SDA securitization grid.

    TODO (not implemented): state-varying foreclosure / REO lag and recovery
    timing. recovery_period_months / recovery_lag_months are pool-level
    constants until state logic exists.
    """

    scenario_id: str
    cohort: str
    psa_multiple: int = Field(description="PSA speed multiple, e.g. 50/100/200")
    sda_multiple: int = Field(description="SDA speed multiple, e.g. 50/100/200")
    recovery_period_months: int = 6
    recovery_lag_months: int = 0
    recovery_rate: float = Field(
        default=0.60,
        description="Fraction of defaulted principal recovered (static)",
    )
    note: str = ""
    state_varying_recovery_todo: bool = True
