"""Translate English Loan QC checks into asf_tape SQL predicates via Groq.

Uses llama-3.1-8b-instant when GROQ_API_KEY is set. Without a key (or on API
failure), returns a heuristic mock predicate so the QC UI stays usable.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from app.repositories.env_load import load_dotenv
from app.services.qc_predicate import validate_predicate
from app.services.qc_tape_schema import schema_prompt_block

GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

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
    load_dotenv()
    key = (os.environ.get("GROQ_API_KEY") or "").strip()
    return key or None


def translate_english(english: str) -> dict[str, Any]:
    """Translate English → runnable failing-row predicate.

    Always returns a dict with ok, english, sql_predicate, required_columns,
    mode (groq|mock), model, and optional warning/error.
    """
    text = (english or "").strip()
    if not text:
        return {
            "ok": False,
            "english": text,
            "sql_predicate": None,
            "required_columns": [],
            "mode": "error",
            "model": None,
            "warning": None,
            "error": "english is required",
        }

    key = groq_api_key()
    if key:
        try:
            raw = _call_groq(key, text)
            predicate, cols = validate_predicate(raw["sql_predicate"])
            return {
                "ok": True,
                "english": text,
                "sql_predicate": predicate,
                "required_columns": cols or list(raw.get("required_columns") or []),
                "mode": "groq",
                "model": GROQ_MODEL,
                "warning": None,
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001
            mock = _mock_translate(text)
            mock["warning"] = (
                f"Groq request failed ({type(exc).__name__}: {exc}); "
                "using heuristic mock"
            )
            return mock

    mock = _mock_translate(text)
    mock["warning"] = "GROQ_API_KEY not set; using heuristic mock"
    return mock


def _call_groq(api_key: str, english: str) -> dict[str, Any]:
    payload = {
        "model": GROQ_MODEL,
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
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc

    content = (
        ((body.get("choices") or [{}])[0].get("message") or {}).get("content")
        or ""
    )
    parsed = json.loads(content)
    if not isinstance(parsed, dict) or not parsed.get("sql_predicate"):
        raise RuntimeError("Groq response missing sql_predicate")
    return parsed


def _mock_translate(english: str) -> dict[str, Any]:
    """Cheap pattern match so demos work without GROQ_API_KEY."""
    lowered = english.lower()
    predicate: str | None = None

    fico = _num_after(lowered, r"fico")
    if fico is not None:
        if _has_any(lowered, ("below", "under", "less than", "<", "missing", "null")):
            if "missing" in lowered or "null" in lowered:
                predicate = (
                    "original_fico IS NULL OR original_fico = 0 "
                    "OR original_fico < 300 OR original_fico > 850"
                )
            else:
                predicate = (
                    f"original_fico IS NOT NULL AND original_fico < {int(fico)}"
                )
        elif _has_any(lowered, ("above", "over", "greater than", ">")):
            predicate = (
                f"original_fico IS NOT NULL AND original_fico > {int(fico)}"
            )

    if predicate is None:
        ltv = _pct_after(lowered, r"\bltv\b")
        if ltv is not None:
            if _has_any(lowered, ("above", "over", "greater", ">")):
                predicate = (
                    f"original_ltv IS NOT NULL AND original_ltv > {ltv}"
                )
            elif _has_any(lowered, ("below", "under", "less", "<")):
                predicate = (
                    f"original_ltv IS NOT NULL AND original_ltv < {ltv}"
                )
            elif "missing" in lowered or "null" in lowered:
                predicate = "original_ltv IS NULL"

    if predicate is None:
        dti = _pct_after(lowered, r"\bdti\b")
        if dti is not None and _has_any(
            lowered, ("above", "over", "greater", ">", "than")
        ):
            predicate = (
                f"originator_dti IS NOT NULL AND originator_dti > {dti}"
            )

    if predicate is None and _has_any(
        lowered, ("zip", "postal")
    ) and _has_any(lowered, ("5", "five", "digit")):
        predicate = (
            "postal_code IS NULL OR length(regexp_replace("
            "trim(postal_code), '[^0-9]', '', 'g')) <> 5"
        )

    if predicate is None and _has_any(
        lowered, ("balance", "upb", "loan amount")
    ) and _has_any(lowered, ("zero", "<= 0", "missing", "null", "blank")):
        predicate = (
            "original_loan_amount IS NULL OR original_loan_amount <= 0"
        )

    if predicate is None and ("dscr" in lowered) and _has_any(
        lowered, ("below", "under", "less", "<")
    ):
        n = _pct_after(lowered, r"\bdscr\b") or 1.0
        predicate = f"dscr IS NOT NULL AND dscr < {n}"

    if predicate is None:
        # Safe default: flag blank / out-of-range FICO so mock still runs.
        predicate = (
            "original_fico IS NULL OR original_fico = 0 "
            "OR original_fico < 300 OR original_fico > 850"
        )

    cleaned, cols = validate_predicate(predicate)
    return {
        "ok": True,
        "english": english.strip(),
        "sql_predicate": cleaned,
        "required_columns": cols,
        "mode": "mock",
        "model": None,
        "warning": None,
        "error": None,
    }


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(n in text for n in needles)


def _num_after(text: str, label: str) -> float | None:
    match = re.search(
        rf"{label}\D{{0,24}}(\d+(?:\.\d+)?)", text, flags=re.I
    )
    if not match:
        match = re.search(
            rf"(\d+(?:\.\d+)?)\D{{0,12}}{label}", text, flags=re.I
        )
    return float(match.group(1)) if match else None


def _pct_after(text: str, label: str) -> float | None:
    """Parse a percent-ish number near a label into a decimal fraction."""
    match = re.search(
        rf"{label}\D{{0,24}}(\d+(?:\.\d+)?)\s*%?", text, flags=re.I
    )
    if not match:
        return None
    raw = float(match.group(1))
    if raw > 1.5:  # treat 50 / 80 as percent points
        return raw / 100.0
    return raw
