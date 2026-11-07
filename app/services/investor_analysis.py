"""Portfolio Manager Investor Analysis — UPB-weighted summary sections.

Does not invent PD. Loss severity uses Urban/Freddie recovery assumptions only.
Sections without required data are returned with available=False (omit in UI).
"""

from __future__ import annotations

from typing import Any

from app.repositories.tranche_repository import TrancheRepository
from app.services.collateral_analysis import (
    AGE_BUCKETS,
    COHORT_DISPLAY,
    FICO_BUCKETS,
    LTV_BUCKETS,
    aggregate_categorical,
    bucket_ordered,
    filter_loans,
    kpi_summary,
    load_enriched_loans,
    upb_weighted_mean,
)
from app.services.scenario_grid import COHORTS
from app.services.severity import lookup_severity_row

# HPA shock grid for CLTV migration (fraction change in property value).
HPA_SHOCKS = (-0.30, -0.20, -0.10, -0.05, 0.0, 0.05, 0.10)

RI_BANDS = (
    ("<0", -100.0, 0.0),
    ("0-1", 0.0, 1.0),
    ("1-2", 1.0, 2.0),
    ("2+", 2.0, 100.0),
)

LARGE_LOAN_N = 15


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return f


def _shocked_cltv(loan: dict[str, Any], hpa: float) -> float | None:
    """Recompute CLTV after property-value shock. hpa is fractional (e.g. -0.1).

    Uses derived current_cltv when present: CLTV' = CLTV / (1 + hpa).
    """
    if hpa <= -1.0:
        return None
    cur = _num(loan.get("current_cltv"))
    if cur is not None:
        return cur / (1.0 + hpa)
    upb = _num(loan.get("current_loan_amount"))
    mrv = _num(loan.get("most_recent_property_value"))
    if upb is None or mrv is None or mrv <= 0:
        return None
    shocked_val = mrv * (1.0 + hpa)
    if shocked_val <= 0:
        return None
    return upb / shocked_val


