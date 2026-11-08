"""Full-horizon CF for all 27 grid scenarios — aggregate by scenario × month.

Each ProcessPoolExecutor worker owns one Scenario cell and projects every loan
in that cell's cohort for the full horizon (performing months + FNMA recovery
lag + recovery period, capped at 480). Aggregates only — no loan×month dump.
"""

from __future__ import annotations

import os
import time
import traceback
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import Any

from app.models.loan import Loan
from app.models.scenario import Scenario
from app.services.base_case_cohort_cf import (
    DEFAULT_HORIZON,
    MAX_ENGINE_MONTHS,
    _loan_horizon_months,
)
from app.services.cashflow_engine import project_loan_cashflows
from app.services.cohort_labels import canonical_cohort_label
from app.services.recovery import resolve_recovery_lag_months
from app.services.scenario_config import label_psa_sda
from app.services.scenario_grid import (
    COHORTS,
    PSA_LEVEL_NAME,
    SDA_LEVEL_NAME,
    build_scenario_grid,
)

MAX_WORKERS = 27


def _wal_years(month_principal: dict[int, float]) -> float | None:
    """WAL_years = sum(month * principal_cash) / sum(principal_cash) / 12."""
    num = 0.0
    den = 0.0
    for m, pc in month_principal.items():
        v = float(pc or 0.0)
        if v == 0.0:
            continue
        num += float(m) * v
        den += v
    if den == 0.0:
        return None
    return round(num / den / 12.0, 6)


