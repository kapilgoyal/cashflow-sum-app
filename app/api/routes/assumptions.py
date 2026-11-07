"""Assumptions catalog from ``data/assumptions.csv`` (not Neon)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services.assumptions import assumptions_payload, bootstrap_assumptions
from app.services.cohort_labels import relabel_payload
from app.services.severity import bootstrap_severity

router = APIRouter(prefix="/api/assumptions", tags=["assumptions"])


@router.get("")
def list_assumptions() -> dict:
    try:
        return relabel_payload(assumptions_payload())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/reload")
def reload_assumptions() -> dict:
    """Re-read CSVs from disk (dev / after editing assumptions)."""
    try:
        boot = bootstrap_assumptions()
        sev = bootstrap_severity()
        return relabel_payload(
            {"assumptions": boot, "severity": sev, **assumptions_payload()}
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
