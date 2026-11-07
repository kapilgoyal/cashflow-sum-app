"""Persist loan-level month-1 cash flows: DATABASE_URL (sqlite or Neon) + JSON.

Neon fact table is normalized (scenario_id FK + CF measures only). Scenario
definition fields come from securitization_scenarios via the enriched view.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.repositories.cashflow_schema import (
    LOAN_CF_MONTH1_ADD_PANEL_COLS_SQL,
    LOAN_CF_MONTH1_ENRICHED_VIEW_SQL,
    LOAN_CF_MONTH1_TABLE_SQL,
    MONTH1_FACT_COLS,
)
from app.repositories.connect import connect, is_postgres_url
from app.repositories.scenario_repository import CREATE_SQL as SCENARIO_SQL

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = REPO_ROOT / "data"
SQLITE_NAME = "loan_cf_month1.sqlite"
LOAN_JSON = "loan_cf_month1.json"
AGG_JSON = "cohort_month1_cf.json"
AGG_CSV = "cohort_month1_cf.csv"

# Back-compat alias used by older import sites / load helpers.
CREATE_SQL = LOAN_CF_MONTH1_TABLE_SQL


def _resolve_db_url() -> str | None:
    from app.repositories.connect import resolve_database_url

    return resolve_database_url()


def _fact_tuple(r: dict[str, Any]) -> tuple:
    default_amt = r.get("default_amt", r.get("default", r.get("new_default")))
    used_lag = r.get("used_recovery_lag_months")
    return (
        r.get("scenario_id"),
        r.get("loan_id"),
        int(r.get("month") or 1),
        r.get("beginning_balance"),
        r.get("interest"),
        r.get("scheduled_principal"),
        default_amt,
        r.get("prepay"),
        r.get("recovery"),
        r.get("ending_balance"),
        r.get("loan_age"),
        r.get("cpr"),
        r.get("smm"),
        r.get("cdr"),
        r.get("mdr"),
        int(used_lag) if used_lag is not None else None,
        r.get("beginning_default_balance"),
        r.get("liquidated_default"),
        r.get("realized_loss"),
        r.get("ending_default_balance"),
        r.get("total_cash"),
    )


class CashflowRepository:
    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else DEFAULT_DATA
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_path = self.data_dir / SQLITE_NAME
        self.loan_json_path = self.data_dir / LOAN_JSON
        self.agg_json_path = self.data_dir / AGG_JSON
        self.agg_csv_path = self.data_dir / AGG_CSV

    def save(
        self,
        loan_rows: list[dict[str, Any]],
        aggregates: list[dict[str, Any]],
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Write local JSON/CSV/SQLite always; try Neon when DATABASE_URL set."""
        status: dict[str, Any] = {
            "neon": None,
            "sqlite": None,
            "json": None,
            "database_url_set": bool(_resolve_db_url()),
        }

        payload = {
            "meta": meta or {},
            "aggregates": aggregates,
            "loan_rows": loan_rows,
        }
        self.loan_json_path.write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        agg_payload = {
            "meta": meta or {},
            "aggregates": aggregates,
            "neon_note": (
                None
                if _resolve_db_url()
                else "DATABASE_URL not set — loan-level CF stored in SQLite/JSON under data/"
            ),
        }
        self.agg_json_path.write_text(
            json.dumps(agg_payload, indent=2), encoding="utf-8"
        )
        import pandas as pd

        pd.DataFrame(aggregates).to_csv(self.agg_csv_path, index=False)
        status["json"] = {
            "loan_json": str(self.loan_json_path),
            "agg_json": str(self.agg_json_path),
            "agg_csv": str(self.agg_csv_path),
            "n_loan_rows": len(loan_rows),
            "n_aggregates": len(aggregates),
        }

        try:
            status["sqlite"] = self._save_sqlite(loan_rows)
        except Exception as exc:  # noqa: BLE001
            status["sqlite"] = f"error: {type(exc).__name__}: {exc}"

        url = _resolve_db_url()
        if not url:
            status["neon"] = "skipped: DATABASE_URL not set (using SQLite/local JSON)"
        else:
            try:
                status["neon"] = self._save_database(url, loan_rows)
            except Exception as exc:  # noqa: BLE001
                status["neon"] = f"skipped: DB unreachable ({type(exc).__name__}: {exc})"

        return status

    def _save_sqlite(self, loan_rows: list[dict[str, Any]]) -> str:
        sqlite_ddl = """
        CREATE TABLE IF NOT EXISTS loan_cashflows_month1 (
            scenario_id TEXT NOT NULL,
            loan_id TEXT NOT NULL,
            month INTEGER NOT NULL,
            beginning_balance REAL,
            interest REAL,
            scheduled_principal REAL,
            default_amt REAL,
            prepay REAL,
            recovery REAL,
            ending_balance REAL,
            loan_age INTEGER,
            cpr REAL,
            smm REAL,
            cdr REAL,
            mdr REAL,
            used_recovery_lag_months INTEGER,
            beginning_default_balance REAL,
            liquidated_default REAL,
            realized_loss REAL,
            ending_default_balance REAL,
            total_cash REAL,
            PRIMARY KEY (scenario_id, loan_id, month)
        );
        """
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute("DROP TABLE IF EXISTS loan_cashflows_month1")
            conn.execute(sqlite_ddl)
            conn.executemany(
                f"""
                INSERT INTO loan_cashflows_month1 (
                    {", ".join(MONTH1_FACT_COLS)}
                ) VALUES ({", ".join("?" for _ in MONTH1_FACT_COLS)})
                """,
                [_fact_tuple(r) for r in loan_rows],
            )
            conn.commit()
        return f"wrote {len(loan_rows)} rows → {self.sqlite_path}"

    def _save_database(self, url: str, loan_rows: list[dict[str, Any]]) -> str:
        with connect(url, connect_timeout=30) as conn:
            with conn.cursor() as cur:
                cur.execute(SCENARIO_SQL)
                cur.execute(LOAN_CF_MONTH1_TABLE_SQL)
                cur.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='loan_cashflows_month1'
                    """
                )
                cols = {r[0] for r in cur.fetchall()}
                if is_postgres_url(url) and (
                    not cols or "cohort" in cols or "psa_multiple" in cols
                ):
                    raise RuntimeError(
                        "loan_cashflows_month1 is missing or denormalized — "
                        "run scripts/migrate_normalize_loan_cf_month1.py first"
                    )
                for stmt in LOAN_CF_MONTH1_ADD_PANEL_COLS_SQL.strip().split(";"):
                    s = stmt.strip()
                    if s:
                        cur.execute(s)
                cur.execute("DELETE FROM loan_cashflows_month1")
                copy_sql = (
                    "COPY loan_cashflows_month1 ("
                    + ", ".join(MONTH1_FACT_COLS)
                    + ") FROM STDIN"
                )
                with cur.copy(copy_sql) as copy_writer:
                    for r in loan_rows:
                        copy_writer.write_row(_fact_tuple(r))
                cur.execute(LOAN_CF_MONTH1_ENRICHED_VIEW_SQL)
            conn.commit()
        kind = "Neon" if is_postgres_url(url) else "SQLite"
        return (
            f"seeded {len(loan_rows)} normalized rows into "
            f"loan_cashflows_month1 ({kind})"
        )

    def load_aggregates(self) -> dict[str, Any] | None:
        if not self.agg_json_path.exists():
            return None
        return json.loads(self.agg_json_path.read_text(encoding="utf-8"))
