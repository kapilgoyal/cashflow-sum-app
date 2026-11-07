"""Loan-level collateral research API (read-only; no cohort reassignment)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.repositories.env_load import load_dotenv
from app.services.collateral_analysis import (
    FIELD_INVENTORY,
    SECTION_REFS,
    analyze,
    load_enriched_loans,
)

router = APIRouter(prefix="/api/asf", tags=["collateral"])


@router.get("/collateral")
def collateral_analysis(
    cohort: str | None = Query(
        default=None,
        description="K-proto cohort name, or 'all'. Excel short labels are not accepted.",
    ),
    ltv_mode: str = Query(default="original", pattern="^(original|current)$"),
    fico_band: str | None = Query(default=None),
    ltv_band: str | None = Query(default=None),
    state: str | None = Query(default=None),
    documentation_type: str | None = Query(default=None),
    occupancy: str | None = Query(default=None),
    loan_purpose: str | None = Query(default=None),
    property_type: str | None = Query(default=None),
    risk_only: bool = Query(default=False),
    include_loans: bool = Query(default=True),
) -> dict:
    """UPB-weighted collateral research payload for the Loan-Level dashboard."""
    load_dotenv()
    try:
        loans, source = load_enriched_loans()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    cohorts = None
    if cohort and cohort.strip().lower() not in ("", "all", "*"):
        cohorts = [cohort.strip()]

    def _split(v: str | None) -> list[str] | None:
        if not v:
            return None
        parts = [p.strip() for p in v.split("|") if p.strip()]
        return parts or None

    payload = analyze(
        loans,
        ltv_mode=ltv_mode,
        cohorts=cohorts,
        fico_bands=_split(fico_band),
        ltv_bands=_split(ltv_band),
        states=_split(state),
        documentation_types=_split(documentation_type),
        occupancies=_split(occupancy),
        purposes=_split(loan_purpose),
        property_types=_split(property_type),
        risk_only=risk_only,
    )
    if not include_loans:
        payload = {**payload, "loans": []}
    payload["source"] = source
    payload["field_inventory"] = FIELD_INVENTORY
    payload["section_refs"] = SECTION_REFS
    return payload


@router.get("/collateral/inventory")
def collateral_inventory() -> dict:
    """Tape field availability for collateral research (no loan rows)."""
    return {
        "field_inventory": FIELD_INVENTORY,
        "section_refs": SECTION_REFS,
    }
