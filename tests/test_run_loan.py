"""POST /api/run-loan projects existing CashFlowRow fields."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.models.cash_flow import CashFlowRow

ENGINE_FIELDS = set(CashFlowRow.model_fields)


def test_run_loan_returns_engine_rows() -> None:
    client = TestClient(app)
    res = client.post(
        "/api/run-loan",
        json={"loan_id": "SYN000001", "scenario_id": "S05", "months": 3},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "ok"
    assert body["loan_id"] == "SYN000001"
    assert body["scenario_id"] == "S05"
    assert body["months"] == 3
    rows = body["cash_flows"]
    assert len(rows) == 3
    first = rows[0]
    assert set(first) <= ENGINE_FIELDS
    assert first["month"] == 1
    assert first["beginning_balance"] > 0
    assert "used_recovery_lag_months" in first
    assert "total_cash" in first
    assert "realized_loss" in first


def test_run_loan_alias_and_cohort_base_case() -> None:
    client = TestClient(app)
    res = client.post(
        "/api/cashflows/run-loan",
        json={"loan_id": "SYN000001", "months": 1},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "ok"
    assert len(body["cash_flows"]) == 1
    assert body["scenario_id"]  # resolved from loan cohort × 100/100


def test_run_loan_unknown_loan_404() -> None:
    client = TestClient(app)
    res = client.post(
        "/api/run-loan",
        json={"loan_id": "DOES-NOT-EXIST", "scenario_id": "S05", "months": 1},
    )
    assert res.status_code == 404
