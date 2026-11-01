"""Loan Quality QC read + optional re-run against public.asf_tape."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.repositories.asf_tape_repository import AsfTapeRepository
from app.repositories.env_load import load_dotenv

router = APIRouter(prefix="/api/qc", tags=["qc"])


def _repo() -> AsfTapeRepository:
    load_dotenv()
    repo = AsfTapeRepository()
    if not repo.url:
        raise HTTPException(status_code=503, detail="DATABASE_URL not set")
    return repo


@router.get("/results")
def qc_results() -> dict:
    repo = _repo()
    try:
        rows = repo.latest_results()
        tape_n = repo.count_tape()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    run_id = next((r.get("run_id") for r in rows if r.get("run_id")), None)
    return {
        "ok": True,
        "tape_row_count": tape_n,
        "run_id": run_id,
        "n": len(rows),
        "source": "neon.qc_checks + neon.qc_results",
        "results": rows,
    }


@router.post("/run")
def qc_run() -> dict:
    repo = _repo()
    try:
        repo.ensure_schema()
        repo.upsert_check_defs()
        run = repo.run_qc()
        rows = repo.latest_results()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "ok": True,
        "run_id": run["run_id"],
        "tape_row_count": run["tape_row_count"],
        "n": len(rows),
        "results": rows,
    }
