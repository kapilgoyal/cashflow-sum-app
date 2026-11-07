"""POST /api/run-loan — project one tape loan × one scenario cell."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.cash_flow import RunLoanRequest, RunLoanResponse
from app.models.loan import Loan
from app.models.scenario import Scenario
from app.repositories.tape_repository import TapeRepository
from app.services.cashflow_engine import project_loan_cashflows
from app.services.recovery import FANNIE_TIMEFRAMES_SOURCE_URL
from app.services.scenario_grid import (
    BASE_PSA,
    BASE_SDA,
    build_scenario_grid,
)

router = APIRouter(prefix="/api", tags=["cashflows"])

_RUN_LOAN_DESCRIPTION = (
    "Load a tape loan and a 27-cell scenario, then project monthly cash flows "
    "with the existing engine (PSA/SDA seasoning, Urban/Freddie recovery when "
    "has_mi, Fannie Mae state lag). Returns ``CashFlowRow`` fields only.\n\n"
    "Select the cell with ``scenario_id`` (e.g. S05), or omit it and use the "
    "loan's cohort at ``psa_multiple``/``sda_multiple`` (default 100/100).\n\n"
    f"FNMA time frames: {FANNIE_TIMEFRAMES_SOURCE_URL}"
)


def _resolve_scenario(body: RunLoanRequest, loan: Loan) -> Scenario:
    grid = build_scenario_grid()
    if body.scenario_id:
        sid = body.scenario_id.strip()
        for scenario in grid:
            if scenario.scenario_id == sid:
                return scenario
        raise HTTPException(status_code=404, detail=f"scenario_id not found: {sid}")

    psa = int(body.psa_multiple) if body.psa_multiple is not None else BASE_PSA
    sda = int(body.sda_multiple) if body.sda_multiple is not None else BASE_SDA
    cohort = loan.cohort
    if not cohort:
        raise HTTPException(
            status_code=400,
            detail="loan has no cohort; pass scenario_id",
        )
    for scenario in grid:
        if (
            scenario.cohort == cohort
            and scenario.psa_multiple == psa
            and scenario.sda_multiple == sda
        ):
            return scenario
    raise HTTPException(
        status_code=404,
        detail=f"no scenario for cohort={cohort!r} PSA={psa} SDA={sda}",
    )


@router.post(
    "/run-loan",
    response_model=RunLoanResponse,
    summary="Run one-loan cash flows",
    description=_RUN_LOAN_DESCRIPTION,
)
@router.post(
    "/cashflows/run-loan",
    response_model=RunLoanResponse,
    summary="Run one-loan cash flows",
    description=_RUN_LOAN_DESCRIPTION,
)
def run_loan(body: RunLoanRequest) -> RunLoanResponse:
    try:
        loan = TapeRepository().get_loan(body.loan_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    scenario = _resolve_scenario(body, loan)
    rows = project_loan_cashflows(loan, scenario, months=body.months)
    if not rows:
        raise HTTPException(status_code=500, detail="engine returned no cash_flows")

    return RunLoanResponse(
        loan_id=loan.loan_id,
        scenario_id=scenario.scenario_id,
        months=len(rows),
        status="ok",
        message="",
        cash_flows=rows,
    )
