"""CLI: full-horizon CF for all 27 grid scenarios via ProcessPoolExecutor.

Aggregates CF components (interest, scheduled_principal, prepay, new_default,
recovery, total_cash, principal_cash, beginning_balance) by scenario × month,
computes cohort AVG + WAL, writes JSON under data/ + public/, and saves
aggregates to Neon when DATABASE_URL is set.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.repositories.env_load import load_dotenv, resolve_pg_url  # noqa: E402
from app.repositories.scenario_repository import ScenarioRepository  # noqa: E402
from app.repositories.tape_repository import (  # noqa: E402
    TapeRepository,
    resolve_default_tape_path,
)
from app.services.base_case_cohort_cf import DEFAULT_HORIZON  # noqa: E402
from app.services.scenario_grid import build_scenario_grid  # noqa: E402
from app.services.scenario_grid_cf import (  # noqa: E402
    run_scenario_grid_cf,
    ui_payload,
)

DATA = ROOT / "data"
PUBLIC = ROOT / "public"
OUT_NAME = "scenario-grid-cashflow.json"


def _progress(done: int, total: int, res: dict) -> None:
    sid = res.get("scenario_id") or "?"
    status = res.get("status")
    wal = res.get("wal_years")
    ms = res.get("elapsed_ms")
    print(
        f"  [{done}/{total}] {sid} status={status} "
        f"n_loans={res.get('n_loans')} wal={wal} "
        f"horizon={res.get('horizon_months')} elapsed_ms={ms}",
        flush=True,
    )


def main() -> None:
    load_dotenv()
    months = DEFAULT_HORIZON
    if len(sys.argv) > 1:
        months = int(sys.argv[1])

    scenarios = build_scenario_grid()
    assert len(scenarios) == 27, len(scenarios)

    scen_csv = ScenarioRepository(DATA / "securitization_scenarios.csv")
    scen_csv.save_csv(scenarios)

    tape = TapeRepository(resolve_default_tape_path())
    t_load = time.perf_counter()
    loans = tape.load_all_loans()
    load_ms = (time.perf_counter() - t_load) * 1000.0
    print(f"Loaded {len(loans)} loans in {load_ms:.0f}ms", flush=True)
    print(
        f"Parallelism: ProcessPoolExecutor max_workers=27 "
        f"(full horizon perform={months} + recovery lag pad)",
        flush=True,
    )

    t0 = time.perf_counter()
    result = run_scenario_grid_cf(
        loans,
        scenarios,
        months=months,
        max_workers=27,
        keep_month1=False,
        progress_cb=_progress,
    )
    wall_s = time.perf_counter() - t0
    p = result["parallelism"]
    print(
        f"Wall clock: {wall_s:.1f}s ({p['wall_ms']:.0f}ms) "
        f"ok={p['ok']} error={p['error']} "
        f"loan_months={p['n_loan_months']} horizon={result['horizon_months']}",
        flush=True,
    )

    payload = ui_payload(result)
    text = json.dumps(payload, indent=2)
    DATA.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    data_path = DATA / OUT_NAME
    public_path = PUBLIC / OUT_NAME
    data_path.write_text(text, encoding="utf-8")
    public_path.write_text(text, encoding="utf-8")
    print(f"Wrote {data_path}", flush=True)
    print(f"Wrote {public_path}", flush=True)

    neon_info: dict | str | None = None
    neon_error: str | None = None
    if resolve_pg_url():
        try:
            from app.repositories.neon_cf_repository import NeonCfRepository

            neon = NeonCfRepository()
            neon_info = neon.save_scenario_grid_cf(
                scenarios,
                result["neon_month_rows"],
                result["wal_rows"],
            )
            print(f"Neon save: {json.dumps(neon_info)}", flush=True)
        except Exception as exc:  # noqa: BLE001
            neon_error = f"{type(exc).__name__}: {exc}"
            print(f"Neon save FAILED: {neon_error}", flush=True)
    else:
        neon_info = "skipped: DATABASE_URL not set"
        print(f"Neon: {neon_info}", flush=True)

    print("--- WAL (years) ---", flush=True)
    for sid, meta in sorted(result["scenarios"].items()):
        print(
            f"  {sid} {meta.get('cohort')} "
            f"PSA{meta.get('psa_multiple')}/SDA{meta.get('sda_multiple')} "
            f"wal={meta.get('wal_years')} cash_sum={meta.get('total_cash_sum')}",
            flush=True,
        )
    for cohort, meta in result["cohort_avg"].items():
        print(
            f"  AVG {cohort} wal={meta.get('wal_years')} "
            f"cash_sum={meta.get('total_cash_sum')}",
            flush=True,
        )

    summary = {
        "json": str(data_path),
        "public_json": str(public_path),
        "parallelism": p,
        "neon": neon_info,
        "neon_error": neon_error,
        "wall_s": round(wall_s, 2),
    }
    print("Summary:", json.dumps(summary, indent=2), flush=True)
    if neon_error:
        # JSON still written — non-zero only for hard CF failures.
        print("NOTE: Neon failed but JSON outputs were written.", flush=True)


if __name__ == "__main__":
    main()
