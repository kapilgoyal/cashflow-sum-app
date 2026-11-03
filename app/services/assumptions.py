"""Load CashFlow modeling assumptions from ``data/assumptions.csv`` (not DB).

Bootstrap on app start / first access. Source of truth for has_mi, severity and
Fannie CSV paths, cohort recovery fallbacks, and PSA/SDA seasoning rules.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Any

ASSUMPTIONS_CSV_NAME = "assumptions.csv"

# Hard defaults if CSV missing a row (keep engine bootable).
_FALLBACK_HAS_MI = True
_FALLBACK_SEVERITY_CSV = "data/urban_freddie_loss_severity_fico_ltv.csv"
_FALLBACK_FANNIE_CSV = "data/fannie_mae_foreclosure_timeframes.csv"
_FALLBACK_SEVERITY_YEAR = "2006"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def assumptions_csv_path() -> Path:
    return _repo_root() / "data" / ASSUMPTIONS_CSV_NAME


@lru_cache(maxsize=1)
def load_assumptions(csv_path: str | None = None) -> list[dict[str, str]]:
    """Return assumption rows as dicts (comment lines skipped)."""
    path = Path(csv_path) if csv_path else assumptions_csv_path()
    if not path.exists():
        raise FileNotFoundError(f"assumptions CSV not found: {path}")
    with path.open(newline="", encoding="utf-8") as fh:
        rows = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    reader = csv.DictReader(rows)
    out: list[dict[str, str]] = []
    for row in reader:
        cleaned = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
        if cleaned.get("assumption_id"):
            out.append(cleaned)
    if not out:
        raise ValueError(f"no assumptions loaded from {path}")
    return out


@lru_cache(maxsize=1)
def assumptions_by_id(csv_path: str | None = None) -> dict[str, dict[str, str]]:
    return {r["assumption_id"]: r for r in load_assumptions(csv_path)}


def get_assumption(assumption_id: str, default: str | None = None) -> str | None:
    row = assumptions_by_id().get(assumption_id)
    if not row:
        return default
    return row.get("value", default)


def default_has_mi() -> bool:
    """Synthetic tape: every loan has MI (from assumptions CSV)."""
    raw = (get_assumption("has_mi_all", str(_FALLBACK_HAS_MI)) or "").strip().lower()
    return raw in {"1", "true", "yes", "y", "t"}


def severity_grid_relpath() -> str:
    return get_assumption("severity_grid_path", _FALLBACK_SEVERITY_CSV) or _FALLBACK_SEVERITY_CSV


def fannie_lag_relpath() -> str:
    return (
        get_assumption("fannie_state_lag_path", _FALLBACK_FANNIE_CSV)
        or _FALLBACK_FANNIE_CSV
    )


def severity_default_year_band() -> str:
    return (
        get_assumption("severity_default_year_band", _FALLBACK_SEVERITY_YEAR)
        or _FALLBACK_SEVERITY_YEAR
    )


def resolve_data_path(relpath: str) -> Path:
    """Resolve a repo-relative ``data/...`` path."""
    p = Path(relpath)
    if p.is_absolute():
        return p
    return _repo_root() / p


def bootstrap_assumptions() -> dict[str, Any]:
    """Eager-load assumptions (+ clear caches if reloading). Return summary."""
    load_assumptions.cache_clear()
    assumptions_by_id.cache_clear()
    rows = load_assumptions()
    return {
        "status": "ok",
        "path": str(assumptions_csv_path()),
        "n": len(rows),
        "has_mi_all": default_has_mi(),
        "severity_grid_path": severity_grid_relpath(),
        "fannie_state_lag_path": fannie_lag_relpath(),
        "severity_year_band_default": severity_default_year_band(),
    }


def assumptions_payload() -> dict[str, Any]:
    """API payload for the Assumptions AG Grid."""
    rows = load_assumptions()
    return {
        "n": len(rows),
        "source": "data/assumptions.csv",
        "bootstrap": {
            "has_mi_all": default_has_mi(),
            "severity_grid_path": severity_grid_relpath(),
            "fannie_state_lag_path": fannie_lag_relpath(),
            "severity_year_band_default": severity_default_year_band(),
        },
        "assumptions": rows,
    }
