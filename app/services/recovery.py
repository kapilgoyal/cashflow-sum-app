"""Recovery timing: constant pool lag for now; state-varying TODO."""

from __future__ import annotations

from collections.abc import Iterable


# Pool-level defaults until state tables exist.
DEFAULT_RECOVERY_LAG_MONTHS = 6
DEFAULT_RECOVERY_PERIOD_MONTHS = 6
DEFAULT_RECOVERY_RATE = 0.60

STATE_VARYING_TODO = (
    "TODO: state-varying foreclosure / REO lag and recovery timing — "
    "not implemented; use constant lag/period/rate only"
)


def schedule_recovery(
    default_principal: float,
    *,
    default_month: int,
    recovery_rate: float = DEFAULT_RECOVERY_RATE,
    recovery_lag_months: int = DEFAULT_RECOVERY_LAG_MONTHS,
    recovery_period_months: int = DEFAULT_RECOVERY_PERIOD_MONTHS,
    state: str | None = None,
) -> list[tuple[int, float]]:
    """Spread recovered principal over a constant lag + period.

    Returns list of (month_index, amount). ``state`` is accepted for the
    future state-varying path and currently ignored.
    """
    if state is not None:
        # Placeholder so callers can pass loan.state without a behavior change.
        _ = state  # noqa: F841 — reserved for state-varying lag tables
    if default_principal <= 0 or recovery_rate <= 0:
        return []
    period = max(int(recovery_period_months), 1)
    lag = max(int(recovery_lag_months), 0)
    chunk = (default_principal * recovery_rate) / period
    start = int(default_month) + lag
    return [(start + k, chunk) for k in range(period)]


def merge_recovery_schedule(
    pending: dict[int, float],
    chunks: Iterable[tuple[int, float]],
) -> dict[int, float]:
    """Accumulate scheduled recovery into a month→amount map."""
    for month, amount in chunks:
        pending[month] = pending.get(month, 0.0) + amount
    return pending
