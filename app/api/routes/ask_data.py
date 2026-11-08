"""Ask Your Data API — Groq + real read tools (no prod mutations)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.ask_data import ask
from app.services.qc_nl_translate import groq_api_key

router = APIRouter(prefix="/api/ask-data", tags=["ask-data"])


class AskBody(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    history: list[dict[str, Any]] | None = None
    session: dict[str, Any] | None = None


@router.get("/status")
def ask_status() -> dict:
    return {
        "ok": True,
        "groq_configured": bool(groq_api_key()),
        "tools": [
            "get_mortgage_ref_rate",
            "get_tape_summary",
            "get_valuation_kpis",
            "whatif_z_spread",
            "get_qc_rule_counts",
            "get_scenario_grid_status",
        ],
    }


@router.post("/ask")
def ask_question(body: AskBody) -> dict:
    return ask(body.question, history=body.history, session=body.session)
