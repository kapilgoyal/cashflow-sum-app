"""Valuation: FRED Treasury curve + QuantLib NPV / Z-spread scenarios."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.services.fred_treasury import get_treasury_curve
from app.services.valuation import (
    DEFAULT_SERVICING_BP,
    DEFAULT_Z_SPREAD_BP,
    build_valuation,
)

router = APIRouter(prefix="/api/valuation", tags=["valuation"])


@router.get("/treasury")
def treasury_curve(
    refresh: bool = Query(False, description="Force re-download from FRED"),
) -> dict:
    try:
        return get_treasury_curve(force=refresh)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("")
def valuation(
    servicing_bp: float = Query(
        DEFAULT_SERVICING_BP, ge=0, le=500, description="Servicing fee in bp"
    ),
    z_spread_bp: float = Query(
        DEFAULT_Z_SPREAD_BP, ge=-500, le=2000, description="Base Z-spread in bp"
    ),
    refresh_fred: bool = Query(False, description="Force FRED curve refresh"),
) -> dict:
    try:
        return build_valuation(
            servicing_bp=servicing_bp,
            z_spread_bp=z_spread_bp,
            refresh_fred=refresh_fred,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
