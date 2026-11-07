"""Loan-level collateral research helpers (enrichment, buckets, UPB weights).

Does not change cohort assignment. Cohort filter keys are the three k-prototype
cluster-tape names; Excel short cohort labels are ignored for filtering.
"""

from __future__ import annotations

from typing import Any

from app.services.scenario_grid import (
    COHORT_HIGH_LTV_STRONG,
    COHORT_HIGH_LTV_WEAK,
    COHORT_LOW_LTV_WEAK,
    COHORTS,
)

# Compact Title Case display labels (assignment keys unchanged).
COHORT_DISPLAY = {
    COHORT_LOW_LTV_WEAK: "LLTV Weak RI",
    COHORT_HIGH_LTV_STRONG: "HLTV Strong RI",
    COHORT_HIGH_LTV_WEAK: "HLTV Weak RI",
}

FICO_BUCKETS = (
    ("<660", 0, 660),
    ("660-699", 660, 700),
    ("700-739", 700, 740),
    ("740-779", 740, 780),
    ("780+", 780, 10000),
)

LTV_BUCKETS = (
    ("<60", 0.0, 0.60),
    ("60-70", 0.60, 0.70),
    ("70-80", 0.70, 0.80),
    ("80-90", 0.80, 0.90),
    ("90+", 0.90, 10.0),
)

DTI_BUCKETS = (
    ("<30", 0.0, 0.30),
    ("30-36", 0.30, 0.36),
    ("36-43", 0.36, 0.43),
    ("43-50", 0.43, 0.50),
    ("50+", 0.50, 10.0),
)

DSCR_BUCKETS = (
    ("<1.0", 0.0, 1.0),
    ("1.0-1.25", 1.0, 1.25),
    ("1.25-1.5", 1.25, 1.5),
    ("1.5+", 1.5, 100.0),
)

AGE_BUCKETS = (
    ("0-6", 0, 7),
    ("7-12", 7, 13),
    ("13-24", 13, 25),
    ("25+", 25, 10000),
)

# Research refs shown on info icons (open / free sources used elsewhere in Project).
SECTION_REFS = {
    "kpis": {
        "title": "Collateral KPIs",
        "refs": [
            "Fitch U.S. RMBS Loan Loss Model Criteria — FICO/LTV/CLTV as core PD drivers",
            "BlackRock NAIC Non-Agency RMBS (2015) — pool strata on FICO, LTV, state, IO",
        ],
    },
    "fico": {
        "title": "FICO Distribution",
        "refs": [
            "KBRA Non-QM Default Study — FICO <660 ~10% cum. default vs >760 <2%",
            "Urban Institute — FICO dominates DTI for default in PLS samples",
        ],
    },
    "ltv": {
        "title": "LTV / CLTV",
        "refs": [
            "Fitch — sLTV / OCLTV among most predictive credit drivers",
            "S&P RMBS criteria — LTV curves dominate foreclosure frequency",
        ],
    },
    "heatmap": {
        "title": "FICO × LTV Heatmap",
        "refs": [
            "Urban/Freddie Table 4 — severity by FICO × LTV bands (agency + MI context)",
            "Fitch PD — joint FICO and LTV risk layering",
        ],
    },
    "dti_dscr": {
        "title": "DTI / DSCR",
        "refs": [
            "Fitch / S&P — DTI affordability; DSCR investor multiples",
            "LSEG Yield Book NQM — CDR uses DSCR; DTI on income path",
        ],
    },
    "documentation": {
        "title": "Documentation Mix",
        "refs": [
            "KBRA — Full Doc lower defaults; Alt Doc uplift",
            "LSEG / Fitch — documentation type drives VPR and CDR",
        ],
    },
    "mix": {
        "title": "Occupancy / Purpose / Property",
        "refs": [
            "Fitch / S&P categorical PD uplifts — investor, cash-out, condo/2–4",
            "BlackRock — purpose and property in non-agency cluster vars",
        ],
    },
    "coupon": {
        "title": "Coupon / RI / Seasoning",
        "refs": [
            "LSEG NQM VPR — SATO / refinance incentive",
            "BlackRock — incentive and seasoning in prepay clusters",
        ],
    },
    "geo": {
        "title": "Geography",
        "refs": [
            "BlackRock non-agency — state as static cluster dimension",
            "Fannie Mae state foreclosure time frames — recovery lag context",
        ],
    },
    "explorer": {
        "title": "Exception Explorer",
        "refs": [
            "KBRA risk layering — high CLTV + low FICO + alt doc",
            "Diligence flags are heuristics, not model PD or expected loss",
        ],
    },
}

