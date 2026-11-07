"""FastAPI Loan QC translate / custom-check routes (mock Groq)."""

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

    bootstrap_database()
    return TestClient(app)


def test_translate_mock_and_save_run(client: TestClient) -> None:
    tr = client.post(
        "/api/qc/translate",
        json={"english": "Flag loans with FICO below 620"},
    )
    assert tr.status_code == 200, tr.text
    body = tr.json()
    assert body["ok"] is True
    assert body["mode"] == "mock"
    assert body["warning"]
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
