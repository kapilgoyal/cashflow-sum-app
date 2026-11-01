"""Load Minimum Case Loan Tape → public.asf_tape; persist + run QC checks.

Touches only asf_tape / qc_checks / qc_results — never loan_cashflows_month1.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg

from app.repositories.asf_qc_checks import ALL_CHECKS, checks_as_rows
from app.repositories.asf_tape_schema import (
    ASF_TAPE_COLUMNS,
    ASF_TAPE_TABLE_SQL,
    EXCEL_TO_ASF,
    QC_CHECKS_TABLE_SQL,
    QC_RESULTS_TABLE_SQL,
)
from app.repositories.env_load import load_dotenv, resolve_pg_url
from app.repositories.tape_repository import DEFAULT_TAPE

INSERT_COLS = ", ".join(ASF_TAPE_COLUMNS)
INSERT_PLACEHOLDERS = ", ".join(f"%s" for _ in ASF_TAPE_COLUMNS)


def _to_py(v: Any) -> Any:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime().date()
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if hasattr(v, "item"):
        try:
            return v.item()
        except (ValueError, AttributeError):
            pass
    return v


class AsfTapeRepository:
    def __init__(self, url: str | None = None) -> None:
        load_dotenv()
        self.url = url or resolve_pg_url()

    def require_url(self) -> str:
        if not self.url:
            raise RuntimeError("DATABASE_URL not set")
        return self.url

    def ensure_schema(self) -> None:
        with psycopg.connect(self.require_url(), connect_timeout=60) as conn:
            with conn.cursor() as cur:
                cur.execute(ASF_TAPE_TABLE_SQL)
                cur.execute(QC_CHECKS_TABLE_SQL)
                cur.execute(QC_RESULTS_TABLE_SQL)
            conn.commit()

    def load_excel(self, path: Path | str | None = None) -> pd.DataFrame:
        tape_path = Path(path) if path else DEFAULT_TAPE
        if not tape_path.exists():
            # Repo-bundled copy used when Agent Store path is unavailable.
            alt = Path(__file__).resolve().parents[2] / "docs" / "data" / "Minimum_Case.xlsx"
            if alt.exists():
                tape_path = alt
            else:
                raise FileNotFoundError(f"Loan tape not found: {tape_path}")
        df = pd.read_excel(tape_path, sheet_name="Loan Tape")
        if "LOAN_ID" in df.columns:
            df = df.drop_duplicates(subset=["LOAN_ID"], keep="first")
        out = pd.DataFrame()
        for excel_col, asf_col in EXCEL_TO_ASF.items():
            if excel_col in df.columns:
                out[asf_col] = df[excel_col]
            else:
                out[asf_col] = None
        # postal_code as 5-char text (pad; Excel int 0 → "00000" unavailable)
        if "postal_code" in out.columns:

            def _zip_text(x: Any) -> str | None:
                if x is None or (isinstance(x, float) and pd.isna(x)):
                    return None
                if pd.isna(x):
                    return None
                try:
                    n = float(x)
                    if n.is_integer():
                        return f"{int(n):05d}"
                except (TypeError, ValueError):
                    pass
                s = str(x).strip()
                if s.endswith(".0") and s[:-2].isdigit():
                    s = s[:-2]
                if s.isdigit() and len(s) <= 5:
                    return s.zfill(5)
                return s

            out["postal_code"] = out["postal_code"].map(_zip_text)
        return out

    def replace_tape(self, df: pd.DataFrame) -> int:
        rows: list[tuple[Any, ...]] = []
        for _, r in df.iterrows():
            rows.append(tuple(_to_py(r.get(c)) for c in ASF_TAPE_COLUMNS))
        with psycopg.connect(self.require_url(), connect_timeout=120) as conn:
            with conn.cursor() as cur:
                cur.execute(ASF_TAPE_TABLE_SQL)
                cur.execute("TRUNCATE public.asf_tape")
                with cur.copy(
                    f"COPY public.asf_tape ({INSERT_COLS}) FROM STDIN"
                ) as copy:
                    for row in rows:
                        copy.write_row(row)
            conn.commit()
        return len(rows)

    def count_tape(self) -> int:
        with psycopg.connect(self.require_url(), connect_timeout=30) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM public.asf_tape")
                return int(cur.fetchone()[0])

    def tape_columns(self) -> set[str]:
        with psycopg.connect(self.require_url(), connect_timeout=30) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'asf_tape'
                    """
                )
                return {r[0] for r in cur.fetchall()}

    def upsert_check_defs(self) -> int:
        rows = checks_as_rows()
        sql = """
            INSERT INTO public.qc_checks (
                check_id, source, edit_number, nl_description, sql_predicate,
                required_columns, status_mode, skip_reason, updated_at
            ) VALUES (
                %(check_id)s, %(source)s, %(edit_number)s, %(nl_description)s,
                %(sql_predicate)s, %(required_columns)s, %(status_mode)s,
                %(skip_reason)s, now()
            )
            ON CONFLICT (check_id) DO UPDATE SET
                source = EXCLUDED.source,
                edit_number = EXCLUDED.edit_number,
                nl_description = EXCLUDED.nl_description,
                sql_predicate = EXCLUDED.sql_predicate,
                required_columns = EXCLUDED.required_columns,
                status_mode = EXCLUDED.status_mode,
                skip_reason = EXCLUDED.skip_reason,
                updated_at = now()
        """
        with psycopg.connect(self.require_url(), connect_timeout=60) as conn:
            with conn.cursor() as cur:
                cur.execute(QC_CHECKS_TABLE_SQL)
                for row in rows:
                    cur.execute(sql, row)
            conn.commit()
        return len(rows)

    def run_qc(self, run_id: str | None = None) -> dict[str, Any]:
        run_id = run_id or uuid.uuid4().hex[:12]
        cols = self.tape_columns()
        tape_n = self.count_tape()
        results: list[dict[str, Any]] = []

        with psycopg.connect(self.require_url(), connect_timeout=120) as conn:
            with conn.cursor() as cur:
                cur.execute(QC_RESULTS_TABLE_SQL)
                for check in ALL_CHECKS:
                    missing = [c for c in check.required_columns if c not in cols]
                    if check.sql_predicate is None or missing:
                        detail = check.skip_reason or (
                            f"asf_tape lacks required field(s): {', '.join(missing)}"
                            if missing
                            else "no SQL predicate"
                        )
                        row = {
                            "check_id": check.check_id,
                            "run_id": run_id,
                            "outcome": "skipped",
                            "tape_row_count": tape_n,
                            "fail_count": None,
                            "pass_count": None,
                            "sql_executed": None,
                            "detail": detail,
                        }
                    else:
                        sql = (
                            f"SELECT COUNT(*) FROM public.asf_tape "
                            f"WHERE {check.sql_predicate}"
                        )
                        cur.execute(sql)
                        fail_n = int(cur.fetchone()[0])
                        pass_n = tape_n - fail_n
                        outcome = "fail" if fail_n > 0 else "pass"
                        row = {
                            "check_id": check.check_id,
                            "run_id": run_id,
                            "outcome": outcome,
                            "tape_row_count": tape_n,
                            "fail_count": fail_n,
                            "pass_count": pass_n,
                            "sql_executed": sql,
                            "detail": None,
                        }
                    cur.execute(
                        """
                        INSERT INTO public.qc_results (
                            check_id, run_id, ran_at, outcome, tape_row_count,
                            fail_count, pass_count, sql_executed, detail
                        ) VALUES (
                            %(check_id)s, %(run_id)s, now(), %(outcome)s,
                            %(tape_row_count)s, %(fail_count)s, %(pass_count)s,
                            %(sql_executed)s, %(detail)s
                        )
                        ON CONFLICT (check_id, run_id) DO UPDATE SET
                            ran_at = now(),
                            outcome = EXCLUDED.outcome,
                            tape_row_count = EXCLUDED.tape_row_count,
                            fail_count = EXCLUDED.fail_count,
                            pass_count = EXCLUDED.pass_count,
                            sql_executed = EXCLUDED.sql_executed,
                            detail = EXCLUDED.detail
                        """,
                        row,
                    )
                    results.append(row)
            conn.commit()

        return {"run_id": run_id, "tape_row_count": tape_n, "results": results}

    def latest_results(self) -> list[dict[str, Any]]:
        """Latest run results joined with check definitions, demo first then edits."""
        sql = """
            WITH latest AS (
                SELECT run_id
                FROM public.qc_results
                ORDER BY ran_at DESC
                LIMIT 1
            )
            SELECT
                c.check_id,
                c.source,
                c.edit_number,
                c.nl_description,
                c.sql_predicate,
                c.required_columns,
                c.status_mode,
                c.skip_reason,
                r.run_id,
                r.ran_at,
                r.outcome,
                r.tape_row_count,
                r.fail_count,
                r.pass_count,
                r.sql_executed,
                r.detail
            FROM public.qc_checks c
            LEFT JOIN public.qc_results r
              ON r.check_id = c.check_id
             AND r.run_id = (SELECT run_id FROM latest)
            ORDER BY
                CASE c.source WHEN 'demo' THEN 0 ELSE 1 END,
                c.edit_number NULLS FIRST,
                c.check_id
        """
        with psycopg.connect(self.require_url(), connect_timeout=30) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                cols = [d.name for d in cur.description]
                out = []
                for tup in cur.fetchall():
                    row = dict(zip(cols, tup))
                    if isinstance(row.get("ran_at"), datetime):
                        row["ran_at"] = row["ran_at"].isoformat()
                    if row.get("required_columns") is not None:
                        row["required_columns"] = list(row["required_columns"])
                    out.append(row)
                return out
