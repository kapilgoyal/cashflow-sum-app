"""Independent CF-178 verification harness (local, no deploy)."""

from __future__ import annotations

from datetime import date
from math import isclose

from app.models.loan import Loan
from app.models.scenario import Scenario
from app.services.cashflow_engine import project_loan_cashflows
from app.services.reconcile import assert_path_reconciles
from app.services.scenario_grid_cf import _wal_years
from app.services.seasoning import age_at_cutoff, months_since_origination


def cpr_at_age(age: int, psa: float) -> float:
    age = max(int(age), 1)
    base = 0.002 * age if age <= 30 else 0.06
    return max(0.0, (psa / 100.0) * base)


def smm_from_cpr(cpr: float) -> float:
    if cpr <= 0:
        return 0.0
    if cpr >= 1:
        return 1.0
    return 1.0 - (1.0 - cpr) ** (1.0 / 12.0)


def contractual_sched(balance: float, rate: float, n: int) -> float:
    if balance <= 0 or n <= 0:
        return 0.0
    if n == 1:
        return balance
    mu = rate / 12.0
    if mu <= 0:
        return balance / n
    return balance * mu / ((1 + mu) ** n - 1)


def indep_path(
    balance0: float = 100_000.0,
    rate: float = 0.06,
    rem: int = 360,
    age0: int = 60,
    psa: float = 100,
    months: int = 60,
) -> list[tuple]:
    bal = balance0
    out = []
    for m in range(1, months + 1):
        n = rem - m + 1
        sched = min(contractual_sched(bal, rate, n), bal)
        age = age0 + m
        smm = smm_from_cpr(cpr_at_age(age, psa))
        prepay = (bal - sched) * smm
        end = bal - sched - prepay
        out.append((m, age, bal, sched, prepay, end))
        bal = end
    return out


def main() -> None:
    indep = indep_path()
    print("INDEP m60 end", f"{indep[-1][5]:.8f}")
    print(
        "INDEP m1 begin/sched/prepay/end/age",
        f"{indep[0][2]:.8f}",
        f"{indep[0][3]:.8f}",
        f"{indep[0][4]:.8f}",
        f"{indep[0][5]:.8f}",
        indep[0][1],
    )

    loan = Loan(
        loan_id="R",
        current_balance=100_000,
        annual_rate=0.06,
        remaining_term_months=360,
        loan_age_months=60,
        monthly_payment=None,
        remaining_io_months=0,
    )
    sc = Scenario(
        scenario_id="T",
        cohort="X",
        psa_multiple=100,
        sda_multiple=0,
        recovery_rate=0.6,
        recovery_lag_months=0,
        recovery_period_months=1,
    )
    erows = project_loan_cashflows(loan, sc, months=60)
    print("ENGINE m60 end", f"{float(erows[59].ending_balance):.8f}")
    print(
        "ENGINE m1 sched/prepay/end/age",
        erows[0].scheduled_principal,
        erows[0].prepay,
        erows[0].ending_balance,
        erows[0].loan_age,
    )
    print("delta engine-indep", float(erows[59].ending_balance) - indep[-1][5])
    print("abs vs 68292.97", abs(float(erows[59].ending_balance) - 68292.97))

    # monthly_payment ignored for Sched?
    loan_pay = Loan(
        loan_id="R",
        current_balance=100_000,
        annual_rate=0.06,
        remaining_term_months=360,
        loan_age_months=60,
        monthly_payment=9999.0,
        remaining_io_months=0,
    )
    erows2 = project_loan_cashflows(loan_pay, sc, months=60)
    print(
        "monthly_payment=9999 m60",
        f"{float(erows2[59].ending_balance):.8f}",
        "same_as_none",
        isclose(
            float(erows2[59].ending_balance),
            float(erows[59].ending_balance),
            abs_tol=1e-8,
        ),
    )
    print(
        "m1 sched huge_pmt vs none",
        erows2[0].scheduled_principal,
        erows[0].scheduled_principal,
    )

    # loan_age=0 vs orig/cutoff implying 60
    print(
        "months_since 2019-11 to 2024-11",
        months_since_origination(date(2019, 11, 1), date(2024, 11, 1)),
    )
    print(
        "age_at_cutoff None",
        age_at_cutoff(
            loan_age_months=None,
            origination_date=date(2019, 11, 1),
            cutoff_date=date(2024, 11, 1),
        ),
    )
    print(
        "age_at_cutoff 0",
        age_at_cutoff(
            loan_age_months=0,
            origination_date=date(2019, 11, 1),
            cutoff_date=date(2024, 11, 1),
        ),
    )
    loan0 = Loan(
        loan_id="R",
        current_balance=100_000,
        annual_rate=0.06,
        remaining_term_months=360,
        loan_age_months=0,
        origination_date=date(2019, 11, 1),
        cutoff_date=date(2024, 11, 1),
        monthly_payment=None,
        remaining_io_months=0,
    )
    e0 = project_loan_cashflows(loan0, sc, months=1)
    e60 = project_loan_cashflows(loan, sc, months=1)
    print(
        "engine age0+dates m1 loan_age/cpr",
        e0[0].loan_age,
        e0[0].cpr,
        "vs age60",
        e60[0].loan_age,
        e60[0].cpr,
    )

    meta = assert_path_reconciles(erows, starting_balance=100_000.0)
    print("reconcile", meta)

    # WAL definitions on engine path principal
    # Code WAL-A: sum(m*prin)/sum(prin)/12 with prin = sched+prepay+recovery
    prin_code = {
        int(r.month): float(r.scheduled_principal)
        + float(r.prepay)
        + float(r.recovery)
        for r in erows
    }
    # Alt prin including new_default (balance reduction, not investor cash)
    prin_with_def = {
        int(r.month): float(r.scheduled_principal)
        + float(r.prepay)
        + float(r.new_default)
        for r in erows
    }
    wal_a = _wal_years(prin_code)
    wal_a_def = _wal_years(prin_with_def)
    num = sum(m * v for m, v in prin_code.items())
    wal_b_over_start = (num / 100_000.0) / 12.0  # sometimes confused with factor WAL
    print("WAL-A code (sched+prepay+recov)", wal_a)
    print("WAL-A' (sched+prepay+default)", wal_a_def)
    print("WAL-B num/start_bal/12", wal_b_over_start)
    print(
        "sum prin_code",
        sum(prin_code.values()),
        "start-end",
        100_000 - float(erows[-1].ending_balance),
    )

    # Zero-prepay fixed amort sanity (fully amortizing, no PSA)
    sc0 = Scenario(
        scenario_id="Z",
        cohort="X",
        psa_multiple=0,
        sda_multiple=0,
        recovery_rate=0.6,
        recovery_lag_months=0,
        recovery_period_months=1,
    )
    z = project_loan_cashflows(loan, sc0, months=12)
    print(
        "0PSA m12 end",
        z[11].ending_balance,
        "m1 sched",
        z[0].scheduled_principal,
        "prepay",
        z[0].prepay,
    )


if __name__ == "__main__":
    main()
