"""CLI: month-1 CF for all 27 scenario cells via ProcessPoolExecutor (27 workers).

Projects every loan in each cell's cohort for ONE MONTH only. Stores loan-level
rows in Neon when DATABASE_URL is set; otherwise SQLite + JSON under data/.
Writes cohort-level aggregates for the UI. Does NOT run a five-year horizon.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.repositories.cashflow_repository import CashflowRepository
from app.repositories.scenario_repository import ScenarioRepository
from app.repositories.tape_repository import TapeRepository
from app.services.month1_parallel import run_month1_parallel
from app.services.scenario_grid import build_scenario_grid

STORE = Path(
    r"C:\Users\kgoya\AppData\Local\Cursor\AgentStores\cursor_agent_stores"
    r"\bc-b8a045d3-83c0-4a57-9767-2701e9c67b11\files"
)
REPO_DATA = ROOT / "data"
STORE_DATA = STORE / "docs" / "data"
DOCS_DATA = ROOT / "docs" / "data"
PUBLIC = ROOT / "public"


def mirror(src: Path, *dests: Path) -> None:
    for d in dests:
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, d)


def main() -> None:
    REPO_DATA.mkdir(parents=True, exist_ok=True)
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    STORE_DATA.mkdir(parents=True, exist_ok=True)

    tape_src = STORE_DATA / "Minimum_Case.xlsx"
    tape_repo = DOCS_DATA / "Minimum_Case.xlsx"
    if tape_src.exists() and not tape_repo.exists():
        shutil.copy2(tape_src, tape_repo)

    scenarios = build_scenario_grid()
    assert len(scenarios) == 27, len(scenarios)

    scen_repo = ScenarioRepository(REPO_DATA / "securitization_scenarios.csv")
    csv_path = scen_repo.save_csv(scenarios)
    mirror(csv_path, DOCS_DATA / "securitization_scenarios.csv", STORE_DATA / "securitization_scenarios.csv")
    db_scenario = scen_repo.try_seed_neon(scenarios)

    tape = TapeRepository(tape_src if tape_src.exists() else tape_repo)
    t_load = time.perf_counter()
    loans = tape.load_all_loans()
    load_ms = (time.perf_counter() - t_load) * 1000.0
    print(f"Loaded {len(loans)} loans with cohort labels in {load_ms:.1f}ms")

    print(
        f"Parallelism: ProcessPoolExecutor max_workers=27 "
        f"(27 independent cohort×PCA×STA workers, month=1 only)"
    )
    result = run_month1_parallel(loans, scenarios, max_workers=27)
    wall = result["parallelism"]["wall_ms"]
    print(
        f"Wall clock: {wall:.1f}ms | ok={result['parallelism']['ok']} "
        f"error={result['parallelism']['error']} "
        f"loan_rows={result['parallelism']['n_loan_rows']}"
    )

    cf_repo = CashflowRepository(REPO_DATA)
    storage = cf_repo.save(
        loan_rows=result["loan_rows"],
        aggregates=result["aggregates"],
        meta={
            "parallelism": result["parallelism"],
            "assumptions": result["assumptions"],
            "ran_scenario_ids": result["ran_scenario_ids"],
            "scenario_db_seed": db_scenario,
            "tape_load_ms": round(load_ms, 3),
        },
    )

    # Mirror cohort aggregates + slim public JSON for the UI (no loan-level bulk).
    mirror(
        cf_repo.agg_json_path,
        DOCS_DATA / "cohort_month1_cf.json",
        STORE_DATA / "cohort_month1_cf.json",
        PUBLIC / "cohort-month1.json",
    )
    mirror(
        cf_repo.agg_csv_path,
        DOCS_DATA / "cohort_month1_cf.csv",
        STORE_DATA / "cohort_month1_cf.csv",
    )
    # Keep a compact summary JSON (aggregates only) under the old filename for continuity.
    slim = {
        "parallelism": result["parallelism"],
        "assumptions": result["assumptions"],
        "db_seed": storage,
        "aggregates": result["aggregates"],
    }
    slim_path = REPO_DATA / "scenario_month1_cf.json"
    slim_path.write_text(json.dumps(slim, indent=2), encoding="utf-8")
    mirror(slim_path, DOCS_DATA / "scenario_month1_cf.json", STORE_DATA / "scenario_month1_cf.json")

    import pandas as pd

    flat = pd.DataFrame(result["aggregates"])
    out_csv = REPO_DATA / "scenario_month1_cf.csv"
    flat.to_csv(out_csv, index=False)
    mirror(out_csv, DOCS_DATA / "scenario_month1_cf.csv", STORE_DATA / "scenario_month1_cf.csv")

    print("Storage:", json.dumps(storage, indent=2))
    if not storage.get("database_url_set"):
        print("NOTE: DATABASE_URL not set — Neon skipped; using SQLite/local JSON under data/")
    cols = [
        "scenario_id",
        "cohort",
        "pca_level",
        "sta_level",
        "n_loans",
        "interest",
        "scheduled_principal",
        "default",
        "prepay",
        "recovery",
        "ending_balance",
    ]
    print(flat[cols].to_string(index=False))


if __name__ == "__main__":
    main()
