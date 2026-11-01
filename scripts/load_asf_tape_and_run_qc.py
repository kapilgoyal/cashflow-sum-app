"""Load Loan Tape → public.asf_tape; upsert QC defs; run QC; print summary.

Does not touch loan_cashflows_month1 or scenario tables.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.repositories.asf_tape_repository import AsfTapeRepository  # noqa: E402
from app.repositories.asf_tape_schema import ASF_TAPE_TABLE_SQL  # noqa: E402
from app.repositories.env_load import load_dotenv, resolve_pg_url  # noqa: E402


def main() -> int:
    load_dotenv()
    url = resolve_pg_url()
    if not url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 1
    # Redact password in any printed URL fragments
    safe = url.split("@")[-1] if "@" in url else "(local)"
    print(f"Neon host/db: {safe}")

    repo = AsfTapeRepository(url)
    repo.ensure_schema()
    print("--- asf_tape DDL ---")
    print(ASF_TAPE_TABLE_SQL.strip())

    df = repo.load_excel()
    n = repo.replace_tape(df)
    print(f"asf_tape rows loaded: {n}")
    print(f"asf_tape COUNT(*): {repo.count_tape()}")

    n_checks = repo.upsert_check_defs()
    print(f"qc_checks upserted: {n_checks}")

    run = repo.run_qc()
    print(f"qc run_id: {run['run_id']}")
    for r in run["results"]:
        print(
            json.dumps(
                {
                    "check_id": r["check_id"],
                    "outcome": r["outcome"],
                    "fail_count": r["fail_count"],
                    "pass_count": r["pass_count"],
                    "detail": r["detail"],
                    "sql_executed": r["sql_executed"],
                },
                default=str,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