def _worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Picklable worker: one scenario × cohort loans → monthly aggregates + WAL."""
    t0 = time.perf_counter()
    scenario_raw = payload.get("scenario") or {}
    perform_months = int(payload.get("perform_months") or DEFAULT_HORIZON)
    keep_month1 = bool(payload.get("keep_month1", False))
    try:
        scenario = Scenario(**scenario_raw)
        loans = [Loan(**ld) for ld in payload.get("loans") or []]

        total_by_m: dict[int, float] = defaultdict(float)
        prin_by_m: dict[int, float] = defaultdict(float)
        beg_by_m: dict[int, float] = defaultdict(float)
        interest_by_m: dict[int, float] = defaultdict(float)
        sched_by_m: dict[int, float] = defaultdict(float)
        prepay_by_m: dict[int, float] = defaultdict(float)
        default_by_m: dict[int, float] = defaultdict(float)
        recovery_by_m: dict[int, float] = defaultdict(float)
        loan_month1: list[dict[str, Any]] = []
        n_loan_months = 0
        max_month = 0
        max_lag = 0
        sum_cash = 0.0
        sum_beg0 = 0.0

        for loan in loans:
            loan_months = _loan_horizon_months(
                loan, scenario, perform_months=perform_months
            )
            lag = resolve_recovery_lag_months(
                loan.state,
                scenario_lag_months=int(scenario.recovery_lag_months),
            )
            max_lag = max(max_lag, lag)
            rows = project_loan_cashflows(
                loan, scenario, months=loan_months, validate=False
            )
            if not rows:
                continue
            n_loan_months += len(rows)
            r0 = rows[0]
            sum_beg0 += float(r0.beginning_balance or 0.0)
            if keep_month1:
                loan_month1.append(
                    {
                        "scenario_id": scenario.scenario_id,
                        "loan_id": loan.loan_id,
                        "cohort": scenario.cohort,
                        "total_cash": r0.total_cash,
                        "beginning_balance": r0.beginning_balance,
                        "horizon_months": loan_months,
                        "used_recovery_lag_months": lag,
                    }
                )
            for r in rows:
                m = int(r.month)
                max_month = max(max_month, m)
                tc = float(r.total_cash or 0.0)
                sched = float(r.scheduled_principal or 0.0)
                prepay = float(r.prepay or 0.0)
                recovery = float(r.recovery or 0.0)
                new_def = float(
                    getattr(r, "new_default", None)
                    if getattr(r, "new_default", None) is not None
                    else getattr(r, "default", 0.0) or 0.0
                )
                pc = sched + prepay + recovery
                total_by_m[m] += tc
                prin_by_m[m] += pc
                beg_by_m[m] += float(r.beginning_balance or 0.0)
                interest_by_m[m] += float(r.interest or 0.0)
                sched_by_m[m] += sched
                prepay_by_m[m] += prepay
                default_by_m[m] += new_def
                recovery_by_m[m] += recovery
                sum_cash += tc

        months_out: list[dict[str, Any]] = []
        for m in range(1, max(max_month, 1) + 1):
            months_out.append(
                {
                    "month": m,
                    "interest": round(float(interest_by_m.get(m) or 0.0), 2),
                    "scheduled_principal": round(
                        float(sched_by_m.get(m) or 0.0), 2
                    ),
                    "prepay": round(float(prepay_by_m.get(m) or 0.0), 2),
                    "new_default": round(float(default_by_m.get(m) or 0.0), 2),
                    "recovery": round(float(recovery_by_m.get(m) or 0.0), 2),
                    "total_cash": round(float(total_by_m.get(m) or 0.0), 2),
                    "principal_cash": round(float(prin_by_m.get(m) or 0.0), 2),
                    "beginning_balance": round(
                        float(beg_by_m.get(m) or 0.0), 2
                    ),
                }
            )

        wal = _wal_years(prin_by_m)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "status": "ok",
            "scenario_id": scenario.scenario_id,
            "cohort": scenario.cohort,
            "psa_multiple": scenario.psa_multiple,
            "sda_multiple": scenario.sda_multiple,
            "psa_sda_label": label_psa_sda(
                scenario.psa_multiple, scenario.sda_multiple
            ),
            "pca_level": PSA_LEVEL_NAME.get(scenario.psa_multiple),
            "sta_level": SDA_LEVEL_NAME.get(scenario.sda_multiple),
            "wal_kind": "scenario_wal",
            "recovery_rate": scenario.recovery_rate,
            "recovery_period_months": scenario.recovery_period_months,
            "recovery_lag_months": scenario.recovery_lag_months,
            "n_loans": len(loans),
            "n_loan_months": n_loan_months,
            "horizon_months": max_month,
            "perform_months": perform_months,
            "max_fnma_lag_months": max_lag,
            "beginning_upb": round(sum_beg0, 2),
            "total_cash_sum": round(sum_cash, 2),
            "wal_years": wal,
            "months": months_out,
            "loan_month1": loan_month1 if keep_month1 else [],
            "elapsed_ms": round(elapsed_ms, 1),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 — surface per-worker failures
        return {
            "status": "error",
            "scenario_id": scenario_raw.get("scenario_id"),
            "cohort": scenario_raw.get("cohort"),
            "psa_multiple": scenario_raw.get("psa_multiple"),
            "sda_multiple": scenario_raw.get("sda_multiple"),
            "psa_sda_label": label_psa_sda(
                int(scenario_raw.get("psa_multiple") or 0),
                int(scenario_raw.get("sda_multiple") or 0),
            )
            if scenario_raw.get("psa_multiple") is not None
            else None,
            "pca_level": PSA_LEVEL_NAME.get(scenario_raw.get("psa_multiple")),
            "sta_level": SDA_LEVEL_NAME.get(scenario_raw.get("sda_multiple")),
            "wal_kind": "scenario_wal",
            "n_loans": len(payload.get("loans") or []),
            "n_loan_months": 0,
            "horizon_months": 0,
            "perform_months": perform_months,
            "max_fnma_lag_months": 0,
            "beginning_upb": 0.0,
            "total_cash_sum": 0.0,
            "wal_years": None,
            "months": [],
            "loan_month1": [],
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 1),
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }


def loans_by_cohort(loans: list[Loan]) -> dict[str, list[Loan]]:
    out: dict[str, list[Loan]] = {}
    for loan in loans:
        key = canonical_cohort_label(loan.cohort or "")
        out.setdefault(key, []).append(loan)
    return out


# Monthly CF component fields averaged across the 9 scenario cells.
_AVG_COMPONENT_FIELDS = (
    "interest",
    "scheduled_principal",
    "prepay",
    "new_default",
    "recovery",
    "total_cash",
    "principal_cash",
)


def _cohort_average(
    cohort: str,
    cell_results: list[dict[str, Any]],
    *,
    perform_months: int,
) -> dict[str, Any]:
    """Simple mean of the 9 scenario monthly CF component series."""
    cells = [r for r in cell_results if r.get("status") == "ok"]
    max_m = max((int(r.get("horizon_months") or 0) for r in cells), default=0)
    max_m = max(max_m, perform_months)
    n = len(cells) or 1

    avgs: dict[str, dict[int, float]] = {
        f: defaultdict(float) for f in _AVG_COMPONENT_FIELDS
    }
    for r in cells:
        by_m = {int(row["month"]): row for row in (r.get("months") or [])}
        for m in range(1, max_m + 1):
            row = by_m.get(m) or {}
            for f in _AVG_COMPONENT_FIELDS:
                avgs[f][m] += float(row.get(f) or 0.0)

    months_out: list[dict[str, Any]] = []
    for m in range(1, max_m + 1):
        months_out.append(
            {
                "month": m,
                **{f: round(avgs[f][m] / n, 2) for f in _AVG_COMPONENT_FIELDS},
            }
        )

    prin_for_wal = {
        m: avgs["principal_cash"][m] / n for m in range(1, max_m + 1)
    }
    n_loans = cells[0]["n_loans"] if cells else 0
    total_cash_sum = round(
        sum(avgs["total_cash"][m] / n for m in range(1, max_m + 1)), 2
    )
    return {
        "cohort": cohort,
        "scenario_id": "AVG",
        "n_cells": len(cells),
        "n_loans": n_loans,
        "perform_months": perform_months,
        "horizon_months": max_m,
        "total_cash_sum": total_cash_sum,
        "wal_years": _wal_years(prin_for_wal),
        "months": months_out,
    }


def run_scenario_grid_cf(
    loans: list[Loan],
    scenarios: list[Scenario] | None = None,
    *,
    months: int = DEFAULT_HORIZON,
    max_workers: int = MAX_WORKERS,
    keep_month1: bool = False,
    progress_cb: Any | None = None,
) -> dict[str, Any]:
    """Execute 27 scenario workers; return UI JSON + Neon-ready aggregates."""
    scenarios = scenarios or build_scenario_grid()
    if len(scenarios) != 27:
        raise ValueError(f"expected 27 scenarios, got {len(scenarios)}")

    perform_months = max(1, min(int(months), MAX_ENGINE_MONTHS))
    by_cohort = loans_by_cohort(loans)
    payloads: list[dict[str, Any]] = []
    for scenario in scenarios:
        cohort_key = canonical_cohort_label(scenario.cohort)
        cohort_loans = by_cohort.get(cohort_key, [])
        payloads.append(
            {
                "scenario": scenario.model_dump(),
                "loans": [ln.model_dump() for ln in cohort_loans],
                "perform_months": perform_months,
                "keep_month1": keep_month1,
            }
        )

    t_wall0 = time.perf_counter()
    results: list[dict[str, Any]] = []
    use_threads = bool(os.environ.get("VERCEL")) or max_workers <= 4
    executor_cls = ThreadPoolExecutor if use_threads else ProcessPoolExecutor
    executor_name = (
        "ThreadPoolExecutor" if use_threads else "ProcessPoolExecutor"
    )
    done = 0
    with executor_cls(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_worker, p): p["scenario"]["scenario_id"] for p in payloads
        }
        for fut in as_completed(futures):
            sid = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001
                res = {
                    "status": "error",
                    "scenario_id": sid,
                    "error": f"future: {type(exc).__name__}: {exc}",
                    "months": [],
                    "wal_years": None,
                    "n_loans": 0,
                    "total_cash_sum": 0.0,
                    "elapsed_ms": None,
                }
            results.append(res)
            done += 1
            if progress_cb is not None:
                progress_cb(done, len(payloads), res)

    wall_ms = (time.perf_counter() - t_wall0) * 1000.0
    results.sort(key=lambda r: r.get("scenario_id") or "")

    max_lag = 0
    max_period = 0
    chart_horizon = perform_months
    scenario_meta: dict[str, dict[str, Any]] = {}
    for r in results:
        sid = r.get("scenario_id") or ""
        max_lag = max(max_lag, int(r.get("max_fnma_lag_months") or 0))
        max_period = max(max_period, int(r.get("recovery_period_months") or 0))
        chart_horizon = max(chart_horizon, int(r.get("horizon_months") or 0))
        scenario_meta[sid] = {
            "scenario_id": sid,
            "cohort": r.get("cohort"),
            "psa_multiple": r.get("psa_multiple"),
            "sda_multiple": r.get("sda_multiple"),
            "pca_level": r.get("pca_level"),
            "sta_level": r.get("sta_level"),
            "recovery_rate": r.get("recovery_rate"),
            "recovery_period_months": r.get("recovery_period_months"),
            "n_loans": r.get("n_loans"),
            "beginning_upb": r.get("beginning_upb"),
            "total_cash_sum": r.get("total_cash_sum"),
            "wal_years": r.get("wal_years"),
            "horizon_months": r.get("horizon_months"),
            "perform_months": perform_months,
            "status": r.get("status"),
            "elapsed_ms": r.get("elapsed_ms"),
            "error": r.get("error"),
        }

    # Wide months table: {month, S01, S02, ...} total_cash (+ optional __prin / __beg)
    by_sid_months: dict[str, dict[int, dict[str, float]]] = {}
    for r in results:
        sid = r.get("scenario_id") or ""
        by_sid_months[sid] = {
            int(row["month"]): {
                "total_cash": float(row.get("total_cash") or 0.0),
                "principal_cash": float(row.get("principal_cash") or 0.0),
                "beginning_balance": float(row.get("beginning_balance") or 0.0),
            }
            for row in (r.get("months") or [])
        }

    sid_order = [s.scenario_id for s in scenarios]
    months_wide: list[dict[str, Any]] = []
    for m in range(1, chart_horizon + 1):
        row: dict[str, Any] = {"month": m}
        for sid in sid_order:
            cell = by_sid_months.get(sid, {}).get(m) or {}
            row[sid] = round(float(cell.get("total_cash") or 0.0), 2)
            row[f"{sid}__prin"] = round(
                float(cell.get("principal_cash") or 0.0), 2
            )
            row[f"{sid}__beg"] = round(
                float(cell.get("beginning_balance") or 0.0), 2
            )
        months_wide.append(row)

    # Per-scenario month rows for Neon (compact).
    neon_month_rows: list[dict[str, Any]] = []
    for r in results:
        if r.get("status") != "ok":
            continue
        sid = r["scenario_id"]
        for row in r.get("months") or []:
            neon_month_rows.append(
                {
                    "scenario_id": sid,
                    "month": int(row["month"]),
                    "interest": row.get("interest"),
                    "scheduled_principal": row.get("scheduled_principal"),
                    "prepay": row.get("prepay"),
                    "new_default": row.get("new_default"),
                    "recovery": row.get("recovery"),
                    "total_cash": row["total_cash"],
                    "principal_cash": row["principal_cash"],
                    "beginning_balance": row["beginning_balance"],
                }
            )

    cohort_avg: dict[str, Any] = {}
    wal_rows: list[dict[str, Any]] = []
    for r in results:
        if r.get("status") != "ok":
            continue
        wal_rows.append(
            {
                "cohort": r["cohort"],
                "scenario_id": r["scenario_id"],
                "psa_multiple": r.get("psa_multiple"),
                "sda_multiple": r.get("sda_multiple"),
                "psa_sda_label": r.get("psa_sda_label")
                or label_psa_sda(
                    int(r.get("psa_multiple") or 0),
                    int(r.get("sda_multiple") or 0),
                ),
                "wal_kind": "scenario_wal",
                "wal_years": r.get("wal_years"),
                "total_cash_sum": r.get("total_cash_sum"),
                "n_loans": r.get("n_loans"),
                "perform_months": perform_months,
                "horizon_months": r.get("horizon_months"),
            }
        )

    for cohort in COHORTS:
        cells = [
            r
            for r in results
            if canonical_cohort_label(r.get("cohort") or "") == cohort
        ]
        avg = _cohort_average(cohort, cells, perform_months=perform_months)
        cohort_avg[cohort] = {
            "months": avg["months"],
            "wal_years": avg["wal_years"],
            "total_cash_sum": avg["total_cash_sum"],
            "n_loans": avg["n_loans"],
            "n_cells": avg["n_cells"],
            "horizon_months": avg["horizon_months"],
        }
        wal_rows.append(
            {
                "cohort": cohort,
                "scenario_id": "AVG",
                "psa_sda_label": "scenario-avg (9 cells)",
                "wal_kind": "scenario_avg_wal",
                "wal_years": avg["wal_years"],
                "total_cash_sum": avg["total_cash_sum"],
                "n_loans": avg["n_loans"],
                "perform_months": perform_months,
                "horizon_months": avg["horizon_months"],
            }
        )

    loan_month1: list[dict[str, Any]] = []
    if keep_month1:
        for r in results:
            loan_month1.extend(r.get("loan_month1") or [])

    return {
        "perform_months": perform_months,
        "horizon_months": chart_horizon,
        "recovery_tail": {
            "max_fnma_lag_months": max_lag,
            "max_recovery_period_months": max_period,
            "note": (
                "Per loan: horizon = max(perform, remaining_term) "
                "+ FNMA lag + recovery_period (cap 480)"
            ),
        },
        "scenarios": scenario_meta,
        "months": months_wide,
        "cohort_avg": cohort_avg,
        "neon_month_rows": neon_month_rows,
        "wal_rows": wal_rows,
        "loan_month1": loan_month1,
        "parallelism": {
            "executor": executor_name,
            "max_workers": max_workers,
            "n_tasks": len(payloads),
            "wall_ms": round(wall_ms, 1),
            "ok": sum(1 for r in results if r.get("status") == "ok"),
            "error": sum(1 for r in results if r.get("status") != "ok"),
            "n_loans_input": len(loans),
            "n_loan_months": sum(int(r.get("n_loan_months") or 0) for r in results),
        },
        "ran_scenario_ids": [
            r["scenario_id"] for r in results if r.get("status") == "ok"
        ],
    }


def ui_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Strip Neon-only bulk arrays for static JSON / API responses."""
    return {
        "perform_months": result["perform_months"],
        "horizon_months": result["horizon_months"],
        "recovery_tail": result["recovery_tail"],
        "scenarios": result["scenarios"],
        "months": [
            {
                "month": row["month"],
                **{
                    k: v
                    for k, v in row.items()
                    if k != "month" and not k.endswith("__prin") and not k.endswith("__beg")
                },
            }
            for row in result["months"]
        ],
        "cohort_avg": {
            cohort: {
                "wal_years": meta.get("wal_years"),
                "total_cash_sum": meta.get("total_cash_sum"),
                "n_loans": meta.get("n_loans"),
                "n_cells": meta.get("n_cells"),
                "horizon_months": meta.get("horizon_months"),
                "months": meta.get("months"),
            }
            for cohort, meta in (result.get("cohort_avg") or {}).items()
        },
        "parallelism": result["parallelism"],
        "ran_scenario_ids": result.get("ran_scenario_ids"),
    }
