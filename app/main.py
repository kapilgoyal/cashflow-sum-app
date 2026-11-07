"""FastAPI securitization cash-flow engine."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import api_router
from app.repositories.bootstrap import bootstrap_database, bootstrap_status_log_line
from app.repositories.env_load import load_dotenv
from app.services.assumptions import bootstrap_assumptions
from app.services.severity import bootstrap_severity

load_dotenv()
_log = logging.getLogger("uvicorn.error")


def _bootstrap_csvs() -> None:
    """Load assumption + severity CSVs from data/ (source of truth; not DB)."""
    bootstrap_assumptions()
    bootstrap_severity()


def _bootstrap_db() -> None:
    status = bootstrap_database()
    _log.info(bootstrap_status_log_line(status))


# Eager bootstrap for always-on uvicorn (Railway) and local dev.
_bootstrap_csvs()
_bootstrap_db()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _bootstrap_csvs()
    _bootstrap_db()
    yield


app = FastAPI(
    title="CashFlow Securitization Engine",
    version=__version__,
    lifespan=lifespan,
    description=(
        "PSA/SDA securitization CF. "
        "POST /api/cashflows/run-month1 runs 27 cohort×PCA×STA workers (month 1). "
        "GET /api/neon/* reads normalized tables + enriched views "
        "(SQLite by default; Postgres/Neon when DATABASE_URL is postgres). "
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
