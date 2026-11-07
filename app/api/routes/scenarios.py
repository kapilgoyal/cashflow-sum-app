"""Scenario-grid read surface (preserved for parallel CF-41 work).

Sample CF projection endpoint retained for offline scripts; the public
run-loan stub under ``/api/run-loan`` does not call the engine.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.repositories.tape_repository import TapeRepository
from app.services.cashflow_engine import project_loan_cashflows
from app.services.cohort_labels import relabel_payload
from app.services.scenario_grid import base_case_scenario, build_scenario_grid

router = APIRouter(tags=["scenarios"])


@router.get("/scenarios")
def scenarios() -> list[dict]:
    return relabel_payload([s.model_dump() for s in build_scenario_grid()])


@router.get("/cashflows/sample")
def sample_cashflow(
    loan_id: str | None = Query(default=None),
    months: int = Query(default=360, ge=1, le=480),
) -> dict:
    """Optional offline sample; prefer POST /api/run-loan stub for API clients."""
    try:
        loan = TapeRepository().get_loan(loan_id)
    except (FileNotFoundError, KeyError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    scenario = base_case_scenario()
    rows = project_loan_cashflows(loan, scenario, months=months)
    return relabel_payload(
        {
            "loan": loan.model_dump(),
            "scenario": scenario.model_dump(),
            "rows": [r.model_dump() for r in rows],
        }
    )
