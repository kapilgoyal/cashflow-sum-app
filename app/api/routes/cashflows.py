"""Month-1 parallel CF run + cohort aggregate read surface."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.repositories.cashflow_repository import CashflowRepository
from app.repositories.env_load import load_dotenv, resolve_pg_url
from app.repositories.scenario_repository import ScenarioRepository
from app.repositories.tape_repository import TapeRepository, resolve_default_tape_path
from app.services.cache_keys import (
    assumptions_fingerprint,
    cache_is_fresh,
    cf_cache_meta,
    tape_hash,
)
from app.services.cashflow_engine import ENGINE_VERSION
from app.services.cohort_labels import relabel_payload
from app.services.month1_parallel import run_month1_parallel
from app.services.scenario_grid import build_scenario_grid

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA = REPO_ROOT / "data"
PUBLIC = REPO_ROOT / "public"

router = APIRouter(prefix="/api", tags=["cashflows-month1"])


def _tape_path() -> Path:
    return resolve_default_tape_path()


def _freshness_stamp(*, kind: str, months: int | None = None, scenario: object = None) -> dict:
    """Engine + assumptions (+ tape) stamp embedded in every CF cache payload."""
    sc = scenario if scenario is not None else {"scenario_id": kind}
    meta = cf_cache_meta(
        tape_path=_tape_path(),
        scenario=sc,
        months=months,
        kind=kind,
    )
    return {
        "engine_version": ENGINE_VERSION,
        "assumptions_fingerprint": assumptions_fingerprint(),
        "tape_hash": tape_hash(_tape_path()),
        "cache": meta,
    }


def _load_cached_aggregates() -> dict | None:
    """Prefer data/ then public/ cohort-month1 JSON (static fallback)."""
    cf_repo = CashflowRepository(DATA)
    payload = cf_repo.load_aggregates()
    if payload:
        return relabel_payload(payload)
    public_path = PUBLIC / "cohort-month1.json"
    if public_path.exists():
        return relabel_payload(json.loads(public_path.read_text(encoding="utf-8")))
    return None


def _month1_cache_fresh(payload: dict | None) -> bool:
    """CF-176: refuse month-1 JSON/Neon without matching engine+assumptions."""
    return cache_is_fresh(payload, tape_path=_tape_path(), require_tape=False)


def _neon_month1_summary() -> dict | None:
    load_dotenv()
    url = resolve_pg_url()
    if not url:
        return None
    try:
        from app.repositories.connect import connect, source_label

        with connect(url, connect_timeout=30) as conn:
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
            "source": source_label("loan_cashflows_month1_enriched", url),
        }
    except Exception:  # noqa: BLE001
        return None


@router.get("/scenarios/grid")
def scenario_grid() -> dict:
    scenarios = [s.model_dump() for s in build_scenario_grid()]
    return relabel_payload({"n": len(scenarios), "scenarios": scenarios})


@router.get("/cashflows/month1")
def get_month1_aggregates() -> dict:
    """Return month-1 aggregates only when cache matches current engine/assumptions."""
    cached = _load_cached_aggregates()
    if cached and _month1_cache_fresh(cached):
        return {**cached, "cached": True, "engine_version": ENGINE_VERSION}
    neon = _neon_month1_summary()
    if neon and _month1_cache_fresh(neon):
        return relabel_payload(
            {**neon, "cached": True, "engine_version": ENGINE_VERSION}
        )
    raise HTTPException(
        status_code=404,
        detail=(
            "No fresh month-1 aggregates for engine "
            f"{ENGINE_VERSION} — POST /api/cashflows/run-month1?force=true"
        ),
    )


@router.post("/cashflows/run-month1")
def run_month1(
    force: bool = Query(
        default=False,
        description="Recompute even when Neon/cached aggregates exist",
    ),
) -> dict:
    """Run all 27 scenario cells for every loan in each cohort (month 1).

    Serves JSON/Neon cache only when engine_version + assumptions fingerprint
    match (CF-176). Otherwise recomputes via the same project_loan_cashflows
    path as POST /api/run-loan.
    """
    load_dotenv()
    constrained = bool(os.environ.get("VERCEL"))
    tape_path = _tape_path()

    if not force:
        cached = _load_cached_aggregates()
        if cached and _month1_cache_fresh(cached):
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
                "storage": {"json": "data/ or public/cohort-month1.json"},
                "neon_missing": not bool(resolve_pg_url()),
                "cached": True,
                **_freshness_stamp(kind="month1_cf", months=1),
            }
        neon = _neon_month1_summary()
        if neon and _month1_cache_fresh(neon):
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
                **_freshness_stamp(kind="month1_cf", months=1),
            }

    tape = TapeRepository(tape_path)
    try:
        loans = tape.load_all_loans()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not loans:
        raise HTTPException(status_code=400, detail="no loans loaded from tape")

    scenarios = build_scenario_grid()
    ScenarioRepository(DATA / "securitization_scenarios.csv").save_csv(scenarios)

    max_workers = 2 if constrained else 27
    result = run_month1_parallel(loans, scenarios, max_workers=max_workers)
    stamp = _freshness_stamp(kind="month1_cf", months=1, scenario=scenarios[0])
    meta = {
        "parallelism": result["parallelism"],
        "assumptions": {
            **result["assumptions"],
            "engine_version": ENGINE_VERSION,
            "assumptions_fingerprint": stamp["assumptions_fingerprint"],
            "same_engine_as": "POST /api/run-loan (project_loan_cashflows)",
        },
        "ran_scenario_ids": result["ran_scenario_ids"],
        **stamp,
    }
    cf_repo = CashflowRepository(DATA)
    storage = cf_repo.save(
        loan_rows=result["loan_rows"],
        aggregates=result["aggregates"],
        meta=meta,
    )

    try:
        PUBLIC.mkdir(parents=True, exist_ok=True)
        public_payload = {
            "meta": meta,
            "aggregates": result["aggregates"],
            **stamp,
        }
        (PUBLIC / "cohort-month1.json").write_text(
            json.dumps(public_payload, indent=2), encoding="utf-8"
        )
        storage["public_json"] = "public/cohort-month1.json"
    except OSError:
        pass

    return {
        "parallelism": result["parallelism"],
        "assumptions": meta["assumptions"],
        "ran_scenario_ids": result["ran_scenario_ids"],
        "aggregates": result["aggregates"],
        "storage": storage,
        "neon_missing": not storage.get("database_url_set"),
        "cached": False,
        "n_loan_rows": len(result["loan_rows"]),
        **stamp,
    }


def _load_base_cohort_cf() -> dict | None:
    for path in (DATA / "cohort-base-cashflow.json", PUBLIC / "cohort-base-cashflow.json"):
        if path.exists():
            return relabel_payload(json.loads(path.read_text(encoding="utf-8")))
    return None


@router.get("/cashflows/base-cohort")
def get_base_cohort_cashflow() -> dict:
    """Monthly total cash by cohort under Base speeds (Scenarios chart)."""
    payload = _load_base_cohort_cf()
    if payload and cache_is_fresh(payload, tape_path=_tape_path()):
        return {**payload, "cached": True}
    raise HTTPException(
        status_code=404,
        detail=(
            "No fresh base cohort CF for engine "
            f"{ENGINE_VERSION} — POST /api/cashflows/run-base-cohort?force=true"
        ),
    )


@router.post("/cashflows/run-base-cohort")
def run_base_cohort(
    months: int = Query(
        default=360,
        ge=1,
        le=360,
        description="Performing horizon; FNMA lag + recovery period extend past this",
    ),
    force: bool = Query(default=False),
) -> dict:
    """Project all loans under Base PSA/SDA per cohort; write aggregate JSON."""
    if not force:
        cached = _load_base_cohort_cf()
        if (
            cached
            and cache_is_fresh(cached, tape_path=_tape_path())
            and int(cached.get("perform_months") or cached.get("horizon_months") or 0)
            >= months
            and cached.get("recovery_tail")
            and cached.get("recovery_months")
        ):
            return {**cached, "cached": True}

    from app.services.base_case_cohort_cf import base_scenarios, run_base_case_cohort_cf

    tape_path = _tape_path()
    tape = TapeRepository(tape_path)
    try:
        loans = tape.load_all_loans()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not loans:
        raise HTTPException(status_code=400, detail="no loans loaded from tape")

    result = run_base_case_cohort_cf(loans, months=months)
    base_sc = base_scenarios()[0]
    stamp = _freshness_stamp(
        kind="base_cohort_cf", months=months, scenario=base_sc
    )
    payload = {
        "scenario": result["scenario"],
        "perform_months": result["perform_months"],
        "horizon_months": result["horizon_months"],
        "seasoning": result["seasoning"],
        "recovery_source": result.get("recovery_source"),
        "recovery_tail": result["recovery_tail"],
        "cohorts": result["cohorts"],
        "months": result["months"],
        "recovery_months": result["recovery_months"],
        "parallelism": result["parallelism"],
        "n_loan_month1": len(result["loan_month1"]),
        **stamp,
        "cached": False,
    }
    text = json.dumps(payload, indent=2)
    DATA.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (DATA / "cohort-base-cashflow.json").write_text(text, encoding="utf-8")
    (PUBLIC / "cohort-base-cashflow.json").write_text(text, encoding="utf-8")
    return relabel_payload(payload)


def _load_scenario_grid_cf() -> dict | None:
    for path in (
        DATA / "scenario-grid-cashflow.json",
        PUBLIC / "scenario-grid-cashflow.json",
    ):
        if path.exists():
            return relabel_payload(json.loads(path.read_text(encoding="utf-8")))
    return None


@router.get("/cashflows/scenario-grid")
def get_scenario_grid_cashflow() -> dict:
    """Monthly total cash for all 27 grid scenarios (+ cohort averages / WAL)."""
    payload = _load_scenario_grid_cf()
    if payload and cache_is_fresh(payload, tape_path=_tape_path()):
        return {**payload, "cached": True}
    raise HTTPException(
        status_code=404,
        detail=(
            "No fresh scenario-grid CF for engine "
            f"{ENGINE_VERSION} — POST /api/cashflows/run-scenario-grid?force=true"
        ),
    )


@router.post("/cashflows/run-scenario-grid")
def run_scenario_grid(
    months: int = Query(
        default=360,
        ge=1,
        le=360,
        description="Performing horizon; FNMA lag + recovery period extend past this",
    ),
    force: bool = Query(
        default=False,
        description="Recompute even when cached scenario-grid JSON exists",
    ),
) -> dict:
    """Project all 27 grid cells (full horizon); write aggregate JSON (+ Neon)."""
    if not force:
        cached = _load_scenario_grid_cf()
        if (
            cached
            and cache_is_fresh(cached, tape_path=_tape_path())
            and int(cached.get("perform_months") or cached.get("horizon_months") or 0)
            >= months
            and cached.get("recovery_tail")
            and cached.get("scenarios")
        ):
            return {**cached, "cached": True}

    from app.services.scenario_grid_cf import run_scenario_grid_cf, ui_payload

    tape_path = _tape_path()
    tape = TapeRepository(tape_path)
    try:
        loans = tape.load_all_loans()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not loans:
        raise HTTPException(status_code=400, detail="no loans loaded from tape")

    scenarios = build_scenario_grid()
    ScenarioRepository(DATA / "securitization_scenarios.csv").save_csv(scenarios)

    constrained = bool(os.environ.get("VERCEL"))
    max_workers = 2 if constrained else 27
    result = run_scenario_grid_cf(
        loans,
        scenarios,
        months=months,
        max_workers=max_workers,
        keep_month1=False,
    )
    payload = ui_payload(result)
    stamp = _freshness_stamp(
        kind="scenario_grid_cf", months=months, scenario=scenarios[0]
    )
    payload.update(stamp)
    payload["cached"] = False

    text = json.dumps(payload, indent=2)
    DATA.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (DATA / "scenario-grid-cashflow.json").write_text(text, encoding="utf-8")
    (PUBLIC / "scenario-grid-cashflow.json").write_text(text, encoding="utf-8")

    neon_info: dict | str | None = None
    neon_error: str | None = None
    load_dotenv()
    if resolve_pg_url():
        try:
            from app.repositories.neon_cf_repository import NeonCfRepository

            neon_info = NeonCfRepository().save_scenario_grid_cf(
                scenarios,
                result["neon_month_rows"],
                result["wal_rows"],
            )
        except Exception as exc:  # noqa: BLE001
            neon_error = f"{type(exc).__name__}: {exc}"
    else:
        neon_info = "skipped: DATABASE_URL not set"

    payload["storage"] = {
        "json": "data/scenario-grid-cashflow.json",
        "public_json": "public/scenario-grid-cashflow.json",
        "neon": neon_info,
        "neon_error": neon_error,
    }
    return relabel_payload(payload)


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
