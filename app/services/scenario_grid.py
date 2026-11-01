"""Build the cohort × PSA × SDA securitization scenario grid.

PSA multiples are uniform across cohorts: 75 / 100 / 125 (base = 100 PSA).
SDA multiples: 50 / 100 / 200.
Full cross: 3 cohorts × 3 PSA × 3 SDA = 27 rows.

Cohorts map to tape strata:
- HLTV-HRI — high LTV + high refinance incentive
- HLTV-LRI — high LTV + low refinance incentive
- LLTV-LRI — low LTV (low refinance incentive / cleaner credit)

Historical pairing note (credit vs prepay stress) still applies when
*selecting* cells: HLTV rows lean toward higher-SDA cells; LLTV toward
higher-PSA / lower-SDA. The grid itself exposes the full product so
sensitivities are comparable across cohorts.
"""

from __future__ import annotations

from app.models.scenario import Scenario

COHORTS = ("LLTV-LRI", "HLTV-HRI", "HLTV-LRI")
PSA_MULTIPLES = (75, 100, 125)
SDA_MULTIPLES = (50, 100, 200)
BASE_PSA = 100
BASE_SDA = 100

RECOVERY_PERIOD_MONTHS = 6
RECOVERY_LAG_MONTHS = 0
RECOVERY_RATE = 0.60

STATE_TODO_NOTE = (
    "TODO: state-varying foreclosure/REO lag not implemented; "
    "recovery_period/lag are pool constants for now"
)


def _cell_note(cohort: str, psa: int, sda: int) -> str:
    bits = [f"{cohort} PSA{psa}/SDA{sda}"]
    if psa == BASE_PSA and sda == BASE_SDA:
        bits.append("BASE CASE (100 PSA / 100 SDA)")
    if "HLTV" in cohort and sda >= 100:
        bits.append("HLTV credit-leaning cell")
    if cohort == "LLTV-LRI" and psa >= 100 and sda <= 100:
        bits.append("LLTV prepay-leaning cell")
    bits.append(STATE_TODO_NOTE)
    return "; ".join(bits)


def build_scenario_grid(
    recovery_period_months: int = RECOVERY_PERIOD_MONTHS,
    recovery_lag_months: int = RECOVERY_LAG_MONTHS,
    recovery_rate: float = RECOVERY_RATE,
) -> list[Scenario]:
    rows: list[Scenario] = []
    i = 0
    for cohort in COHORTS:
        for psa in PSA_MULTIPLES:
            for sda in SDA_MULTIPLES:
                i += 1
                rows.append(
                    Scenario(
                        scenario_id=f"S{i:02d}",
                        cohort=cohort,
                        psa_multiple=psa,
                        sda_multiple=sda,
                        recovery_period_months=recovery_period_months,
                        recovery_lag_months=recovery_lag_months,
                        recovery_rate=recovery_rate,
                        note=_cell_note(cohort, psa, sda),
                        state_varying_recovery_todo=True,
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
    """First-cohort (LLTV-LRI) base cell at 100 PSA / 100 SDA."""
    scenarios = scenarios or build_scenario_grid()
    for s in scenarios:
        if (
            s.cohort == COHORTS[0]
            and s.psa_multiple == BASE_PSA
            and s.sda_multiple == BASE_SDA
        ):
            return s
    raise ValueError("base case 100 PSA / 100 SDA not found for first cohort")
