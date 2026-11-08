"""Deterministic one-loan cash flows under PSA prepays + SDA defaults.

Three-panel row semantics (see docs/cf-panel-refs/):
1. Performing UPB — Beg/Interest/Sched/CPR/CDR/Prepay/New Default/End
2. Default roll — Beg Def / New / Liquidated (after lag) / Recovery / Loss / End Def
3. Actual cash — Interest + Sched + Prepay + Recovery (= Total Cash); defaults ≠ cash

=============================================================================
Monthly order of operations (CF-175)
=============================================================================
For projection month ``k`` on performing UPB ``B``:

1. Beginning UPB / beginning default inventory
2. Interest on beginning UPB: ``I = B × r/12``
3. **Contractual scheduled principal** (not survival-weighted twice):
   - IO months: ``Sched = 0`` (interest only)
   - Amortizing months: fractional contractual amort on *current* performing
     balance with remaining term ``n``::

         Sched = B × (r/12) / ((1 + r/12)^n − 1)

     Equivalent to survival-weighting a contractual schedule: prepays/defaults
     shrink ``B``, and Sched scales with ``B`` — they do **not** accelerate a
     fixed dollar payment (that bug produced ~63382 vs ~68292.97 on the
     reference case).
   - Final remaining-term month: balloon/maturity — ``Sched = B`` (after
     interest); no voluntary prepay/default on that residual.
4. New default = ``MDR × B``, capped so ``Sched + NewDefault ≤ B``
5. Prepay = ``SMM × max(0, B − Sched − NewDefault)``
6. Ending UPB = ``B − Sched − NewDefault − Prepay``
7. Liquidate aged default inventory after used_recovery_lag_months, spread
   evenly over recovery_period_months; recovery = liq × rate
   (Urban grid when has_mi; else cohort); realized loss = liq × (1 − rate).
   Defaults themselves are not cash.

PSA/SDA seasoning: curve age for projection month ``k`` is
``age_at_cutoff + k`` (from ``loan_age_months`` or origination→cutoff),
never projection month alone.
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
from app.services.seasoning import age_at_cutoff, curve_age
from app.services.severity import resolve_loan_recovery_rate

# Bump when projection math or cache-relevant semantics change (CF-175+).
ENGINE_VERSION = "1.1.0-cf175"


class LoanEngineError(ValueError):
    """Invalid loan inputs or unsupported product features for this engine."""


def contractual_scheduled_principal(
    balance: float,
    annual_rate: float,
    remaining_term_months: int,
) -> float:
    """Contractual sched prin on ``balance`` for ``remaining_term_months`` left.

    Uses the closed-form level-payment identity::

        Sched = B × μ / ((1+μ)^n − 1),  μ = r/12

    so Sched scales with performing UPB (survival weighting) and does not
    accelerate a frozen dollar payment after prepays.
    """
    if balance <= 0 or remaining_term_months <= 0:
        return 0.0
    if remaining_term_months == 1:
        return float(balance)
    mu = float(annual_rate) / 12.0
    if mu <= 0:
        return float(balance) / float(remaining_term_months)
    denom = (1.0 + mu) ** int(remaining_term_months) - 1.0
    if denom <= 0:
        return float(balance)
    return float(balance) * mu / denom


def validate_loan_for_engine(loan: Loan, *, months: int = 360) -> None:
    """Raise ``LoanEngineError`` on bad inputs or unsupported ARM resets."""
    if loan.current_balance is None or float(loan.current_balance) <= 0:
        raise LoanEngineError("current_balance must be > 0")
    if float(loan.annual_rate) < 0:
        raise LoanEngineError("annual_rate must be >= 0")
    if int(loan.remaining_term_months) <= 0:
        raise LoanEngineError("remaining_term_months must be > 0")
    if int(loan.loan_age_months or 0) < 0:
        raise LoanEngineError("loan_age_months must be >= 0")
    if int(loan.remaining_io_months or 0) < 0:
        raise LoanEngineError("remaining_io_months must be >= 0")
    io = int(loan.remaining_io_months or 0)
    rem = int(loan.remaining_term_months)
    if io > rem:
        raise LoanEngineError(
            f"remaining_io_months ({io}) exceeds remaining_term_months ({rem})"
        )

    # ARM: engine is fixed-rate for the projection. Explicit unsupported when
    # a reset would fall inside the performing horizon.
    reset_freq = getattr(loan, "arm_reset_frequency_months", None)
    initial_fixed = getattr(loan, "arm_initial_fixed_months", None)
    arm_index = getattr(loan, "arm_index", None)
    is_arm = bool(arm_index) or (
        reset_freq is not None and int(reset_freq or 0) > 0
    )
    if not is_arm:
        return

    horizon = min(int(months), rem)
    # Months from origination until first reset after cutoff.
    age0 = age_at_cutoff(
        loan_age_months=int(loan.loan_age_months),
        origination_date=loan.origination_date,
        cutoff_date=loan.cutoff_date,
    )
    fixed_total = int(initial_fixed) if initial_fixed is not None else None
    freq = int(reset_freq) if reset_freq is not None else 0
    if fixed_total is not None and fixed_total >= 0:
        months_to_first_reset = fixed_total - age0
        if 1 <= months_to_first_reset <= horizon:
            raise LoanEngineError(
                "ARM rate reset during projection is unsupported "
                f"(first reset in projection month {months_to_first_reset}; "
                "engine is fixed-coupon only)"
            )
    elif freq > 0:
        # Unknown initial fixed — any positive reset frequency is unsupported.
        raise LoanEngineError(
            "ARM with reset frequency is unsupported "
            "(engine is fixed-coupon only; pass arm_initial_fixed_months "
            "past the horizon to project as fixed)"
        )


def project_loan_cashflows(
    loan: Loan,
    scenario: Scenario,
    months: int = 360,
    *,
    validate: bool = True,
) -> list[CashflowRow]:
    """Project months 1..N with competing scheduled / default / prepay.

    See module docstring for monthly order and contractual vs survival rules.
    """
    if validate:
        validate_loan_for_engine(loan, months=months)

    bal = float(loan.current_balance)
    rate = float(loan.annual_rate)
    rem_term = int(loan.remaining_term_months)
    age0 = age_at_cutoff(
        loan_age_months=int(loan.loan_age_months),
        origination_date=loan.origination_date,
        cutoff_date=loan.cutoff_date,
    )
    io_left = int(loan.remaining_io_months or 0)

    # IO → amort: capture level payment once at conversion (metadata / callers
    # that still pass monthly_payment). Projection Sched uses contractual
    # fractional amort, not this frozen dollar amount — so prepays cannot
    # accelerate amortization.
    payment = loan.monthly_payment
    amort_payment_set = False
    if io_left <= 0 and payment is not None and payment > 0:
        amort_payment_set = True
    elif io_left <= 0 and (payment is None or payment <= 0):
        payment = level_payment(bal, rate, max(rem_term, 1))
        amort_payment_set = True

    psa = float(scenario.psa_multiple)
    sda = float(scenario.sda_multiple)
    lag = resolve_recovery_lag_months(
        loan.state,
        scenario_lag_months=int(scenario.recovery_lag_months),
    )
    period = max(int(scenario.recovery_period_months), 1)
    rec_rate, _rec_src = resolve_loan_recovery_rate(
        has_mi=loan.has_mi,
        original_fico=loan.original_fico,
        original_ltv=loan.original_ltv,
        cohort_recovery_rate=float(scenario.recovery_rate),
    )

    pending_liq: dict[int, float] = defaultdict(float)
    default_bal = 0.0
    rows: list[CashflowRow] = []
    horizon = max(int(months), rem_term)

    for m in range(1, horizon + 1):
        age = curve_age(age0, m)
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
                    loan_age=age,
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
        months_left = max(rem_term - m + 1, 1)
        r_mo = rate / 12.0
        interest = begin * r_mo
        maturity_month = m >= rem_term

        if io_left > 0:
            sched = 0.0
            io_left -= 1
        elif maturity_month:
            # Balloon / maturity: contractual residual is the full begin UPB.
            sched = begin
        else:
            if not amort_payment_set:
                # IO→amort (or missing payment): lock level payment once from
                # first amortizing month's begin UPB + remaining term.
                payment = level_payment(begin, rate, months_left)
                amort_payment_set = True
            sched = min(
                contractual_scheduled_principal(begin, rate, months_left),
                begin,
            )

        cpr = cpr_at_age(age, psa)
        cdr = cdr_at_age(age, sda)
        smm = smm_from_cpr(cpr)
        mdr = mdr_from_cdr(cdr)

        if maturity_month:
            new_default = 0.0
            prepay = 0.0
            end = 0.0
        else:
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
