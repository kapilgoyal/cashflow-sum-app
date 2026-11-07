"""Run month-1 cash flows for all 27 cohort × PCA × STA cells in parallel.

Each ProcessPoolExecutor worker owns one scenario cell and projects every loan
in that cell's cohort for exactly one month. Results are aggregated to
cohort-level summaries for the UI; loan-level rows are returned for persistence.
"""

from __future__ import annotations

import time
import traceback
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import Any

from app.models.loan import Loan
from app.models.scenario import Scenario
from app.services.cashflow_engine import project_loan_cashflows
from app.services.scenario_grid import (
    COHORT_HIGH_LTV_STRONG,
    COHORT_HIGH_LTV_WEAK,
    COHORT_LOW_LTV_WEAK,
    PSA_LEVEL_NAME,
    SDA_LEVEL_NAME,
    build_scenario_grid,
)

MAX_WORKERS = 27
HORIZON_MONTHS = 1

SUM_FIELDS = (
    "beginning_balance",
    "interest",
    "scheduled_principal",
    "default",
    "new_default",
    "prepay",
    "recovery",
    "ending_balance",
    "beginning_default_balance",
    "liquidated_default",
    "realized_loss",
    "ending_default_balance",
    "total_cash",
)


def _upb_weighted_mean(
    rows: list[dict[str, Any]],
    value_key: str,
    *,
    weight_key: str = "beginning_balance",
) -> float | None:
    """UPB-weighted mean; skips non-positive weights. Never loan-count average."""
    num = 0.0
    den = 0.0
    for r in rows:
        try:
            w = float(r.get(weight_key) or 0.0)
            v = float(r.get(value_key) or 0.0)
        except (TypeError, ValueError):
            continue
        if w <= 0:
            continue
        num += v * w
        den += w
    if den <= 0:
        return None
    return round(num / den, 3)


def _worker(payload: dict[str, Any]) -> dict[str, Any]:
    """Picklable worker: one scenario × all loans in its cohort → month-1 rows."""
    t0 = time.perf_counter()
    scenario_raw = payload.get("scenario") or {}
    try:
        scenario = Scenario(**scenario_raw)
        loans = [Loan(**ld) for ld in payload.get("loans") or []]
        loan_rows: list[dict[str, Any]] = []
        totals = {k: 0.0 for k in SUM_FIELDS}
        for loan in loans:
            rows = project_loan_cashflows(loan, scenario, months=HORIZON_MONTHS)
            if not rows:
                raise RuntimeError(f"engine returned no rows for {loan.loan_id}")
            row = rows[0].model_dump()
            loan_rows.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "loan_id": loan.loan_id,
                    "cohort": scenario.cohort,
                    "psa_multiple": scenario.psa_multiple,
                    "sda_multiple": scenario.sda_multiple,
                    "pca_level": PSA_LEVEL_NAME[scenario.psa_multiple],
                    "sta_level": SDA_LEVEL_NAME[scenario.sda_multiple],
                    "state": loan.state,
                    **row,
                }
            )
            for k in SUM_FIELDS:
                totals[k] += float(row.get(k) or 0.0)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "status": "ok",
            "scenario_id": scenario.scenario_id,
            "cohort": scenario.cohort,
            "psa_multiple": scenario.psa_multiple,
            "sda_multiple": scenario.sda_multiple,
            "pca_level": PSA_LEVEL_NAME[scenario.psa_multiple],
            "sta_level": SDA_LEVEL_NAME[scenario.sda_multiple],
            "recovery_rate": scenario.recovery_rate,
            "recovery_period_months": scenario.recovery_period_months,
            "recovery_lag_months": scenario.recovery_lag_months,
            "n_loans": len(loans),
            "elapsed_ms": round(elapsed_ms, 3),
            "aggregate": {
                "month": HORIZON_MONTHS,
                "n_loans": len(loans),
                **{k: round(v, 8) for k, v in totals.items()},
                # UPB-weighted from loan CF (never scenario-grid constants /
                # loan-count simple average). Recovery = Urban/severity per loan;
                # lag = FNMA state months used on that loan.
                "avg_used_recovery_rate": _upb_weighted_mean(
                    loan_rows,
                    "recovery_rate",
                    weight_key="beginning_balance",
                ),
                "avg_used_recovery_lag_months": _upb_weighted_mean(
                    loan_rows,
                    "used_recovery_lag_months",
                    weight_key="beginning_balance",
                ),
            },
            "loan_rows": loan_rows,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 — surface per-worker failures
        return {
            "status": "error",
            "scenario_id": scenario_raw.get("scenario_id"),
            "cohort": scenario_raw.get("cohort"),
            "psa_multiple": scenario_raw.get("psa_multiple"),
            "sda_multiple": scenario_raw.get("sda_multiple"),
            "pca_level": PSA_LEVEL_NAME.get(scenario_raw.get("psa_multiple")),
            "sta_level": SDA_LEVEL_NAME.get(scenario_raw.get("sda_multiple")),
            "n_loans": len(payload.get("loans") or []),
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            "aggregate": None,
            "loan_rows": [],
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }


