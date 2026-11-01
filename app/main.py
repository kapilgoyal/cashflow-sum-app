"""FastAPI securitization cash-flow engine (SOLID scaffold)."""

from __future__ import annotations

from fastapi import FastAPI

from app import __version__
from app.api.routes import api_router

app = FastAPI(
    title="CashFlow Securitization Engine",
    version=__version__,
    description=(
        "PSA/SDA securitization CF scaffold. "
        "POST /api/run-loan is a schema stub (no engine run). "
        "Recovery uses constant lag; state-varying lag is TODO."
    ),
)
app.include_router(api_router)
