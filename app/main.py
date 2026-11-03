"""FastAPI securitization cash-flow engine."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import api_router
from app.repositories.env_load import load_dotenv
from app.services.assumptions import bootstrap_assumptions
from app.services.severity import bootstrap_severity

load_dotenv()


def _bootstrap_csvs() -> None:
    """Load assumption + severity CSVs from data/ (source of truth; not DB)."""
    bootstrap_assumptions()
    bootstrap_severity()


# Eager bootstrap for Vercel/Mangum (lifespan="off") and local uvicorn.
_bootstrap_csvs()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _bootstrap_csvs()
    yield


app = FastAPI(
    title="CashFlow Securitization Engine",
    version=__version__,
    lifespan=lifespan,
    description=(
        "PSA/SDA securitization CF. "
        "POST /api/cashflows/run-month1 runs 27 cohort×PCA×STA workers (month 1). "
        "GET /api/neon/* reads normalized Neon tables + enriched views. "
        "GET /api/assumptions reads data/assumptions.csv (has_mi, severity path, "
        "Fannie lag path, cohort recovery, PSA/SDA seasoning). "
        "Recovery rate = 1 − Urban/Freddie severity when has_mi; else cohort rate."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)