FIELD_INVENTORY = {
    "available": [
        {"field": "loan_id", "spec": "Loan ID (explorer only)", "coverage_note": "100%"},
        {"field": "current_loan_amount", "spec": "UPB weight", "coverage_note": "100%"},
        {"field": "original_fico", "spec": "FICO (original only)", "coverage_note": "100%"},
        {"field": "original_ltv", "spec": "Original LTV", "coverage_note": "100%"},
        {"field": "original_cltv", "spec": "Original CLTV", "coverage_note": "100%"},
        {
            "field": "current_ltv_derived",
            "spec": "Current LTV (derived)",
            "coverage_note": "balances ÷ most_recent_property_value",
        },
        {
            "field": "current_cltv_derived",
            "spec": "Current CLTV (derived)",
            "coverage_note": "(UPB + liens) ÷ most_recent_property_value",
        },
        {"field": "originator_dti", "spec": "DTI", "coverage_note": "~57% (DTI path)"},
        {"field": "dscr", "spec": "DSCR", "coverage_note": "~43% (DSCR path)"},
        {"field": "documentation_type", "spec": "Documentation", "coverage_note": "100%"},
        {"field": "occupancy", "spec": "Occupancy", "coverage_note": "100%"},
        {"field": "loan_purpose", "spec": "Purpose", "coverage_note": "100%"},
        {"field": "property_type", "spec": "Property type", "coverage_note": "100%"},
        {"field": "current_interest_rate", "spec": "Coupon", "coverage_note": "100%"},
        {"field": "refinance_incentive", "spec": "Refinance incentive", "coverage_note": "100%"},
        {"field": "loan_age_months", "spec": "Seasoning", "coverage_note": "100%"},
        {"field": "state", "spec": "State", "coverage_note": "100%"},
        {"field": "days_delinquent", "spec": "Delinquency", "coverage_note": "100%"},
        {
            "field": "cohort_kproto",
            "spec": "Cohort filter (cluster-tape)",
            "coverage_note": "100% via loan_id overlay",
        },
    ],
    "missing": [
        {"field": "current_fico", "spec": "Current / updated FICO", "reason": "Not on tape"},
        {
            "field": "current_ltv",
            "spec": "Issuer-provided current LTV/CLTV",
            "reason": "Not on tape; derived proxy only",
        },
        {
            "field": "market_rate_curve",
            "spec": "Live market rate for RI",
            "reason": "Only stored refinance_incentive; no benchmark series",
        },
        {
            "field": "loan_pd_loss",
            "spec": "Loan-level PD / expected loss",
            "reason": "Out of scope — do not invent",
        },
    ],
}


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _int(v: Any) -> int | None:
    f = _num(v)
    if f is None:
        return None
    return int(f)


def bucket_ordered(value: float | None, bands: tuple[tuple[str, float, float], ...]) -> str:
    if value is None:
        return "missing"
    for label, lo, hi in bands:
        if lo <= value < hi:
            return label
    return bands[-1][0]


def derived_current_ltv(
    current_upb: float | None,
    most_recent_value: float | None,
) -> float | None:
    if current_upb is None or most_recent_value is None or most_recent_value <= 0:
        return None
    return current_upb / most_recent_value


def derived_current_cltv(
    current_upb: float | None,
    senior: float | None,
    junior: float | None,
    most_recent_value: float | None,
) -> float | None:
    if most_recent_value is None or most_recent_value <= 0:
        return None
    if current_upb is None:
        return None
    total = current_upb + (senior or 0.0) + (junior or 0.0)
    return total / most_recent_value


