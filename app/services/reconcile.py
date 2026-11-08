"""Monthly and life reconciliation identities for engine cash-flow rows."""

from __future__ import annotations

from typing import Any, Iterable

from app.models.cash_flow import CashFlowRow
from app.services.psa_sda import round_money

# Tolerances for money identities (engine stores ~8 dp).
MONEY_TOL = 0.02


def month_identity_errors(row: CashFlowRow) -> list[str]:
    """Return human-readable breaches of within-month identities."""
    errs: list[str] = []
    begin = float(row.beginning_balance)
    end = float(row.ending_balance)
    sched = float(row.scheduled_principal)
    prepay = float(row.prepay)
    new_def = float(row.new_default)
    interest = float(row.interest)
    recovery = float(row.recovery)
    total = float(row.total_cash)

    bal_end = begin - sched - new_def - prepay
    if abs(bal_end - end) > MONEY_TOL:
        errs.append(
            f"m{row.month} UPB: begin-sched-default-prepay={bal_end:.8f} "
            f"!= ending={end:.8f}"
        )

    cash = interest + sched + prepay + recovery
    if abs(cash - total) > MONEY_TOL:
        errs.append(
            f"m{row.month} cash: I+SP+PP+Rec={cash:.8f} != total_cash={total:.8f}"
        )

    if new_def < -MONEY_TOL or prepay < -MONEY_TOL or sched < -MONEY_TOL:
        errs.append(f"m{row.month} negative principal component")

    if sched + new_def + prepay - begin > MONEY_TOL:
        errs.append(f"m{row.month} principal uses exceed begin UPB")

    return errs


def life_identity_errors(
    rows: Iterable[CashFlowRow],
    *,
    starting_balance: float | None = None,
) -> list[str]:
    """Life identities across a projected path.

    1. Chain: each month begin ≈ prior end (performing UPB).
    2. Cum principal: sum(sched+prepay+new_default) ≈ start − final_end
       (defaults leave performing UPB; they are included as balance reduction).
    3. Cum cash: sum(total_cash) == sum(I+SP+PP+Rec) per month (already monthly).
    """
    seq = list(rows)
    errs: list[str] = []
    if not seq:
        return ["empty path"]

    if starting_balance is None:
        starting_balance = float(seq[0].beginning_balance)

    prev_end = float(starting_balance)
    sum_prin = 0.0
    sum_cash = 0.0
    sum_cash_parts = 0.0

    for i, row in enumerate(seq):
        errs.extend(month_identity_errors(row))
        begin = float(row.beginning_balance)
        if i == 0:
            if abs(begin - float(starting_balance)) > MONEY_TOL:
                errs.append(
                    f"start UPB {starting_balance:.8f} != m1 begin {begin:.8f}"
                )
        elif abs(begin - prev_end) > MONEY_TOL:
            errs.append(
                f"m{row.month} begin {begin:.8f} != prior end {prev_end:.8f}"
            )
        sum_prin += (
            float(row.scheduled_principal)
            + float(row.prepay)
            + float(row.new_default)
        )
        sum_cash += float(row.total_cash)
        sum_cash_parts += (
            float(row.interest)
            + float(row.scheduled_principal)
            + float(row.prepay)
            + float(row.recovery)
        )
        prev_end = float(row.ending_balance)

    final_end = float(seq[-1].ending_balance)
    expected_prin = float(starting_balance) - final_end
    if abs(sum_prin - expected_prin) > MONEY_TOL:
        errs.append(
            f"life principal: sum(sched+prepay+default)={sum_prin:.8f} "
            f"!= start-end={expected_prin:.8f}"
        )
    if abs(sum_cash - sum_cash_parts) > MONEY_TOL:
        errs.append(
            f"life cash: sum(total)={sum_cash:.8f} != sum(parts)={sum_cash_parts:.8f}"
        )
    return errs


def assert_path_reconciles(
    rows: list[CashFlowRow],
    *,
    starting_balance: float | None = None,
) -> dict[str, Any]:
    errs = life_identity_errors(rows, starting_balance=starting_balance)
    if errs:
        raise AssertionError("; ".join(errs[:8]) + (f" (+{len(errs)-8} more)" if len(errs) > 8 else ""))
    start = float(starting_balance if starting_balance is not None else rows[0].beginning_balance)
    return {
        "ok": True,
        "months": len(rows),
        "starting_balance": round_money(start),
        "ending_balance": round_money(float(rows[-1].ending_balance)),
        "sum_total_cash": round_money(sum(float(r.total_cash) for r in rows)),
    }
