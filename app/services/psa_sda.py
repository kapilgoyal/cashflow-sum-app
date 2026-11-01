"""SIFMA PSA and GFMI/SIFMA SDA curve helpers (100% base × multiple)."""

from __future__ import annotations

import math


def cpr_at_age(age_months: int, psa_multiple: float) -> float:
    """Annual CPR under n% PSA. age_months is loan age at month-end (1+)."""
    age = max(int(age_months), 1)
    if age <= 30:
        base = 0.002 * age  # 0.2% × age → 6% at month 30
    else:
        base = 0.06
    return max(0.0, (psa_multiple / 100.0) * base)


def cdr_at_age(age_months: int, sda_multiple: float) -> float:
    """Annual CDR under n% SDA (GFMI ramp / peak / tail)."""
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


def smm_from_cpr(cpr: float) -> float:
    if cpr <= 0:
        return 0.0
    if cpr >= 1:
        return 1.0
    return 1.0 - (1.0 - cpr) ** (1.0 / 12.0)


def mdr_from_cdr(cdr: float) -> float:
    if cdr <= 0:
        return 0.0
    if cdr >= 1:
        return 1.0
    return 1.0 - (1.0 - cdr) ** (1.0 / 12.0)


def level_payment(balance: float, annual_rate: float, n_months: int) -> float:
    if n_months <= 0:
        return 0.0
    r = annual_rate / 12.0
    if r <= 0:
        return balance / n_months
    factor = (1.0 + r) ** n_months
    return balance * r * factor / (factor - 1.0)


def round_money(x: float) -> float:
    return float(f"{x:.8f}") if math.isfinite(x) else 0.0
