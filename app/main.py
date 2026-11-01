"""FastAPI securitization cash-flow engine."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import api_router
from app.repositories.env_load import load_dotenv

load_dotenv()

app = FastAPI(
    title="CashFlow Securitization Engine",
    version=__version__,
    description=(
        "PSA/SDA securitization CF. "
        "POST /api/cashflows/run-month1 runs 27 cohort×PCA×STA workers (month 1). "
        "GET /api/neon/* reads normalized Neon tables + enriched views. "
        "Recovery uses constant lag; state-varying lag is TODO."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)
