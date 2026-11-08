"""Pool valuation: servicing haircut, QuantLib discount, Z-spread scenarios.

Discount curve contract
-----------------------
* Inputs: FRED CMT **par yields** (decimal), not continuous zeros.
* Bootstrap: QuantLib rate helpers → piecewise log-linear **discount** factors
  (``PiecewiseLogLinearDiscount``). Short tenors (<1Y) use
  ``DepositRateHelper``; coupon tenors use ``FixedRateBondHelper`` at par
  with coupon = CMT yield (semi-annual, Actual/Actual Bond).
* Fallback: if helpers cannot be built, an **explicit flat continuous zero**
  curve at 4% (labeled in ``curve_meta``) — never silent "par-as-zero".
* Valuation date: ``ql.Settings.evaluationDate`` = calendar today
  (``_ql_today``).
* Day count (curve DF / NPV): ``Actual/365 (Fixed)`` on the discount curve
  handle used for cashflow PV.
* Z-spread: constant continuous spread via ``ZeroSpreadedTermStructure``
  (bp → decimal); scenarios bump this spread only.
* Compounding on the spreaded curve: Continuous / NoFrequency.

WAL contract
------------
``pool_wal_years`` weights **returned principal only**:
``scheduled_principal + prepay + recovery``. Interest, servicing fees,
defaults, and realized losses are excluded.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import QuantLib as ql

from app.repositories.env_load import REPO_ROOT
from app.services.fred_treasury import get_treasury_curve
from app.services.psa_prepay import cpr_at_age
from app.services.sda_default import cdr_at_age

DATA_DIR = REPO_ROOT / "data"
BASE_CF_PATH = DATA_DIR / "cohort-base-cashflow.json"

DEFAULT_SERVICING_BP = 35.0
DEFAULT_Z_SPREAD_BP = 100.0
Z_SCENARIO_OFFSETS_BP = (-50, -25, 0, 25, 50)
# Finite-difference bump for spread / curve risk.
RISK_BUMP_BP = 10.0
# Explicit flat continuous zero used only when CMT bootstrap fails.
FLAT_FALLBACK_ZERO = 0.04
# Key-rate knots (match FRED CMT tenors used in the discount curve).
KEY_RATE_TENORS: list[tuple[float, str]] = [
    (0.5, "6M"),
    (1.0, "1Y"),
    (2.0, "2Y"),
    (3.0, "3Y"),
    (5.0, "5Y"),
    (7.0, "7Y"),
    (10.0, "10Y"),
    (20.0, "20Y"),
    (30.0, "30Y"),
]

# Last curve build metadata (for API / tests — not a global rate store).
_LAST_CURVE_META: dict[str, Any] = {}


def curve_meta() -> dict[str, Any]:
    """Copy of metadata from the most recent ``build_discount_curve`` call."""
    return dict(_LAST_CURVE_META)


def _load_base_cf() -> dict[str, Any]:
    if not BASE_CF_PATH.is_file():
        raise FileNotFoundError(f"Missing {BASE_CF_PATH}")
    return json.loads(BASE_CF_PATH.read_text(encoding="utf-8"))


def pool_gross_months(payload: dict[str, Any]) -> list[dict[str, float]]:
    """Monthly pool total_cash + beginning UPB (sum of cohort __beg)."""
    rows_out: list[dict[str, float]] = []
    for row in payload.get("months") or []:
        m = int(row.get("month") or 0)
        if m <= 0:
            continue
        beg = 0.0
        for k, v in row.items():
            if k.endswith("__beg"):
                beg += float(v or 0.0)
        cash = float(row.get("Pool") or 0.0)
        rows_out.append(
            {
                "month": float(m),
                "beginning_upb": beg,
                "total_cash": cash,
            }
        )
    return rows_out


def apply_servicing(
    months: list[dict[str, float]],
    servicing_bp: float = DEFAULT_SERVICING_BP,
) -> list[dict[str, float]]:
    """net_cf = total_cash − (bp/10000) × beg_UPB / 12."""
    rate = float(servicing_bp) / 10_000.0
    out: list[dict[str, float]] = []
    for row in months:
        beg = float(row["beginning_upb"])
        fee = rate * beg / 12.0
        gross = float(row["total_cash"])
        out.append(
            {
                "month": int(row["month"]),
                "beginning_upb": round(beg, 2),
                "total_cash": round(gross, 2),
                "servicing_fee": round(fee, 2),
                "net_cash": round(gross - fee, 2),
            }
        )
    return out


def _ql_today() -> ql.Date:
    d = ql.Date.todaysDate()
    ql.Settings.instance().evaluationDate = d
    return d


def _flat_continuous_curve(
    today: ql.Date,
    rate: float,
    *,
    reason: str,
) -> ql.YieldTermStructureHandle:
    """Honest flat continuous-zero fallback (not CMT par yields)."""
    calendar = ql.NullCalendar()
    day_count = ql.Actual365Fixed()
    dates = [today, calendar.advance(today, ql.Period(30, ql.Years))]
    rates = [float(rate), float(rate)]
    curve = ql.ZeroCurve(
        dates, rates, day_count, calendar, ql.Linear(), ql.Continuous
    )
    curve.enableExtrapolation()
    _LAST_CURVE_META.clear()
    _LAST_CURVE_META.update(
        {
            "method": "flat_continuous_zero",
            "flat_zero": float(rate),
            "compounding": "Continuous",
            "day_count": "Actual/365 (Fixed)",
            "calendar": "NullCalendar",
            "valuation_date": ql.Date_isoFormat(today)
            if hasattr(ql, "Date_isoFormat")
            else str(today),
            "z_spread_compounding": "Continuous",
            "z_spread_day_count": "Actual/365 (Fixed)",
            "note": reason,
            "n_helpers": 0,
        }
    )
    return ql.YieldTermStructureHandle(curve)


def _cmt_rate_helpers(
    today: ql.Date,
    curve_points: list[dict[str, Any]],
) -> list[Any]:
    """Build QuantLib helpers from FRED CMT **par** yields (decimal)."""
    calendar = ql.UnitedStates(ql.UnitedStates.GovernmentBond)
    dc_deposit = ql.Actual365Fixed()
    dc_bond = ql.ActualActual(ql.ActualActual.Bond)
    settlement_days = 0
    face = 100.0
    helpers: list[Any] = []
    seen_dates: list[ql.Date] = []

    for p in sorted(curve_points, key=lambda x: float(x["tenor_years"])):
        if p.get("extrapolated"):
            # Chart-only 40Y — do not bootstrap.
            continue
        tenor = float(p["tenor_years"])
        if tenor <= 0:
            continue
        y = float(p["yield"])
        if not (0.0 <= y < 1.0):
            continue

        if tenor < 1.0:
            months = max(1, int(round(tenor * 12.0)))
            period = ql.Period(months, ql.Months)
            maturity = calendar.advance(today, period)
            if seen_dates and maturity <= seen_dates[-1]:
                continue
            helper = ql.DepositRateHelper(
                ql.QuoteHandle(ql.SimpleQuote(y)),
                period,
                settlement_days,
                calendar,
                ql.Unadjusted,
                False,
                dc_deposit,
            )
        else:
            years = max(1, int(round(tenor)))
            maturity = calendar.advance(today, ql.Period(years, ql.Years))
            if seen_dates and maturity <= seen_dates[-1]:
                continue
            schedule = ql.Schedule(
                today,
                maturity,
                ql.Period(ql.Semiannual),
                calendar,
                ql.Unadjusted,
                ql.Unadjusted,
                ql.DateGeneration.Backward,
                False,
            )
            # Par bond: clean price 100, coupon = CMT par yield (SA BEY).
            helper = ql.FixedRateBondHelper(
                ql.QuoteHandle(ql.SimpleQuote(face)),
                settlement_days,
                face,
                schedule,
                [y],
                dc_bond,
                ql.Unadjusted,
                face,
            )
        helpers.append(helper)
        seen_dates.append(maturity)

    return helpers


def build_discount_curve(
    curve_points: list[dict[str, Any]],
) -> ql.YieldTermStructureHandle:
    """Bootstrap a discount curve from CMT **par** yields (not continuous zeros).

    See module docstring for units / compounding / day count / val date / spread.
    """
    today = _ql_today()
    helpers = _cmt_rate_helpers(today, curve_points or [])
    if len(helpers) < 2:
        return _flat_continuous_curve(
            today,
            FLAT_FALLBACK_ZERO,
            reason=(
                "Fewer than 2 CMT helpers — using explicit flat continuous "
                f"zero {FLAT_FALLBACK_ZERO:.2%} (not par-as-zero)."
            ),
        )

    try:
        curve = ql.PiecewiseLogLinearDiscount(
            today, helpers, ql.Actual365Fixed()
        )
        # Force first bootstrap evaluation before enabling extrapolation.
        _ = curve.discount(today + ql.Period(1, ql.Years))
        curve.enableExtrapolation()
    except RuntimeError as exc:
        return _flat_continuous_curve(
            today,
            FLAT_FALLBACK_ZERO,
            reason=(
                f"CMT bootstrap failed ({exc}); using explicit flat continuous "
                f"zero {FLAT_FALLBACK_ZERO:.2%}."
            ),
        )

    _LAST_CURVE_META.clear()
    _LAST_CURVE_META.update(
        {
            "method": "cmt_par_bootstrap",
            "compounding": "log-linear discount (implied zeros Continuous)",
            "day_count": "Actual/365 (Fixed) on discount curve",
            "helper_day_count_short": "Actual/365 (Fixed) deposits",
            "helper_day_count_bonds": "Actual/Actual (Bond) semi-annual pars",
            "calendar": "UnitedStates.GovernmentBond",
            "valuation_date": str(today),
            "z_spread_compounding": "Continuous",
            "z_spread_day_count": "Actual/365 (Fixed)",
            "inputs": "FRED CMT par yields (decimal)",
            "n_helpers": len(helpers),
            "note": (
                "CMT pars bootstrapped via DepositRateHelper (<1Y) and "
                "FixedRateBondHelper (≥1Y, coupon=par yield, price=100)."
            ),
        }
    )
    return ql.YieldTermStructureHandle(curve)


def _spreaded_curve(
    curve_handle: ql.YieldTermStructureHandle,
    z_spread_bp: float,
) -> ql.ZeroSpreadedTermStructure:
    spread = float(z_spread_bp) / 10_000.0
    spreaded = ql.ZeroSpreadedTermStructure(
        curve_handle,
        ql.QuoteHandle(ql.SimpleQuote(spread)),
        ql.Continuous,
        ql.NoFrequency,
        ql.Actual365Fixed(),
    )
    spreaded.enableExtrapolation()
    return spreaded


def discount_net_cashflows(
    net_months: list[dict[str, float]],
    curve_handle: ql.YieldTermStructureHandle,
    z_spread_bp: float,
) -> tuple[float, list[dict[str, float]]]:
    """Return (NPV, monthly PV rows) on Treasury + Z-spread."""
    today = ql.Settings.instance().evaluationDate
    calendar = ql.NullCalendar()
    spreaded = _spreaded_curve(curve_handle, z_spread_bp)

    total = 0.0
    rows: list[dict[str, float]] = []
    for row in net_months:
        m = int(row["month"])
        cf = float(row["net_cash"])
        if abs(cf) < 1e-12:
            continue
        dt = calendar.advance(today, ql.Period(m, ql.Months))
        df = float(spreaded.discount(dt))
        pv = cf * df
        total += pv
        rows.append(
            {
                "month": m,
                "net_cash": cf,
                "df": df,
                "pv": pv,
            }
        )
    return total, rows


def npv_net_cashflows(
    net_months: list[dict[str, float]],
    curve_handle: ql.YieldTermStructureHandle,
    z_spread_bp: float,
) -> float:
    """Discount net monthly CF on curve + constant Z-spread (continuous)."""
    total, _ = discount_net_cashflows(net_months, curve_handle, z_spread_bp)
    return total


def pv_profile_by_year(
    monthly_pv: list[dict[str, float]],
    *,
    max_years: int = 30,
) -> list[dict[str, Any]]:
    """Annual PV buckets + cumulative % of total NPV (valuation lens)."""
    buckets: dict[int, float] = {}
    for row in monthly_pv:
        y = int((int(row["month"]) - 1) // 12) + 1
        if y < 1 or y > max_years:
            if y > max_years:
                buckets[max_years] = buckets.get(max_years, 0.0) + float(row["pv"])
            continue
        buckets[y] = buckets.get(y, 0.0) + float(row["pv"])

    total = sum(buckets.values())
    out: list[dict[str, Any]] = []
    running = 0.0
    for y in range(1, max_years + 1):
        pv = float(buckets.get(y, 0.0))
        if abs(pv) < 1e-9 and y > 1 and not any(
            abs(buckets.get(k, 0.0)) > 1e-9 for k in range(y, max_years + 1)
        ):
            break
        running += pv
        out.append(
            {
                "year": y,
                "label": f"Y{y}",
                "pv": round(pv, 2),
                "cum_pv": round(running, 2),
                "cum_pct": round((running / total * 100.0) if total else 0.0, 2),
            }
        )
    return out


def _bump_curve_points(
    curve_points: list[dict[str, Any]],
    *,
    parallel_bp: float = 0.0,
    tenor_years: float | None = None,
    tenor_bump_bp: float = 0.0,
) -> list[dict[str, Any]]:
    """Copy CMT points with optional parallel and/or single-tenor yield bump."""
    out: list[dict[str, Any]] = []
    for p in curve_points:
        q = dict(p)
        if q.get("extrapolated"):
            out.append(q)
            continue
        y = float(q["yield"])
        if parallel_bp:
            y += float(parallel_bp) / 10_000.0
        if (
            tenor_years is not None
            and abs(float(q["tenor_years"]) - float(tenor_years)) < 1e-9
        ):
            y += float(tenor_bump_bp) / 10_000.0
        q["yield"] = y
        q["yield_pct"] = round(y * 100.0, 6)
        out.append(q)
    return out


def spread_risk_metrics(
    net_months: list[dict[str, float]],
    curve_handle: ql.YieldTermStructureHandle,
    z_spread_bp: float,
    start_upb: float,
    *,
    bump_bp: float = RISK_BUMP_BP,
) -> dict[str, float]:
    """Z-spread duration, CS01, convexity (static CF; CF does not reprice).

    Bump Z ±bump_bp holding the Treasury curve fixed.
    Duration = effective spread duration (years).
    CS01 = $ NPV change per 1 bp of Z-spread.
    Convexity = second-order (per 1.0 = 100% yield).
    """
    bump = float(bump_bp)
    if bump <= 0 or start_upb <= 0:
        return {
            "duration": 0.0,
            "cs01": 0.0,
            "dv01": 0.0,
            "convexity": 0.0,
            "convexity_dollar": 0.0,
            "bump_bp": bump,
        }

    p0 = npv_net_cashflows(net_months, curve_handle, z_spread_bp)
    p_up = npv_net_cashflows(net_months, curve_handle, z_spread_bp + bump)
    p_dn = npv_net_cashflows(net_months, curve_handle, z_spread_bp - bump)

    dy = bump / 10_000.0  # decimal yield
    second = p_up + p_dn - 2.0 * p0
    if abs(p0) < 1e-9:
        duration = 0.0
        convexity = 0.0
    else:
        duration = (p_dn - p_up) / (2.0 * p0 * dy)
        convexity = second / (p0 * dy * dy)

    # CS01: $ change per 1 bp Z-spread widen (credit / Z risk).
    cs01 = (p_dn - p_up) / (2.0 * bump)
    # Dollar convexity: $ per bp² (same units family as DV01 / CS01).
    convexity_dollar = second / (bump * bump)

    return {
        "duration": round(duration, 4),
        "cs01": round(cs01, 2),
        # Back-compat alias — same Z-spread 01; rates DV01 computed separately.
        "dv01": round(cs01, 2),
        "convexity": round(convexity, 2),
        "convexity_dollar": round(convexity_dollar, 2),
        "bump_bp": bump,
        "npv_up": round(p_up, 2),
        "npv_dn": round(p_dn, 2),
    }


def rates_dv01(
    net_months: list[dict[str, float]],
    curve_points: list[dict[str, Any]],
    z_spread_bp: float,
    *,
    bump_bp: float = RISK_BUMP_BP,
) -> dict[str, float]:
    """Parallel Treasury bump → rates DV01 ($ / bp) and rates duration."""
    bump = float(bump_bp)
    base_curve = build_discount_curve(curve_points)
    p0 = npv_net_cashflows(net_months, base_curve, z_spread_bp)
    up = build_discount_curve(
        _bump_curve_points(curve_points, parallel_bp=bump)
    )
    dn = build_discount_curve(
        _bump_curve_points(curve_points, parallel_bp=-bump)
    )
    p_up = npv_net_cashflows(net_months, up, z_spread_bp)
    p_dn = npv_net_cashflows(net_months, dn, z_spread_bp)
    dy = bump / 10_000.0
    duration = (p_dn - p_up) / (2.0 * p0 * dy) if abs(p0) > 1e-9 else 0.0
    dv01 = (p_dn - p_up) / (2.0 * bump)
    return {
        "rates_duration": round(duration, 4),
        "rates_dv01": round(dv01, 2),
        "bump_bp": bump,
    }


def key_rate_durations(
    net_months: list[dict[str, float]],
    curve_points: list[dict[str, Any]],
    z_spread_bp: float,
    *,
    bump_bp: float = RISK_BUMP_BP,
) -> list[dict[str, Any]]:
    """Partial durations from single-tenor CMT bumps (static CF)."""
    bump = float(bump_bp)
    dy = bump / 10_000.0
    base_curve = build_discount_curve(curve_points)
    p0 = npv_net_cashflows(net_months, base_curve, z_spread_bp)
    available = {
        round(float(p["tenor_years"]), 6)
        for p in curve_points
        if not p.get("extrapolated")
    }

    out: list[dict[str, Any]] = []
    for tenor, label in KEY_RATE_TENORS:
        if round(tenor, 6) not in available:
            continue
        up = build_discount_curve(
            _bump_curve_points(
                curve_points, tenor_years=tenor, tenor_bump_bp=bump
            )
        )
        dn = build_discount_curve(
            _bump_curve_points(
                curve_points, tenor_years=tenor, tenor_bump_bp=-bump
            )
        )
        p_up = npv_net_cashflows(net_months, up, z_spread_bp)
        p_dn = npv_net_cashflows(net_months, dn, z_spread_bp)
        duration = (p_dn - p_up) / (2.0 * p0 * dy) if abs(p0) > 1e-9 else 0.0
        krd_dv01 = (p_dn - p_up) / (2.0 * bump)
        out.append(
            {
                "tenor_years": tenor,
                "label": label,
                "duration": round(duration, 4),
                "dv01": round(krd_dv01, 2),
            }
        )
    return out


def _row_returned_principal(row: dict[str, Any]) -> float:
    """Returned principal for WAL: sched + prepay + recovery (never interest/fees/default/loss)."""
    if row.get("principal_cash") is not None:
        return max(0.0, float(row["principal_cash"] or 0.0))
    sched = float(row.get("scheduled_principal") or 0.0)
    prepay = float(row.get("prepay") or 0.0)
    recovery = float(row.get("recovery") or 0.0)
    # Explicit zeros still win over net_cash / balance runoff fallbacks.
    if any(k in row for k in ("scheduled_principal", "prepay", "recovery")):
        return max(0.0, sched + prepay + recovery)
    return 0.0


def pool_wal_years(months: list[dict[str, Any]]) -> float:
    """Weighted-average life in years from returned principal only.

    Includes: ``scheduled_principal``, ``prepay``, ``recovery`` (or
    pre-aggregated ``principal_cash``).
    Excludes: interest, servicing fees, defaults, realized losses, net_cash,
    and performing-balance runoff (which mixes in defaults).
    """
    num = 0.0
    den = 0.0
    for row in months:
        m = int(row.get("month") or 0)
        if m <= 0:
            continue
        prin = _row_returned_principal(row)
        if prin <= 0.0:
            continue
        num += float(m) * prin
        den += prin
    if den <= 0.0:
        return 0.0
    return round(num / den / 12.0, 4)


def pool_principal_months(payload: dict[str, Any]) -> list[dict[str, float]]:
    """Build WAL principal rows from base-CF payload when components exist.

    Prefers ``principal_months`` (sched / prepay / recovery or ``principal_cash``).
    Falls back to ``months`` only when those rows carry returned-principal
    fields (``Pool__prin`` / ``scheduled_principal`` / …). Does **not** treat
    ``recovery_months`` alone as WAL input (that would omit sched+prepay).
    Returns [] → ``pool_wal_years`` = 0 when the series is absent.
    """
    if payload.get("principal_months"):
        rows_src = list(payload["principal_months"])
        allow_recovery_only_row = True
    else:
        rows_src = list(payload.get("months") or [])
        allow_recovery_only_row = False

    out: list[dict[str, float]] = []
    for row in rows_src:
        m = int(row.get("month") or 0)
        if m <= 0:
            continue
        has_prin_fields = any(
            k in row
            for k in (
                "principal_cash",
                "Pool__prin",
                "scheduled_principal",
                "Pool__sched",
                "prepay",
                "Pool__prepay",
                "recovery",
                "Pool__recovery",
            )
        )
        if not has_prin_fields and not allow_recovery_only_row:
            continue
        sched = float(
            row.get("scheduled_principal") or row.get("Pool__sched") or 0.0
        )
        prepay = float(row.get("prepay") or row.get("Pool__prepay") or 0.0)
        recovery = float(
            row.get("recovery") or row.get("Pool__recovery") or 0.0
        )
        prin = float(row.get("principal_cash") or row.get("Pool__prin") or 0.0)
        if prin <= 0.0:
            prin = sched + prepay + recovery
        if prin <= 0.0:
            continue
        out.append(
            {
                "month": float(m),
                "scheduled_principal": sched,
                "prepay": prepay,
                "recovery": recovery,
                "principal_cash": prin,
            }
        )
    return out


def pool_speed_kpis(payload: dict[str, Any], age_months: int = 60) -> dict[str, float]:
    """UPB-weighted PSA/SDA → CPR / CDR / CRR at a representative age."""
    cohorts = payload.get("cohorts") or {}
    w_psa = 0.0
    w_sda = 0.0
    w = 0.0
    for meta in cohorts.values():
        upb = float(meta.get("beginning_upb") or 0.0)
        if upb <= 0:
            continue
        w += upb
        w_psa += upb * float(meta.get("psa_multiple") or 100.0)
        w_sda += upb * float(meta.get("sda_multiple") or 100.0)
    if w <= 0:
        return {"cpr": 0.0, "cdr": 0.0, "crr": 0.0, "wa_psa": 0.0, "wa_sda": 0.0}
    wa_psa = w_psa / w
    wa_sda = w_sda / w
    cpr = float(cpr_at_age(age_months, wa_psa))
    cdr = float(cdr_at_age(age_months, wa_sda))
    crr = 1.0 - (1.0 - cpr) * (1.0 - cdr)
    return {
        "cpr": round(cpr, 6),
        "cdr": round(cdr, 6),
        "crr": round(crr, 6),
        "wa_psa": round(wa_psa, 2),
        "wa_sda": round(wa_sda, 2),
        "speed_age_months": age_months,
    }


class StaleCashflowCacheError(RuntimeError):
    """Base cohort CF cache does not match current engine/assumptions (CF-191)."""


def build_valuation(
    *,
    servicing_bp: float = DEFAULT_SERVICING_BP,
    z_spread_bp: float = DEFAULT_Z_SPREAD_BP,
    refresh_fred: bool = False,
) -> dict[str, Any]:
    """Full valuation payload for the Valuation tab."""
    from app.repositories.tape_repository import resolve_default_tape_path
    from app.services.cache_keys import (
        assumptions_fingerprint,
        cache_is_fresh,
    )
    from app.services.cashflow_engine import ENGINE_VERSION

    base = _load_base_cf()
    # CF-191: never value on a stale base CF (no silent static bypass).
    if not cache_is_fresh(base, tape_path=resolve_default_tape_path()):
        raise StaleCashflowCacheError(
            "Base cohort cashflow cache is stale or missing engine/assumptions "
            f"fingerprints (engine={ENGINE_VERSION}, "
            f"assumptions={assumptions_fingerprint()}). "
            "Recompute with POST /api/cashflows/run-base-cohort?force=true "
            "before running Valuation."
        )
    if not base.get("principal_months"):
        # Older caches lack returned-principal series — WAL would be wrong.
        raise StaleCashflowCacheError(
            "Base cohort cashflow cache has no principal_months "
            "(sched+prepay+recovery). Recompute with "
            "POST /api/cashflows/run-base-cohort?force=true "
            "(older caches are not used for WAL)."
        )

    gross = pool_gross_months(base)
    net = apply_servicing(gross, servicing_bp=servicing_bp)
    if not net:
        raise RuntimeError("No pool months in cohort-base-cashflow.json")

    start_upb = float(net[0]["beginning_upb"])
    treasury = get_treasury_curve(force=refresh_fred)
    curve = build_discount_curve(treasury.get("points") or [])

    base_npv, monthly_pv = discount_net_cashflows(net, curve, z_spread_bp)
    base_price = (base_npv / start_upb * 100.0) if start_upb > 0 else 0.0

    scenarios: list[dict[str, Any]] = []
    for off in Z_SCENARIO_OFFSETS_BP:
        zs = float(z_spread_bp) + float(off)
        if off == 0:
            npv = base_npv
        else:
            npv = npv_net_cashflows(net, curve, zs)
        price = (npv / start_upb * 100.0) if start_upb > 0 else 0.0
        scenarios.append(
            {
                "label": (
                    "Base"
                    if off == 0
                    else (f"{off:+.0f} bp" if off else "Base")
                ),
                "offset_bp": off,
                "z_spread_bp": zs,
                "npv": round(npv, 2),
                "price_pts": round(price, 4),
                "is_base": off == 0,
            }
        )

    speeds = pool_speed_kpis(base)
    prin_months = pool_principal_months(base)
    wal = pool_wal_years(prin_months)
    pts = treasury.get("points") or []
    risk = spread_risk_metrics(net, curve, z_spread_bp, start_upb)
    rates = rates_dv01(net, pts, z_spread_bp)
    krds = key_rate_durations(net, pts, z_spread_bp)
    pv_profile = pv_profile_by_year(monthly_pv, max_years=30)
    meta = curve_meta()

    return {
        "ok": True,
        "engine": "QuantLib",
        "quantlib_version": getattr(ql, "__version__", "unknown"),
        "servicing_bp": servicing_bp,
        "z_spread_bp": z_spread_bp,
        "start_upb": round(start_upb, 2),
        "npv": round(base_npv, 2),
        "price_pts": round(base_price, 4),
        "wal_years": wal,
        "duration": risk["duration"],
        "cs01": risk["cs01"],
        "cs01_pts": round(
            (risk["cs01"] / start_upb * 100.0) if start_upb > 0 else 0.0, 6
        ),
        "dv01": rates["rates_dv01"],
        "rates_duration": rates["rates_duration"],
        "convexity": risk["convexity"],
        "convexity_dollar": risk["convexity_dollar"],
        "risk": {**risk, **rates},
        "key_rate_durations": krds,
        "speeds": speeds,
        "scenarios": scenarios,
        "pv_profile": pv_profile,
        "curve_meta": meta,
        "treasury": {
            "as_of": treasury.get("as_of"),
            "fetched_at": treasury.get("fetched_at"),
            "cached": treasury.get("cached"),
            "stale": treasury.get("stale"),
            "seed": treasury.get("seed"),
            "note": treasury.get("note"),
            "points": pts,
        },
        "base_cf": {
            "path": str(BASE_CF_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
            "engine_version": base.get("engine_version"),
            "n_months": len(net),
            "n_principal_months": len(prin_months),
        },
        "formula": {
            "servicing_fee": "servicing_bp × beginning_UPB / 12",
            "net_cash": "pool total_cash − servicing_fee",
            "price_pts": "100 × NPV(net CF @ Treasury + Z-spread) / start_UPB",
            "discount_curve": (
                "CMT par bootstrap (DepositRateHelper <1Y, "
                "FixedRateBondHelper >=1Y SA Actual/Actual Bond) -> "
                "PiecewiseLogLinearDiscount; Z-spread = continuous "
                "ZeroSpreadedTermStructure (bp->decimal); val date = QL today; "
                "DF day count Actual/365 Fixed"
            ),
            "wal_years": (
                "Σ(month × (sched+prepay+recovery)) / Σ(sched+prepay+recovery) / 12; "
                "excludes interest, fees, defaults, losses"
            ),
            "duration": "(P− − P+) / (2 × P0 × Δy) · Z-spread bump",
            "cs01": "(NPV− − NPV+) / (2 × bump_bp) · $ per 1 bp Z-spread",
            "dv01": "(NPV− − NPV+) / (2 × bump_bp) · $ per 1 bp parallel Treasury",
            "krd": "single-tenor CMT bump · partial duration years",
            "convexity": "(P+ + P− − 2×P0) / (P0 × Δy²)",
            "convexity_dollar": "(P+ + P− − 2×P0) / bump_bp² · $ per bp²",
        },
    }
