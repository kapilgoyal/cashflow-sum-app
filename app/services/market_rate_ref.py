"""Mortgage ref rate (Freddie Mac 30Y PMMS) — mirrors src/marketRateRef.js."""

from __future__ import annotations

from typing import Any

# Keep in sync with src/marketRateRef.js (RI benchmark baked into the tape).
MARKET_RATE_REF: dict[str, Any] = {
    "rate": 0.0686,
    "rate_pct": 6.86,
    "label": "30Y PMMS",
    "source": "Freddie Mac PMMS",
    "survey": "Primary Mortgage Market Survey 30-Year Fixed",
    "as_of": "Sep 2026",
    "as_of_iso": "2026-09",
    "caption": "Mortgage Ref Rate: Freddie Mac PMMS 30Y · As Of Sep 2026",
    "note": (
        "Used for refinance incentive (note − PMMS); not pool WAC. "
        "Same constant as Investor Tape / Loan Strats Mort Ref KPI."
    ),
}


def get_pmms_ref() -> dict[str, Any]:
    return dict(MARKET_RATE_REF)
