"""Deterministic one-loan cash flows under PSA prepays + SDA defaults.

Three-panel row semantics (see docs/cf-panel-refs/):
1. Performing UPB — Beg/Interest/Sched/CPR/CDR/Prepay/New Default/End
2. Default roll — Beg Def / New / Liquidated (after lag) / Recovery / Loss / End Def
3. Actual cash — Interest + Sched + Prepay + Recovery (= Total Cash); defaults ≠ cash

Recovery rate stays cohort (60/55/75). Liquidation lag from Fannie Mae state
time frames when loan.state is known.
"""

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
from app.services.recovery import resolve_recovery_lag_months


def project_loan_cashflows(
    loan: Loan,
    scenario: Scenario,
    months: int = 360,
) -> list[CashflowRow]:
    """Project months 1..N with competing scheduled / default / prepay.

    Timing:
    1. Beginning UPB / beginning default inventory
    2. Interest on beginning UPB
    3. Scheduled principal (level amort; IO until remaining_io exhausted)
    4. New default = MDR × beginning UPB (capped)
    5. Prepay = SMM × max(0, begin − sched − new_default)
    6. Liquidate aged default inventory after used_recovery_lag_months,
       spread evenly over recovery_period_months; recovery = liq × rate;
       realized loss = liq × (1 − rate). Defaults themselves are not cash.
    """
    bal = float(loan.current_balance)
    rate = float(loan.annual_rate)
    rem_term = int(loan.remaining_term_months)
    age0 = int(loan.loan_age_months)
    io_left = int(loan.remaining_io_months or 0)
    payment = loan.monthly_payment
    if payment is None or payment <= 0:
        amort_n = max(rem_term - io_left, 1)
        payment = level_payment(bal, rate, amort_n)

    psa = float(scenario.psa_multiple)
    sda = float(scenario.sda_multiple)
    lag = resolve_recovery_lag_months(
        loan.state,
        scenario_lag_months=int(scenario.recovery_lag_months),
    )
    period = max(int(scenario.recovery_period_months), 1)
    rec_rate = float(scenario.recovery_rate)

    # month → face amount of default inventory liquidating that month
    pending_liq: dict[int, float] = defaultdict(float)
    default_bal = 0.0
    rows: list[CashflowRow] = []
    horizon = max(int(months), rem_term)

    for m in range(1, horizon + 1):
        still_pending = any(
            pending_liq[k] for k in range(m, m + lag + period + 1)
        )
        if bal <= 0.005 and default_bal <= 0.005 and not still_pending:
            if m > months:
                break
            liquidated = pending_liq.pop(m, 0.0)
            recovery = round_money(liquidated * rec_rate)
            loss = round_money(liquidated * (1.0 - rec_rate))
            end_def = max(default_bal + 0.0 - liquidated, 0.0)
            rows.append(
                CashflowRow(
                    month=m,
                    beginning_balance=0.0,
                    interest=0.0,
                    scheduled_principal=0.0,
                    cpr=0.0,
                    cdr=0.0,
                    prepay=0.0,
                    new_default=0.0,
                    default=0.0,
                    ending_balance=0.0,
                    beginning_default_balance=round_money(default_bal),
                    liquidated_default=round_money(liquidated),
                    recovery=recovery,
                    realized_loss=loss,
                    ending_default_balance=round_money(end_def),
                    total_cash=recovery,
                    loan_age=age0 + m,
                    smm=0.0,
                    mdr=0.0,
                    used_recovery_lag_months=lag,
                    recovery_rate=rec_rate,
                )
            )
            default_bal = end_def
            if m >= months:
                break
            continue

        begin = bal
        begin_def = default_bal
        age = age0 + m
        months_left = max(rem_term - m + 1, 1)
        r_mo = rate / 12.0
        interest = begin * r_mo

        if io_left > 0:
            sched = 0.0
            io_left -= 1
        else:
            pmt = payment
            if pmt <= interest and begin > 0 and months_left > 0:
                pmt = level_payment(begin, rate, months_left)
            sched = min(max(pmt - interest, 0.0), begin)

        cpr = cpr_at_age(age, psa)
        cdr = cdr_at_age(age, sda)
        smm = smm_from_cpr(cpr)
        mdr = mdr_from_cdr(cdr)

        new_default = min(begin * mdr, max(begin - sched, 0.0))
        surviving = max(begin - sched - new_default, 0.0)
        prepay = min(surviving * smm, surviving)
        end = max(begin - sched - new_default - prepay, 0.0)

        if new_default > 0:
            chunk = new_default / period
            start = m + lag
            for k in range(period):
                pending_liq[start + k] += chunk

        liquidated = pending_liq.pop(m, 0.0)
        recovery = liquidated * rec_rate
        realized_loss = liquidated * (1.0 - rec_rate)
        end_def = max(begin_def + new_default - liquidated, 0.0)

        interest_r = round_money(interest)
        sched_r = round_money(sched)
        prepay_r = round_money(prepay)
        recovery_r = round_money(recovery)
        total_cash = round_money(interest_r + sched_r + prepay_r + recovery_r)

        rows.append(
            CashflowRow(
                month=m,
                beginning_balance=round_money(begin),
                interest=interest_r,
                scheduled_principal=sched_r,
                cpr=round_money(cpr),
                cdr=round_money(cdr),
                prepay=prepay_r,
                new_default=round_money(new_default),
                default=round_money(new_default),
                ending_balance=round_money(end),
                beginning_default_balance=round_money(begin_def),
                liquidated_default=round_money(liquidated),
                recovery=recovery_r,
                realized_loss=round_money(realized_loss),
                ending_default_balance=round_money(end_def),
                total_cash=total_cash,
                loan_age=age,
                smm=round_money(smm),
                mdr=round_money(mdr),
                used_recovery_lag_months=lag,
                recovery_rate=rec_rate,
            )
        )
        bal = end
        default_bal = end_def
        if m >= months:
            break
        if end <= 0.005 and m >= months:
            break

    return rows[:months]
