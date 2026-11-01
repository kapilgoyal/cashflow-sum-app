"""Seed public.securitization_scenarios from the 27-cell scenario grid.

No loan math changes — dimension table only.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.repositories.env_load import load_dotenv, resolve_pg_url  # noqa: E402
from app.repositories.scenario_repository import ScenarioRepository  # noqa: E402
from app.services.scenario_grid import build_scenario_grid  # noqa: E402


def main() -> int:
    load_dotenv()
    url = resolve_pg_url()
    if not url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 1
    scenarios = build_scenario_grid()
    csv_path = REPO_ROOT / "data" / "securitization_scenarios.csv"
    repo = ScenarioRepository(csv_path)
    repo.save_csv(scenarios)
    msg = repo.try_seed_neon(scenarios)
    print(msg)
    print(f"grid_n={len(scenarios)} csv={csv_path}")

    import psycopg

    with psycopg.connect(url, connect_timeout=30) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.securitization_scenarios")
            n = cur.fetchone()[0]
            cur.execute(
                """
                SELECT COUNT(*) FROM public.loan_cashflows_month1 l
                LEFT JOIN public.securitization_scenarios s
                  ON l.scenario_id = s.scenario_id
                WHERE s.scenario_id IS NULL
                """
            )
            orphans = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM public.loan_cashflows_month1")
            cf_n = cur.fetchone()[0]
    print(f"scenarios_count={n} orphans={orphans} month1_cf={cf_n}")
    return 0 if n == 27 and orphans == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
