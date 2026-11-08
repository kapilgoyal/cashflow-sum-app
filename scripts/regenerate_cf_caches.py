"""Regenerate month1 / base / scenario-grid CF JSON with current engine (CF-176).

Local only — writes data/ + public/ JSON stamped with ENGINE_VERSION +
assumptions_fingerprint. Does not push or deploy.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.repositories.scenario_repository import ScenarioRepository  # noqa: E402
from app.repositories.tape_repository import TapeRepository, resolve_default_tape_path  # noqa: E402
from app.services.base_case_cohort_cf import base_scenarios, run_base_case_cohort_cf  # noqa: E402
from app.services.cache_keys import assumptions_fingerprint, cf_cache_meta, tape_hash  # noqa: E402
from app.services.cashflow_engine import ENGINE_VERSION  # noqa: E402
from app.services.month1_parallel import run_month1_parallel  # noqa: E402
from app.services.scenario_grid import build_scenario_grid  # noqa: E402
from app.services.scenario_grid_cf import run_scenario_grid_cf, ui_payload  # noqa: E402

DATA = ROOT / "data"
PUBLIC = ROOT / "public"


def _stamp(kind: str, scenario, months: int | None) -> dict:
    tape = resolve_default_tape_path()
    meta = cf_cache_meta(
        tape_path=tape, scenario=scenario, months=months, kind=kind
    )
    return {
        "engine_version": ENGINE_VERSION,
        "assumptions_fingerprint": assumptions_fingerprint(),
        "tape_hash": tape_hash(tape),
        "cache": meta,
    }


def main() -> None:
    tape_path = resolve_default_tape_path()
    print(f"tape={tape_path}")
    print(f"engine={ENGINE_VERSION}")
    print(f"assumptions={assumptions_fingerprint()}")
    loans = TapeRepository(tape_path).load_all_loans()
    print(f"loans={len(loans)}")
    scenarios = build_scenario_grid()
    ScenarioRepository(DATA / "securitization_scenarios.csv").save_csv(scenarios)
    DATA.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)

    # --- month 1 ---
    print("running month1…")
    m1 = run_month1_parallel(loans, scenarios, max_workers=27)
    stamp = _stamp("month1_cf", scenarios[0], 1)
    meta = {
        "parallelism": m1["parallelism"],
        "assumptions": {
            **m1["assumptions"],
            "engine_version": ENGINE_VERSION,
            "assumptions_fingerprint": stamp["assumptions_fingerprint"],
            "same_engine_as": "POST /api/run-loan (project_loan_cashflows)",
        },
        "ran_scenario_ids": m1["ran_scenario_ids"],
        **stamp,
    }
    from app.repositories.cashflow_repository import CashflowRepository

    CashflowRepository(DATA).save(
        loan_rows=m1["loan_rows"],
        aggregates=m1["aggregates"],
        meta=meta,
    )
    public_m1 = {"meta": meta, "aggregates": m1["aggregates"], **stamp}
    (PUBLIC / "cohort-month1.json").write_text(
        json.dumps(public_m1, indent=2), encoding="utf-8"
    )
    print(f"  month1 ok={m1['parallelism'].get('ok')} rows={len(m1['loan_rows'])}")

    # --- base cohort ---
    print("running base cohort…")
    base = run_base_case_cohort_cf(loans, months=360)
    base_sc = base_scenarios()[0]
    stamp_b = _stamp("base_cohort_cf", base_sc, 360)
    base_payload = {
        "scenario": base["scenario"],
        "perform_months": base["perform_months"],
        "horizon_months": base["horizon_months"],
        "seasoning": base["seasoning"],
        "recovery_source": base.get("recovery_source"),
        "recovery_tail": base["recovery_tail"],
        "cohorts": base["cohorts"],
        "months": base["months"],
        "recovery_months": base["recovery_months"],
        "parallelism": base["parallelism"],
        "n_loan_month1": len(base["loan_month1"]),
        **stamp_b,
        "cached": False,
    }
    text_b = json.dumps(base_payload, indent=2)
    (DATA / "cohort-base-cashflow.json").write_text(text_b, encoding="utf-8")
    (PUBLIC / "cohort-base-cashflow.json").write_text(text_b, encoding="utf-8")
    print(f"  base horizon={base['horizon_months']}")

    # --- 27 scenario grid ---
    print("running scenario grid (27)…")
    grid = run_scenario_grid_cf(
        loans, scenarios, months=360, max_workers=27, keep_month1=False
    )
    payload = ui_payload(grid)
    stamp_g = _stamp("scenario_grid_cf", scenarios[0], 360)
    payload.update(stamp_g)
    payload["cached"] = False
    text_g = json.dumps(payload, indent=2)
    (DATA / "scenario-grid-cashflow.json").write_text(text_g, encoding="utf-8")
    (PUBLIC / "scenario-grid-cashflow.json").write_text(text_g, encoding="utf-8")
    print(f"  grid scenarios={len(payload.get('scenarios') or [])}")
    print("done.")


if __name__ == "__main__":
    main()
