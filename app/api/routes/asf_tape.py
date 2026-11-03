"""ASF tape read surfaces: loan grid, stratification, cohort pool stats."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.repositories.asf_tape_repository import AsfTapeRepository
from app.repositories.env_load import load_dotenv

router = APIRouter(prefix="/api/asf", tags=["asf-tape"])


def _repo() -> AsfTapeRepository:
    load_dotenv()
    return AsfTapeRepository()


@router.get("/tape")
def asf_tape(
    limit: int = Query(default=2000, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    repo = _repo()
    try:
        if repo.url:
            # Ensure has_mi exists before SELECT (Neon DBs predate the column).
            try:
                repo.ensure_has_mi_column()
            except Exception:  # noqa: BLE001
                pass
            rows, total = repo.list_loans(limit=limit, offset=offset)
            source = "neon.asf_tape"
        else:
            rows, total = repo.list_loans_from_excel(limit=limit)
            source = "excel.Minimum_Case"
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "n": len(rows),
        "total": total,
        "source": source,
        "database_url_set": bool(repo.url),
        "loans": rows,
    }


@router.get("/stratification")
def asf_stratification(
    by: str = Query(default="documentation_type", alias="by"),
) -> dict:
    repo = _repo()
    if not repo.url:
        raise HTTPException(
            status_code=503,
            detail="DATABASE_URL not set — load asf_tape to Neon for stratification",
        )
    try:
        payload = repo.stratification(by)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    payload["source"] = "neon.asf_tape"
    return payload


@router.get("/cohort-stats")
def asf_cohort_stats() -> dict:
    repo = _repo()
    if not repo.url:
        raise HTTPException(status_code=503, detail="DATABASE_URL not set")
    try:
        rows = repo.cohort_stats()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "n": len(rows),
        "source": "neon.asf_tape",
        "rows": rows,
    }
