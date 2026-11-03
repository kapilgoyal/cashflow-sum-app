"""Recovery timing: state foreclosure lag from Fannie Mae; cohort recovery rates."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

# Pool-level defaults when state is missing / unknown.
DEFAULT_RECOVERY_LAG_MONTHS = 6
DEFAULT_RECOVERY_PERIOD_MONTHS = 6
DEFAULT_RECOVERY_RATE = 0.60

FANNIE_TIMEFRAMES_SOURCE_URL = (
    "https://singlefamily.fanniemae.com/media/6726/display"
)
FANNIE_CSV_NAME = "fannie_mae_foreclosure_timeframes.csv"

# Alias codes → canonical CSV state_code (NYC is separate from NY in Fannie table).
_STATE_ALIASES: dict[str, str] = {
    "NEW YORK": "NY",
    "NEWYORK": "NY",
    "N.Y.": "NY",
    "NEW YORK CITY": "NYC",
    "NEWYORKCITY": "NYC",
    "DISTRICT OF COLUMBIA": "DC",
    "WASHINGTON DC": "DC",
    "WASHINGTON D.C.": "DC",
    "PUERTO RICO": "PR",
    "VIRGIN ISLANDS": "VI",
}


def _data_csv_path() -> Path:
    """Resolve committed timeframe CSV under repo ``data/``."""
    return Path(__file__).resolve().parents[2] / "data" / FANNIE_CSV_NAME


@lru_cache(maxsize=1)
def load_foreclosure_timeframes(
    csv_path: str | None = None,
) -> dict[str, dict[str, object]]:
    """Load Fannie Mae state time frames keyed by uppercase state_code.

    Each value: state_name, method_of_foreclosure, state_time_frame_days,
    recovery_lag_months (≈ days/30, rounded).
    """
    path = Path(csv_path) if csv_path else _data_csv_path()
    out: dict[str, dict[str, object]] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        # Skip leading # comment lines; DictReader still needs the header row.
        rows = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    reader = csv.DictReader(rows)
    for row in reader:
        code = (row.get("state_code") or "").strip().upper()
        if not code:
            continue
        days = int(float(row["state_time_frame_days"]))
        months = int(float(row["recovery_lag_months"]))
        out[code] = {
            "state_code": code,
            "state_name": (row.get("state_name") or "").strip(),
            "method_of_foreclosure": (row.get("method_of_foreclosure") or "").strip(),
            "state_time_frame_days": days,
            "recovery_lag_months": months,
        }
    if not out:
        raise ValueError(f"no foreclosure timeframes loaded from {path}")
    return out


def normalize_state_code(state: str | None) -> str | None:
    """Map loan.state / name to a Fannie CSV state_code, or None."""
    if state is None:
        return None
    raw = str(state).strip()
    if not raw:
        return None
    upper = raw.upper()
    table = load_foreclosure_timeframes()
    if upper in table:
        return upper
    compact = upper.replace(".", "").replace(",", " ")
    compact = " ".join(compact.split())
    if compact in _STATE_ALIASES:
        return _STATE_ALIASES[compact]
    nospace = compact.replace(" ", "")
    if nospace in _STATE_ALIASES:
        return _STATE_ALIASES[nospace]
    # Match by state name (case-insensitive).
    for code, meta in table.items():
        name = str(meta.get("state_name") or "").upper()
        if compact == name or nospace == name.replace(" ", ""):
            return code
    return None


def recovery_lag_months_for_state(
    state: str | None,
    *,
    fallback_months: int = DEFAULT_RECOVERY_LAG_MONTHS,
) -> int:
    """Return recovery lag months from Fannie state time frame (days/30).

    Unknown / missing state → ``fallback_months`` (default pool constant).
    """
    code = normalize_state_code(state)
    if code is None:
        return max(int(fallback_months), 0)
    meta = load_foreclosure_timeframes().get(code)
    if not meta:
        return max(int(fallback_months), 0)
    return max(int(meta["recovery_lag_months"]), 0)


def resolve_recovery_lag_months(
    state: str | None,
    *,
    scenario_lag_months: int | None = None,
) -> int:
    """Prefer state-based Fannie lag; else scenario lag; else module default."""
    code = normalize_state_code(state)
    if code is not None and code in load_foreclosure_timeframes():
        return recovery_lag_months_for_state(state)
    if scenario_lag_months is not None:
        return max(int(scenario_lag_months), 0)
    return DEFAULT_RECOVERY_LAG_MONTHS


def schedule_recovery(
    default_principal: float,
    *,
    default_month: int,
    recovery_rate: float = DEFAULT_RECOVERY_RATE,
    recovery_lag_months: int | None = None,
    recovery_period_months: int = DEFAULT_RECOVERY_PERIOD_MONTHS,
    state: str | None = None,
) -> list[tuple[int, float]]:
    """Spread recovered principal over lag + period.

    ``recovery_rate`` stays caller-supplied (cohort rates). Lag resolves from
    ``loan.state`` via Fannie Mae time frames when ``recovery_lag_months`` is
    omitted; an explicit lag wins over state lookup.
    """
    if recovery_lag_months is None:
        lag = resolve_recovery_lag_months(state)
    else:
        lag = max(int(recovery_lag_months), 0)
        # If lag explicitly passed as scenario default (0) but state known,
        # callers should use resolve_recovery_lag_months themselves.
    if default_principal <= 0 or recovery_rate <= 0:
        return []
    period = max(int(recovery_period_months), 1)
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
