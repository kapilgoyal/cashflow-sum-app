"""CF-191: cache freshness, scenario-grid completeness, principal-only WAL."""

from __future__ import annotations

import pytest

from app.services.cache_keys import (
    assumptions_fingerprint,
    cache_is_fresh,
    cf_cache_meta,
)
from app.services.cashflow_engine import ENGINE_VERSION
from app.services.scenario_grid import COHORTS
from app.services.scenario_grid_cf import (
    _wal_years,
    assert_grid_complete,
    grid_failure_payload,
)
from app.services.valuation import (
    StaleCashflowCacheError,
    build_valuation,
    pool_wal_years,
)


def _fresh_payload(**extra):
    meta = cf_cache_meta(
        tape_path=None,
        scenario={"scenario_id": "BASE"},
        months=360,
        kind="base_cohort_cf",
    )
    return {
        "engine_version": ENGINE_VERSION,
        "assumptions_fingerprint": assumptions_fingerprint(),
        "cache": meta,
        **extra,
    }


def test_cache_is_fresh_rejects_stale_and_missing_stamps() -> None:
    fresh = _fresh_payload(months=[])
    assert cache_is_fresh(fresh) is True
    assert cache_is_fresh({**fresh, "engine_version": "0.0-stale"}) is False
    assert (
        cache_is_fresh(
            {**fresh, "assumptions_fingerprint": "assumptions:deadbeef"}
        )
        is False
    )
    assert cache_is_fresh({"months": [], "Pool": 1}) is False


def test_valuation_refuses_stale_base_cf(monkeypatch) -> None:
    stale = {"months": [{"month": 1, "Pool": 1.0}], "principal_months": []}

    def _stale():
        return stale

    monkeypatch.setattr(
        "app.services.valuation._load_base_cf", _stale
    )
    with pytest.raises(StaleCashflowCacheError) as exc:
        build_valuation()
    msg = str(exc.value).lower()
    assert "stale" in msg or "fingerprint" in msg or "principal_months" in msg
    assert "recompute" in msg or "run-base-cohort" in msg


def test_assert_grid_complete_requires_27_and_9_per_cohort() -> None:
    scenarios = {
        f"S{i:02d}": {"status": "ok", "scenario_id": f"S{i:02d}"}
        for i in range(1, 28)
    }
    cohort_avg = {
        c: {"n_cells": 9, "months": [], "wal_years": 1.0} for c in COHORTS
    }
    ok = {
        "ran_scenario_ids": [f"S{i:02d}" for i in range(1, 28)],
        "scenarios": scenarios,
        "cohort_avg": cohort_avg,
        "parallelism": {"ok": 27, "error": 0},
    }
    assert_grid_complete(ok)  # no raise

    bad = {
        **ok,
        "ran_scenario_ids": ok["ran_scenario_ids"][:26],
        "parallelism": {"ok": 26, "error": 1},
        "scenarios": {
            **scenarios,
            "S27": {"status": "error", "scenario_id": "S27"},
        },
    }
    with pytest.raises(RuntimeError, match="27"):
        assert_grid_complete(bad)

    bad_avg = {
        **ok,
        "cohort_avg": {
            **cohort_avg,
            COHORTS[0]: {"n_cells": 8, "months": []},
        },
    }
    with pytest.raises(RuntimeError, match="9"):
        assert_grid_complete(bad_avg)


def test_grid_failure_keeps_prior_cache_flag() -> None:
    prior = _fresh_payload(scenarios={f"S{i:02d}": {} for i in range(1, 28)})
    fail = grid_failure_payload(
        error="Scenario grid incomplete: 26/27 ok",
        prior=prior,
        result={"ran_scenario_ids": [], "scenarios": {}, "parallelism": {}},
    )
    assert fail["ok"] is False
    assert fail["cache_retained"] is True
    assert fail["prior_cache"]["engine_version"] == ENGINE_VERSION


def test_wal_twelve_equal_months() -> None:
    """12 equal principal months → mean month 6.5 → 6.5/12 ≈ 0.541667y."""
    rows = [
        {"month": m, "scheduled_principal": 10.0, "prepay": 0.0, "recovery": 0.0}
        for m in range(1, 13)
    ]
    wal = pool_wal_years(rows)
    assert wal == pytest.approx(0.5417, abs=5e-4)
    by_m = {m: 10.0 for m in range(1, 13)}
    # scenario_grid rounds WAL to 6 dp → 0.541667 years (6.5/12).
    assert _wal_years(by_m) == pytest.approx(0.541667, abs=1e-9)


def test_wal_balloon_and_delayed_recovery() -> None:
    # Balloon: all principal at month 360.
    balloon = [{"month": 360, "principal_cash": 100.0}]
    assert pool_wal_years(balloon) == pytest.approx(30.0, abs=1e-9)

    # Delayed recovery only (no interest/default in denominator).
    delayed = [
        {
            "month": 12,
            "scheduled_principal": 50.0,
            "prepay": 0.0,
            "recovery": 0.0,
            "interest": 999.0,
            "new_default": 20.0,
        },
        {
            "month": 36,
            "scheduled_principal": 0.0,
            "prepay": 0.0,
            "recovery": 30.0,
            "realized_loss": 20.0,
            "new_default": 0.0,
        },
    ]
    assert pool_wal_years(delayed) == pytest.approx(1.75, abs=1e-9)
