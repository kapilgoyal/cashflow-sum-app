"""Confirm PSA/SDA curve age = loan_age_at_cutoff + projection month (not t=1)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.loan import Loan
from app.models.scenario import Scenario
from app.services.cashflow_engine import project_loan_cashflows
from app.services.psa_prepay import cpr_at_age
from app.services.sda_default import cdr_at_age
from app.services.seasoning import curve_age


def main() -> int:
    age_at_cutoff = 24
    loan = Loan(
        loan_id="EX-SEASONED",
        current_balance=300_000.0,
        annual_rate=0.08,
        remaining_term_months=336,
        loan_age_months=age_at_cutoff,
        monthly_payment=2_200.0,
    )
    scenario = Scenario(
        scenario_id="EX100",
        cohort="example",
        psa_multiple=100,
        sda_multiple=100,
        recovery_period_months=12,
        recovery_lag_months=0,
        recovery_rate=0.6,
    )
    row = project_loan_cashflows(loan, scenario, months=1)[0]
    expect_age = curve_age(age_at_cutoff, 1)  # 25
    expect_cpr = cpr_at_age(expect_age, 100)  # 0.2% * 25 = 5.0%
    expect_cdr = cdr_at_age(expect_age, 100)  # 0.02% * 25 = 0.50%
    wrong_t1_cpr = cpr_at_age(1, 100)  # 0.2%

    print(
        f"loan_age_at_cutoff={age_at_cutoff} → month 1 curve_age={row.loan_age} "
        f"CPR={row.cpr:.4%} CDR={row.cdr:.4%}"
    )
    print(f"expected age={expect_age} CPR={expect_cpr:.4%} CDR={expect_cdr:.4%}")
    print(f"wrong always-t=1 CPR would be {wrong_t1_cpr:.4%}")

    ok = (
        row.loan_age == expect_age
        and abs(row.cpr - expect_cpr) < 1e-12
        and abs(row.cdr - expect_cdr) < 1e-12
        and abs(row.cpr - wrong_t1_cpr) > 1e-6
    )
    if not ok:
        print("FAIL: seasoning index incorrect", file=sys.stderr)
        return 1
    print("OK: seasoned PSA/SDA index (age_at_cutoff + k)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