def _cltv_band_counts(
    loans: list[dict[str, Any]],
    *,
    hpa: float,
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {
        label: {"bucket": label, "loan_count": 0, "upb": 0.0}
        for label, _, _ in LTV_BUCKETS
    }
    buckets["missing"] = {"bucket": "missing", "loan_count": 0, "upb": 0.0}
    for loan in loans:
        if hpa == 0.0:
            cltv = _num(loan.get("current_cltv"))
            if cltv is None:
                cltv = _num(loan.get("original_cltv"))
        else:
            cltv = _shocked_cltv(loan, hpa)
            if cltv is None:
                cltv = _num(loan.get("current_cltv"))
        label = bucket_ordered(cltv, LTV_BUCKETS)
        buckets[label]["loan_count"] += 1
        buckets[label]["upb"] += float(loan.get("current_loan_amount") or 0)
    order = [b[0] for b in LTV_BUCKETS] + ["missing"]
    return [buckets[k] for k in order if buckets[k]["loan_count"]]


def cohort_scorecard(loans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Side-by-side UPB-weighted credit-quality metrics by k-proto cohort."""
    rows: list[dict[str, Any]] = []
    for cohort_id in COHORTS:
        subset = [loan for loan in loans if loan.get("cohort") == cohort_id]
        kpis = kpi_summary(subset)
        rows.append(
            {
                "cohort": cohort_id,
                "cohort_display": COHORT_DISPLAY.get(cohort_id, cohort_id),
                "loan_count": kpis["loan_count"],
                "upb": kpis["upb"],
                "wa_fico": kpis["wa_fico"],
                "wa_cltv": kpis["wa_cltv"],
                "wa_current_cltv": upb_weighted_mean(subset, "current_cltv"),
                "wa_dti": kpis["wa_dti"],
                "wa_dscr": kpis["wa_dscr"],
                "wa_ri": kpis["wa_ri"],
                "wac": kpis["wac"],
                "wam": kpis["wam"],
                "wa_age": kpis["wa_age"],
                "flagged_loan_count": kpis["flagged_loan_count"],
                "upb_share": None,
            }
        )
    total_upb = sum(r["upb"] for r in rows) or 0.0
    for row in rows:
        row["upb_share"] = (row["upb"] / total_upb) if total_upb else None
    return rows


def fico_cltv_heatmap(loans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """UPB by FICO band × original CLTV band."""
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    fico_order = [b[0] for b in FICO_BUCKETS] + ["missing"]
    cltv_order = [b[0] for b in LTV_BUCKETS] + ["missing"]
    for loan in loans:
        fico_b = loan.get("fico_band") or bucket_ordered(
            _num(loan.get("original_fico")), FICO_BUCKETS
        )
        cltv_b = loan.get("cltv_band_original") or bucket_ordered(
            _num(loan.get("original_cltv")), LTV_BUCKETS
        )
        key = (fico_b, cltv_b)
        slot = cells.setdefault(
            key,
            {
                "fico_band": fico_b,
                "cltv_band": cltv_b,
                "loan_count": 0,
                "upb": 0.0,
            },
        )
        slot["loan_count"] += 1
        slot["upb"] += float(loan.get("current_loan_amount") or 0)
    out = list(cells.values())
    out.sort(
        key=lambda r: (
            fico_order.index(r["fico_band"])
            if r["fico_band"] in fico_order
            else 99,
            cltv_order.index(r["cltv_band"])
            if r["cltv_band"] in cltv_order
            else 99,
        )
    )
    return out


def ri_seasoning_heatmap(loans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """UPB by refinance-incentive band × seasoning (age) band."""
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    ri_order = [b[0] for b in RI_BANDS] + ["missing"]
    age_order = [b[0] for b in AGE_BUCKETS] + ["missing"]
    for loan in loans:
        ri_b = bucket_ordered(_num(loan.get("refinance_incentive")), RI_BANDS)
        age_b = loan.get("age_band") or bucket_ordered(
            _num(loan.get("loan_age_months")), AGE_BUCKETS
        )
        key = (ri_b, age_b)
        slot = cells.setdefault(
            key,
            {
                "ri_band": ri_b,
                "age_band": age_b,
                "loan_count": 0,
                "upb": 0.0,
            },
        )
        slot["loan_count"] += 1
        slot["upb"] += float(loan.get("current_loan_amount") or 0)
    out = list(cells.values())
    out.sort(
        key=lambda r: (
            ri_order.index(r["ri_band"]) if r["ri_band"] in ri_order else 99,
            age_order.index(r["age_band"]) if r["age_band"] in age_order else 99,
        )
    )
    return out


def hpa_stress_payload(loans: list[dict[str, Any]]) -> dict[str, Any]:
    """CLTV migration under property-value shocks (requires most_recent value)."""
    with_value = [
        loan
        for loan in loans
        if _num(loan.get("most_recent_property_value")) is not None
        and _num(loan.get("most_recent_property_value")) > 0
    ]
    coverage = (len(with_value) / len(loans)) if loans else 0.0
    if coverage < 0.5:
        return {
            "available": False,
            "reason": "Current property value coverage too low for HPA stress",
            "coverage": coverage,
        }

    shocks: list[dict[str, Any]] = []
    for hpa in HPA_SHOCKS:
        bands = _cltv_band_counts(with_value, hpa=hpa)
        wa_cltv = None
        num = den = 0.0
        for loan in with_value:
            cltv = (
                _num(loan.get("current_cltv"))
                if hpa == 0.0
                else _shocked_cltv(loan, hpa)
            )
            w = _num(loan.get("current_loan_amount"))
            if cltv is None or w is None or w <= 0:
                continue
            num += cltv * w
            den += w
        if den > 0:
            wa_cltv = num / den
        high_upb = sum(b["upb"] for b in bands if b["bucket"] in ("80-90", "90+"))
        total_upb = sum(b["upb"] for b in bands) or 1.0
        shocks.append(
            {
                "hpa": hpa,
                "wa_cltv": wa_cltv,
                "high_cltv_upb_share": high_upb / total_upb,
                "bands": bands,
            }
        )

    return {
        "available": True,
        "coverage": coverage,
        "loan_count": len(with_value),
        "shocks": shocks,
        "default_hpa": 0.0,
    }


def loss_severity_payload(loans: list[dict[str, Any]]) -> dict[str, Any]:
    """UPB-weighted Urban/Freddie severity — no PD, no expected loss."""
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    cohort_sev: dict[str, dict[str, Any]] = {}
    matched = 0
    for loan in loans:
        row = lookup_severity_row(
            original_fico=loan.get("original_fico"),
            original_ltv=loan.get("original_ltv"),
        )
        if row is None:
            continue
        matched += 1
        sev = float(row["severity_pct"]) / 100.0  # store as 0–1
        rec = float(row["recovery_rate"])
        w = float(loan.get("current_loan_amount") or 0)
        fico_b = loan.get("fico_band") or "missing"
        cltv_b = loan.get("cltv_band_original") or "missing"
        key = (fico_b, cltv_b)
        slot = cells.setdefault(
            key,
            {
                "fico_band": fico_b,
                "cltv_band": cltv_b,
                "loan_count": 0,
                "upb": 0.0,
                "sev_upb": 0.0,
                "rec_upb": 0.0,
            },
        )
        slot["loan_count"] += 1
        slot["upb"] += w
        slot["sev_upb"] += sev * w
        slot["rec_upb"] += rec * w

        cid = loan.get("cohort") or "unknown"
        cslot = cohort_sev.setdefault(
            cid,
            {
                "cohort": cid,
                "cohort_display": COHORT_DISPLAY.get(cid, cid),
                "loan_count": 0,
                "upb": 0.0,
                "sev_upb": 0.0,
                "rec_upb": 0.0,
            },
        )
        cslot["loan_count"] += 1
        cslot["upb"] += w
        cslot["sev_upb"] += sev * w
        cslot["rec_upb"] += rec * w

    if matched == 0:
        return {
            "available": False,
            "reason": "No Urban/Freddie severity cells matched the book",
        }

    heat = []
    for slot in cells.values():
        heat.append(
            {
                "fico_band": slot["fico_band"],
                "cltv_band": slot["cltv_band"],
                "loan_count": slot["loan_count"],
                "upb": slot["upb"],
                "wa_severity": (slot["sev_upb"] / slot["upb"]) if slot["upb"] else None,
                "wa_recovery": (slot["rec_upb"] / slot["upb"]) if slot["upb"] else None,
            }
        )

    by_cohort = []
    for cid in COHORTS:
        slot = cohort_sev.get(cid)
        if not slot:
            continue
        by_cohort.append(
            {
                "cohort": cid,
                "cohort_display": slot["cohort_display"],
                "loan_count": slot["loan_count"],
                "upb": slot["upb"],
                "wa_severity": (slot["sev_upb"] / slot["upb"]) if slot["upb"] else None,
                "wa_recovery": (slot["rec_upb"] / slot["upb"]) if slot["upb"] else None,
            }
        )

    pool_upb = sum(s["upb"] for s in cohort_sev.values()) or 0.0
    pool_sev = (
        sum(s["sev_upb"] for s in cohort_sev.values()) / pool_upb if pool_upb else None
    )
    pool_rec = (
        sum(s["rec_upb"] for s in cohort_sev.values()) / pool_upb if pool_upb else None
    )

    return {
        "available": True,
        "source": "Urban/Freddie Table 4 severity → recovery = 1 − severity",
        "note": "Severity / recovery only — no PD or expected loss",
        "matched_loans": matched,
        "pool_wa_severity": pool_sev,
        "pool_wa_recovery": pool_rec,
        "by_cohort": by_cohort,
        "heatmap": heat,
    }


def large_loans_table(loans: list[dict[str, Any]], n: int = LARGE_LOAN_N) -> list[dict[str, Any]]:
    ranked = sorted(
        loans,
        key=lambda loan: float(loan.get("current_loan_amount") or 0),
        reverse=True,
    )[:n]
    out = []
    for loan in ranked:
        out.append(
            {
                "cohort_display": loan.get("cohort_display")
                or COHORT_DISPLAY.get(loan.get("cohort") or "", loan.get("cohort")),
                "upb": loan.get("current_loan_amount"),
                "original_fico": loan.get("original_fico"),
                "original_cltv": loan.get("original_cltv"),
                "state": loan.get("state"),
                "occupancy": loan.get("occupancy"),
                "loan_purpose": loan.get("loan_purpose"),
                "documentation_type": loan.get("documentation_type"),
            }
        )
    return out


def historical_dq_payload(loans: list[dict[str, Any]]) -> dict[str, Any]:
    """Gate: need DQ history / material delinquency — not a sparse point-in-time flag."""
    dq = [loan for loan in loans if (_num(loan.get("days_delinquent")) or 0) > 0]
    # Synthetic Minimum Case has ~6 DQ loans and no vintage history series.
    if len(dq) < max(20, int(0.02 * len(loans) if loans else 0)):
        return {
            "available": False,
            "reason": "No DQ history series; point-in-time delinquency too sparse",
            "dq_loan_count": len(dq),
            "loan_count": len(loans),
        }
    # If a future tape has material DQ, return a simple status cut (still not history).
    bands = (
        ("Current", 0, 1),
        ("30", 1, 60),
        ("60", 60, 90),
        ("90+", 90, 100000),
    )
    rows = []
    for label, lo, hi in bands:
        subset = [
            loan
            for loan in loans
            if lo <= (_num(loan.get("days_delinquent")) or 0) < hi
        ]
        rows.append(
            {
                "bucket": label,
                "loan_count": len(subset),
                "upb": sum(float(loan.get("current_loan_amount") or 0) for loan in subset),
            }
        )
    return {"available": True, "status": rows}


def tranche_payload() -> dict[str, Any]:
    repo = TrancheRepository()
    tranches = repo.list()
    if not tranches:
        return {
            "available": False,
            "reason": "Tranche waterfall not wired",
            "stub": repo.neon_stub_status(),
        }
    return {"available": True, "tranches": [t.model_dump() for t in tranches]}


def build_investor_analysis(
    loans: list[dict[str, Any]] | None = None,
    *,
    cohorts: list[str] | None = None,
) -> dict[str, Any]:
    source = "caller"
    if loans is None:
        loans, source = load_enriched_loans()
    filtered = filter_loans(loans, cohorts=cohorts) if cohorts else list(loans)

    ri_present = sum(
        1 for loan in filtered if loan.get("refinance_incentive") is not None
    )
    value_present = sum(
        1
        for loan in filtered
        if _num(loan.get("most_recent_property_value")) is not None
        and _num(loan.get("most_recent_property_value")) > 0
    )

    scorecard = cohort_scorecard(filtered)
    heat = fico_cltv_heatmap(filtered)
    hpa = hpa_stress_payload(filtered)
    dti = aggregate_categorical(filtered, "dti_band")
    dscr = aggregate_categorical(filtered, "dscr_band")
    docs = aggregate_categorical(filtered, "documentation_type")
    occ = aggregate_categorical(filtered, "occupancy")
    purpose = aggregate_categorical(filtered, "loan_purpose")
    states = aggregate_categorical(filtered, "state")
    ri_heat = (
        ri_seasoning_heatmap(filtered)
        if ri_present == len(filtered) and filtered
        else []
    )
    severity = loss_severity_payload(filtered)
    historical = historical_dq_payload(filtered)
    tranche = tranche_payload()
    kpis = kpi_summary(filtered)

    sections = {
        "scorecard": {
            "available": bool(scorecard),
            "viz": "grouped_bars",
            "title": "Cohort Credit Quality",
            "rows": scorecard,
        },
        "fico_cltv": {
            "available": bool(heat),
            "viz": "heatmap",
            "title": "FICO × CLTV",
            "cells": heat,
            "fico_bands": [b[0] for b in FICO_BUCKETS],
            "cltv_bands": [b[0] for b in LTV_BUCKETS],
        },
        "hpa_stress": {
            **hpa,
            "viz": "line_migration",
            "title": "HPA Stress — CLTV Migration",
        },
        "affordability": {
            "available": True,
            "viz": "histogram_donut",
            "title": "Affordability / Documentation",
            "dti": dti,
            "dscr": dscr,
            "documentation": docs,
            "dti_coverage": kpis["coverage"]["dti"],
            "dscr_coverage": kpis["coverage"]["dscr"],
        },
        "mix": {
            "available": True,
            "viz": "stacked_bars_table",
            "title": "Occupancy / Purpose / Large Loans",
            "occupancy": occ,
            "loan_purpose": purpose,
            "large_loans": large_loans_table(filtered),
        },
        "geo": {
            "available": bool(states),
            "viz": "map_table",
            "title": "Geographic Concentration",
            "states": states,
            "top_states": states[:10],
        },
        "ri_seasoning": {
            "available": bool(ri_heat),
            "viz": "heatmap",
            "title": "Refinance Incentive × Seasoning",
            "cells": ri_heat,
            "ri_bands": [b[0] for b in RI_BANDS],
            "age_bands": [b[0] for b in AGE_BUCKETS],
            "reason": None
            if ri_heat
            else "Refinance incentive not fully populated on tape",
        },
        "historical_dq": {
            **historical,
            "viz": "status_bars",
            "title": "Historical Performance",
        },
        "loss_severity": {
            **severity,
            "viz": "severity_heat",
            "title": "Loss Severity (Assumptions)",
        },
        "tranche": {
            **tranche,
            "viz": "ce_sensitivity",
            "title": "Tranche Protection",
        },
    }

    return {
        "source": source,
        "kpis": kpis,
        "cohorts": [
            {
                "id": c,
                "label": COHORT_DISPLAY[c],
                "loan_count": sum(1 for loan in loans if loan.get("cohort") == c),
            }
            for c in COHORTS
        ],
        "coverage": {
            "property_value": value_present,
            "refinance_incentive": ri_present,
            "n": len(filtered),
        },
        "sections": sections,
        "skipped": [
            {
                "id": sid,
                "title": sec.get("title"),
                "reason": sec.get("reason") or "Unavailable",
            }
            for sid, sec in sections.items()
            if not sec.get("available")
        ],
    }


def analyze_investor(
    *,
    cohorts: list[str] | None = None,
) -> dict[str, Any]:
    loans, source = load_enriched_loans()
    payload = build_investor_analysis(loans, cohorts=cohorts)
    payload["source"] = source
    return payload
