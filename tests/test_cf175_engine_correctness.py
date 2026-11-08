"""CF-175: contractual amort, IO/maturity/ARM, reconcile, scenario config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.loan import Loan
from app.models.scenario import Scenario
from app.services.cache_keys import cf_cache_key, cf_cache_meta
from app.services.cashflow_engine import (
    ENGINE_VERSION,
    LoanEngineError,
    contractual_scheduled_principal,
    project_loan_cashflows,
    validate_loan_for_engine,
)
from app.services.reconcile import assert_path_reconciles, life_identity_errors
from app.services.scenario_config import (
    base_speeds,
    frontend_scenario_config_path,
    label_psa_sda,
    load_scenario_config,
    scenario_config_path,
)
from app.services.scenario_grid import build_scenario_grid


def _ref_scenario(**kwargs) -> Scenario:
    base = dict(
        scenario_id="REF",
        name="ref",
        cohort="LLTV Weak RI",
        psa_multiple=100,
        sda_multiple=0,
        recovery_rate=0.6,
        recovery_lag_months=0,
        recovery_period_months=1,
    )
    # Scenario model has no "name" — drop if unused
    base.pop("name", None)
    base.update(kwargs)
    return Scenario(**base)


def _ref_loan(**kwargs) -> Loan:
    base = dict(
        loan_id="REF100",
        current_balance=100_000.0,
        annual_rate=0.06,
        remaining_term_months=360,
        loan_age_months=60,
        remaining_io_months=0,
    )
    base.update(kwargs)
    return Loan(**base)


def test_reference_case_ending_upb_month_60() -> None:
    """$100k / 6% / 360 rem / age 60 / 100 PSA / 0 SDA → ~68292.97 not ~63382."""
    rows = project_loan_cashflows(_ref_loan(), _ref_scenario(), months=60)
    end = float(rows[59].ending_balance)
    assert abs(end - 68292.97) < 0.05, f"got {end}"
    # Guard against regressing to fixed-payment acceleration (~63382).
    assert abs(end - 63382.19) > 100.0


def test_contractual_sched_scales_with_balance() -> None:
    full = contractual_scheduled_principal(100_000.0, 0.06, 360)
    half = contractual_scheduled_principal(50_000.0, 0.06, 360)
    assert abs(half - full / 2.0) < 1e-9


def test_zero_prepay_matches_level_amort_path() -> None:
    rows = project_loan_cashflows(
        _ref_loan(), _ref_scenario(psa_multiple=0, sda_multiple=0), months=12
    )
    assert_path_reconciles(rows, starting_balance=100_000.0)
    # With 0 PSA/SDA, sched should equal contractual fraction on begin each month.
    for r in rows:
        expect = contractual_scheduled_principal(
            float(r.beginning_balance), 0.06, 360 - r.month + 1
        )
        assert abs(float(r.scheduled_principal) - expect) < 0.02
        assert float(r.prepay) == 0.0
        assert float(r.new_default) == 0.0


def test_io_then_amort_payment_once_and_sched_nonzero() -> None:
    loan = _ref_loan(remaining_io_months=3, monthly_payment=None)
    rows = project_loan_cashflows(loan, _ref_scenario(psa_multiple=0), months=6)
    assert all(float(r.scheduled_principal) == 0.0 for r in rows[:3])
    assert float(rows[3].scheduled_principal) > 0.0
    assert_path_reconciles(rows, starting_balance=100_000.0)


def test_maturity_balloon_clears_balance() -> None:
    loan = _ref_loan(remaining_term_months=3, loan_age_months=100)
    rows = project_loan_cashflows(
        loan, _ref_scenario(psa_multiple=0, sda_multiple=0), months=3
    )
    assert len(rows) == 3
    assert float(rows[-1].ending_balance) == pytest.approx(0.0, abs=0.02)
    assert float(rows[-1].scheduled_principal) == pytest.approx(
        float(rows[-1].beginning_balance), abs=0.02
    )
    assert float(rows[-1].prepay) == 0.0


def test_validate_rejects_bad_io_and_arm_reset() -> None:
    with pytest.raises(LoanEngineError):
        validate_loan_for_engine(
            _ref_loan(remaining_io_months=400, remaining_term_months=360)
        )
    arm = _ref_loan(
        loan_age_months=40,
        arm_index="SOFR",
        arm_initial_fixed_months=42,
        arm_reset_frequency_months=6,
    )
    with pytest.raises(LoanEngineError, match="ARM"):
        validate_loan_for_engine(arm, months=24)


def test_arm_past_horizon_allowed_as_fixed() -> None:
    loan = _ref_loan(
        loan_age_months=10,
        arm_index="SOFR",
        arm_initial_fixed_months=120,
        arm_reset_frequency_months=12,
    )
    # First reset at month 110 of projection — beyond short horizon.
    rows = project_loan_cashflows(loan, _ref_scenario(), months=6)
    assert len(rows) == 6


def test_life_reconcile_reference_path() -> None:
    rows = project_loan_cashflows(_ref_loan(), _ref_scenario(), months=120)
    meta = assert_path_reconciles(rows, starting_balance=100_000.0)
    assert meta["ok"] is True
    assert life_identity_errors(rows, starting_balance=100_000.0) == []


def test_scenario_config_shared_frontend_backend() -> None:
    backend = json.loads(scenario_config_path().read_text(encoding="utf-8"))
    frontend = json.loads(
        frontend_scenario_config_path().read_text(encoding="utf-8")
    )
    assert backend == frontend
    cfg = load_scenario_config()
    assert cfg["grid_axes"]["psa_multiples"] == [75, 100, 125]
    speeds = base_speeds()
    assert speeds["HLTV Strong RI"] == (150, 150)
    grid = build_scenario_grid()
    assert len(grid) == 27
    assert label_psa_sda(100, 50) == "PSA 100 / SDA 50"


def test_cache_key_includes_engine_and_scenario() -> None:
    sc = _ref_scenario()
    key = cf_cache_key(tape_path=None, scenario=sc, months=60)
    assert ENGINE_VERSION in key
    assert "scenario:" in key
    meta = cf_cache_meta(tape_path=None, scenario=sc, months=60)
    assert meta["engine_version"] == ENGINE_VERSION
    assert meta["cache_key"] == key


def test_mi_severity_vintage_documented_not_invented() -> None:
    notes = load_scenario_config()["mi_credit_recovery"]
    assert notes["severity_default_year_band"] == "2006"
    assert "not inferred" in notes["severity_year_rationale"].lower() or (
        "not" in notes["severity_year_rationale"].lower()
        and "origination" in notes["severity_year_rationale"].lower()
    )
