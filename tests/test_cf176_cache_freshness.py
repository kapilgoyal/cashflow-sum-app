"""CF-176: month1/base/grid caches must match engine + assumptions fingerprints."""

from __future__ import annotations

from app.services.cache_keys import (
    assumptions_fingerprint,
    cache_is_fresh,
    cf_cache_meta,
)
from app.services.cashflow_engine import ENGINE_VERSION


def test_assumptions_fingerprint_stable() -> None:
    a = assumptions_fingerprint()
    b = assumptions_fingerprint()
    assert a == b
    assert a.startswith("assumptions:")
    assert ENGINE_VERSION.startswith("1.")


def test_cache_is_fresh_requires_engine_and_assumptions() -> None:
    meta = cf_cache_meta(
        tape_path=None,
        scenario={"scenario_id": "S01", "psa_multiple": 100, "sda_multiple": 100},
        months=1,
        kind="month1_cf",
    )
    fresh = {
        "engine_version": ENGINE_VERSION,
        "assumptions_fingerprint": assumptions_fingerprint(),
        "cache": meta,
        "aggregates": [],
    }
    assert cache_is_fresh(fresh) is True

    stale_engine = {**fresh, "engine_version": "0.0.0-stale"}
    assert cache_is_fresh(stale_engine) is False

    stale_assum = {**fresh, "assumptions_fingerprint": "assumptions:deadbeef"}
    assert cache_is_fresh(stale_assum) is False

    # Pre-CF-176 payloads (no stamps) must not be served as fresh.
    assert cache_is_fresh({"aggregates": [{"scenario_id": "S01"}]}) is False
    assert cache_is_fresh(None) is False


def test_pre_cf175_month1_json_shape_is_stale() -> None:
    """Old public/cohort-month1.json without fingerprints is refused."""
    legacy = {
        "meta": {
            "parallelism": {"executor": "static-cache"},
            "assumptions": {"horizon_months": 1},
        },
        "aggregates": [{"scenario_id": "S01", "recovery": 0.0}],
    }
    assert cache_is_fresh(legacy) is False
