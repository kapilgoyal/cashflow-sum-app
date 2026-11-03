"""Route modules: health, run-loan stub, scenario-grid, month-1 CF, Neon, ASF, QC, assumptions."""

from fastapi import APIRouter

from app.api.routes import (
    asf_tape,
    assumptions,
    cashflows,
    health,
    neon_data,
    qc,
    run_loan,
    scenarios,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(run_loan.router)
api_router.include_router(scenarios.router)
api_router.include_router(cashflows.router)
api_router.include_router(neon_data.router)
api_router.include_router(asf_tape.router)
api_router.include_router(qc.router)
api_router.include_router(assumptions.router)

__all__ = ["api_router"]
