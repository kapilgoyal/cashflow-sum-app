from __future__ import annotations

import os
from pathlib import Path

from app.models.scenario import Scenario
from app.services.scenario_grid import build_scenario_grid, scenarios_to_records

CREATE_SQL = """
-- TODO: state-varying foreclosure/REO lag not implemented; columns are pool constants.
CREATE TABLE IF NOT EXISTS securitization_scenarios (
    scenario_id TEXT PRIMARY KEY,
    cohort TEXT NOT NULL,
    psa_multiple INTEGER NOT NULL,
    sda_multiple INTEGER NOT NULL,
    recovery_period_months INTEGER NOT NULL,
    recovery_lag_months INTEGER NOT NULL,
    recovery_rate DOUBLE PRECISION NOT NULL,
    state_varying_recovery_todo BOOLEAN NOT NULL DEFAULT TRUE,
    note TEXT
);
"""


class ScenarioRepository:
    def __init__(self, csv_path: Path | str) -> None:
        self.csv_path = Path(csv_path)

    def save_csv(self, scenarios: list[Scenario] | None = None) -> Path:
        import pandas as pd

        scenarios = scenarios or build_scenario_grid()
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(scenarios_to_records(scenarios))
        df.to_csv(self.csv_path, index=False)
        return self.csv_path

    def try_seed_neon(self, scenarios: list[Scenario] | None = None) -> str:
        """Seed Neon/Postgres when DATABASE_URL is set and reachable."""
        try:
            from app.repositories.env_load import load_dotenv, resolve_pg_url

            load_dotenv()
            url = resolve_pg_url()
        except Exception:  # noqa: BLE001
            url = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
        if not url:
            return "skipped: DATABASE_URL not set"

        scenarios = scenarios or build_scenario_grid()
        try:
            import psycopg
        except ImportError:
            return "skipped: psycopg not installed"

        try:
            with psycopg.connect(url, connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    cur.execute(CREATE_SQL)
                    cur.execute("DELETE FROM securitization_scenarios")
                    for s in scenarios:
                        cur.execute(
                            """
                            INSERT INTO securitization_scenarios (
                                scenario_id, cohort, psa_multiple, sda_multiple,
                                recovery_period_months, recovery_lag_months,
                                recovery_rate, state_varying_recovery_todo, note
                            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            """,
                            (
                                s.scenario_id,
                                s.cohort,
                                s.psa_multiple,
                                s.sda_multiple,
                                s.recovery_period_months,
                                s.recovery_lag_months,
                                s.recovery_rate,
                                s.state_varying_recovery_todo,
                                s.note,
                            ),
                        )
                conn.commit()
            return f"seeded {len(scenarios)} rows into securitization_scenarios"
        except Exception as exc:  # noqa: BLE001 — report and continue offline
            return f"skipped: DB unreachable ({type(exc).__name__}: {exc})"
