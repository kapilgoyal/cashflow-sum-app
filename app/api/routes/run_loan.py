"""Run-loan endpoint: documents 360-mo CF schema; returns empty placeholder.

Does NOT invoke the cash-flow engine.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.models.cash_flow import RunLoanRequest, RunLoanResponse
from app.services.recovery import FANNIE_TIMEFRAMES_SOURCE_URL

router = APIRouter(prefix="/api", tags=["cashflows"])


@router.post(
    "/run-loan",
    response_model=RunLoanResponse,
    summary="Run one-loan cash flows (stub)",
    description=(
        "Accepts ``loan_id`` + scenario selectors and returns the documented "
        "360-month cash-flow response schema. Scaffold returns an empty "
        "``cash_flows`` list — the projection engine is not called.\n\n"
        "When wired: cohort recovery_rate (60/55/75); recovery lag from "
        f"loan.state via Fannie Mae time frames ({FANNIE_TIMEFRAMES_SOURCE_URL})."
    ),
)
def run_loan(body: RunLoanRequest) -> RunLoanResponse:
    # Intentionally no engine call / no tape I/O / no CSV writes.
    return RunLoanResponse(
        loan_id=body.loan_id,
        scenario_id=body.scenario_id,
        months=body.months,
        status="stub",
        message=(
            "placeholder — cash-flow engine not invoked; "
            "response schema documents 360-mo CF rows"
        ),
        cash_flows=[],
    )
