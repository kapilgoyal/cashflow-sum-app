"""CLI: Base-scenario loan CF for all 3 cohorts → monthly total-cash aggregates.

Writes data/cohort-base-cashflow.json (+ public/ mirror) for the Scenarios chart.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.repositories.tape_repository import (  # noqa: E402
    TapeRepository,
    resolve_default_tape_path,
)
from app.services.base_case_cohort_cf import (  # noqa: E402
    DEFAULT_HORIZON,
    run_base_case_cohort_cf,
)

DATA = ROOT / "data"
PUBLIC = ROOT / "public"
OUT_NAME = "cohort-base-cashflow.json"


def main() -> None:
    months = DEFAULT_HORIZON
    if len(sys.argv) > 1:
        months = int(sys.argv[1])

    tape = TapeRepository(resolve_default_tape_path())
    t0 = time.perf_counter()
    loans = tape.load_all_loans()
    print(f"Loaded {len(loans)} loans in {(time.perf_counter() - t0) * 1000:.0f}ms")

    result = run_base_case_cohort_cf(loans, months=months)
    # Drop full loan_month1 from static JSON (keep summary counts); UI chart needs months.
    payload = {
        "scenario": result["scenario"],
        "perform_months": result["perform_months"],
        "horizon_months": result["horizon_months"],
        "seasoning": result["seasoning"],
        "recovery_source": result.get("recovery_source"),
        "recovery_tail": result["recovery_tail"],
        "cohorts": result["cohorts"],
        "months": result["months"],
        "recovery_months": result["recovery_months"],
        "parallelism": result["parallelism"],
        "n_loan_month1": len(result["loan_month1"]),
    }

    DATA.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2)
    (DATA / OUT_NAME).write_text(text, encoding="utf-8")
    (PUBLIC / OUT_NAME).write_text(text, encoding="utf-8")

    p = result["parallelism"]
    print(
        f"Done wall={p['wall_ms']:.0f}ms loans={p['n_loans']} "
        f"loan_months={p['n_loan_months']} horizon={result['horizon_months']}"
    )
    for cohort, meta in result["cohorts"].items():
        print(
            f"  {cohort}: n={meta['n_loans']} PSA{meta['psa_multiple']}/"
            f"SDA{meta['sda_multiple']} cash_sum=${meta['total_cash_sum']:,.0f}"
        )
    print(f"Wrote {DATA / OUT_NAME}")
    print(f"Wrote {PUBLIC / OUT_NAME}")


if __name__ == "__main__":
    main()
