"""Generate scenario grid CSV + one-loan CF sample (100 PSA / 100 SDA)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.repositories.scenario_repository import ScenarioRepository
from app.repositories.tape_repository import TapeRepository
from app.services.cashflow_engine import project_loan_cashflows
from app.services.scenario_grid import base_case_scenario, build_scenario_grid

STORE = Path(
    r"C:\Users\kgoya\AppData\Local\Cursor\AgentStores\cursor_agent_stores"
    r"\bc-b8a045d3-83c0-4a57-9767-2701e9c67b11\files"
)
REPO_DATA = ROOT / "data"
STORE_DATA = STORE / "docs" / "data"
DOCS_DATA = ROOT / "docs" / "data"

SCENARIO_CSV = "securitization_scenarios.csv"
CF_CSV = "one_loan_cf_sample.csv"
META_JSON = "one_loan_cf_meta.json"


def mirror(src: Path, *dests: Path) -> None:
    for d in dests:
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, d)


def main() -> None:
    REPO_DATA.mkdir(parents=True, exist_ok=True)
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    STORE_DATA.mkdir(parents=True, exist_ok=True)

    # Mirror tape into repo docs/data if missing
    tape_src = STORE_DATA / "Minimum_Case.xlsx"
    tape_repo = DOCS_DATA / "Minimum_Case.xlsx"
    if tape_src.exists() and not tape_repo.exists():
        shutil.copy2(tape_src, tape_repo)

    scenarios = build_scenario_grid()
    repo = ScenarioRepository(REPO_DATA / SCENARIO_CSV)
    csv_path = repo.save_csv(scenarios)
    mirror(csv_path, DOCS_DATA / SCENARIO_CSV, STORE_DATA / SCENARIO_CSV)
    db_status = repo.try_seed_neon(scenarios)

    scenario = base_case_scenario(scenarios)
    tape = TapeRepository(tape_src if tape_src.exists() else tape_repo)
    loan = tape.get_loan()  # first Fixed loan (SYN000001)
    rows = project_loan_cashflows(loan, scenario, months=360)
    cf_df = pd.DataFrame([r.model_dump() for r in rows])
    cf_path = REPO_DATA / CF_CSV
    cf_df.to_csv(cf_path, index=False)
    mirror(cf_path, DOCS_DATA / CF_CSV, STORE_DATA / CF_CSV)

    meta = {
        "loan": loan.model_dump(),
        "scenario": scenario.model_dump(),
        "n_months": len(rows),
        "db_seed": db_status,
        "sample_rows": [r.model_dump() for r in rows[:6] + rows[11:13] + rows[59:61]],
    }
    meta_path = REPO_DATA / META_JSON
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    mirror(meta_path, DOCS_DATA / META_JSON, STORE_DATA / META_JSON)

    print("=== SCENARIO GRID ===")
    print(pd.DataFrame([{k: getattr(s, k) for k in (
        "scenario_id", "cohort", "psa_multiple", "sda_multiple",
        "recovery_period_months", "recovery_lag_months",
        "state_varying_recovery_todo",
    )} for s in scenarios]).to_string(index=False))
    print()
    print("DB:", db_status)
    print("Loan:", loan.loan_id, "bal", loan.current_balance, "rate", loan.annual_rate)
    print("Scenario:", scenario.scenario_id, scenario.cohort, scenario.psa_multiple, scenario.sda_multiple)
    print("=== SAMPLE CF ROWS ===")
    show = cf_df.loc[cf_df["month"].isin([1, 2, 3, 6, 12, 60, 120, 360]), [
        "month", "beginning_balance", "interest", "scheduled_principal",
        "default", "prepay", "recovery", "ending_balance",
    ]]
    print(show.to_string(index=False))
    print()
    print("Wrote:", csv_path)
    print("Wrote:", cf_path)


if __name__ == "__main__":
    main()