def risk_flags(loan: dict[str, Any]) -> list[str]:
    """Diligence heuristics only — not model PD."""
    flags: list[str] = []
    fico = _int(loan.get("original_fico"))
    if fico is not None and fico < 660:
        flags.append("Low FICO")
    for key, label in (
        ("original_ltv", "High Original LTV"),
        ("original_cltv", "High Original CLTV"),
        ("current_ltv", "High Current LTV"),
        ("current_cltv", "High Current CLTV"),
    ):
        v = _num(loan.get(key))
        if v is not None and v >= 0.90:
            flags.append(f"{label} ≥90%")
        elif v is not None and v >= 0.80:
            flags.append(f"{label} ≥80%")
    dti = _num(loan.get("originator_dti"))
    if dti is not None and dti >= 0.45:
        flags.append("High DTI")
    dscr = _num(loan.get("dscr"))
    if dscr is not None and dscr < 1.0:
        flags.append("DSCR <1.0")
    dq = _int(loan.get("days_delinquent"))
    if dq is not None and dq > 0:
        flags.append("Delinquent")
    doc = str(loan.get("documentation_type") or "").strip().lower()
    if doc and "full" not in doc:
        flags.append("Alt Documentation")
    occ = str(loan.get("occupancy") or "").strip().lower()
    if "investor" in occ:
        flags.append("Investor Occupancy")
    purpose = str(loan.get("loan_purpose") or "").strip().lower()
    if "cash-out" in purpose or "cash out" in purpose:
        flags.append("Cash-Out")
    return flags


def enrich_loan(raw: dict[str, Any], cohort_kproto: str | None) -> dict[str, Any]:
    """Normalize one tape row for collateral research."""
    upb = _num(raw.get("current_loan_amount"))
    mrv = _num(raw.get("most_recent_property_value"))
    senior = _num(raw.get("senior_lien_current_balance"))
    junior = _num(raw.get("junior_lien_balance"))
    cur_ltv = derived_current_ltv(upb, mrv)
    cur_cltv = derived_current_cltv(upb, senior, junior, mrv)
    row = {
        "loan_id": str(raw.get("loan_id") or ""),
        "current_loan_amount": upb,
        "current_interest_rate": _num(raw.get("current_interest_rate")),
        "remaining_term": _int(raw.get("remaining_term")),
        "loan_age_months": _int(raw.get("loan_age_months")),
        "original_fico": _int(raw.get("original_fico")),
        "original_ltv": _num(raw.get("original_ltv")),
        "original_cltv": _num(raw.get("original_cltv")),
        "current_ltv": cur_ltv,
        "current_cltv": cur_cltv,
        "most_recent_property_value": mrv,
        "state": (str(raw["state"]).strip().upper() if raw.get("state") not in (None, "") else None),
        "postal_code": str(raw["postal_code"]) if raw.get("postal_code") not in (None, "") else None,
        "property_type": raw.get("property_type"),
        "occupancy": raw.get("occupancy"),
        "loan_purpose": raw.get("loan_purpose"),
        "documentation_type": raw.get("documentation_type"),
        "originator_dti": _num(raw.get("originator_dti")),
        "dscr": _num(raw.get("dscr")),
        "days_delinquent": _int(raw.get("days_delinquent")),
        "refinance_incentive": _num(raw.get("refinance_incentive")),
        "has_mi": bool(raw.get("has_mi")) if raw.get("has_mi") is not None else True,
        "excel_cohort": raw.get("cohort"),
        "cohort": cohort_kproto,
        "cohort_display": COHORT_DISPLAY.get(cohort_kproto or "", cohort_kproto),
        "fico_band": bucket_ordered(_num(raw.get("original_fico")), FICO_BUCKETS),
        "ltv_band_original": bucket_ordered(_num(raw.get("original_ltv")), LTV_BUCKETS),
        "cltv_band_original": bucket_ordered(_num(raw.get("original_cltv")), LTV_BUCKETS),
        "ltv_band_current": bucket_ordered(cur_ltv, LTV_BUCKETS),
        "cltv_band_current": bucket_ordered(cur_cltv, LTV_BUCKETS),
        "dti_band": bucket_ordered(_num(raw.get("originator_dti")), DTI_BUCKETS),
        "dscr_band": bucket_ordered(_num(raw.get("dscr")), DSCR_BUCKETS),
        "age_band": bucket_ordered(_num(raw.get("loan_age_months")), AGE_BUCKETS),
    }
    row["risk_flags"] = risk_flags(row)
    row["risk_flag_count"] = len(row["risk_flags"])
    return row


def upb_weighted_mean(loans: list[dict[str, Any]], field: str) -> float | None:
    num = 0.0
    den = 0.0
    for loan in loans:
        w = _num(loan.get("current_loan_amount"))
        v = _num(loan.get(field))
        if w is None or w <= 0 or v is None:
            continue
        num += v * w
        den += w
    if den <= 0:
        return None
    return num / den


