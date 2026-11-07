"""Portfolio Manager Investor Analysis API (read-only)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.repositories.env_load import load_dotenv
from app.services.investor_analysis import analyze_investor

router = APIRouter(prefix="/api/asf", tags=["investor-analysis"])


@router.get("/investor-analysis")
def investor_analysis(
    cohort: str | None = Query(
        default=None,
        description="K-proto cohort name, or 'all'. Excel short labels are not accepted.",
    ),
) -> dict:
    """UPB-weighted PM summary. Unavailable sections are flagged — no invented PD."""
    load_dotenv()
    try:
        cohorts = None
        if cohort and cohort.strip().lower() not in ("", "all", "*"):
            cohorts = [c.strip() for c in cohort.split("|") if c.strip()]
        return analyze_investor(cohorts=cohorts)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