def loans_by_cohort(loans: list[Loan]) -> dict[str, list[Loan]]:
    out: dict[str, list[Loan]] = {}
    for loan in loans:
        key = loan.cohort or ""
        out.setdefault(key, []).append(loan)
    return out


def run_month1_parallel(
    loans: list[Loan],
    scenarios: list[Scenario] | None = None,
    *,
    max_workers: int = MAX_WORKERS,
) -> dict[str, Any]:
    """Execute 27 scenario workers; return loan-level rows + cohort aggregates."""
    scenarios = scenarios or build_scenario_grid()
    if len(scenarios) != 27:
        raise ValueError(f"expected 27 scenarios, got {len(scenarios)}")

    by_cohort = loans_by_cohort(loans)
    payloads: list[dict[str, Any]] = []
    for scenario in scenarios:
        cohort_loans = by_cohort.get(scenario.cohort, [])
        payloads.append(
            {
                "scenario": scenario.model_dump(),
                "loans": [ln.model_dump() for ln in cohort_loans],
            }
        )

    t_wall0 = time.perf_counter()
    results: list[dict[str, Any]] = []
    # Constrained runtimes: threads (same _worker, no formula change).
    use_threads = bool(os.environ.get("VERCEL")) or max_workers <= 4
    executor_cls = ThreadPoolExecutor if use_threads else ProcessPoolExecutor
    executor_name = (
        "ThreadPoolExecutor" if use_threads else "ProcessPoolExecutor"
    )
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
                    "aggregate": None,
                    "loan_rows": [],
                    "elapsed_ms": None,
                    "n_loans": 0,
                }
            results.append(res)

    wall_ms = (time.perf_counter() - t_wall0) * 1000.0
    results.sort(key=lambda r: r.get("scenario_id") or "")

    loan_rows: list[dict[str, Any]] = []
    aggregates: list[dict[str, Any]] = []
    for r in results:
        loan_rows.extend(r.get("loan_rows") or [])
        agg = {
            "scenario_id": r.get("scenario_id"),
            "cohort": r.get("cohort"),
            "psa_multiple": r.get("psa_multiple"),
            "sda_multiple": r.get("sda_multiple"),
            "pca_level": r.get("pca_level"),
            "sta_level": r.get("sta_level"),
            "recovery_period_months": r.get("recovery_period_months"),
            "status": r.get("status"),
            "elapsed_ms": r.get("elapsed_ms"),
            "error": r.get("error"),
        }
        if r.get("aggregate"):
            agg.update(r["aggregate"])
        # Prefer loan UPB-weighted rates over scenario-grid constants.
        if agg.get("avg_used_recovery_rate") is not None:
            agg["recovery_rate"] = agg["avg_used_recovery_rate"]
        else:
            agg["recovery_rate"] = r.get("recovery_rate")
        if agg.get("avg_used_recovery_lag_months") is not None:
            agg["recovery_lag_months"] = agg["avg_used_recovery_lag_months"]
        else:
            agg["recovery_lag_months"] = r.get("recovery_lag_months")
        aggregates.append(agg)

    return {
        "parallelism": {
            "executor": executor_name,
            "max_workers": max_workers,
            "n_tasks": len(payloads),
            "wall_ms": round(wall_ms, 3),
            "ok": sum(1 for r in results if r.get("status") == "ok"),
            "error": sum(1 for r in results if r.get("status") != "ok"),
            "n_loan_rows": len(loan_rows),
            "n_loans_input": len(loans),
        },
        "assumptions": {
            "horizon_months": HORIZON_MONTHS,
            "psa_sda_seasoning": (
                "curve_age = loan_age_at_cutoff + projection_month "
                "(loan_age_months or origination→cutoff); not t=1 for every loan"
            ),
            "pca_levels": {"Down": 75, "Base": 100, "Up": 125},
            "sta_levels": {"Down": 50, "Base": 100, "Up": 200},
            "recovery_by_cohort": {
                COHORT_HIGH_LTV_STRONG: {
                    "rate": 0.60,
                    "period_months": 12,
                    "lag_months_fallback": 0,
                },
                COHORT_HIGH_LTV_WEAK: {
                    "rate": 0.55,
                    "period_months": 15,
                    "lag_months_fallback": 0,
                },
                COHORT_LOW_LTV_WEAK: {
                    "rate": 0.75,
                    "period_months": 9,
                    "lag_months_fallback": 0,
                },
            },
            "note": (
                "PCA=PSA, STA=SDA. Down/Base/Up from CF-41 grid. "
                "Each of 27 cells runs its cohort loans for month 1 only. "
                "Recovery + lag on aggregates are UPB-weighted from loans "
                "(Urban/severity recovery; FNMA state lag); cohort 60/55/75 "
                "is only the no-MI / missing-cell fallback. "
                "https://singlefamily.fanniemae.com/media/6726/display"
            ),
        },
        "aggregates": aggregates,
        "loan_rows": loan_rows,
        "ran_scenario_ids": [
            r["scenario_id"] for r in results if r.get("status") == "ok"
        ],
    }
