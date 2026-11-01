"""Month-1 parallel CF run + cohort aggregate read surface."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.repositories.cashflow_repository import CashflowRepository
from app.repositories.scenario_repository import ScenarioRepository
from app.repositories.tape_repository import TapeRepository
from app.services.month1_parallel import run_month1_parallel
from app.services.scenario_grid import build_scenario_grid

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA = REPO_ROOT / "data"
STORE_TAPE = Path(
    r"C:\Users\kgoya\AppData\Local\Cursor\AgentStores\cursor_agent_stores"
    r"\bc-b8a045d3-83c0-4a57-9767-2701e9c67b11\files\docs\data\Minimum_Case.xlsx"
)

router = APIRouter(prefix="/api", tags=["cashflows-month1"])


def _tape_path() -> Path:
    local = DATA / "Minimum_Case.xlsx"
    docs = REPO_ROOT / "docs" / "data" / "Minimum_Case.xlsx"
    for p in (STORE_TAPE, local, docs):
        if p.exists():
            return p
    return STORE_TAPE


@router.get("/scenarios/grid")
def scenario_grid() -> dict:
    scenarios = [s.model_dump() for s in build_scenario_grid()]
    return {"n": len(scenarios), "scenarios": scenarios}


@router.get("/cashflows/month1")
def get_month1_aggregates() -> dict:
    repo = CashflowRepository(DATA)
    payload = repo.load_aggregates()
    if not payload:
        raise HTTPException(
            status_code=404,
            detail="No month-1 cohort aggregates yet — POST /api/cashflows/run-month1",
        )
    return payload


@router.post("/cashflows/run-month1")
def run_month1() -> dict:
    """Run all 27 scenario cells (ProcessPoolExecutor, 27 workers), month 1 only."""
    tape = TapeRepository(_tape_path())
    try:
        loans = tape.load_all_loans()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not loans:
        raise HTTPException(status_code=400, detail="no loans loaded from tape")

    scenarios = build_scenario_grid()
    ScenarioRepository(DATA / "securitization_scenarios.csv").save_csv(scenarios)

    result = run_month1_parallel(loans, scenarios, max_workers=27)
    cf_repo = CashflowRepository(DATA)
    storage = cf_repo.save(
        loan_rows=result["loan_rows"],
        aggregates=result["aggregates"],
        meta={
            "parallelism": result["parallelism"],
            "assumptions": result["assumptions"],
            "ran_scenario_ids": result["ran_scenario_ids"],
        },
    )

    # Drop bulky loan_rows from HTTP response; they live in storage.
    return {
        "parallelism": result["parallelism"],
        "assumptions": result["assumptions"],
        "ran_scenario_ids": result["ran_scenario_ids"],
        "aggregates": result["aggregates"],
        "storage": storage,
        "neon_missing": not storage.get("database_url_set"),
    }


@router.get("/loans/summary")
def loans_summary() -> dict:
    tape = TapeRepository(_tape_path())
    try:
        loans = tape.load_all_loans()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    by_cohort: dict[str, int] = {}
    for ln in loans:
        by_cohort[ln.cohort or ""] = by_cohort.get(ln.cohort or "", 0) + 1
    return {
        "n_loans": len(loans),
        "by_cohort": by_cohort,
        "loans": [
            {
                "loan_id": ln.loan_id,
                "cohort": ln.cohort,
                "current_balance": ln.current_balance,
                "annual_rate": ln.annual_rate,
                "remaining_term_months": ln.remaining_term_months,
                "loan_age_months": ln.loan_age_months,
                "state": ln.state,
            }
            for ln in loans
        ],
    }
