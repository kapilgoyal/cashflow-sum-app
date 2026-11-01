"""Load gitignored .env / .env.local into os.environ (no secret logging)."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(overwrite: bool = False) -> list[str]:
    """Load KEY=VALUE from .env.local then .env. Returns keys loaded."""
    loaded: list[str] = []
    for name in (".env.local", ".env"):
        path = REPO_ROOT / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if not key:
                continue
            if not overwrite and key in os.environ:
                continue
            os.environ[key] = val.strip().strip('"').strip("'")
            loaded.append(key)
    return loaded


def resolve_pg_url() -> str | None:
    """Prefer UNPOOLED for bulk writes; fall back to pooled DATABASE_URL."""
    return (
        os.environ.get("DATABASE_URL_UNPOOLED")
        or os.environ.get("POSTGRES_URL_NON_POOLING")
        or os.environ.get("DATABASE_URL")
        or os.environ.get("NEON_DATABASE_URL")
    )
