"""Investor Analysis: UPB weights, data gates, no invented PD."""

from __future__ import annotations

from app.services.collateral_analysis import enrich_loan
from app.services.investor_analysis import (
    build_investor_analysis,
    cohort_scorecard,
    historical_dq_payload,
    hpa_stress_payload,
    loss_severity_payload,
    ri_seasoning_heatmap,
)
from app.services.scenario_grid import (
    COHORT_HIGH_LTV_STRONG,
    COHORT_HIGH_LTV_WEAK,
    COHORT_LOW_LTV_WEAK,
)
from app.services.severity import bootstrap_severity


def _make(cohort, **kwargs):
    raw = {
        "loan_id": kwargs.pop("loan_id", "X"),
        "current_loan_amount": kwargs.pop("upb", 100_000),
        "current_interest_rate": 0.075,
        "remaining_term": 360,
        "loan_age_months": kwargs.pop("age", 12),
        "original_fico": kwargs.pop("fico", 740),
        "original_ltv": kwargs.pop("ltv", 0.7),
        "original_cltv": kwargs.pop("cltv", 0.7),
        "most_recent_property_value": kwargs.pop("value", 150_000),
        "senior_lien_current_balance": 0,
        "junior_lien_balance": 0,
        "state": kwargs.pop("state", "TX"),
        "documentation_type": kwargs.pop("doc", "Full Documentation"),
        "occupancy": kwargs.pop("occ", "Primary"),
        "loan_purpose": kwargs.pop("purpose", "Purchase"),
        "originator_dti": 0.32,
        "dscr": None,
        "days_delinquent": kwargs.pop("dq", 0),
        "refinance_incentive": kwargs.pop("ri", 1.0),
        "has_mi": True,
    }
    return enrich_loan(raw, cohort)


def test_scorecard_upb_weighted_and_shares():
    loans = [
        _make(COHORT_LOW_LTV_WEAK, loan_id="a", upb=100, fico=600, cltv=0.5),
        _make(COHORT_LOW_LTV_WEAK, loan_id="b", upb=300, fico=800, cltv=0.5),
        _make(COHORT_HIGH_LTV_STRONG, loan_id="c", upb=200, fico=700, cltv=0.85),
    ]
    rows = {r["cohort"]: r for r in cohort_scorecard(loans)}
    # WA FICO LLTV = (600*100 + 800*300) / 400 = 750
    assert abs(rows[COHORT_LOW_LTV_WEAK]["wa_fico"] - 750) < 1e-6
    assert abs(rows[COHORT_LOW_LTV_WEAK]["upb_share"] - 400 / 600) < 1e-9


def test_hpa_stress_requires_property_value():
    with_val = [_make(COHORT_HIGH_LTV_WEAK, loan_id="1", value=200_000, upb=160_000, cltv=0.8)]
    ok = hpa_stress_payload(with_val)
    assert ok["available"] is True
    zero = next(s for s in ok["shocks"] if s["hpa"] == 0.0)
    down = next(s for s in ok["shocks"] if s["hpa"] == -0.20)
    assert zero["wa_cltv"] is not None
    assert down["wa_cltv"] > zero["wa_cltv"]


def test_historical_dq_skipped_when_sparse():
    loans = [_make(COHORT_LOW_LTV_WEAK, loan_id=str(i), dq=0) for i in range(50)]
    loans[0] = _make(COHORT_LOW_LTV_WEAK, loan_id="dq", dq=30)
    payload = historical_dq_payload(loans)
    assert payload["available"] is False


def test_loss_severity_no_pd_field():
    bootstrap_severity()
    loans = [
        _make(COHORT_HIGH_LTV_STRONG, loan_id="s1", fico=680, ltv=0.85, cltv=0.85),
        _make(COHORT_LOW_LTV_WEAK, loan_id="s2", fico=780, ltv=0.55, cltv=0.55),
    ]
    payload = loss_severity_payload(loans)
    assert payload["available"] is True
    assert "pd" not in payload
    assert "expected_loss" not in payload
    assert payload["pool_wa_severity"] is not None
    assert 0 < payload["pool_wa_severity"] < 1
    assert payload["pool_wa_recovery"] is not None


def test_ri_seasoning_heatmap_cells():
    loans = [
        _make(COHORT_LOW_LTV_WEAK, loan_id="r1", ri=-0.5, age=3),
        _make(COHORT_HIGH_LTV_STRONG, loan_id="r2", ri=1.5, age=20),
    ]
    cells = ri_seasoning_heatmap(loans)
    assert len(cells) == 2
    assert {c["ri_band"] for c in cells} == {"<0", "1-2"}


def test_build_skips_tranche_and_sparse_dq():
    bootstrap_severity()
    loans = [
        _make(COHORT_LOW_LTV_WEAK, loan_id="1"),
        _make(COHORT_HIGH_LTV_STRONG, loan_id="2", fico=650, cltv=0.9, ltv=0.9),
        _make(COHORT_HIGH_LTV_WEAK, loan_id="3", ri=2.1, age=30),
    ]
    payload = build_investor_analysis(loans)
    assert payload["sections"]["scorecard"]["available"] is True
    assert payload["sections"]["fico_cltv"]["available"] is True
    assert payload["sections"]["hpa_stress"]["available"] is True
    assert payload["sections"]["ri_seasoning"]["available"] is True
    assert payload["sections"]["loss_severity"]["available"] is True
    assert payload["sections"]["historical_dq"]["available"] is False
    assert payload["sections"]["tranche"]["available"] is False
    skipped_ids = {s["id"] for s in payload["skipped"]}
    assert "historical_dq" in skipped_ids
    assert "tranche" in skipped_ids
