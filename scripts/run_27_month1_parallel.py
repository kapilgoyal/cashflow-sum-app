"""Run month-1 cash flows for all 27 scenario cells in parallel.

Uses ProcessPoolExecutor (CPU-bound engine work) with max_workers=27 —
one independent worker per (cohort × PCA/PSA × STA/SDA) cell.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models.loan import Loan
from app.models.scenario import Scenario
from app.repositories.scenario_repository import ScenarioRepository
from app.repositories.tape_repository import TapeRepository
from app.services.cashflow_engine import project_loan_cashflows
from app.services.scenario_grid import (
    PSA_LEVEL_NAME,
    SDA_LEVEL_NAME,
    base_case_scenario,
    build_scenario_grid,
)

STORE = Path(
    r"C:\Users\kgoya\AppData\Local\Cursor\AgentStores\cursor_agent_stores"
    r"\bc-b8a045d3-83c0-4a57-9767-2701e9c67b11\files"
)
REPO_DATA = ROOT / "data"
STORE_DATA = STORE / "docs" / "data"
DOCS_DATA = ROOT / "docs" / "data"
INTERNAL = STORE / "internal"

SCENARIO_CSV = "securitization_scenarios.csv"
MONTH1_CSV = "scenario_month1_cf.csv"
MONTH1_JSON = "scenario_month1_cf.json"
META_JSON = "one_loan_cf_meta.json"
CF_CSV = "one_loan_cf_sample.csv"

MAX_WORKERS = 27


def mirror(src: Path, *dests: Path) -> None:
    for d in dests:
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, d)


def _worker(payload: dict) -> dict:
    """Picklable worker: one scenario × one loan → month-1 row."""
    t0 = time.perf_counter()
    try:
        loan = Loan(**payload["loan"])
        scenario = Scenario(**payload["scenario"])
        rows = project_loan_cashflows(loan, scenario, months=1)
        if not rows:
            raise RuntimeError("engine returned no rows")
        row = rows[0].model_dump()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "status": "ok",
            "scenario_id": scenario.scenario_id,
            "cohort": scenario.cohort,
            "psa_multiple": scenario.psa_multiple,
            "sda_multiple": scenario.sda_multiple,
            "pca_level": PSA_LEVEL_NAME[scenario.psa_multiple],
            "sta_level": SDA_LEVEL_NAME[scenario.sda_multiple],
            "recovery_rate": scenario.recovery_rate,
            "recovery_period_months": scenario.recovery_period_months,
            "recovery_lag_months": scenario.recovery_lag_months,
            "elapsed_ms": round(elapsed_ms, 3),
            "month1": row,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 — surface per-worker failures
        return {
            "status": "error",
            "scenario_id": payload.get("scenario", {}).get("scenario_id"),
            "cohort": payload.get("scenario", {}).get("cohort"),
            "psa_multiple": payload.get("scenario", {}).get("psa_multiple"),
            "sda_multiple": payload.get("scenario", {}).get("sda_multiple"),
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            "month1": None,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }


def main() -> None:
    REPO_DATA.mkdir(parents=True, exist_ok=True)
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    STORE_DATA.mkdir(parents=True, exist_ok=True)
    INTERNAL.mkdir(parents=True, exist_ok=True)

    tape_src = STORE_DATA / "Minimum_Case.xlsx"
    tape_repo = DOCS_DATA / "Minimum_Case.xlsx"
    if tape_src.exists() and not tape_repo.exists():
        shutil.copy2(tape_src, tape_repo)

    scenarios = build_scenario_grid()
    assert len(scenarios) == 27, len(scenarios)

    repo = ScenarioRepository(REPO_DATA / SCENARIO_CSV)
    csv_path = repo.save_csv(scenarios)
    mirror(csv_path, DOCS_DATA / SCENARIO_CSV, STORE_DATA / SCENARIO_CSV)
    db_status = repo.try_seed_neon(scenarios)

    tape = TapeRepository(tape_src if tape_src.exists() else tape_repo)
    loan = tape.get_loan()
    loan_dict = loan.model_dump()

    payloads = [
        {"loan": loan_dict, "scenario": s.model_dump()} for s in scenarios
    ]

    print(
        f"Parallelism: ProcessPoolExecutor max_workers={MAX_WORKERS} "
        f"({len(payloads)} independent cohort×PCA×STA workers)"
    )
    t_wall0 = time.perf_counter()
    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_worker, p): p["scenario"]["scenario_id"] for p in payloads}
        for fut in as_completed(futures):
            sid = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001
                res = {
                    "status": "error",
                    "scenario_id": sid,
                    "error": f"future: {type(exc).__name__}: {exc}",
                    "month1": None,
                    "elapsed_ms": None,
                }
            results.append(res)
            print(
                f"  [{res.get('status')}] {res.get('scenario_id')} "
                f"cohort={res.get('cohort')} "
                f"PCA={res.get('pca_level')} STA={res.get('sta_level')} "
                f"{res.get('elapsed_ms')}ms"
                + (f" ERR={res.get('error')}" if res.get("status") != "ok" else "")
            )

    wall_ms = (time.perf_counter() - t_wall0) * 1000.0
    results.sort(key=lambda r: r.get("scenario_id") or "")

    flat_rows = []
    for r in results:
        m1 = r.get("month1") or {}
        flat_rows.append(
            {
                "scenario_id": r.get("scenario_id"),
                "cohort": r.get("cohort"),
                "psa_multiple": r.get("psa_multiple"),
                "sda_multiple": r.get("sda_multiple"),
                "pca_level": r.get("pca_level"),
                "sta_level": r.get("sta_level"),
                "recovery_rate": r.get("recovery_rate"),
                "recovery_period_months": r.get("recovery_period_months"),
                "recovery_lag_months": r.get("recovery_lag_months"),
                "status": r.get("status"),
                "elapsed_ms": r.get("elapsed_ms"),
                "error": r.get("error"),
                "month": m1.get("month"),
                "beginning_balance": m1.get("beginning_balance"),
                "interest": m1.get("interest"),
                "scheduled_principal": m1.get("scheduled_principal"),
                "default": m1.get("default"),
                "prepay": m1.get("prepay"),
                "recovery": m1.get("recovery"),
                "ending_balance": m1.get("ending_balance"),
                "cpr": m1.get("cpr"),
                "cdr": m1.get("cdr"),
                "smm": m1.get("smm"),
                "mdr": m1.get("mdr"),
            }
        )

    cf_df = pd.DataFrame(flat_rows)
    out_csv = REPO_DATA / MONTH1_CSV
    cf_df.to_csv(out_csv, index=False)
    mirror(out_csv, DOCS_DATA / MONTH1_CSV, STORE_DATA / MONTH1_CSV)

    summary = {
        "parallelism": {
            "executor": "ProcessPoolExecutor",
            "max_workers": MAX_WORKERS,
            "n_tasks": len(payloads),
            "wall_ms": round(wall_ms, 3),
            "ok": sum(1 for r in results if r.get("status") == "ok"),
            "error": sum(1 for r in results if r.get("status") != "ok"),
        },
        "loan": loan_dict,
        "assumptions": {
            "horizon_months": 1,
            "pca_levels": {"Down": 75, "Base": 100, "Up": 125},
            "sta_levels": {"Down": 50, "Base": 100, "Up": 200},
            "recovery_by_cohort": {
                "high LTV and strong refinance incentive": {
                    "rate": 0.60,
                    "period_months": 12,
                    "lag_months": 0,
                },
                "high LTV and weak refinance incentive": {
                    "rate": 0.55,
                    "period_months": 15,
                    "lag_months": 0,
                },
                "low LTV and weak refinance incentive": {
                    "rate": 0.75,
                    "period_months": 9,
                    "lag_months": 0,
                },
            },
            "note": "PCA=PSA, STA=SDA (user synonym). Down/Base/Up from CF-41 ChatGPT grid.",
        },
        "db_seed": db_status,
        "workers": results,
    }
    out_json = REPO_DATA / MONTH1_JSON
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    mirror(out_json, DOCS_DATA / MONTH1_JSON, STORE_DATA / MONTH1_JSON)

    # Refresh base-case full CF sample + meta for README continuity
    base = base_case_scenario(scenarios)
    full_rows = project_loan_cashflows(loan, base, months=360)
    full_df = pd.DataFrame([r.model_dump() for r in full_rows])
    full_path = REPO_DATA / CF_CSV
    full_df.to_csv(full_path, index=False)
    mirror(full_path, DOCS_DATA / CF_CSV, STORE_DATA / CF_CSV)
    meta = {
        "loan": loan_dict,
        "scenario": base.model_dump(),
        "n_months": len(full_rows),
        "db_seed": db_status,
        "sample_rows": [
            r.model_dump() for r in full_rows[:6] + full_rows[11:13] + full_rows[59:61]
        ],
    }
    meta_path = REPO_DATA / META_JSON
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    mirror(meta_path, DOCS_DATA / META_JSON, STORE_DATA / META_JSON)

    print()
    print(f"Wall clock: {wall_ms:.1f}ms | ok={summary['parallelism']['ok']} "
          f"error={summary['parallelism']['error']}")
    print("Wrote:", out_csv)
    print("Wrote:", out_json)
    print(cf_df[["scenario_id", "cohort", "pca_level", "sta_level", "status",
                 "interest", "scheduled_principal", "default", "prepay",
                 "recovery", "ending_balance"]].to_string(index=False))


if __name__ == "__main__":
    main()
