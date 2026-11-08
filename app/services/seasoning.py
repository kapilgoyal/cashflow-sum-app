"""PSA/SDA curve seasoning: index by loan age, not projection month alone.

Standard convention used by this engine
---------------------------------------
At cutoff, the loan has seasoning ``age_at_cutoff`` (tape ``loan_age_months``,
or months from ``origination_date`` to ``cutoff_date`` when age is absent).

Projection month ``k`` (1 = first month after cutoff) looks up PSA CPR / SDA CDR
at curve age::

    curve_age = age_at_cutoff + k

Example (100% PSA): ``loan_age_months=24`` → month 1 uses age 25 →
CPR = 0.2% × 25 = 5.0% (not the unseasoned t=1 CPR of 0.2%).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def as_date(value: Any) -> date | None:
    if value is None or value is False:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        # ISO first; tolerate date-only timestamps
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    # Excel serial (days since 1899-12-30)
    if isinstance(value, (int, float)):
        try:
            from datetime import timedelta

            return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()
        except (OverflowError, ValueError):
            return None
    # pandas Timestamp duck-type
    to_pydatetime = getattr(value, "to_pydatetime", None)
    if callable(to_pydatetime):
        try:
            return to_pydatetime().date()
        except Exception:  # noqa: BLE001
            return None
    return None


def months_since_origination(origination: Any, as_of: Any) -> int | None:
    """Whole months from origination to as-of (cutoff / projection)."""
    start = as_date(origination)
    end = as_date(as_of)
    if start is None or end is None:
        return None
    return (end.year - start.year) * 12 + (end.month - start.month)


def age_at_cutoff(
    *,
    loan_age_months: int | None = None,
    origination_date: Any = None,
    cutoff_date: Any = None,
) -> int:
    """Seasoning at cutoff: prefer tape ``loan_age_months``, else origination span.

    ``loan_age_months is None`` or ``0`` with usable orig→cutoff dates falls
    back to the date span (CF-178: tape zeros were blocking seasoning).
    Explicit positive ages win. Age 0 with no dates stays 0 (true unseasoned).
    """
    derived = months_since_origination(origination_date, cutoff_date)
    if loan_age_months is None:
        return max(0, int(derived)) if derived is not None else 0
    age = max(0, int(loan_age_months))
    # Sentinel / missing zero on tape: prefer derived seasoning when dates exist.
    if age == 0 and derived is not None and derived > 0:
        return max(0, int(derived))
    return age


def curve_age(age_at_cutoff_months: int, projection_month: int) -> int:
    """PSA/SDA curve month for projection month ``k``: ``age_at_cutoff + k``."""
    k = int(projection_month)
    if k < 1:
        raise ValueError(f"projection_month must be >= 1, got {projection_month}")
    return max(0, int(age_at_cutoff_months)) + k
