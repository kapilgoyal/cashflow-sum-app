"""CF-189: valuation discount curve bootstrap + principal-only WAL."""

from __future__ import annotations

import math

import QuantLib as ql
import pytest

from app.services.valuation import (
    FLAT_FALLBACK_ZERO,
    apply_servicing,
    build_discount_curve,
    curve_meta,
    discount_net_cashflows,
    npv_net_cashflows,
    pool_wal_years,
)


def test_pool_wal_sched_prepay_recovery_excludes_loss_and_fees():
    """50 @ m12 + 30 recovery @ m36 + 20 loss → WAL 1.75y; fees ignored."""
    rows = [
        {
            "month": 12,
            "scheduled_principal": 50.0,
            "prepay": 0.0,
            "recovery": 0.0,
            "interest": 999.0,
            "servicing_fee": 50.0,
            "net_cash": 1.0,
            "realized_loss": 0.0,
            "default": 0.0,
        },
        {
            "month": 36,
            "scheduled_principal": 0.0,
            "prepay": 0.0,
            "recovery": 30.0,
            "interest": 0.0,
            "servicing_fee": 10.0,
            "net_cash": 500.0,
            "realized_loss": 20.0,
            "default": 20.0,
        },
    ]
    wal = pool_wal_years(rows)
    assert wal == pytest.approx(1.75, abs=1e-9)

    # Fees / net_cash / interest alone must not move WAL.
    fat_fees = [
        {**rows[0], "servicing_fee": 1_000_000.0, "net_cash": -1_000_000.0},
        {**rows[1], "servicing_fee": 1_000_000.0, "interest": 1_000_000.0},
    ]
    assert pool_wal_years(fat_fees) == pytest.approx(1.75, abs=1e-9)

    # Loss-only / default-only rows contribute nothing.
    loss_only = [
        {"month": 24, "realized_loss": 100.0, "default": 100.0, "net_cash": 0.0}
    ]
    assert pool_wal_years(loss_only) == 0.0


def test_pool_wal_principal_cash_field():
    rows = [
        {"month": 12, "principal_cash": 50.0},
        {"month": 36, "principal_cash": 30.0},
    ]
    assert pool_wal_years(rows) == pytest.approx(1.75, abs=1e-9)


def test_build_discount_curve_bootstraps_cmt_pars_not_as_zeros():
    """Flat 4% CMT pars → bootstrap; 2Y par bond ≈ 100 (not ZeroCurve-on-par)."""
    points = [
        {"tenor_years": t, "yield": 0.04}
        for t in (0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0)
    ]
    handle = build_discount_curve(points)
    meta = curve_meta()
    assert meta["method"] == "cmt_par_bootstrap"
    assert meta["n_helpers"] >= 2
    assert "par" in meta["inputs"].lower() or "CMT" in meta["note"]

    today = ql.Settings.instance().evaluationDate
    calendar = ql.UnitedStates(ql.UnitedStates.GovernmentBond)
    maturity = calendar.advance(today, ql.Period(2, ql.Years))
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
    bond = ql.FixedRateBond(
        0,
        100.0,
        schedule,
        [0.04],
        ql.ActualActual(ql.ActualActual.Bond),
        ql.Unadjusted,
        100.0,
    )
    engine = ql.DiscountingBondEngine(handle)
    bond.setPricingEngine(engine)
    # Par input should reprice near par after a proper bootstrap.
    assert bond.cleanPrice() == pytest.approx(100.0, abs=0.15)


def test_build_discount_curve_flat_fallback_is_labeled():
    handle = build_discount_curve([])
    meta = curve_meta()
    assert meta["method"] == "flat_continuous_zero"
    assert meta["flat_zero"] == FLAT_FALLBACK_ZERO
    assert "flat" in meta["note"].lower()
    today = ql.Settings.instance().evaluationDate
    df = float(handle.discount(today + ql.Period(1, ql.Years)))
    # Continuous Actual/365Fixed: DF ≈ exp(-r * t)
    t = ql.Actual365Fixed().yearFraction(today, today + ql.Period(1, ql.Years))
    assert df == pytest.approx(math.exp(-FLAT_FALLBACK_ZERO * t), rel=1e-9)


def test_reference_npv_flat_continuous_zero():
    """Reference NPV: single CF discounted on explicit flat continuous zero."""
    build_discount_curve([])  # labeled flat fallback
    handle = build_discount_curve([])
    assert curve_meta()["method"] == "flat_continuous_zero"

    months = [
        {
            "month": 12,
            "beginning_upb": 1_000_000.0,
            "total_cash": 10_000.0,
        }
    ]
    net = apply_servicing(months, servicing_bp=0.0)
    npv, rows = discount_net_cashflows(net, handle, z_spread_bp=0.0)
    assert len(rows) == 1

    today = ql.Settings.instance().evaluationDate
    dt = ql.NullCalendar().advance(today, ql.Period(12, ql.Months))
    t = ql.Actual365Fixed().yearFraction(today, dt)
    expected = 10_000.0 * math.exp(-FLAT_FALLBACK_ZERO * t)
    assert npv == pytest.approx(expected, rel=1e-9)
    assert float(rows[0]["df"]) == pytest.approx(math.exp(-FLAT_FALLBACK_ZERO * t), rel=1e-9)

    # Continuous Z-spread widens DF (lower NPV).
    npv_wide = npv_net_cashflows(net, handle, z_spread_bp=100.0)
    assert npv_wide < npv
