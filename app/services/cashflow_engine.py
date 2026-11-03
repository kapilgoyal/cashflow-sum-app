"""Deterministic one-loan cash flows under PSA prepays + SDA defaults."""

from __future__ import annotations

from collections import defaultdict

from app.models.cashflow import CashflowRow
from app.models.loan import Loan
from app.models.scenario import Scenario
from app.services.psa_sda import (
    cdr_at_age,
    cpr_at_age,
    level_payment,
    mdr_from_cdr,
    round_money,
    smm_from_cpr,
)
from app.services.seasoning import age_at_cutoff, curve_age


def project_loan_cashflows(
    loan: Loan,
    scenario: Scenario,
    months: int = 360,
) -> list[CashflowRow]:
    """Project months 1..N with competing scheduled / default / prepay.

    Timing convention (static minimum case):
    1. Beginning UPB
    2. Interest on beginning UPB
    3. Scheduled principal (level amort; IO until remaining_io exhausted)
    4. Default = MDR × beginning UPB (capped)
    5. Prepay = SMM × max(0, begin − sched − default)
    6. Recovery of defaulted principal at scenario.recovery_rate, starting
       after recovery_lag_months, spread evenly over recovery_period_months

    PSA/SDA seasoning: curve age for projection month ``k`` is
    ``age_at_cutoff + k`` (from ``loan_age_months`` or origination→cutoff),
    never projection month alone (which would force every loan to t=1).

    TODO: state-level foreclosure/REO lag — not applied (pool constants only).
    """
    bal = float(loan.current_balance)
    rate = float(loan.annual_rate)
    rem_term = int(loan.remaining_term_months)
    age0 = age_at_cutoff(
        loan_age_months=int(loan.loan_age_months),
        origination_date=loan.origination_date,
        cutoff_date=loan.cutoff_date,
    )
    io_left = int(loan.remaining_io_months or 0)
    payment = loan.monthly_payment
    if payment is None or payment <= 0:
        amort_n = max(rem_term - io_left, 1)
        payment = level_payment(bal, rate, amort_n)

    psa = float(scenario.psa_multiple)
    sda = float(scenario.sda_multiple)
    lag = int(scenario.recovery_lag_months)
    period = max(int(scenario.recovery_period_months), 1)
    rec_rate = float(scenario.recovery_rate)

    pending: dict[int, float] = defaultdict(float)
    rows: list[CashflowRow] = []
    horizon = max(int(months), rem_term)

    for m in range(1, horizon + 1):
        age = curve_age(age0, m)
        if bal <= 0.005 and not any(pending[k] for k in range(m, m + lag + period + 1)):
            # Still emit remaining months with zeros if requested, else stop early
            if m > months:
                break
            recovery = round_money(pending.pop(m, 0.0))
            rows.append(
                CashflowRow(
                    month=m,
                    beginning_balance=0.0,
                    interest=0.0,
                    scheduled_principal=0.0,
                    default=0.0,
                    prepay=0.0,
                    recovery=recovery,
                    ending_balance=0.0,
                    loan_age=age,
                    cpr=0.0,
                    smm=0.0,
                    cdr=0.0,
                    mdr=0.0,
                )
            )
            if m >= months:
                break
            continue

        begin = bal
        months_left = max(rem_term - m + 1, 1)
        r_mo = rate / 12.0
        interest = begin * r_mo

        if io_left > 0:
            sched = 0.0
            io_left -= 1
            pmt = interest  # interest-only
        else:
            pmt = payment
            # Recompute level payment if still None-like edge
            if pmt <= interest and begin > 0 and months_left > 0:
                pmt = level_payment(begin, rate, months_left)
            sched = min(max(pmt - interest, 0.0), begin)

        # Index CPR/CDR by seasoned curve age — not by projection month alone.
        cpr = cpr_at_age(age, psa)
        cdr = cdr_at_age(age, sda)
        smm = smm_from_cpr(cpr)
        mdr = mdr_from_cdr(cdr)

        default = min(begin * mdr, max(begin - sched, 0.0))
        surviving = max(begin - sched - default, 0.0)
        prepay = min(surviving * smm, surviving)
        end = max(begin - sched - default - prepay, 0.0)

        if default > 0 and rec_rate > 0:
            chunk = (default * rec_rate) / period
            start = m + lag
            for k in range(period):
                pending[start + k] += chunk

        recovery = round_money(pending.pop(m, 0.0))
        bal = end

        rows.append(
            CashflowRow(
                month=m,
                beginning_balance=round_money(begin),
                interest=round_money(interest),
                scheduled_principal=round_money(sched),
                default=round_money(default),
                prepay=round_money(prepay),
                recovery=recovery,
                ending_balance=round_money(end),
                loan_age=age,
                cpr=round_money(cpr),
                smm=round_money(smm),
                cdr=round_money(cdr),
                mdr=round_money(mdr),
            )
        )
        if m >= months:
            break
        if end <= 0.005 and m >= months:
            break

    # Drain any recovery past horizon into last row if within requested months only
    return rows[:months]
