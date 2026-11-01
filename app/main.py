"""Minimal FastAPI surface for the securitization engine."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from app import __version__
from app.repositories.tape_repository import TapeRepository
from app.services.cashflow_engine import project_loan_cashflows
from app.services.scenario_grid import base_case_scenario, build_scenario_grid

app = FastAPI(title="CashFlow Securitization Engine", version=__version__)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/scenarios")
def scenarios() -> list[dict]:
    return [s.model_dump() for s in build_scenario_grid()]


@app.get("/cashflows/sample")
def sample_cashflow(
    loan_id: str | None = Query(default=None),
    months: int = Query(default=360, ge=1, le=480),
) -> dict:
    try:
        loan = TapeRepository().get_loan(loan_id)
    except (FileNotFoundError, KeyError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    scenario = base_case_scenario()
    rows = project_loan_cashflows(loan, scenario, months=months)
    return {
        "loan": loan.model_dump(),
        "scenario": scenario.model_dump(),
        "rows": [r.model_dump() for r in rows],
    }
