"""Loan Quality QC: built-in NQM rules + English custom rules via Groq."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.repositories.asf_tape_repository import AsfTapeRepository
from app.repositories.connect import source_label
from app.repositories.env_load import load_dotenv
from app.services.qc_nl_translate import groq_api_key, translate_english
from app.services.qc_predicate import validate_predicate

router = APIRouter(prefix="/api/qc", tags=["qc"])


class TranslateBody(BaseModel):
    english: str = Field(..., min_length=1, max_length=2000)


class CustomCheckBody(BaseModel):
    english: str = Field(..., min_length=1, max_length=2000)
    sql_predicate: str | None = Field(default=None, max_length=2000)
    check_id: str | None = Field(default=None, max_length=64)


class CustomCheckUpdateBody(BaseModel):
    english: str | None = Field(default=None, min_length=1, max_length=2000)
    sql_predicate: str | None = Field(default=None, max_length=2000)


def _repo() -> AsfTapeRepository:
    load_dotenv()
    repo = AsfTapeRepository()
    if not repo.url:
        raise HTTPException(status_code=503, detail="DATABASE_URL not set")
    return repo


def _enrich_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        outcome = row.get("outcome")
        if outcome == "pass":
            row["status_label"] = "Pass"
        elif outcome == "fail":
            row["status_label"] = "Fail"
        elif outcome == "skipped":
            row["status_label"] = "Skip"
        else:
            row["status_label"] = ""
    return rows


@router.get("/results")
def qc_results() -> dict:
    repo = _repo()
    try:
        rows = _enrich_results(repo.latest_results())
        tape_n = repo.count_tape()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    run_id = next((r.get("run_id") for r in rows if r.get("run_id")), None)
    return {
        "ok": True,
        "tape_row_count": tape_n,
        "run_id": run_id,
        "n": len(rows),
        "groq_configured": bool(groq_api_key()),
        "source": (
            f"{source_label('qc_checks', repo.url)} + "
            f"{source_label('qc_results', repo.url)}"
        ),
        "results": rows,
    }


@router.get("/results/{check_id}/loans")
def qc_check_loans(
    check_id: str,
    failing_only: bool = Query(True),
    limit: int = Query(2000, ge=1, le=5000),
) -> dict:
    """Loans for a QC rule (default: failing rows for drill-down)."""
    repo = _repo()
    try:
        loans, total, meta = repo.list_check_loans(
            check_id, failing_only=failing_only, limit=limit
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "ok": True,
        "n": len(loans),
        "total": total,
        "loans": loans,
        **meta,
    }


@router.post("/run")
def qc_run() -> dict:
    repo = _repo()
    try:
        repo.ensure_schema()
        repo.upsert_check_defs()
        run = repo.run_qc()
        rows = _enrich_results(repo.latest_results())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "ok": True,
        "run_id": run["run_id"],
        "tape_row_count": run["tape_row_count"],
        "n": len(rows),
        "groq_configured": bool(groq_api_key()),
        "results": rows,
    }


@router.post("/translate")
def qc_translate(body: TranslateBody) -> dict:
    """English → failing-row SQL predicate (Groq or heuristic mock)."""
    result = translate_english(body.english)
    if not result.get("ok"):
        raise HTTPException(
            status_code=400, detail=result.get("error") or "translate failed"
        )
    return {"ok": True, **result}


@router.get("/checks")
def qc_list_checks(source: str | None = Query(None)) -> dict:
    repo = _repo()
    try:
        if source == "custom":
            rows = repo.list_custom_checks()
        else:
            rows = repo.latest_results()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "ok": True,
        "n": len(rows),
        "groq_configured": bool(groq_api_key()),
        "checks": rows,
    }


@router.post("/checks")
def qc_create_check(body: CustomCheckBody) -> dict:
    """Translate (if needed) and save a custom English QC rule to SQLite/Postgres."""
    repo = _repo()
    predicate = (body.sql_predicate or "").strip() or None
    mode = "provided"
    warning = None
    model = None
    required: list[str] = []

    if predicate:
        try:
            predicate, required = validate_predicate(predicate)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        translated = translate_english(body.english)
        if not translated.get("ok") or not translated.get("sql_predicate"):
            raise HTTPException(
                status_code=400,
                detail=translated.get("error") or "translate failed",
            )
        predicate = translated["sql_predicate"]
        required = list(translated.get("required_columns") or [])
        mode = translated.get("mode") or "mock"
        warning = translated.get("warning")
        model = translated.get("model")

    try:
        repo.ensure_schema()
        saved = repo.save_custom_check(
            nl_description=body.english.strip(),
            sql_predicate=predicate,
            required_columns=required,
            check_id=body.check_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "ok": True,
        "mode": mode,
        "model": model,
        "warning": warning,
        "groq_configured": bool(groq_api_key()),
        "check": saved,
    }


@router.put("/checks/{check_id}")
def qc_update_check(check_id: str, body: CustomCheckUpdateBody) -> dict:
    repo = _repo()
    existing = repo.get_check(check_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"unknown check_id: {check_id}")
    if existing.get("source") != "custom":
        raise HTTPException(status_code=400, detail="cannot edit a built-in QC check")

    english = (body.english if body.english is not None else existing["nl_description"])
    predicate = body.sql_predicate
    mode = "provided"
    warning = None
    model = None
    required = list(existing.get("required_columns") or [])

    if predicate is None and body.english is not None:
        translated = translate_english(body.english)
        if not translated.get("ok") or not translated.get("sql_predicate"):
            raise HTTPException(
                status_code=400,
                detail=translated.get("error") or "translate failed",
            )
        predicate = translated["sql_predicate"]
        required = list(translated.get("required_columns") or [])
        mode = translated.get("mode") or "mock"
        warning = translated.get("warning")
        model = translated.get("model")
    elif predicate is not None:
        try:
            predicate, required = validate_predicate(predicate)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        predicate = existing.get("sql_predicate")

    if not predicate:
        raise HTTPException(status_code=400, detail="sql_predicate is required")

    try:
        saved = repo.save_custom_check(
            nl_description=str(english).strip(),
            sql_predicate=predicate,
            required_columns=required,
            check_id=check_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "ok": True,
        "mode": mode,
        "model": model,
        "warning": warning,
        "groq_configured": bool(groq_api_key()),
        "check": saved,
    }


@router.delete("/checks/{check_id}")
def qc_delete_check(check_id: str) -> dict:
    repo = _repo()
    try:
        deleted = repo.delete_custom_check(check_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail=f"unknown check_id: {check_id}")
    return {"ok": True, "deleted": check_id}
