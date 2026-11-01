"""Month-1 parallel CF run + cohort aggregate read surface."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.repositories.cashflow_repository import CashflowRepository
from app.repositories.env_load import load_dotenv, resolve_pg_url
from app.repositories.scenario_repository import ScenarioRepository
from app.repositories.tape_repository import TapeRepository
from app.services.month1_parallel import run_month1_parallel
from app.services.scenario_grid import build_scenario_grid

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA = REPO_ROOT / "data"
PUBLIC = REPO_ROOT / "public"
STORE_TAPE = Path(
    r"C:\Users\kgoya\AppData\Local\Cursor\AgentStores\cursor_agent_stores"
    r"\bc-b8a045d3-83c0-4a57-9767-2701e9c67b11\files\docs\data\Minimum_Case.xlsx"
)

router = APIRouter(prefix="/api", tags=["cashflows-month1"])


def _tape_path() -> Path:
    local = DATA / "Minimum_Case.xlsx"
    docs = REPO_ROOT / "docs" / "data" / "Minimum_Case.xlsx"
    for p in (docs, local, STORE_TAPE):
        if p.exists():
            return p
    return docs if docs.exists() else STORE_TAPE


def _load_cached_aggregates() -> dict | None:
    """Prefer data/ then public/ cohort-month1 JSON (committed for Vercel)."""
    cf_repo = CashflowRepository(DATA)
    payload = cf_repo.load_aggregates()
    if payload:
        return payload
    public_path = PUBLIC / "cohort-month1.json"
    if public_path.exists():
        return json.loads(public_path.read_text(encoding="utf-8"))
    return None


def _neon_month1_summary() -> dict | None:
    load_dotenv()
    url = resolve_pg_url()
    if not url:
        return None
    try:
        import psycopg

        with psycopg.connect(url, connect_timeout=30) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT scenario_id, COUNT(*)::int AS n_loans,
                           COALESCE(SUM(beginning_balance),0)::float AS beginning_balance,
                           COALESCE(SUM(interest),0)::float AS interest,
                           COALESCE(SUM(scheduled_principal),0)::float AS scheduled_principal,
                           COALESCE(SUM(default_amt),0)::float AS default_amt,
                           COALESCE(SUM(prepay),0)::float AS prepay,
                           COALESCE(SUM(recovery),0)::float AS recovery,
                           COALESCE(SUM(ending_balance),0)::float AS ending_balance
                    FROM public.loan_cashflows_month1_enriched
                    GROUP BY scenario_id
                    ORDER BY scenario_id
                    """
                )
                cols = [d.name for d in cur.description]
                rows = [dict(zip(cols, tup)) for tup in cur.fetchall()]
                cur.execute(
                    "SELECT DISTINCT scenario_id FROM public.loan_cashflows_month1 "
                    "ORDER BY 1"
                )
                ids = [r[0] for r in cur.fetchall()]
        if not rows:
            return None
        return {
            "aggregates": rows,
            "ran_scenario_ids": ids,
            "source": "neon.loan_cashflows_month1_enriched",
        }
    except Exception:  # noqa: BLE001
        return None


@router.get("/scenarios/grid")
def scenario_grid() -> dict:
    scenarios = [s.model_dump() for s in build_scenario_grid()]
    return {"n": len(scenarios), "scenarios": scenarios}


@router.get("/cashflows/month1")
def get_month1_aggregates() -> dict:
    neon = _neon_month1_summary()
    if neon:
        return neon
    payload = _load_cached_aggregates()
    if not payload:
        raise HTTPException(
            status_code=404,
            detail="No month-1 cohort aggregates yet — POST /api/cashflows/run-month1",
        )
    return payload


@router.post("/cashflows/run-month1")
def run_month1(
    force: bool = Query(
        default=False,
        description="Recompute even when Neon/cached aggregates exist",
    ),
) -> dict:
    """Run all 27 scenario cells for every loan in each cohort (month 1).

    On Vercel, prefer Neon / committed cohort JSON unless ``force=true`` — ProcessPool
    is unavailable in the serverless runtime. Local/dev still runs the full engine
    and persists loan-level rows to Neon when DATABASE_URL is set.
    """
    load_dotenv()
    on_vercel = bool(os.environ.get("VERCEL"))

    if not force:
        neon = _neon_month1_summary()
        if neon:
            return {
                "parallelism": {
                    "executor": "neon-cache",
                    "max_workers": 0,
                    "n_tasks": len(neon.get("ran_scenario_ids") or []),
                    "wall_ms": 0,
                    "ok": len(neon.get("ran_scenario_ids") or []),
                    "error": 0,
                    "n_loan_rows": None,
                },
                "assumptions": {"horizon_months": 1, "source": neon["source"]},
                "ran_scenario_ids": neon["ran_scenario_ids"],
                "aggregates": neon["aggregates"],
                "storage": {"neon": neon["source"]},
                "neon_missing": False,
                "cached": True,
            }
        if on_vercel:
            cached = _load_cached_aggregates()
            if cached:
                meta = cached.get("meta") or {}
                return {
                    "parallelism": meta.get("parallelism")
                    or {"executor": "static-cache", "n_tasks": 27},
                    "assumptions": meta.get("assumptions") or {"horizon_months": 1},
                    "ran_scenario_ids": meta.get("ran_scenario_ids")
                    or [
                        a.get("scenario_id")
                        for a in (cached.get("aggregates") or [])
                        if a.get("scenario_id")
                    ],
                    "aggregates": cached.get("aggregates") or [],
                    "storage": {"json": "public/cohort-month1.json"},
                    "neon_missing": not bool(resolve_pg_url()),
                    "cached": True,
                }

    tape = TapeRepository(_tape_path())
    try:
        loans = tape.load_all_loans()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not loans:
        raise HTTPException(status_code=400, detail="no loans loaded from tape")

    scenarios = build_scenario_grid()
    ScenarioRepository(DATA / "securitization_scenarios.csv").save_csv(scenarios)

    # Serverless: avoid ProcessPool; use fewer workers. Local keeps 27.
    max_workers = 2 if on_vercel else 27
    result = run_month1_parallel(loans, scenarios, max_workers=max_workers)
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

    # Mirror aggregates into public/ for static Vercel fallbacks.
    try:
        PUBLIC.mkdir(parents=True, exist_ok=True)
        public_payload = {
            "meta": {
                "parallelism": result["parallelism"],
                "assumptions": result["assumptions"],
                "ran_scenario_ids": result["ran_scenario_ids"],
            },
            "aggregates": result["aggregates"],
        }
        (PUBLIC / "cohort-month1.json").write_text(
            json.dumps(public_payload, indent=2), encoding="utf-8"
        )
        storage["public_json"] = "public/cohort-month1.json"
    except OSError:
        pass

    return {
        "parallelism": result["parallelism"],
        "assumptions": result["assumptions"],
        "ran_scenario_ids": result["ran_scenario_ids"],
        "aggregates": result["aggregates"],
        "storage": storage,
        "neon_missing": not storage.get("database_url_set"),
        "cached": False,
        "n_loan_rows": len(result["loan_rows"]),
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
