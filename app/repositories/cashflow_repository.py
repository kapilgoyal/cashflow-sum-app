"""Persist loan-level month-1 cash flows: Neon if DATABASE_URL, else SQLite + JSON."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = REPO_ROOT / "data"
SQLITE_NAME = "loan_cf_month1.sqlite"
LOAN_JSON = "loan_cf_month1.json"
AGG_JSON = "cohort_month1_cf.json"
AGG_CSV = "cohort_month1_cf.csv"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS loan_cashflows_month1 (
    scenario_id TEXT NOT NULL,
    loan_id TEXT NOT NULL,
    cohort TEXT NOT NULL,
    psa_multiple INTEGER,
    sda_multiple INTEGER,
    pca_level TEXT,
    sta_level TEXT,
    month INTEGER NOT NULL,
    beginning_balance DOUBLE PRECISION,
    interest DOUBLE PRECISION,
    scheduled_principal DOUBLE PRECISION,
    default_amt DOUBLE PRECISION,
    prepay DOUBLE PRECISION,
    recovery DOUBLE PRECISION,
    ending_balance DOUBLE PRECISION,
    loan_age INTEGER,
    cpr DOUBLE PRECISION,
    smm DOUBLE PRECISION,
    cdr DOUBLE PRECISION,
    mdr DOUBLE PRECISION,
    PRIMARY KEY (scenario_id, loan_id, month)
);
"""


def _resolve_db_url() -> str | None:
    return os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")


def _row_tuple(r: dict[str, Any]) -> tuple:
    return (
        r.get("scenario_id"),
        r.get("loan_id"),
        r.get("cohort"),
        r.get("psa_multiple"),
        r.get("sda_multiple"),
        r.get("pca_level"),
        r.get("sta_level"),
        int(r.get("month") or 1),
        r.get("beginning_balance"),
        r.get("interest"),
        r.get("scheduled_principal"),
        r.get("default"),
        r.get("prepay"),
        r.get("recovery"),
        r.get("ending_balance"),
        r.get("loan_age"),
        r.get("cpr"),
        r.get("smm"),
        r.get("cdr"),
        r.get("mdr"),
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

        # --- local JSON (loan-level + cohort aggregates) ---
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
        pd.DataFrame(aggregates).to_csv(self.agg_csv_path, index=False)
        status["json"] = {
            "loan_json": str(self.loan_json_path),
            "agg_json": str(self.agg_json_path),
            "agg_csv": str(self.agg_csv_path),
            "n_loan_rows": len(loan_rows),
            "n_aggregates": len(aggregates),
        }

        # --- SQLite always (offline default) ---
        try:
            status["sqlite"] = self._save_sqlite(loan_rows)
        except Exception as exc:  # noqa: BLE001
            status["sqlite"] = f"error: {type(exc).__name__}: {exc}"

        # --- Neon when configured ---
        url = _resolve_db_url()
        if not url:
            status["neon"] = "skipped: DATABASE_URL not set (using SQLite/local JSON)"
        else:
            try:
                status["neon"] = self._save_neon(url, loan_rows)
            except Exception as exc:  # noqa: BLE001
                status["neon"] = f"skipped: DB unreachable ({type(exc).__name__}: {exc})"

        return status

    def _save_sqlite(self, loan_rows: list[dict[str, Any]]) -> str:
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute(CREATE_SQL.replace("DOUBLE PRECISION", "REAL"))
            conn.execute("DELETE FROM loan_cashflows_month1")
            conn.executemany(
                """
                INSERT INTO loan_cashflows_month1 (
                    scenario_id, loan_id, cohort, psa_multiple, sda_multiple,
                    pca_level, sta_level, month, beginning_balance, interest,
                    scheduled_principal, default_amt, prepay, recovery,
                    ending_balance, loan_age, cpr, smm, cdr, mdr
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [_row_tuple(r) for r in loan_rows],
            )
            conn.commit()
        return f"wrote {len(loan_rows)} rows → {self.sqlite_path}"

    def _save_neon(self, url: str, loan_rows: list[dict[str, Any]]) -> str:
        try:
            import psycopg
        except ImportError:
            return "skipped: psycopg not installed"

        with psycopg.connect(url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute(CREATE_SQL)
                cur.execute("DELETE FROM loan_cashflows_month1")
                for r in loan_rows:
                    cur.execute(
                        """
                        INSERT INTO loan_cashflows_month1 (
                            scenario_id, loan_id, cohort, psa_multiple, sda_multiple,
                            pca_level, sta_level, month, beginning_balance, interest,
                            scheduled_principal, default_amt, prepay, recovery,
                            ending_balance, loan_age, cpr, smm, cdr, mdr
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        _row_tuple(r),
                    )
            conn.commit()
        return f"seeded {len(loan_rows)} rows into loan_cashflows_month1 (Neon)"

    def load_aggregates(self) -> dict[str, Any] | None:
        if not self.agg_json_path.exists():
            return None
        return json.loads(self.agg_json_path.read_text(encoding="utf-8"))
