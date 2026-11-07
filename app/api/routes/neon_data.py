"""Neon-backed read surfaces for scenarios + loan CF (normalized + enriched)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.repositories.connect import connect, source_label
from app.repositories.env_load import load_dotenv
from app.repositories.neon_cf_repository import NeonCfRepository

router = APIRouter(prefix="/api/neon", tags=["neon"])


def _repo() -> NeonCfRepository:
    load_dotenv()
    repo = NeonCfRepository()
    if not repo.url:
        raise HTTPException(status_code=503, detail="DATABASE_URL not set")
    return repo


@router.get("/status")
def neon_status() -> dict:
    repo = _repo()
    try:
        return {
            "ok": True,
            "scenarios": repo.count_scenarios(),
            "loan_cashflows_month1": repo.count_month1(),
            "loan_cashflows_month1_enriched": repo.count_month1_enriched(),
            "orphans": repo.orphan_month1_count(),
            "month1_scenario_ids": repo.distinct_month1_scenario_ids(),
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/scenarios")
def neon_scenarios() -> dict:
    repo = _repo()
    try:
        rows = repo.list_scenarios()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "n": len(rows),
        "source": source_label("securitization_scenarios", repo.url),
        "scenarios": rows,
    }


@router.get("/cashflows/month1")
def neon_month1(
    scenario_id: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    repo = _repo()
    try:
        rows = repo.list_month1_enriched(
            scenario_id=scenario_id, limit=limit, offset=offset
        )
        with connect(repo.require_url(), connect_timeout=30) as conn:
            with conn.cursor() as cur:
                if scenario_id:
                    cur.execute(
                        """
                        SELECT COUNT(*) FROM public.loan_cashflows_month1_enriched
                        WHERE scenario_id = %s
                        """,
                        (scenario_id,),
                    )
                else:
                    cur.execute(
                        "SELECT COUNT(*) FROM public.loan_cashflows_month1_enriched"
                    )
                total = int(cur.fetchone()[0])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "n": len(rows),
        "total": total,
        "scenario_id": scenario_id,
        "source": source_label("loan_cashflows_month1_enriched", repo.url),
        "rows": rows,
    }


@router.get("/cashflows/loan-month")
def neon_loan_month(
    loan_id: str = Query(...),
    scenario_id: str | None = Query(default=None),
) -> dict:
    repo = _repo()
    try:
        rows = repo.list_loan_month_cf_enriched(
            loan_id=loan_id, scenario_id=scenario_id
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "n": len(rows),
        "loan_id": loan_id,
        "scenario_id": scenario_id,
        "source": source_label("loan_month_cf_enriched", repo.url),
        "rows": rows,
    }
