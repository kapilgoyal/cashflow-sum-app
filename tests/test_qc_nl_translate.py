"""English → QC predicate translation (mock path without GROQ_API_KEY)."""

from __future__ import annotations

import os

import pytest

from app.services.qc_nl_translate import translate_english
from app.services.qc_predicate import validate_predicate


def test_mock_fico_below(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    out = translate_english("Flag loans with FICO below 620")
    assert out["ok"] is True
    assert out["mode"] == "mock"
    assert out["warning"]
    assert "original_fico" in out["sql_predicate"]
    assert "620" in out["sql_predicate"]
    validate_predicate(out["sql_predicate"])


def test_mock_ltv_above(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    out = translate_english("LTV above 80%")
    assert out["ok"] is True
    assert "original_ltv" in out["sql_predicate"]
    assert "0.8" in out["sql_predicate"]


def test_validate_rejects_injection() -> None:
    with pytest.raises(ValueError):
        validate_predicate("1=1; DROP TABLE asf_tape")
    with pytest.raises(ValueError):
        validate_predicate("loan_id IN (SELECT loan_id FROM secrets)")


def test_validate_unknown_column() -> None:
    with pytest.raises(ValueError, match="unknown column"):
        validate_predicate("borrower_ssn IS NULL")
