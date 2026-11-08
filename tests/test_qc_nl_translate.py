"""English → QC predicate translation (Groq required; no mock fallback)."""

from __future__ import annotations

import pytest

from app.services.qc_nl_translate import translate_english
from app.services.qc_predicate import validate_predicate


def test_missing_key_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.qc_nl_translate.groq_api_key", lambda: None
    )
    out = translate_english("Flag loans with FICO below 620")
    assert out["ok"] is False
    assert out["mode"] == "error"
    assert out["sql_predicate"] is None
    assert "GROQ_API_KEY" in (out["error"] or "")


def test_groq_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.qc_nl_translate.groq_api_key", lambda: "test-key"
    )

    def fake_call(_key: str, _english: str):
        return (
            {
                "sql_predicate": (
                    "original_fico IS NOT NULL AND original_fico < 620"
                ),
                "required_columns": ["original_fico"],
            },
            "openai/gpt-oss-20b",
        )

    monkeypatch.setattr(
        "app.services.qc_nl_translate._call_groq", fake_call
    )
    out = translate_english("Flag loans with FICO below 620")
    assert out["ok"] is True
    assert out["mode"] == "groq"
    assert out["model"] == "openai/gpt-oss-20b"
    assert out["warning"] is None
    assert "620" in out["sql_predicate"]
    validate_predicate(out["sql_predicate"])


def test_groq_failure_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.qc_nl_translate.groq_api_key", lambda: "test-key"
    )

    def boom(_key: str, _english: str):
        raise RuntimeError("HTTP 403: blocked")

    monkeypatch.setattr("app.services.qc_nl_translate._call_groq", boom)
    out = translate_english("LTV above 80%")
    assert out["ok"] is False
    assert out["mode"] == "error"
    assert out["sql_predicate"] is None
    assert "Groq translate failed" in (out["error"] or "")


def test_validate_rejects_injection() -> None:
    with pytest.raises(ValueError):
        validate_predicate("1=1; DROP TABLE asf_tape")
    with pytest.raises(ValueError):
        validate_predicate("loan_id IN (SELECT loan_id FROM secrets)")


def test_validate_unknown_column() -> None:
    with pytest.raises(ValueError, match="unknown column"):
        validate_predicate("borrower_ssn IS NULL")
