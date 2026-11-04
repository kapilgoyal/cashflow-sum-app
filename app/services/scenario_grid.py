"""Build the cohort × PSA × SDA securitization scenario grid.

Down/Base/Up (ChatGPT grid; PCA=PSA, STA=SDA):
  PSA (PCA): Down=75, Base=100, Up=125
  SDA (STA): Down=50, Base=100, Up=200
Full cross: 3 cohorts × 3 PSA × 3 SDA = 27 rows.

Display names (cluster ids 0/1/2 unchanged):
- LLTV Weak RI   (cluster 0)
- HLTV Strong RI (cluster 1)
- HLTV Weak RI   (cluster 2)

Per-cohort recovery (rate / period months; lag=0):
- HLTV Strong RI → 60% / 12mo
- HLTV Weak RI → 55% / 15mo
- LLTV Weak RI → 75% / 9mo
"""

from __future__ import annotations

from app.models.scenario import Scenario
from app.services.cohort_labels import (
    COHORT_HIGH_LTV_STRONG,
    COHORT_HIGH_LTV_WEAK,
    COHORT_LOW_LTV_WEAK,
    canonical_cohort_label,
)

# Order matches prior S01–S09 / S10–S18 / S19–S27 blocks (clusters 0 / 1 / 2).
COHORTS = (
    COHORT_LOW_LTV_WEAK,
    COHORT_HIGH_LTV_STRONG,
    COHORT_HIGH_LTV_WEAK,
)

CREDIT_LEAN_COHORTS = (COHORT_HIGH_LTV_STRONG, COHORT_HIGH_LTV_WEAK)
PREPAY_LEAN_COHORT = COHORT_LOW_LTV_WEAK

PSA_MULTIPLES = (75, 100, 125)  # Down / Base / Up
SDA_MULTIPLES = (50, 100, 200)  # Down / Base / Up
PSA_LEVEL_NAME = {75: "Down", 100: "Base", 125: "Up"}
SDA_LEVEL_NAME = {50: "Down", 100: "Base", 200: "Up"}
BASE_PSA = 100
BASE_SDA = 100

# recovery_rate, recovery_period_months, recovery_lag_months
COHORT_RECOVERY: dict[str, tuple[float, int, int]] = {
    COHORT_HIGH_LTV_STRONG: (0.60, 12, 0),
    COHORT_HIGH_LTV_WEAK: (0.55, 15, 0),
    COHORT_LOW_LTV_WEAK: (0.75, 9, 0),
}

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
        f"{cohort} PSA{psa}/SDA{sda}",
        f"PCA={PSA_LEVEL_NAME[psa]} STA={SDA_LEVEL_NAME[sda]}",
    ]
    if psa == BASE_PSA and sda == BASE_SDA:
        bits.append("BASE CASE (100 PSA / 100 SDA)")
    if cohort in CREDIT_LEAN_COHORTS and sda >= 100:
        bits.append(f"{cohort} credit-leaning cell")
    if cohort == PREPAY_LEAN_COHORT and psa >= 100 and sda <= 100:
        bits.append(f"{cohort} prepay-leaning cell")
    rate, period, lag = recovery_for_cohort(cohort)
    bits.append(f"cohort recovery {rate:.0%}/{period}mo scenario_lag_fallback={lag}")
    bits.append(STATE_LAG_NOTE)
    return "; ".join(bits)


def build_scenario_grid() -> list[Scenario]:
    rows: list[Scenario] = []
    i = 0
    for cohort in COHORTS:
        rate, period, lag = recovery_for_cohort(cohort)
        for psa in PSA_MULTIPLES:
            for sda in SDA_MULTIPLES:
                i += 1
                rows.append(
                    Scenario(
                        scenario_id=f"S{i:02d}",
                        cohort=cohort,
                        psa_multiple=psa,
                        sda_multiple=sda,
                        recovery_period_months=period,
                        recovery_lag_months=lag,
                        recovery_rate=rate,
                        note=_cell_note(cohort, psa, sda),
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
            "recovery_period_months": s.recovery_period_months,
            "recovery_lag_months": s.recovery_lag_months,
            "recovery_rate": s.recovery_rate,
            "state_varying_recovery_todo": s.state_varying_recovery_todo,
            "note": s.note,
        }
        for s in scenarios
    ]


def base_case_scenario(scenarios: list[Scenario] | None = None) -> Scenario:
    """First-cohort base cell at 100 PSA / 100 SDA."""
    scenarios = scenarios or build_scenario_grid()
    for s in scenarios:
        if (
            s.cohort == COHORTS[0]
            and s.psa_multiple == BASE_PSA
            and s.sda_multiple == BASE_SDA
        ):
            return s
    raise ValueError("base case 100 PSA / 100 SDA not found for first cohort")