def coverage(loans: list[dict[str, Any]], field: str) -> dict[str, Any]:
    n = len(loans)
    present = sum(1 for loan in loans if loan.get(field) is not None and loan.get(field) != "")
    return {
        "field": field,
        "n": n,
        "present": present,
        "missing": n - present,
        "pct": (present / n) if n else None,
    }


def aggregate_categorical(
    loans: list[dict[str, Any]],
    field: str,
    *,
    order: list[str] | None = None,
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for loan in loans:
        raw = loan.get(field)
        key = "missing" if raw is None or raw == "" else str(raw)
        slot = buckets.setdefault(
            key, {"bucket": key, "loan_count": 0, "upb": 0.0}
        )
        slot["loan_count"] += 1
        slot["upb"] += float(loan.get("current_loan_amount") or 0)
    rows = list(buckets.values())
    if order:
        rank = {b: i for i, b in enumerate(order)}
        rows.sort(key=lambda r: (rank.get(r["bucket"], 999), -r["upb"]))
    else:
        rows.sort(key=lambda r: (-r["upb"], r["bucket"]))
    return rows


def fico_ltv_heatmap(
    loans: list[dict[str, Any]],
    *,
    ltv_field: str = "original_ltv",
) -> list[dict[str, Any]]:
    """UPB by FICO band × LTV band."""
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    fico_order = [b[0] for b in FICO_BUCKETS] + ["missing"]
    ltv_order = [b[0] for b in LTV_BUCKETS] + ["missing"]
    for loan in loans:
        fico_b = bucket_ordered(_num(loan.get("original_fico")), FICO_BUCKETS)
        ltv_b = bucket_ordered(_num(loan.get(ltv_field)), LTV_BUCKETS)
        key = (fico_b, ltv_b)
        slot = cells.setdefault(
            key,
            {
                "fico_band": fico_b,
                "ltv_band": ltv_b,
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
            ltv_order.index(r["ltv_band"]) if r["ltv_band"] in ltv_order else 99,
        )
    )
    return out


def filter_loans(
    loans: list[dict[str, Any]],
    *,
    cohorts: list[str] | None = None,
    fico_bands: list[str] | None = None,
    ltv_bands: list[str] | None = None,
    ltv_mode: str = "original",
    states: list[str] | None = None,
    documentation_types: list[str] | None = None,
    occupancies: list[str] | None = None,
    purposes: list[str] | None = None,
    property_types: list[str] | None = None,
    dti_bands: list[str] | None = None,
    dscr_bands: list[str] | None = None,
    age_bands: list[str] | None = None,
    risk_only: bool = False,
) -> list[dict[str, Any]]:
    ltv_key = "ltv_band_current" if ltv_mode == "current" else "ltv_band_original"

    def ok(loan: dict[str, Any]) -> bool:
        if cohorts and loan.get("cohort") not in cohorts:
            return False
        if fico_bands and loan.get("fico_band") not in fico_bands:
            return False
        if ltv_bands and loan.get(ltv_key) not in ltv_bands:
            return False
        if states and loan.get("state") not in states:
            return False
        if documentation_types and loan.get("documentation_type") not in documentation_types:
            return False
        if occupancies and loan.get("occupancy") not in occupancies:
            return False
        if purposes and loan.get("loan_purpose") not in purposes:
            return False
        if property_types and loan.get("property_type") not in property_types:
            return False
        if dti_bands and loan.get("dti_band") not in dti_bands:
            return False
        if dscr_bands and loan.get("dscr_band") not in dscr_bands:
            return False
        if age_bands and loan.get("age_band") not in age_bands:
            return False
        if risk_only and not loan.get("risk_flags"):
            return False
        return True

    return [loan for loan in loans if ok(loan)]


def kpi_summary(loans: list[dict[str, Any]]) -> dict[str, Any]:
    upb = sum(float(loan.get("current_loan_amount") or 0) for loan in loans)
    flagged = sum(1 for loan in loans if loan.get("risk_flags"))
    return {
        "loan_count": len(loans),
        "upb": upb,
        "wac": upb_weighted_mean(loans, "current_interest_rate"),
        "wam": upb_weighted_mean(loans, "remaining_term"),
        "wa_fico": upb_weighted_mean(loans, "original_fico"),
        "wa_ltv": upb_weighted_mean(loans, "original_ltv"),
        "wa_cltv": upb_weighted_mean(loans, "original_cltv"),
        "wa_current_ltv": upb_weighted_mean(loans, "current_ltv"),
        "wa_dti": upb_weighted_mean(loans, "originator_dti"),
        "wa_dscr": upb_weighted_mean(loans, "dscr"),
        "wa_ri": upb_weighted_mean(loans, "refinance_incentive"),
        "wa_age": upb_weighted_mean(loans, "loan_age_months"),
        "flagged_loan_count": flagged,
        "coverage": {
            "fico": coverage(loans, "original_fico"),
            "ltv": coverage(loans, "original_ltv"),
            "cltv": coverage(loans, "original_cltv"),
            "current_ltv": coverage(loans, "current_ltv"),
            "dti": coverage(loans, "originator_dti"),
            "dscr": coverage(loans, "dscr"),
            "ri": coverage(loans, "refinance_incentive"),
        },
    }


def build_observations(loans: list[dict[str, Any]], kpis: dict[str, Any]) -> dict[str, str]:
    """Short live observations from filtered data (not canned marketing copy)."""
    n = kpis["loan_count"]
    if n == 0:
        empty = "No loans in the current filter."
        return {k: empty for k in (
            "fico", "ltv", "heatmap", "dti_dscr", "documentation", "mix", "coupon", "geo", "explorer"
        )}

    fico_rows = aggregate_categorical(loans, "fico_band")  # UPB-desc for "largest"
    top_fico = fico_rows[0] if fico_rows else None
    wa_fico = kpis.get("wa_fico")
    fico_obs = (
        f"WA FICO {wa_fico:.0f} on {n:,} loans"
        if wa_fico is not None
        else f"{n:,} loans; FICO coverage incomplete"
    )
    if top_fico:
        share = (top_fico["upb"] / kpis["upb"] * 100) if kpis["upb"] else 0
        fico_obs += f"; largest band {top_fico['bucket']} holds {share:.0f}% of UPB"

    ltv_rows = aggregate_categorical(
        loans, "ltv_band_original", order=[b[0] for b in LTV_BUCKETS] + ["missing"]
    )
    wa_ltv = kpis.get("wa_ltv")
    high_ltv_upb = sum(
        r["upb"] for r in ltv_rows if r["bucket"] in ("80-90", "90+")
    )
    high_share = (high_ltv_upb / kpis["upb"] * 100) if kpis["upb"] else 0
    ltv_obs = (
        f"WA original LTV {(wa_ltv * 100):.1f}%; ≥80% LTV is {high_share:.0f}% of UPB"
        if wa_ltv is not None
        else f"≥80% original LTV is {high_share:.0f}% of UPB"
    )

    heat = fico_ltv_heatmap(loans)
    heat_sorted = sorted(heat, key=lambda r: -r["upb"])
    if heat_sorted:
        top = heat_sorted[0]
        heat_obs = (
            f"Largest cell: FICO {top['fico_band']} × LTV {top['ltv_band']} "
            f"({top['loan_count']:,} loans)"
        )
    else:
        heat_obs = "No FICO × LTV cells"

    dti_cov = kpis["coverage"]["dti"]["pct"] or 0
    dscr_cov = kpis["coverage"]["dscr"]["pct"] or 0
    dti_obs = (
        f"DTI on {dti_cov:.0%} of loans (WA {(kpis['wa_dti'] * 100):.1f}% when present); "
        f"DSCR on {dscr_cov:.0%}"
        if kpis.get("wa_dti") is not None
        else f"DTI coverage {dti_cov:.0%}; DSCR coverage {dscr_cov:.0%}"
    )

    doc_rows = aggregate_categorical(loans, "documentation_type")
    if doc_rows:
        top_doc = doc_rows[0]
        share = (top_doc["upb"] / kpis["upb"] * 100) if kpis["upb"] else 0
        doc_obs = f"{top_doc['bucket']} leads at {share:.0f}% of UPB ({len(doc_rows)} types)"
    else:
        doc_obs = "No documentation mix"

    occ = aggregate_categorical(loans, "occupancy")
    purpose = aggregate_categorical(loans, "loan_purpose")
    mix_obs = (
        f"Top occupancy {occ[0]['bucket'] if occ else '—'}; "
        f"top purpose {purpose[0]['bucket'] if purpose else '—'}"
    )

    wa_rate = kpis.get("wac")
    wa_ri = kpis.get("wa_ri")
    wa_age = kpis.get("wa_age")
    coupon_obs = (
        f"WAC {(wa_rate * 100):.2f}%; WA RI {wa_ri:.2f}; WA age {wa_age:.1f} mo"
        if wa_rate is not None and wa_ri is not None and wa_age is not None
        else "Coupon / RI / age incomplete for weighted averages"
    )

    states = aggregate_categorical(loans, "state")
    if states:
        top10_upb = sum(r["upb"] for r in states[:10])
        share = (top10_upb / kpis["upb"] * 100) if kpis["upb"] else 0
        geo_obs = (
            f"Top state {states[0]['bucket']} ({states[0]['loan_count']:,} loans); "
            f"top 10 states = {share:.0f}% of UPB"
        )
    else:
        geo_obs = "No state concentration"

    explorer_obs = (
        f"{kpis['flagged_loan_count']:,} of {n:,} loans carry ≥1 diligence flag"
    )

    return {
        "fico": fico_obs,
        "ltv": ltv_obs,
        "heatmap": heat_obs,
        "dti_dscr": dti_obs,
        "documentation": doc_obs,
        "mix": mix_obs,
        "coupon": coupon_obs,
        "geo": geo_obs,
        "explorer": explorer_obs,
    }


def analyze(
    loans: list[dict[str, Any]],
    *,
    ltv_mode: str = "original",
    **filter_kwargs: Any,
) -> dict[str, Any]:
    filtered = filter_loans(loans, ltv_mode=ltv_mode, **filter_kwargs)
    kpis = kpi_summary(filtered)
    ltv_field = "ltv_band_current" if ltv_mode == "current" else "ltv_band_original"
    cltv_field = "cltv_band_current" if ltv_mode == "current" else "cltv_band_original"
    heat_ltv = "current_ltv" if ltv_mode == "current" else "original_ltv"
    return {
        "ltv_mode": ltv_mode,
        "kpis": kpis,
        "observations": build_observations(filtered, kpis),
        "fico": aggregate_categorical(
            filtered, "fico_band", order=[b[0] for b in FICO_BUCKETS] + ["missing"]
        ),
        "ltv": aggregate_categorical(
            filtered, ltv_field, order=[b[0] for b in LTV_BUCKETS] + ["missing"]
        ),
        "cltv": aggregate_categorical(
            filtered, cltv_field, order=[b[0] for b in LTV_BUCKETS] + ["missing"]
        ),
        "heatmap": fico_ltv_heatmap(filtered, ltv_field=heat_ltv),
        "dti": aggregate_categorical(
            filtered, "dti_band", order=[b[0] for b in DTI_BUCKETS] + ["missing"]
        ),
        "dscr": aggregate_categorical(
            filtered, "dscr_band", order=[b[0] for b in DSCR_BUCKETS] + ["missing"]
        ),
        "documentation": aggregate_categorical(filtered, "documentation_type"),
        "occupancy": aggregate_categorical(filtered, "occupancy"),
        "loan_purpose": aggregate_categorical(filtered, "loan_purpose"),
        "property_type": aggregate_categorical(filtered, "property_type"),
        "coupon_bands": _coupon_bands(filtered),
        "ri_bands": _ri_bands(filtered),
        "age": aggregate_categorical(
            filtered, "age_band", order=[b[0] for b in AGE_BUCKETS] + ["missing"]
        ),
        "state": aggregate_categorical(filtered, "state"),
        "top_states": aggregate_categorical(filtered, "state")[:10],
        "loans": filtered,
        "cohorts": [
            {"id": c, "label": COHORT_DISPLAY[c], "loan_count": sum(1 for L in loans if L.get("cohort") == c)}
            for c in COHORTS
        ],
        "section_refs": SECTION_REFS,
        "field_inventory": FIELD_INVENTORY,
    }


def _coupon_bands(loans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bands = (
        ("<6%", 0.0, 0.06),
        ("6-7%", 0.06, 0.07),
        ("7-8%", 0.07, 0.08),
        ("8-9%", 0.08, 0.09),
        ("9%+", 0.09, 1.0),
    )
    buckets: dict[str, dict[str, Any]] = {
        label: {"bucket": label, "loan_count": 0, "upb": 0.0} for label, _, _ in bands
    }
    buckets["missing"] = {"bucket": "missing", "loan_count": 0, "upb": 0.0}
    for loan in loans:
        rate = _num(loan.get("current_interest_rate"))
        label = bucket_ordered(rate, bands)
        buckets[label]["loan_count"] += 1
        buckets[label]["upb"] += float(loan.get("current_loan_amount") or 0)
    order = [b[0] for b in bands] + ["missing"]
    return [buckets[k] for k in order if buckets[k]["loan_count"]]


def _ri_bands(loans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bands = (
        ("<0", -100.0, 0.0),
        ("0-1", 0.0, 1.0),
        ("1-2", 1.0, 2.0),
        ("2+", 2.0, 100.0),
    )
    buckets: dict[str, dict[str, Any]] = {
        label: {"bucket": label, "loan_count": 0, "upb": 0.0} for label, _, _ in bands
    }
    buckets["missing"] = {"bucket": "missing", "loan_count": 0, "upb": 0.0}
    for loan in loans:
        ri = _num(loan.get("refinance_incentive"))
        label = bucket_ordered(ri, bands)
        buckets[label]["loan_count"] += 1
        buckets[label]["upb"] += float(loan.get("current_loan_amount") or 0)
    order = [b[0] for b in bands] + ["missing"]
    return [buckets[k] for k in order if buckets[k]["loan_count"]]


COLLATERAL_RAW_FIELDS = (
    "loan_id",
    "current_loan_amount",
    "current_interest_rate",
    "remaining_term",
    "loan_age_months",
    "original_fico",
    "original_ltv",
    "original_cltv",
    "most_recent_property_value",
    "senior_lien_current_balance",
    "junior_lien_balance",
    "state",
    "postal_code",
    "property_type",
    "occupancy",
    "loan_purpose",
    "documentation_type",
    "originator_dti",
    "dscr",
    "days_delinquent",
    "refinance_incentive",
    "cohort",
    "has_mi",
)


def load_enriched_loans_from_excel(
    path: Any | None = None,
    cluster_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Load Minimum Case tape and enrich with cluster cohort + derived LTV."""
    from app.repositories.asf_tape_repository import AsfTapeRepository, _to_py
    from app.repositories.tape_repository import TapeRepository

    repo = AsfTapeRepository()
    df = repo.load_excel(path)
    if cluster_map is None:
        try:
            cluster_map = TapeRepository().load_cluster_map()
        except FileNotFoundError:
            cluster_map = {}
    loans: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        cleaned = {c: _to_py(r.get(c)) for c in COLLATERAL_RAW_FIELDS}
        lid = str(cleaned.get("loan_id") or "")
        loans.append(enrich_loan(cleaned, cluster_map.get(lid)))
    return loans


def load_enriched_loans(
    cluster_map: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Prefer Neon asf_tape; fall back to Excel. Always overlay k-proto cohort."""
    from app.repositories.asf_tape_repository import AsfTapeRepository
    from app.repositories.tape_repository import TapeRepository

    if cluster_map is None:
        try:
            cluster_map = TapeRepository().load_cluster_map()
        except FileNotFoundError:
            cluster_map = {}

    repo = AsfTapeRepository()
    if repo.url:
        try:
            import psycopg

            cols = [c for c in COLLATERAL_RAW_FIELDS]
            # Ensure optional columns exist
            present = repo.tape_columns()
            select_cols = [c for c in cols if c in present or c == "loan_id"]
            col_sql = ", ".join(select_cols)
            with psycopg.connect(repo.require_url(), connect_timeout=60) as conn:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT {col_sql} FROM public.asf_tape ORDER BY loan_id")
                    rows = [dict(zip(select_cols, tup)) for tup in cur.fetchall()]
            out = []
            for raw in rows:
                for c in COLLATERAL_RAW_FIELDS:
                    raw.setdefault(c, None)
                lid = str(raw.get("loan_id") or "")
                out.append(enrich_loan(raw, cluster_map.get(lid)))
            return out, "neon.asf_tape+cluster-tape"
        except Exception:  # noqa: BLE001
            pass
    return load_enriched_loans_from_excel(cluster_map=cluster_map), "excel.Minimum_Case+cluster-tape"
