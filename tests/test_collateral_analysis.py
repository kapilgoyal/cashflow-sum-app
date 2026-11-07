"""UPB weights, buckets, filters, derived LTV, risk flags for collateral research."""

from __future__ import annotations

from app.services.collateral_analysis import (
    COHORT_DISPLAY,
    analyze,
    bucket_ordered,
    derived_current_cltv,
    derived_current_ltv,
    enrich_loan,
    filter_loans,
    fico_ltv_heatmap,
    kpi_summary,
    load_enriched_loans_from_excel,
    risk_flags,
    upb_weighted_mean,
)
from app.services.scenario_grid import (
    COHORT_HIGH_LTV_STRONG,
    COHORT_LOW_LTV_WEAK,
)


def test_derived_current_ltv_and_cltv():
    assert derived_current_ltv(80_000, 100_000) == 0.8
    assert derived_current_ltv(80_000, 0) is None
    assert derived_current_cltv(80_000, 10_000, 0, 100_000) == 0.9


def test_fico_buckets():
    assert bucket_ordered(640, (("a", 0, 660), ("b", 660, 700))) == "a"
    assert bucket_ordered(None, (("a", 0, 660),)) == "missing"


def test_upb_weighted_mean():
    loans = [
        {"current_loan_amount": 100, "original_fico": 600},
        {"current_loan_amount": 300, "original_fico": 800},
    ]
    # (600*100 + 800*300) / 400 = 750
    assert upb_weighted_mean(loans, "original_fico") == 750


def test_risk_flags_layering():
    row = enrich_loan(
        {
            "loan_id": "X1",
            "current_loan_amount": 200_000,
            "current_interest_rate": 0.08,
            "original_fico": 640,
            "original_ltv": 0.92,
            "original_cltv": 0.92,
            "most_recent_property_value": 200_000,
            "senior_lien_current_balance": 0,
            "junior_lien_balance": 0,
            "documentation_type": "Bank statement 12m",
            "occupancy": "Investor",
            "loan_purpose": "Cash-out refinance",
            "originator_dti": 0.50,
            "dscr": None,
            "days_delinquent": 30,
            "refinance_incentive": 1.2,
            "has_mi": True,
        },
        COHORT_HIGH_LTV_STRONG,
    )
    flags = set(row["risk_flags"])
    assert "Low FICO" in flags
    assert "High Original LTV ≥90%" in flags
    assert "Alt Documentation" in flags
    assert "Investor Occupancy" in flags
    assert "Cash-Out" in flags
    assert "Delinquent" in flags
    assert "High DTI" in flags


def test_filter_by_kproto_cohort_not_excel_label():
    loans = [
        enrich_loan(
            {
                "loan_id": "A",
                "current_loan_amount": 100,
                "current_interest_rate": 0.07,
                "original_fico": 720,
                "original_ltv": 0.65,
                "original_cltv": 0.65,
                "most_recent_property_value": 150,
                "cohort": "High Quality",
            },
            COHORT_LOW_LTV_WEAK,
        ),
        enrich_loan(
            {
                "loan_id": "B",
                "current_loan_amount": 100,
                "current_interest_rate": 0.08,
                "original_fico": 680,
                "original_ltv": 0.85,
                "original_cltv": 0.85,
                "most_recent_property_value": 120,
                "cohort": "Middle",
            },
            COHORT_HIGH_LTV_STRONG,
        ),
    ]
    filtered = filter_loans(loans, cohorts=[COHORT_LOW_LTV_WEAK])
    assert len(filtered) == 1
    assert filtered[0]["loan_id"] == "A"
    assert filtered[0]["cohort_display"] == COHORT_DISPLAY[COHORT_LOW_LTV_WEAK]


def test_heatmap_and_analyze_kpis():
    loans = [
        enrich_loan(
            {
                "loan_id": "A",
                "current_loan_amount": 200,
                "current_interest_rate": 0.07,
                "remaining_term": 360,
                "loan_age_months": 4,
                "original_fico": 720,
                "original_ltv": 0.75,
                "original_cltv": 0.75,
                "most_recent_property_value": 300,
                "state": "FL",
                "documentation_type": "Full documentation",
                "occupancy": "Owner",
                "loan_purpose": "Purchase",
                "property_type": "Single family / PUD",
                "originator_dti": 0.32,
                "refinance_incentive": 0.5,
            },
            COHORT_LOW_LTV_WEAK,
        ),
        enrich_loan(
            {
                "loan_id": "B",
                "current_loan_amount": 100,
                "current_interest_rate": 0.09,
                "remaining_term": 300,
                "loan_age_months": 18,
                "original_fico": 640,
                "original_ltv": 0.91,
                "original_cltv": 0.91,
                "most_recent_property_value": 110,
                "state": "TX",
                "documentation_type": "DSCR",
                "occupancy": "Investor",
                "loan_purpose": "Cash-out refinance",
                "property_type": "Condo",
                "dscr": 0.95,
                "refinance_incentive": 1.5,
            },
            COHORT_HIGH_LTV_STRONG,
        ),
    ]
    heat = fico_ltv_heatmap(loans)
    assert any(c["fico_band"] == "700-739" and c["ltv_band"] == "70-80" for c in heat)
    kpis = kpi_summary(loans)
    assert kpis["loan_count"] == 2
    assert kpis["upb"] == 300
    # WAC = (0.07*200 + 0.09*100)/300 = 0.07666...
    assert abs(kpis["wac"] - (0.07 * 200 + 0.09 * 100) / 300) < 1e-9
    payload = analyze(loans, cohorts=[COHORT_HIGH_LTV_STRONG])
    assert payload["kpis"]["loan_count"] == 1
    assert payload["observations"]["fico"]


def test_live_tape_load_and_cohort_overlay():
    loans = load_enriched_loans_from_excel()
    assert len(loans) == 1043
    # All loans get a k-proto cohort from cluster-tape
    assert all(loan.get("cohort") for loan in loans)
    # Excel short labels must not be used as filter keys
    excel_shorts = {"High Quality", "Middle", "Low Credit Low Pay"}
    assert not any(loan["cohort"] in excel_shorts for loan in loans)
    kpis = kpi_summary(loans)
    assert kpis["loan_count"] == 1043
    assert kpis["upb"] > 0
    assert kpis["wa_fico"] is not None
    # Cross-filter FICO band
    filtered = filter_loans(loans, fico_bands=["<660"])
    assert all(loan["fico_band"] == "<660" for loan in filtered)
    assert sum(loan["current_loan_amount"] or 0 for loan in filtered) <= kpis["upb"]
