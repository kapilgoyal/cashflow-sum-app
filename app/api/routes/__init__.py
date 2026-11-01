"""Route modules: health, run-loan stub, scenario-grid, month-1 CF, QC."""

from fastapi import APIRouter

from app.api.routes import cashflows, health, qc, run_loan, scenarios

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(run_loan.router)
api_router.include_router(scenarios.router)
api_router.include_router(cashflows.router)
api_router.include_router(qc.router)

__all__ = ["api_router"]
