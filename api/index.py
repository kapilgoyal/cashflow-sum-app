"""Vercel Python entry — mount FastAPI via Mangum so /api/* stops 404ing."""

from __future__ import annotations

from mangum import Mangum

from app.main import app
from app.repositories.env_load import load_dotenv

load_dotenv()

# lifespan off: Vercel cold starts should not block on startup/shutdown hooks
handler = Mangum(app, lifespan="off")
