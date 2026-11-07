"""Custom QC checks persist in SQLite and survive built-in upsert."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.repositories.asf_tape_repository import AsfTapeRepository
from app.repositories.bootstrap import bootstrap_database


@pytest.fixture()
def sqlite_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsfTapeRepository:
    db = tmp_path / "qc_custom.db"
    url = f"sqlite:///{db}"
    monkeypatch.setenv("DATABASE_URL", url)
    # Clear optional overrides that resolve_database_url prefers.
    for key in (
        "DATABASE_URL_UNPOOLED",
        "POSTGRES_URL_NON_POOLING",
        "NEON_DATABASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    bootstrap_database()
    return AsfTapeRepository(url)


def test_custom_check_save_run_survives_upsert(sqlite_repo: AsfTapeRepository) -> None:
    repo = sqlite_repo
    saved = repo.save_custom_check(
        nl_description="FICO Below 620",
        sql_predicate="original_fico IS NOT NULL AND original_fico < 620",
        required_columns=["original_fico"],
    )
    assert saved["source"] == "custom"
    assert saved["check_id"].startswith("custom_")

    n_before = len(repo.list_custom_checks())
    assert n_before == 1

    repo.upsert_check_defs()
    customs = repo.list_custom_checks()
    assert len(customs) == 1
    assert customs[0]["check_id"] == saved["check_id"]

    run = repo.run_qc()
    assert run["tape_row_count"] > 0
    ids = {r["check_id"] for r in run["results"]}
    assert saved["check_id"] in ids
    custom_row = next(r for r in run["results"] if r["check_id"] == saved["check_id"])
    assert custom_row["outcome"] in {"pass", "fail"}
    assert custom_row["fail_count"] is not None

    latest = repo.latest_results()
    assert any(r["check_id"] == saved["check_id"] for r in latest)

    loans, total, meta = repo.list_check_loans(saved["check_id"], failing_only=True)
    assert meta["source"] == "custom"
    assert total == custom_row["fail_count"]
    assert len(loans) == min(total, 2000)

    assert repo.delete_custom_check(saved["check_id"]) is True
    assert repo.list_custom_checks() == []
