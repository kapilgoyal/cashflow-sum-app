"""Base-case loan CF for all three cohorts — aggregate cash + recovery by month.

Uses the Scenarios pane Base speeds (COHORT_SPEED_SCHEDULE psaBase/sdaBase),
not the uniform 100/100 grid cell. PSA/SDA CPR/CDR still season by loan age
(``curve_age = age_at_cutoff + projection_month``). Also emits ``recovery_months``
(engine ``recovery`` principal from liquidated defaults) per cohort + Pool.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from app.models.loan import Loan
from app.models.scenario import Scenario
from app.services.cashflow_engine import project_loan_cashflows
from app.services.cohort_labels import (
    COHORT_HIGH_LTV_STRONG,
    COHORT_HIGH_LTV_WEAK,
    COHORT_LOW_LTV_WEAK,
    canonical_cohort_label,
)
from app.services.recovery import resolve_recovery_lag_months
from app.services.scenario_config import base_speeds, label_psa_sda
from app.services.scenario_grid import COHORT_RECOVERY

# From data/scenario_config.json cohort_speed_schedule (psaBase/sdaBase).
BASE_SPEEDS: dict[str, tuple[int, int]] = base_speeds()

COHORT_ORDER = (
    COHORT_LOW_LTV_WEAK,
    COHORT_HIGH_LTV_STRONG,
    COHORT_HIGH_LTV_WEAK,
)

# Performing / scheduled horizon. Actual path extends by FNMA lag + period.
DEFAULT_HORIZON = 360
MAX_ENGINE_MONTHS = 480


def base_scenarios() -> list[Scenario]:
    """One Base cell per cohort (scenario family = Base)."""
    rows: list[Scenario] = []
    for i, cohort in enumerate(COHORT_ORDER, start=1):
        psa, sda = BASE_SPEEDS[cohort]
        rate, period, lag = COHORT_RECOVERY[cohort]
        rows.append(
            Scenario(
                scenario_id=f"BASE{i:02d}",
                cohort=cohort,
                psa_multiple=psa,
                sda_multiple=sda,
                recovery_period_months=period,
                recovery_lag_months=lag,
                recovery_rate=rate,
                note=(
                    f"Base scenario · {cohort} {label_psa_sda(psa, sda)}; "
                    "CPR/CDR from PSA/SDA curves at loan age + month; "
                    "horizon includes FNMA recovery lag + period; "
                    "WAL kind = base_wal (cohort psaBase/sdaBase)"
                ),
            )
        )
    return rows


def _loan_horizon_months(
    loan: Loan,
    scenario: Scenario,
    *,
    perform_months: int,
) -> int:
    """Performing months + FNMA state lag + recovery period (capped).

    Defaults near the end of the path still liquidate after lag, spread over
    recovery_period_months — so chart/totals must extend past 360.
    """
    rem = max(int(loan.remaining_term_months or 0), 0)
    perform = max(int(perform_months), rem, 1)
    lag = resolve_recovery_lag_months(
        loan.state,
        scenario_lag_months=int(scenario.recovery_lag_months),
    )
    period = max(int(scenario.recovery_period_months), 1)
    return min(perform + lag + period, MAX_ENGINE_MONTHS)


def run_base_case_cohort_cf(
    loans: list[Loan],
    *,
    months: int = DEFAULT_HORIZON,
) -> dict[str, Any]:
    """Project every loan under its cohort Base cell; aggregate total cash.

    Returns monthly series (chart), per-cohort totals, and loan-level month-1
    rows (compact loan proof without dumping full paths).
    """
    t0 = time.perf_counter()
    perform_months = max(1, min(int(months), MAX_ENGINE_MONTHS))
    scenarios = {s.cohort: s for s in base_scenarios()}

    by_cohort_loans: dict[str, list[Loan]] = defaultdict(list)
    for loan in loans:
        key = canonical_cohort_label(loan.cohort)
        if key in scenarios:
            by_cohort_loans[key].append(loan)

    # month → cohort → total_cash / beginning_balance / returned principal
    cash: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    beg: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    recovery: dict[int, dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    sched_prin: dict[int, dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    prepay: dict[int, dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    cohort_meta: dict[str, dict[str, Any]] = {}
    loan_month1: list[dict[str, Any]] = []
    n_loan_months = 0
    max_month = 0
    max_lag_used = 0
    max_period_used = 0

    for cohort in COHORT_ORDER:
        scenario = scenarios[cohort]
        cohort_loans = by_cohort_loans.get(cohort) or []
        sum_cash = 0.0
        sum_recovery = 0.0
        sum_beg0 = 0.0
        max_period_used = max(
            max_period_used, int(scenario.recovery_period_months)
        )
        for loan in cohort_loans:
            loan_months = _loan_horizon_months(
                loan, scenario, perform_months=perform_months
            )
            lag = resolve_recovery_lag_months(
                loan.state,
                scenario_lag_months=int(scenario.recovery_lag_months),
            )
            max_lag_used = max(max_lag_used, lag)
            rows = project_loan_cashflows(
                loan, scenario, months=loan_months, validate=False
            )
            if not rows:
                continue
            n_loan_months += len(rows)
            r0 = rows[0].model_dump()
            loan_month1.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "loan_id": loan.loan_id,
                    "cohort": cohort,
                    "psa_multiple": scenario.psa_multiple,
                    "sda_multiple": scenario.sda_multiple,
                    "loan_age_months": int(loan.loan_age_months or 0),
                    "curve_age_m1": int(r0.get("loan_age") or 0),
                    "used_recovery_lag_months": lag,
                    "recovery_period_months": int(
                        scenario.recovery_period_months
                    ),
                    "horizon_months": loan_months,
                    "cpr": r0.get("cpr"),
                    "cdr": r0.get("cdr"),
                    "total_cash": r0.get("total_cash"),
                    "beginning_balance": r0.get("beginning_balance"),
                    "ending_balance": r0.get("ending_balance"),
                    "recovery": r0.get("recovery"),
                }
            )
            sum_beg0 += float(r0.get("beginning_balance") or 0.0)
            for r in rows:
                m = int(r.month)
                max_month = max(max_month, m)
                tc = float(r.total_cash or 0.0)
                rc = float(r.recovery or 0.0)
                sp = float(r.scheduled_principal or 0.0)
                pp = float(r.prepay or 0.0)
                cash[m][cohort] += tc
                recovery[m][cohort] += rc
                sched_prin[m][cohort] += sp
                prepay[m][cohort] += pp
                beg[m][cohort] += float(r.beginning_balance or 0.0)
                sum_cash += tc
                sum_recovery += rc
        cohort_meta[cohort] = {
            "scenario_id": scenario.scenario_id,
            "psa_multiple": scenario.psa_multiple,
            "sda_multiple": scenario.sda_multiple,
            "psa_sda_label": label_psa_sda(
                scenario.psa_multiple, scenario.sda_multiple
            ),
            "wal_kind": "base_wal",
            "recovery_period_months": int(scenario.recovery_period_months),
            "n_loans": len(cohort_loans),
            "beginning_upb": round(sum_beg0, 2),
            "total_cash_sum": round(sum_cash, 2),
            "recovery_sum": round(sum_recovery, 2),
        }

    chart_horizon = max(max_month, perform_months)
    months_out: list[dict[str, Any]] = []
    recovery_months_out: list[dict[str, Any]] = []
    principal_months_out: list[dict[str, Any]] = []
    for m in range(1, chart_horizon + 1):
        row: dict[str, Any] = {"month": m}
        rec_row: dict[str, Any] = {"month": m}
        prin_row: dict[str, Any] = {"month": m}
        pool = 0.0
        pool_rec = 0.0
        pool_sched = 0.0
        pool_prepay = 0.0
        for cohort in COHORT_ORDER:
            v = round(float(cash[m].get(cohort) or 0.0), 2)
            rv = round(float(recovery[m].get(cohort) or 0.0), 2)
            sp = round(float(sched_prin[m].get(cohort) or 0.0), 2)
            pp = round(float(prepay[m].get(cohort) or 0.0), 2)
            row[cohort] = v
            rec_row[cohort] = rv
            pool += v
            pool_rec += rv
            pool_sched += sp
            pool_prepay += pp
            row[f"{cohort}__beg"] = round(float(beg[m].get(cohort) or 0.0), 2)
        row["Pool"] = round(pool, 2)
        rec_row["Pool"] = round(pool_rec, 2)
        pool_sched_r = round(pool_sched, 2)
        pool_prepay_r = round(pool_prepay, 2)
        pool_rec_r = round(pool_rec, 2)
        prin_row["scheduled_principal"] = pool_sched_r
        prin_row["prepay"] = pool_prepay_r
        prin_row["recovery"] = pool_rec_r
        prin_row["principal_cash"] = round(
            pool_sched_r + pool_prepay_r + pool_rec_r, 2
        )
        months_out.append(row)
        recovery_months_out.append(rec_row)
        principal_months_out.append(prin_row)

    wall_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "scenario": "Base",
        "perform_months": perform_months,
        "horizon_months": chart_horizon,
        "seasoning": (
            "PSA CPR / SDA CDR at curve_age = loan_age_months + projection_month; "
            "path extends by FNMA state recovery lag + cohort recovery period"
        ),
        "recovery_source": (
            "Base scenario — engine field recovery "
            "(principal from liquidated defaults)"
        ),
        "recovery_tail": {
            "max_fnma_lag_months": max_lag_used,
            "max_recovery_period_months": max_period_used,
            "note": (
                "Per loan: horizon = max(perform, remaining_term) "
                "+ FNMA lag + recovery_period"
            ),
        },
        "cohorts": cohort_meta,
        "months": months_out,
        "recovery_months": recovery_months_out,
        "principal_months": principal_months_out,
        "loan_month1": loan_month1,
        "parallelism": {
            "executor": "serial-base",
            "n_loans": len(loans),
            "n_loan_months": n_loan_months,
            "wall_ms": round(wall_ms, 1),
        },
    }
