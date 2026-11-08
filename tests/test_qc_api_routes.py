"""FastAPI Loan QC translate / custom-check routes (Groq stubbed)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db = tmp_path / "qc_api.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    for key in (
        "DATABASE_URL_UNPOOLED",
        "POSTGRES_URL_NON_POOLING",
        "NEON_DATABASE_URL",
        "GROQ_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    # Import after env so bootstrap picks the temp sqlite file.
    from app.repositories.bootstrap import bootstrap_database
    from app.main import app
    import app.services.qc_nl_translate as qc_nl

    monkeypatch.setattr(qc_nl, "groq_api_key", lambda: "test-key")

    def fake_call(_key: str, english: str):
        if "FICO" in english.upper() or "fico" in english:
            pred = "original_fico IS NOT NULL AND original_fico < 620"
            cols = ["original_fico"]
        else:
            pred = "original_ltv IS NOT NULL AND original_ltv > 0.8"
            cols = ["original_ltv"]
        return (
            {"sql_predicate": pred, "required_columns": cols},
            "openai/gpt-oss-20b",
        )

    monkeypatch.setattr(qc_nl, "_call_groq", fake_call)

    bootstrap_database()
    return TestClient(app)


def test_translate_requires_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "qc_api_nokey.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    from app.repositories.bootstrap import bootstrap_database
    from app.main import app
    import app.services.qc_nl_translate as qc_nl

    monkeypatch.setattr(qc_nl, "groq_api_key", lambda: None)
    bootstrap_database()
    c = TestClient(app)
    tr = c.post(
        "/api/qc/translate",
        json={"english": "Flag loans with FICO below 620"},
    )
    assert tr.status_code == 400, tr.text
    assert "GROQ_API_KEY" in tr.json()["detail"]


def test_translate_and_save_run(client: TestClient) -> None:
    tr = client.post(
        "/api/qc/translate",
        json={"english": "Flag loans with FICO below 620"},
    )
    assert tr.status_code == 200, tr.text
    body = tr.json()
    assert body["ok"] is True
    assert body["mode"] == "groq"
    assert body["warning"] is None
    assert "original_fico" in body["sql_predicate"]

    preview = client.post(
        "/api/qc/preview",
        json={
            "english": "Flag loans with FICO below 620",
            "sql_predicate": body["sql_predicate"],
            "failing_only": True,
        },
    )
    assert preview.status_code == 200, preview.text
    prev = preview.json()
    assert prev["ok"] is True
    assert prev["fail_count"] is not None
    assert prev["pass_count"] is not None
    assert prev["outcome"] in {"pass", "fail"}
    assert isinstance(prev["loans"], list)

    created = client.post(
        "/api/qc/checks",
        json={
            "english": "Flag loans with FICO below 620",
            "sql_predicate": body["sql_predicate"],
        },
    )
    assert created.status_code == 200, created.text
    check = created.json()["check"]
    assert check["source"] == "custom"

    run = client.post("/api/qc/run")
    assert run.status_code == 200, run.text
    results = run.json()["results"]
    assert results[0]["scope"] == "Custom"
    custom = next(r for r in results if r["check_id"] == check["check_id"])
    assert custom["outcome"] in {"pass", "fail"}
    assert custom["status_label"] in {"Pass", "Fail"}
    assert custom["scope"] == "Custom"

    listed = client.get("/api/qc/checks", params={"source": "custom"})
    assert listed.status_code == 200
    assert listed.json()["n"] >= 1

    deleted = client.delete(f"/api/qc/checks/{check['check_id']}")
    assert deleted.status_code == 200
