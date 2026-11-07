"""FastAPI securitization cash-flow engine."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.routes import api_router
from app.repositories.bootstrap import bootstrap_database, bootstrap_status_log_line
from app.repositories.env_load import load_dotenv
from app.services.assumptions import bootstrap_assumptions
from app.services.severity import bootstrap_severity

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist"
_log = logging.getLogger("uvicorn.error")

# Paths that must stay JSON 404s, not the SPA, when no API route matches.
_BACKEND_EXACT = frozenset(
    {"health", "docs", "redoc", "openapi.json", "scenarios"}
)
_BACKEND_PREFIXES = ("api/", "cashflows")

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
        "POST /api/run-loan (alias POST /api/cashflows/run-loan) projects one "
        "tape loan × scenario cell. "
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


def _is_backend_path(full_path: str) -> bool:
    p = full_path.lstrip("/")
    if not p:
        return False
    if p in _BACKEND_EXACT:
        return True
    return p == "api" or p.startswith(_BACKEND_PREFIXES)


def _mount_spa(application: FastAPI) -> None:
    """Serve the Vite build from FastAPI when dist/ is present (container image).

    Local ``uvicorn`` without ``npm run build`` is unchanged (Vite still proxies).
    """
    if not DIST_DIR.is_dir() or not (DIST_DIR / "index.html").is_file():
        return

    assets = DIST_DIR / "assets"
    if assets.is_dir():
        application.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @application.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if _is_backend_path(full_path):
            raise HTTPException(status_code=404, detail="Not Found")
        dist_root = DIST_DIR.resolve()
        candidate = (DIST_DIR / full_path).resolve()
        try:
            candidate.relative_to(dist_root)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Not Found") from exc
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(
            DIST_DIR / "index.html",
            headers={"Cache-Control": "no-cache"},
        )

    _log.info("Serving SPA from %s", DIST_DIR)


_mount_spa(app)
