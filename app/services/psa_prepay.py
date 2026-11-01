"""SIFMA PSA prepay curve helpers (100% base × multiple)."""

from __future__ import annotations


def cpr_at_age(age_months: int, psa_multiple: float) -> float:
    """Annual CPR under n% PSA. age_months is loan age at month-end (1+)."""
    age = max(int(age_months), 1)
    if age <= 30:
        base = 0.002 * age  # 0.2% × age → 6% at month 30
    else:
        base = 0.06
    return max(0.0, (psa_multiple / 100.0) * base)


def smm_from_cpr(cpr: float) -> float:
    if cpr <= 0:
        return 0.0
    if cpr >= 1:
        return 1.0
    return 1.0 - (1.0 - cpr) ** (1.0 / 12.0)
