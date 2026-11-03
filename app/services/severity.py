"""Urban/Freddie loss-severity grid → recovery_rate = 1 − severity.

Source CSV: ``data/urban_freddie_loss_severity_fico_ltv.csv`` (Table 4).
Applied when ``has_mi`` is known True; otherwise caller uses cohort recovery.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.assumptions import (
    default_has_mi,
    resolve_data_path,
    severity_default_year_band,
    severity_grid_relpath,
)


def _normalize_ltv(ltv: float | None) -> str | None:
    """Map original_ltv (fraction or percent) → Urban band label."""
    if ltv is None:
        return None
    x = float(ltv)
    if x > 1.5:  # stored as percent e.g. 80
        x = x / 100.0
    if x <= 0.60:
        return "<=60"
    if x <= 0.80:
        return "60-80"
    return ">80"


def _normalize_fico(fico: float | int | None) -> str | None:
    if fico is None:
        return None
    s = float(fico)
    if s <= 700:
        return "<=700"
    if s <= 750:
        return "700-750"
    return ">750"


@lru_cache(maxsize=1)
def load_severity_grid(csv_path: str | None = None) -> list[dict[str, Any]]:
    rel = csv_path or severity_grid_relpath()
    path = resolve_data_path(rel) if not Path(rel).is_absolute() else Path(rel)
    if csv_path and Path(csv_path).is_absolute():
        path = Path(csv_path)
    elif csv_path:
        path = resolve_data_path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"severity grid CSV not found: {path}")
    with path.open(newline="", encoding="utf-8") as fh:
        lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    reader = csv.DictReader(lines)
    out: list[dict[str, Any]] = []
    for row in reader:
        sev = float(row["severity_pct"])
        rec = float(row["recovery_rate"])
        out.append(
            {
                "origination_year_band": row["origination_year_band"].strip(),
                "fico_band": row["fico_band"].strip(),
                "ltv_band": row["ltv_band"].strip(),
                "severity_pct": sev,
                "recovery_rate": rec,
                "source_url": (row.get("source_url") or "").strip(),
                "source_table": (row.get("source_table") or "").strip(),
                "notes": (row.get("notes") or "").strip(),
            }
        )
    if not out:
        raise ValueError(f"no severity rows in {path}")
    return out


@lru_cache(maxsize=1)
def _severity_index(
    csv_path: str | None = None,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    return {
        (r["origination_year_band"], r["fico_band"], r["ltv_band"]): r
        for r in load_severity_grid(csv_path)
    }


def lookup_severity_row(
    *,
    original_fico: float | int | None,
    original_ltv: float | None,
    year_band: str | None = None,
) -> dict[str, Any] | None:
    """Find Urban Table 4 cell; fall back FICO→Total then year→Total."""
    idx = _severity_index()
    year = (year_band or severity_default_year_band()).strip()
    ltv_b = _normalize_ltv(original_ltv)
    fico_b = _normalize_fico(original_fico)
    if ltv_b is None:
        return None

    candidates: list[tuple[str, str, str]] = []
    if fico_b:
        candidates.append((year, fico_b, ltv_b))
    candidates.append((year, "Total", ltv_b))
    if year != "Total":
        if fico_b:
            candidates.append(("Total", fico_b, ltv_b))
        candidates.append(("Total", "Total", ltv_b))

    for key in candidates:
        hit = idx.get(key)
        if hit is not None:
            return hit
    return None


def resolve_loan_recovery_rate(
    *,
    has_mi: bool | None,
    original_fico: float | int | None,
    original_ltv: float | None,
    cohort_recovery_rate: float,
    year_band: str | None = None,
) -> tuple[float, str]:
    """Return ``(recovery_rate, source_tag)``.

    - ``has_mi is True`` (or None with assumptions default True): try Urban grid
      ``recovery = 1 − severity``; if no cell, fall back to cohort rate.
    - ``has_mi is False``: cohort rate only.
    """
    mi = default_has_mi() if has_mi is None else bool(has_mi)
    if not mi:
        return float(cohort_recovery_rate), "cohort_fallback_no_mi"

    row = lookup_severity_row(
        original_fico=original_fico,
        original_ltv=original_ltv,
        year_band=year_band,
    )
    if row is None:
        return float(cohort_recovery_rate), "cohort_fallback_no_severity_cell"
    return float(row["recovery_rate"]), (
        f"urban_table4:{row['origination_year_band']}/"
        f"{row['fico_band']}/{row['ltv_band']}"
    )


def bootstrap_severity() -> dict[str, Any]:
    load_severity_grid.cache_clear()
    _severity_index.cache_clear()
    rows = load_severity_grid()
    return {
        "status": "ok",
        "path": severity_grid_relpath(),
        "n": len(rows),
        "default_year_band": severity_default_year_band(),
    }
