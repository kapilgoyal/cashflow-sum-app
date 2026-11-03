"""GFMI/SIFMA SDA default curve helpers (100% base × multiple)."""

from __future__ import annotations


def cdr_at_age(age_months: int, sda_multiple: float) -> float:
    """Annual CDR under n% SDA (GFMI ramp / peak / tail).

    ``age_months`` is seasoned curve age (age_at_cutoff + projection month),
    not the projection month index alone.
    """
    age = max(int(age_months), 1)
    if age <= 30:
        base = 0.0002 * age  # 0.02% × age → 0.60% at month 30
    elif age <= 60:
        base = 0.0060
    elif age <= 120:
        # Linear decline 0.60% → 0.03% from month 60 → 120
        base = 0.0060 + (0.0003 - 0.0060) * (age - 60) / (120 - 60)
    else:
        base = 0.0003
    return max(0.0, (sda_multiple / 100.0) * base)


def mdr_from_cdr(cdr: float) -> float:
    if cdr <= 0:
        return 0.0
    if cdr >= 1:
        return 1.0
    return 1.0 - (1.0 - cdr) ** (1.0 / 12.0)
