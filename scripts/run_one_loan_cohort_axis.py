"""Project ONE loan × 9 cohort-axis scenarios (months 1..360 / until payoff).

Persists normalized rows to Neon public.loan_month_cf (scenario defs via view).
No engine formula changes.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.repositories.env_load import load_dotenv  # noqa: E402
from app.repositories.neon_cf_repository import NeonCfRepository  # noqa: E402
from app.repositories.tape_repository import TapeRepository  # noqa: E402
from app.services.cashflow_engine import project_loan_cashflows  # noqa: E402
from app.services.psa_sda import round_money  # noqa: E402
from app.services.recovery import resolve_recovery_lag_months  # noqa: E402
from app.services.scenario_grid import (  # noqa: E402
    PSA_LEVEL_NAME,
    SDA_LEVEL_NAME,
    build_scenario_grid,
)

DEFAULT_LOAN_ID = "SYN001040"
EPS = 0.02
OUT_DIR = REPO_ROOT / "data"


def _trim_at_payoff(rows: list) -> list:
    last = -1
    for i, r in enumerate(rows):
        if (
            abs(r.beginning_balance) > EPS
            or abs(r.ending_balance) > EPS
            or abs(r.interest) > EPS
            or abs(r.scheduled_principal) > EPS
            or abs(r.default) > EPS
            or abs(r.prepay) > EPS
            or abs(r.recovery) > EPS
        ):
            last = i
    if last < 0:
        return rows[:1] if rows else []
    return rows[: last + 1]


def _verify(rows: list, scenario, loan=None) -> dict[str, Any]:
    lag = resolve_recovery_lag_months(
        getattr(loan, "state", None) if loan is not None else None,
        scenario_lag_months=int(scenario.recovery_lag_months),
    )
    period = max(int(scenario.recovery_period_months), 1)
    rec_rate = float(scenario.recovery_rate)

    neg = True
    chain = True
    stop_ok = True
    def_rec_ok = True
    spread_ok = True
    details: dict[str, Any] = {}

    for r in rows:
        if (
            r.beginning_balance < -EPS
            or r.ending_balance < -EPS
            or r.interest < -EPS
            or r.scheduled_principal < -EPS
            or r.default < -EPS
            or r.prepay < -EPS
            or r.recovery < -EPS
        ):
            neg = False
            details["neg_example_month"] = r.month
            break

    for i in range(len(rows) - 1):
        a, b = rows[i], rows[i + 1]
        if abs(a.ending_balance - b.beginning_balance) > EPS:
            chain = False
            details["chain_break"] = {
                "month": a.month,
                "end": a.ending_balance,
                "next_beg": b.beginning_balance,
            }
            break

    zero_idx = None
    for i, r in enumerate(rows):
        if r.ending_balance <= EPS and r.beginning_balance <= EPS and r.recovery <= EPS:
            if all(
                x.beginning_balance <= EPS
                and x.ending_balance <= EPS
                and x.interest <= EPS
                and x.scheduled_principal <= EPS
                and x.default <= EPS
                and x.prepay <= EPS
                and x.recovery <= EPS
                for x in rows[i:]
            ):
                zero_idx = i
                break
    if zero_idx is not None and zero_idx < len(rows) - 1:
        stop_ok = False
        details["stop_extra_months"] = len(rows) - zero_idx

    saw_end_zero = False
    for r in rows:
        if saw_end_zero and (
            r.beginning_balance > EPS
            or r.scheduled_principal > EPS
            or r.default > EPS
            or r.prepay > EPS
        ):
            stop_ok = False
            details["activity_after_payoff_month"] = r.month
            break
        if r.ending_balance <= EPS and r.beginning_balance > EPS:
            saw_end_zero = True
        elif r.ending_balance <= EPS and r.beginning_balance <= EPS:
            saw_end_zero = True

    # (d) While UPB remains: default+recovery ≤ beg.
    # After UPB=0, engine may still drain lagged recovery with default=0.
    for r in rows:
        if r.beginning_balance > EPS:
            if r.default + r.recovery > r.beginning_balance + EPS:
                def_rec_ok = False
                details["def_rec_month"] = {
                    "month": r.month,
                    "beg": r.beginning_balance,
                    "default": r.default,
                    "recovery": r.recovery,
                }
                break
        elif r.default > EPS:
            def_rec_ok = False
            details["def_rec_month"] = {
                "month": r.month,
                "beg": r.beginning_balance,
                "default": r.default,
                "recovery": r.recovery,
                "note": "default after zero UPB",
            }
            break

    pending: dict[int, float] = {}
    for r in rows:
        if r.default > EPS and rec_rate > 0:
            chunk = (r.default * rec_rate) / period
            start = r.month + lag
            for k in range(period):
                pending[start + k] = pending.get(start + k, 0.0) + chunk
    for r in rows:
        expected = round_money(pending.pop(r.month, 0.0))
        if abs(expected - r.recovery) > max(EPS, 0.05):
            spread_ok = False
            details["spread_mismatch"] = {
                "month": r.month,
                "expected": expected,
                "actual": r.recovery,
            }
            break
    leftover = sum(pending.values())
    if leftover > max(EPS, 0.05):
        details["spread_leftover"] = round_money(leftover)

    checks = {
        "a_no_negative_balances": neg,
        "b_end_equals_next_beg": chain,
        "c_end_zero_stops_further_months": stop_ok,
        "d_default_plus_recovery_le_beg": def_rec_ok,
        "e_recovery_spread_rate_over_period": spread_ok,
    }
    return {
        "scenario_id": scenario.scenario_id,
        "n_months": len(rows),
        "checks": {k: ("PASS" if v else "FAIL") for k, v in checks.items()},
        "all_pass": all(checks.values()),
        "details": details,
    }


def main() -> int:
    load_dotenv()
    loan_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_LOAN_ID
    months = int(sys.argv[2]) if len(sys.argv) > 2 else 360

    loan = TapeRepository().get_loan(loan_id)
    if not loan.cohort:
        print(f"ERROR: loan {loan_id} missing cohort", file=sys.stderr)
        return 1

    grid = build_scenario_grid()
    axis = [s for s in grid if s.cohort == loan.cohort]
    if len(axis) != 9:
        print(
            f"ERROR: expected 9 scenarios for cohort={loan.cohort!r}, got {len(axis)}",
            file=sys.stderr,
        )
        return 1

    neon = NeonCfRepository()
    neon.ensure_schema()

    all_db_rows: list[dict[str, Any]] = []
    csv_rows: list[dict[str, Any]] = []
    verifications: list[dict[str, Any]] = []

    for scenario in axis:
        projected = project_loan_cashflows(loan, scenario, months=months)
        trimmed = _trim_at_payoff(projected)
        verifications.append(_verify(trimmed, scenario, loan=loan))
        for r in trimmed:
            all_db_rows.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "loan_id": loan.loan_id,
                    "month": r.month,
                    "beginning_balance": r.beginning_balance,
                    "interest": r.interest,
                    "scheduled_principal": r.scheduled_principal,
                    "default_amt": r.new_default,
                    "prepay": r.prepay,
                    "recovery": r.recovery,
                    "ending_balance": r.ending_balance,
                    "loan_age": r.loan_age,
                    "cpr": r.cpr,
                    "smm": r.smm,
                    "cdr": r.cdr,
                    "mdr": r.mdr,
                    "used_recovery_lag_months": r.used_recovery_lag_months,
                    "beginning_default_balance": r.beginning_default_balance,
                    "liquidated_default": r.liquidated_default,
                    "realized_loss": r.realized_loss,
                    "ending_default_balance": r.ending_default_balance,
                    "total_cash": r.total_cash,
                }
            )
            csv_rows.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "loan_id": loan.loan_id,
                    "cohort": loan.cohort,
                    "psa_multiple": scenario.psa_multiple,
                    "sda_multiple": scenario.sda_multiple,
                    "pca_level": PSA_LEVEL_NAME.get(scenario.psa_multiple),
                    "sta_level": SDA_LEVEL_NAME.get(scenario.sda_multiple),
                    "month": r.month,
                    "beg_bal": r.beginning_balance,
                    "interest": r.interest,
                    "sched_prin": r.scheduled_principal,
                    "prepaid": r.prepay,
                    "default": r.default,
                    "recovery": r.recovery,
                    "loss": loss,
                    "end_bal": r.ending_balance,
                }
            )

    n = neon.replace_loan_month_cf(
        loan_id=loan.loan_id,
        scenario_ids=[s.scenario_id for s in axis],
        rows=all_db_rows,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / f"loan_month_cf_{loan.loan_id}_cohort_axis.csv"
    fieldnames = [
        "scenario_id",
        "loan_id",
        "cohort",
        "psa_multiple",
        "sda_multiple",
        "pca_level",
        "sta_level",
        "month",
        "beg_bal",
        "interest",
        "sched_prin",
        "prepaid",
        "default",
        "recovery",
        "loss",
        "end_bal",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in csv_rows:
            w.writerow(row)

    summary = {
        "loan_id": loan.loan_id,
        "cohort": loan.cohort,
        "scenario_ids": [s.scenario_id for s in axis],
        "n_db_rows": n,
        "csv_path": str(csv_path),
        "verifications": verifications,
        "all_scenarios_pass": all(v["all_pass"] for v in verifications),
        "neon_table": "public.loan_month_cf",
        "neon_view": "public.loan_month_cf_enriched",
    }
    summary_path = OUT_DIR / f"loan_month_cf_{loan.loan_id}_verify.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"loan_id={loan.loan_id}")
    print(f"cohort={loan.cohort}")
    print(f"scenarios={[s.scenario_id for s in axis]}")
    print(f"neon_rows={n}")
    print(f"csv={csv_path}")
    print(f"verify={summary_path}")
    for v in verifications:
        print(
            f"  {v['scenario_id']}: months={v['n_months']} "
            f"pass={v['all_pass']} checks={v['checks']}"
        )
        if v["details"]:
            print(f"    details={v['details']}")
    return 0 if summary["all_scenarios_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
