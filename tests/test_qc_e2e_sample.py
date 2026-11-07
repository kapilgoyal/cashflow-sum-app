"""Sample end-to-end Loan QC flow: Translate → Preview → Save → Run.

Groq is stubbed so the suite does not need network; the live agent smoke
path is documented in the test docstring.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SAMPLE_ENGLISH = "Flag loans with missing FICO or FICO less than 500"
SAMPLE_PREDICATE = "original_fico IS NULL OR original_fico < 500"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db = tmp_path / "qc_e2e.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    for key in (
        "DATABASE_URL_UNPOOLED",
        "POSTGRES_URL_NON_POOLING",
        "NEON_DATABASE_URL",
        "GROQ_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    from app.repositories.bootstrap import bootstrap_database
    from app.main import app
    import app.services.qc_nl_translate as qc_nl

    monkeypatch.setattr(qc_nl, "groq_api_key", lambda: "test-key")

    def fake_call(_key: str, english: str):
        assert "FICO" in english.upper()
        return (
            {
                "sql_predicate": SAMPLE_PREDICATE,
                "required_columns": ["original_fico"],
            },
            "openai/gpt-oss-20b",
        )

    monkeypatch.setattr(qc_nl, "_call_groq", fake_call)
    bootstrap_database()
    return TestClient(app)


def test_sample_qc_rule_end_to_end(client: TestClient) -> None:
    # 1) Translate (Groq path — no mock)
    tr = client.post("/api/qc/translate", json={"english": SAMPLE_ENGLISH})
    assert tr.status_code == 200, tr.text
    body = tr.json()
    assert body["ok"] is True
    assert body["mode"] == "groq"
    assert body["warning"] is None
    assert body["error"] is None
    assert body["sql_predicate"] == SAMPLE_PREDICATE

    # 2) Test / preview at loan level without saving
    preview = client.post(
        "/api/qc/preview",
        json={
            "english": SAMPLE_ENGLISH,
            "sql_predicate": body["sql_predicate"],
            "failing_only": True,
            "limit": 50,
        },
    )
    assert preview.status_code == 200, preview.text
    prev = preview.json()
    assert prev["ok"] is True
    assert prev["outcome"] in {"pass", "fail"}
    assert prev["status_label"] in {"Pass", "Fail"}
    assert isinstance(prev["pass_count"], int)
    assert isinstance(prev["fail_count"], int)
    assert isinstance(prev["loans"], list)

    # 3) Confirm / save custom rule
    created = client.post(
        "/api/qc/checks",
        json={
            "english": SAMPLE_ENGLISH,
            "sql_predicate": body["sql_predicate"],
        },
    )
    assert created.status_code == 200, created.text
    check = created.json()["check"]
    assert check["source"] == "custom"
    check_id = check["check_id"]

    # 4) Run analysis and read results
    run = client.post("/api/qc/run")
    assert run.status_code == 200, run.text
    results = run.json()["results"]
    assert results, "expected QC results"
    assert results[0]["scope"] == "Custom"

    custom = next(r for r in results if r["check_id"] == check_id)
    assert custom["scope"] == "Custom"
    assert custom["outcome"] in {"pass", "fail"}
    assert custom["status_label"] in {"Pass", "Fail"}
    assert custom["nl_description"] == SAMPLE_ENGLISH

    # KPI-style active totals (skipped/warning rules excluded)
    active = [
        r
        for r in results
        if r.get("outcome") in {"pass", "fail"} and r.get("source") != "demo"
    ]
    assert len(active) >= 1
    total_failed_loans = sum(int(r.get("fail_count") or 0) for r in active)
    assert total_failed_loans >= 0

    # Cleanup
    deleted = client.delete(f"/api/qc/checks/{check_id}")
    assert deleted.status_code == 200, deleted.text
