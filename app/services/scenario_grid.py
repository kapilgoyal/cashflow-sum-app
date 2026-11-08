"""Build the cohort × PSA × SDA securitization scenario grid.

Axes and cohort recovery come from ``data/scenario_config.json`` (shared with UI).

Full cross: 3 cohorts × 3 PSA × 3 SDA = 27 rows.
"""

from __future__ import annotations

from app.models.scenario import Scenario
from app.services.cohort_labels import (
    COHORT_HIGH_LTV_STRONG,
    COHORT_HIGH_LTV_WEAK,
    COHORT_LOW_LTV_WEAK,
    canonical_cohort_label,
)
from app.services.scenario_config import (
    COHORT_GRID_ORDER,
    cohort_recovery_map,
    grid_psa_multiples,
    grid_sda_multiples,
    label_psa_sda,
    load_scenario_config,
    psa_level_name,
    sda_level_name,
)

COHORTS = COHORT_GRID_ORDER

CREDIT_LEAN_COHORTS = (COHORT_HIGH_LTV_STRONG, COHORT_HIGH_LTV_WEAK)
PREPAY_LEAN_COHORT = COHORT_LOW_LTV_WEAK


def _axes() -> tuple[tuple[int, ...], tuple[int, ...], int, int]:
    cfg = load_scenario_config()["grid_axes"]
    return (
        tuple(int(x) for x in cfg["psa_multiples"]),
        tuple(int(x) for x in cfg["sda_multiples"]),
        int(cfg["base_psa"]),
        int(cfg["base_sda"]),
    )


PSA_MULTIPLES = grid_psa_multiples()
SDA_MULTIPLES = grid_sda_multiples()
PSA_LEVEL_NAME = {p: psa_level_name(p) for p in PSA_MULTIPLES}
SDA_LEVEL_NAME = {s: sda_level_name(s) for s in SDA_MULTIPLES}
_BASE = load_scenario_config()["grid_axes"]
BASE_PSA = int(_BASE["base_psa"])
BASE_SDA = int(_BASE["base_sda"])

COHORT_RECOVERY: dict[str, tuple[float, int, int]] = cohort_recovery_map()

STATE_LAG_NOTE = (
    "recovery_rate is cohort (not one pool rate); "
    "engine lag from Fannie Mae state foreclosure time frames "
    "(https://singlefamily.fanniemae.com/media/6726/display); "
    "scenario recovery_lag_months is fallback when state unknown"
)


def recovery_for_cohort(cohort: str) -> tuple[float, int, int]:
    key = canonical_cohort_label(cohort)
    if key not in COHORT_RECOVERY:
        raise KeyError(f"unknown cohort for recovery: {cohort}")
    return COHORT_RECOVERY[key]


def _cell_note(cohort: str, psa: int, sda: int) -> str:
    bits = [
        f"{cohort} {label_psa_sda(psa, sda)}",
        f"PCA={psa_level_name(psa)} STA={sda_level_name(sda)}",
    ]
    if psa == BASE_PSA and sda == BASE_SDA:
        bits.append(f"GRID BASE CASE ({label_psa_sda(BASE_PSA, BASE_SDA)})")
    if cohort in CREDIT_LEAN_COHORTS and sda >= 100:
        bits.append(f"{cohort} credit-leaning cell")
    if cohort == PREPAY_LEAN_COHORT and psa >= 100 and sda <= 100:
        bits.append(f"{cohort} prepay-leaning cell")
    rate, period, lag = recovery_for_cohort(cohort)
    bits.append(f"cohort recovery {rate:.0%}/{period}mo scenario_lag_fallback={lag}")
    bits.append(STATE_LAG_NOTE)
    return "; ".join(bits)


def build_scenario_grid() -> list[Scenario]:
    psa_mults, sda_mults, _, _ = _axes()
    rows: list[Scenario] = []
    i = 0
    for cohort in COHORTS:
        rate, period, lag = recovery_for_cohort(cohort)
        for psa in psa_mults:
            for sda in sda_mults:
                i += 1
                rows.append(
                    Scenario(
                        scenario_id=f"S{i:02d}",
                        cohort=cohort,
                        psa_multiple=int(psa),
                        sda_multiple=int(sda),
                        recovery_period_months=period,
                        recovery_lag_months=lag,
                        recovery_rate=rate,
                        note=_cell_note(cohort, int(psa), int(sda)),
                        state_varying_recovery_todo=False,
                    )
                )
    return rows


def scenarios_to_records(scenarios: list[Scenario]) -> list[dict]:
    return [
        {
            "scenario_id": s.scenario_id,
            "cohort": s.cohort,
            "psa_multiple": s.psa_multiple,
            "sda_multiple": s.sda_multiple,
            "psa_sda_label": label_psa_sda(s.psa_multiple, s.sda_multiple),
            "recovery_period_months": s.recovery_period_months,
            "recovery_lag_months": s.recovery_lag_months,
            "recovery_rate": s.recovery_rate,
            "state_varying_recovery_todo": s.state_varying_recovery_todo,
            "note": s.note,
        }
        for s in scenarios
    ]


def base_case_scenario(scenarios: list[Scenario] | None = None) -> Scenario:
    """First-cohort grid base cell at BASE_PSA / BASE_SDA (usually 100/100)."""
    scenarios = scenarios or build_scenario_grid()
    for s in scenarios:
        if (
            s.cohort == COHORTS[0]
            and s.psa_multiple == BASE_PSA
            and s.sda_multiple == BASE_SDA
        ):
            return s
    raise ValueError(
        f"base case {label_psa_sda(BASE_PSA, BASE_SDA)} not found for first cohort"
    )
