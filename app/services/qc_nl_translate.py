"""Translate English Loan QC checks into asf_tape SQL predicates via Groq.

Requires GROQ_API_KEY. There is no heuristic mock fallback — missing key or
API failure returns ok=False with an error. Override model via GROQ_MODEL /
GROQ_MODEL_FALLBACKS in .env.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from app.repositories.env_load import load_dotenv
from app.services.qc_predicate import validate_predicate
from app.services.qc_tape_schema import schema_prompt_block

# Primary + fallbacks: llama-3.1-8b-instant was removed from many Groq accounts.
_DEFAULT_MODELS = (
    "openai/gpt-oss-20b",
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "qwen/qwen3-32b",
)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def _groq_models() -> list[str]:
    load_dotenv(overwrite=False)
    primary = (os.environ.get("GROQ_MODEL") or "").strip()
    extra = (os.environ.get("GROQ_MODEL_FALLBACKS") or "").strip()
    models: list[str] = []
    if primary:
        models.append(primary)
    if extra:
        models.extend(m.strip() for m in extra.split(",") if m.strip())
    for m in _DEFAULT_MODELS:
        if m not in models:
            models.append(m)
    return models


GROQ_MODEL = _DEFAULT_MODELS[0]

_SCHEMA = schema_prompt_block()

_SYSTEM = f"""You translate English loan-tape QC checks into SQL WHERE fragments.

{_SCHEMA}

Rules:
- Return JSON only: {{"sql_predicate": "...", "required_columns": ["col", ...]}}
- sql_predicate identifies FAILING rows (boolean true = the loan fails the check).
- Use only the columns listed above. No semicolons, comments, JOINs, or subqueries.
- Prefer IS NULL / comparisons / COALESCE / length / regexp_replace / abs / trim.
- Rates and LTV/CLTV/DTI are decimals (0.80 = 80%). FICO is integer 300–850.
- Example: "FICO below 620" → original_fico IS NOT NULL AND original_fico < 620
- Example: "LTV above 80%" → original_ltv IS NOT NULL AND original_ltv > 0.80
"""


def groq_api_key() -> str | None:
    # Always merge .env / .env.local so a blank process env cannot hide the key.
    load_dotenv(overwrite=False)
    if not (os.environ.get("GROQ_API_KEY") or "").strip():
        load_dotenv(overwrite=True)
    key = (os.environ.get("GROQ_API_KEY") or "").strip()
    return key or None


def _error_result(english: str, error: str) -> dict[str, Any]:
    return {
        "ok": False,
        "english": english,
        "sql_predicate": None,
        "required_columns": [],
        "mode": "error",
        "model": None,
        "warning": None,
        "error": error,
    }


def translate_english(english: str) -> dict[str, Any]:
    """Translate English → runnable failing-row predicate via Groq only."""
    text = (english or "").strip()
    if not text:
        return _error_result(text, "english is required")

    key = groq_api_key()
    if not key:
        return _error_result(
            text,
            "GROQ_API_KEY is required. Set it in .env and restart the API.",
        )

    try:
        raw, used_model = _call_groq(key, text)
        predicate, cols = validate_predicate(raw["sql_predicate"])
        return {
            "ok": True,
            "english": text,
            "sql_predicate": predicate,
            "required_columns": cols or list(raw.get("required_columns") or []),
            "mode": "groq",
            "model": used_model,
            "warning": None,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return _error_result(
            text,
            f"Groq translate failed ({type(exc).__name__}: {exc})",
        )


def _call_groq(api_key: str, english: str) -> tuple[dict[str, Any], str]:
    models = _groq_models()
    errors: list[str] = []
    for model in models:
        payload = {
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": (
                        "Translate this Loan QC check into a failing-row SQL "
                        f"predicate:\n{english}"
                    ),
                },
            ],
        }
        req = urllib.request.Request(
            GROQ_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "cashflow-sum-app-qc/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            errors.append(f"{model}: HTTP {exc.code}: {detail}")
            # Try next model on missing/decommissioned/forbidden.
            if exc.code in (400, 403, 404):
                continue
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc

        content = (
            ((body.get("choices") or [{}])[0].get("message") or {}).get("content")
            or ""
        )
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            errors.append(f"{model}: invalid JSON content")
            continue
        if not isinstance(parsed, dict) or not parsed.get("sql_predicate"):
            errors.append(f"{model}: missing sql_predicate")
            continue
        return parsed, model

    raise RuntimeError("; ".join(errors) or "no Groq models available")
