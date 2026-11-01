"""Back-compat facade: PSA/SDA helpers + payment utilities used by the engine.

Prefer importing from ``psa_prepay``, ``sda_default``, and ``recovery`` in new code.
"""

from __future__ import annotations

import math

from app.services.psa_prepay import cpr_at_age, smm_from_cpr
from app.services.sda_default import cdr_at_age, mdr_from_cdr

__all__ = [
    "cdr_at_age",
    "cpr_at_age",
    "level_payment",
    "mdr_from_cdr",
    "round_money",
    "smm_from_cpr",
]


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
