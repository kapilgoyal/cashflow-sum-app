"""Load Minimum Case Loan Tape → public.asf_tape; persist + run QC checks.

Touches only asf_tape / qc_checks / qc_results — never loan_cashflows_month1.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.repositories.asf_qc_checks import (
    ALL_CHECKS,
    CHECKS_BY_ID,
    checks_as_rows,
)
from app.repositories.asf_tape_schema import (
    ASF_TAPE_COLUMNS,
    ASF_TAPE_HAS_MI_ALTER_SQL,
    ASF_TAPE_HAS_MI_BACKFILL_SQL,
    ASF_TAPE_HAS_MI_NOT_NULL_SQL,
    ASF_TAPE_TABLE_SQL,
    EXCEL_TO_ASF,
    QC_CHECKS_TABLE_SQL,
    QC_RESULTS_TABLE_SQL,
)
from app.services.assumptions import default_has_mi
from app.repositories.connect import connect
from app.repositories.env_load import load_dotenv, resolve_pg_url
from app.repositories.tape_repository import DEFAULT_TAPE, TapeRepository
from app.services.cohort_labels import (
    canonical_cohort_label,
    cohort_match_values,
    relabel_records,
)
from app.services.recovery import recovery_lag_months_for_state
from app.services.scenario_grid import recovery_for_cohort
from app.services.severity import resolve_loan_recovery_rate


INSERT_COLS = ", ".join(ASF_TAPE_COLUMNS)
INSERT_PLACEHOLDERS = ", ".join(f"%s" for _ in ASF_TAPE_COLUMNS)


def _pd():
    """Lazy pandas — keep container boot light (Neon paths don't need it)."""
    import pandas as pd

    return pd


def _to_py(v: Any) -> Any:
    pd = _pd()
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
        with connect(self.require_url(), connect_timeout=60) as conn:
            with conn.cursor() as cur:
                cur.execute(ASF_TAPE_TABLE_SQL)
                cur.execute(ASF_TAPE_HAS_MI_ALTER_SQL)
                cur.execute(ASF_TAPE_HAS_MI_BACKFILL_SQL)
            conn.commit()
            with conn.cursor() as cur:
                try:
                    cur.execute(ASF_TAPE_HAS_MI_NOT_NULL_SQL)
                    conn.commit()
                except Exception:  # noqa: BLE001
                    conn.rollback()
            with conn.cursor() as cur:
                cur.execute(QC_CHECKS_TABLE_SQL)
                cur.execute(QC_RESULTS_TABLE_SQL)
            conn.commit()

    def ensure_has_mi_column(self) -> bool:
        """Add + backfill has_mi DEFAULT true NOT NULL. Returns True if present."""
        with connect(self.require_url(), connect_timeout=60) as conn:
            with conn.cursor() as cur:
                cur.execute(ASF_TAPE_HAS_MI_ALTER_SQL)
                cur.execute(ASF_TAPE_HAS_MI_BACKFILL_SQL)
            conn.commit()
            with conn.cursor() as cur:
                try:
                    cur.execute(ASF_TAPE_HAS_MI_NOT_NULL_SQL)
                    conn.commit()
                except Exception:  # noqa: BLE001
                    # Column usable even if NOT NULL enforcement fails.
                    conn.rollback()
        return "has_mi" in self.tape_columns()

    def load_excel(self, path: Path | str | None = None) -> Any:
        pd = _pd()
        tape_path = Path(path) if path else DEFAULT_TAPE
        if not tape_path.exists():
            repo = Path(__file__).resolve().parents[2]
            for alt in (
                repo / "data" / "Minimum_Case.xlsx",
                repo / "docs" / "data" / "Minimum_Case.xlsx",
            ):
                if alt.exists():
                    tape_path = alt
                    break
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
        # postal_code as text (preserve leading zeros when present)
        if "postal_code" in out.columns:
            out["postal_code"] = out["postal_code"].map(
                lambda x: None
                if x is None or (isinstance(x, float) and pd.isna(x))
                else str(int(x))
                if isinstance(x, (int, float)) and float(x).is_integer()
                else str(x).strip()
            )
        # has_mi from data/assumptions.csv — never from monthly_insurance_cost.
        out["has_mi"] = bool(default_has_mi())
        return out

    def replace_tape(self, df: Any) -> int:
        rows: list[tuple[Any, ...]] = []
        for _, r in df.iterrows():
            rows.append(tuple(_to_py(r.get(c)) for c in ASF_TAPE_COLUMNS))
        with connect(self.require_url(), connect_timeout=120) as conn:
            with conn.cursor() as cur:
                cur.execute(ASF_TAPE_TABLE_SQL)
                cur.execute(ASF_TAPE_HAS_MI_ALTER_SQL)
                cur.execute(ASF_TAPE_HAS_MI_BACKFILL_SQL)
                try:
                    cur.execute(ASF_TAPE_HAS_MI_NOT_NULL_SQL)
                except Exception:  # noqa: BLE001
                    pass
                cur.execute("TRUNCATE public.asf_tape")
                with cur.copy(
                    f"COPY public.asf_tape ({INSERT_COLS}) FROM STDIN"
                ) as copy:
                    for row in rows:
                        copy.write_row(row)
            conn.commit()
        return len(rows)

    def count_tape(self) -> int:
        with connect(self.require_url(), connect_timeout=30) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM public.asf_tape")
                return int(cur.fetchone()[0])

    def tape_columns(self) -> set[str]:
        with connect(self.require_url(), connect_timeout=30) as conn:
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
        keep_ids = tuple(r["check_id"] for r in rows)
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
                status_mode = CASE
                    WHEN public.qc_checks.status_mode = 'disabled'
                    THEN 'disabled'
                    ELSE EXCLUDED.status_mode
                END,
                skip_reason = EXCLUDED.skip_reason,
                updated_at = now()
        """
        with connect(self.require_url(), connect_timeout=60) as conn:
            with conn.cursor() as cur:
                cur.execute(QC_CHECKS_TABLE_SQL)
                for row in rows:
                    cur.execute(sql, row)
                # Drop retired built-in defs only — never wipe source='custom'.
                if keep_ids:
                    cur.execute(
                        """
                        DELETE FROM public.qc_results
                        WHERE check_id IN (
                            SELECT check_id FROM public.qc_checks
                            WHERE source <> 'custom'
                              AND check_id <> ALL(%s)
                        )
                        """,
                        (list(keep_ids),),
                    )
                    cur.execute(
                        """
                        DELETE FROM public.qc_checks
                        WHERE source <> 'custom'
                          AND check_id <> ALL(%s)
                        """,
                        (list(keep_ids),),
                    )
            conn.commit()
        return len(rows)

    def list_custom_checks(self) -> list[dict[str, Any]]:
        sql = """
            SELECT
                check_id, source, edit_number, nl_description, sql_predicate,
                required_columns, status_mode, skip_reason, updated_at
            FROM public.qc_checks
            WHERE source = 'custom'
            ORDER BY updated_at DESC, check_id
        """
        with connect(self.require_url(), connect_timeout=30) as conn:
            with conn.cursor() as cur:
                cur.execute(QC_CHECKS_TABLE_SQL)
                cur.execute(sql)
                cols = [d.name for d in cur.description]
                out = []
                for tup in cur.fetchall():
                    row = dict(zip(cols, tup))
                    if isinstance(row.get("updated_at"), datetime):
                        row["updated_at"] = row["updated_at"].isoformat()
                    if row.get("required_columns") is not None:
                        row["required_columns"] = list(row["required_columns"])
                    out.append(row)
                return out

    def get_check(self, check_id: str) -> dict[str, Any] | None:
        builtin = CHECKS_BY_ID.get(check_id)
        if builtin is not None:
            return {
                "check_id": builtin.check_id,
                "source": builtin.source,
                "edit_number": builtin.edit_number,
                "nl_description": builtin.nl_description,
                "sql_predicate": builtin.sql_predicate,
                "required_columns": list(builtin.required_columns),
                "status_mode": (
                    "skipped" if builtin.sql_predicate is None else "active"
                ),
                "skip_reason": builtin.skip_reason,
                "rule_name": builtin.rule_name,
            }
        sql = """
            SELECT
                check_id, source, edit_number, nl_description, sql_predicate,
                required_columns, status_mode, skip_reason, updated_at
            FROM public.qc_checks
            WHERE check_id = %s
        """
        with connect(self.require_url(), connect_timeout=30) as conn:
            with conn.cursor() as cur:
                cur.execute(QC_CHECKS_TABLE_SQL)
                cur.execute(sql, (check_id,))
                tup = cur.fetchone()
                if not tup:
                    return None
                cols = [d.name for d in cur.description]
                row = dict(zip(cols, tup))
                if isinstance(row.get("updated_at"), datetime):
                    row["updated_at"] = row["updated_at"].isoformat()
                if row.get("required_columns") is not None:
                    row["required_columns"] = list(row["required_columns"])
                row["rule_name"] = (
                    f"NQM-{row['edit_number']}"
                    if row.get("edit_number") is not None
                    else "Custom"
                )
                return row

    def save_custom_check(
        self,
        *,
        nl_description: str,
        sql_predicate: str,
        required_columns: list[str] | None = None,
        check_id: str | None = None,
        skip_reason: str | None = None,
        status_mode: str = "active",
    ) -> dict[str, Any]:
        """Insert or update a Groq/custom English rule (source=custom)."""
        from app.services.qc_predicate import validate_predicate

        cleaned, cols = validate_predicate(sql_predicate)
        req = list(required_columns or cols)
        cid = (check_id or "").strip() or f"custom_{uuid.uuid4().hex[:10]}"
        if check_id:
            existing = self.get_check(cid)
            if existing and existing.get("source") not in (None, "custom"):
                raise ValueError("cannot overwrite a built-in QC check")
        row = {
            "check_id": cid,
            "source": "custom",
            "edit_number": None,
            "nl_description": (nl_description or "").strip(),
            "sql_predicate": cleaned,
            "required_columns": req,
            "status_mode": status_mode,
            "skip_reason": skip_reason,
        }
        if not row["nl_description"]:
            raise ValueError("nl_description is required")
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
                source = 'custom',
                edit_number = NULL,
                nl_description = EXCLUDED.nl_description,
                sql_predicate = EXCLUDED.sql_predicate,
                required_columns = EXCLUDED.required_columns,
                status_mode = EXCLUDED.status_mode,
                skip_reason = EXCLUDED.skip_reason,
                updated_at = now()
        """
        with connect(self.require_url(), connect_timeout=30) as conn:
            with conn.cursor() as cur:
                cur.execute(QC_CHECKS_TABLE_SQL)
                cur.execute(sql, row)
            conn.commit()
        saved = self.get_check(cid)
        assert saved is not None
        return saved

    def list_disabled_check_ids(self) -> set[str]:
        sql = """
            SELECT check_id FROM public.qc_checks
            WHERE status_mode = 'disabled'
        """
        with connect(self.require_url(), connect_timeout=30) as conn:
            with conn.cursor() as cur:
                cur.execute(QC_CHECKS_TABLE_SQL)
                cur.execute(sql)
                return {r[0] for r in cur.fetchall()}

    def delete_custom_check(self, check_id: str) -> bool:
        """Remove a custom rule, or soft-disable a Standard/built-in rule."""
        with connect(self.require_url(), connect_timeout=30) as conn:
            with conn.cursor() as cur:
                cur.execute(QC_CHECKS_TABLE_SQL)
                cur.execute(
                    "SELECT source FROM public.qc_checks WHERE check_id = %s",
                    (check_id,),
                )
                tup = cur.fetchone()
                if not tup:
                    return False
                cur.execute(
                    "DELETE FROM public.qc_results WHERE check_id = %s",
                    (check_id,),
                )
                if tup[0] == "custom":
                    cur.execute(
                        "DELETE FROM public.qc_checks WHERE check_id = %s",
                        (check_id,),
                    )
                else:
                    # Soft-disable so upsert_check_defs does not revive it.
                    cur.execute(
                        """
                        UPDATE public.qc_checks
                        SET status_mode = 'disabled', updated_at = now()
                        WHERE check_id = %s
                        """,
                        (check_id,),
                    )
            conn.commit()
        return True

    def _checks_for_run(self) -> list[dict[str, Any]]:
        """Built-in ALL_CHECKS plus persisted custom rules (skip disabled)."""
        disabled = self.list_disabled_check_ids()
        out: list[dict[str, Any]] = []
        for check in ALL_CHECKS:
            if check.check_id in disabled:
                continue
            out.append(
                {
                    "check_id": check.check_id,
                    "sql_predicate": check.sql_predicate,
                    "required_columns": list(check.required_columns),
                    "skip_reason": check.skip_reason,
                }
            )
        for custom in self.list_custom_checks():
            if custom["check_id"] in disabled:
                continue
            out.append(
                {
                    "check_id": custom["check_id"],
                    "sql_predicate": custom.get("sql_predicate"),
                    "required_columns": list(custom.get("required_columns") or []),
                    "skip_reason": custom.get("skip_reason"),
                }
            )
        return out

    def run_qc(self, run_id: str | None = None) -> dict[str, Any]:
        run_id = run_id or uuid.uuid4().hex[:12]
        cols = self.tape_columns()
        tape_n = self.count_tape()
        results: list[dict[str, Any]] = []
        checks = self._checks_for_run()

        with connect(self.require_url(), connect_timeout=120) as conn:
            with conn.cursor() as cur:
                cur.execute(QC_RESULTS_TABLE_SQL)
                for check in checks:
                    required = list(check.get("required_columns") or [])
                    missing = [c for c in required if c not in cols]
                    predicate = check.get("sql_predicate")
                    if predicate is None or missing:
                        detail = check.get("skip_reason") or (
                            f"asf_tape lacks required field(s): {', '.join(missing)}"
                            if missing
                            else "no SQL predicate"
                        )
                        row = {
                            "check_id": check["check_id"],
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
                            f"WHERE {predicate}"
                        )
                        cur.execute(sql)
                        fail_n = int(cur.fetchone()[0])
                        pass_n = tape_n - fail_n
                        outcome = "fail" if fail_n > 0 else "pass"
                        row = {
                            "check_id": check["check_id"],
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
        """Latest run results joined with check definitions (foundation then NQM edits)."""
        sql = """
            WITH latest AS (
                SELECT run_id
                FROM public.qc_results
                GROUP BY run_id
                ORDER BY MAX(ran_at) DESC, COUNT(*) DESC, run_id DESC
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
            WHERE c.source <> 'demo'
              AND COALESCE(c.status_mode, 'active') <> 'disabled'
            ORDER BY
                CASE c.source
                    WHEN 'custom' THEN 0
                    WHEN 'foundation' THEN 1
                    WHEN 'absolute_basis' THEN 2
                    ELSE 3
                END,
                c.edit_number NULLS FIRST,
                c.check_id
        """
        with connect(self.require_url(), connect_timeout=30) as conn:
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
                    cdef = CHECKS_BY_ID.get(row["check_id"])
                    row["rule_name"] = (
                        cdef.rule_name
                        if cdef
                        else (
                            f"NQM-{row['edit_number']}"
                            if row.get("edit_number") is not None
                            else "Custom"
                        )
                    )
                    row["scope"] = (
                        "Custom" if row.get("source") == "custom" else "Standard"
                    )
                    out.append(row)
                return out

    def list_check_loans(
        self,
        check_id: str,
        *,
        failing_only: bool = True,
        limit: int = 2000,
    ) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
        """Loans matching a QC check predicate (default: failing rows)."""
        check = self.get_check(check_id)
        if check is None:
            raise KeyError(f"unknown check_id: {check_id}")
        meta = {
            "check_id": check["check_id"],
            "rule_name": check.get("rule_name") or "Custom",
            "nl_description": check.get("nl_description"),
            "failing_only": failing_only,
            "source": check.get("source"),
        }
        predicate = check.get("sql_predicate")
        if not predicate:
            return [], 0, {
                **meta,
                "skipped": True,
                "skip_reason": check.get("skip_reason"),
            }

        cols = (
            "loan_id",
            "current_loan_amount",
            "current_interest_rate",
            "original_fico",
            "original_ltv",
            "original_cltv",
            "state",
            "postal_code",
            "documentation_type",
            "property_type",
            "occupancy",
            "loan_purpose",
            "remaining_term",
            "refinance_incentive",
            "cohort",
            "has_mi",
        )
        present = self.tape_columns()
        select_cols = tuple(c for c in cols if c in present or c == "loan_id")
        # loan_id always required
        if "loan_id" not in select_cols:
            select_cols = ("loan_id",) + select_cols
        col_sql = ", ".join(select_cols)
        where = predicate if failing_only else f"NOT ({predicate})"
        # When failing_only=False and we want "passing", NOT (fail predicate).
        # For "all loans for rule context" callers can pass failing_only=True only.
        count_sql = f"SELECT COUNT(*) FROM public.asf_tape WHERE {where}"
        data_sql = (
            f"SELECT {col_sql} FROM public.asf_tape "
            f"WHERE {where} ORDER BY loan_id LIMIT %s"
        )
        with connect(self.require_url(), connect_timeout=60) as conn:
            with conn.cursor() as cur:
                cur.execute(count_sql)
                total = int(cur.fetchone()[0])
                cur.execute(data_sql, (limit,))
                colnames = [d.name for d in cur.description]
                loans = [dict(zip(colnames, tup)) for tup in cur.fetchall()]
        return relabel_records(loans), total, meta

    def preview_predicate(
        self,
        sql_predicate: str,
        *,
        failing_only: bool = True,
        limit: int = 2000,
    ) -> dict[str, Any]:
        """Run a draft predicate against asf_tape without saving a check."""
        from app.services.qc_predicate import validate_predicate

        cleaned, required = validate_predicate(sql_predicate)
        present = self.tape_columns()
        missing = [c for c in required if c not in present]
        tape_n = self.count_tape()
        if missing:
            return {
                "ok": False,
                "sql_predicate": cleaned,
                "required_columns": required,
                "tape_row_count": tape_n,
                "fail_count": None,
                "pass_count": None,
                "outcome": "skipped",
                "detail": f"asf_tape lacks required field(s): {', '.join(missing)}",
                "loans": [],
                "total": 0,
            }

        cols = (
            "loan_id",
            "current_loan_amount",
            "current_interest_rate",
            "original_fico",
            "original_ltv",
            "original_cltv",
            "state",
            "postal_code",
            "documentation_type",
            "property_type",
            "occupancy",
            "loan_purpose",
            "remaining_term",
            "refinance_incentive",
            "cohort",
            "has_mi",
        )
        select_cols = tuple(c for c in cols if c in present or c == "loan_id")
        if "loan_id" not in select_cols:
            select_cols = ("loan_id",) + select_cols
        col_sql = ", ".join(select_cols)
        fail_where = cleaned
        pass_where = f"NOT ({cleaned})"
        list_where = fail_where if failing_only else pass_where

        with connect(self.require_url(), connect_timeout=60) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT COUNT(*) FROM public.asf_tape WHERE {fail_where}"
                )
                fail_n = int(cur.fetchone()[0])
                pass_n = tape_n - fail_n
                cur.execute(
                    f"SELECT COUNT(*) FROM public.asf_tape WHERE {list_where}"
                )
                total = int(cur.fetchone()[0])
                cur.execute(
                    f"SELECT {col_sql} FROM public.asf_tape "
                    f"WHERE {list_where} ORDER BY loan_id LIMIT %s",
                    (limit,),
                )
                colnames = [d.name for d in cur.description]
                loans = [dict(zip(colnames, tup)) for tup in cur.fetchall()]

        outcome = "fail" if fail_n > 0 else "pass"
        return {
            "ok": True,
            "sql_predicate": cleaned,
            "required_columns": required,
            "tape_row_count": tape_n,
            "fail_count": fail_n,
            "pass_count": pass_n,
            "outcome": outcome,
            "status_label": "Fail" if outcome == "fail" else "Pass",
            "failing_only": failing_only,
            "detail": None,
            "loans": relabel_records(loans),
            "total": total,
            "n": len(loans),
        }

    def list_loans(
        self, limit: int = 2000, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        """Page through asf_tape for the ASF Tape AG Grid."""
        cols = (
            "loan_id",
            "current_loan_amount",
            "current_interest_rate",
            "remaining_term",
            "loan_age_months",
            "original_ltv",
            "original_cltv",
            "original_fico",
            "state",
            "property_type",
            "occupancy",
            "loan_purpose",
            "documentation_type",
            "originator_dti",
            "dscr",
            "days_delinquent",
            "refinance_incentive",
            "cohort",
            "has_mi",
        )
        # Migrate before SELECT — production Neon may predate has_mi.
        has_mi_col = False
        try:
            has_mi_col = self.ensure_has_mi_column()
        except Exception:  # noqa: BLE001
            has_mi_col = "has_mi" in self.tape_columns()
        select_cols = cols if has_mi_col else tuple(c for c in cols if c != "has_mi")
        col_sql = ", ".join(select_cols)
        default_mi = bool(default_has_mi())
        with connect(self.require_url(), connect_timeout=60) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM public.asf_tape")
                total = int(cur.fetchone()[0])
                cur.execute(
                    f"""
                    SELECT {col_sql}
                    FROM public.asf_tape
                    ORDER BY loan_id
                    LIMIT %s OFFSET %s
                    """,
                    (limit, offset),
                )
                rows = []
                for tup in cur.fetchall():
                    row = dict(zip(select_cols, tup))
                    if "has_mi" not in row:
                        row["has_mi"] = default_mi
                    elif row["has_mi"] is None:
                        row["has_mi"] = default_mi
                    rows.append(row)
        return relabel_records(rows), total

    def list_loans_from_excel(
        self, path: Path | str | None = None, limit: int = 2000
    ) -> tuple[list[dict[str, Any]], int]:
        """Local fallback when Neon is unavailable."""
        df = self.load_excel(path)
        total = len(df)
        keep = [
            "loan_id",
            "current_loan_amount",
            "current_interest_rate",
            "remaining_term",
            "loan_age_months",
            "original_ltv",
            "original_cltv",
            "original_fico",
            "state",
            "property_type",
            "occupancy",
            "loan_purpose",
            "documentation_type",
            "originator_dti",
            "dscr",
            "days_delinquent",
            "refinance_incentive",
            "cohort",
            "has_mi",
        ]
        for c in keep:
            if c not in df.columns:
                df[c] = None
        slim = df[keep].head(limit)
        rows = []
        for _, r in slim.iterrows():
            rows.append({c: _to_py(r.get(c)) for c in keep})
        return relabel_records(rows), total

    STRAT_DIMENSIONS = frozenset(
        {
            "documentation_type",
            "state",
            "property_type",
            "occupancy",
            "loan_purpose",
            "cohort",
            "ltv_bucket",
            "cltv_bucket",
            "fico_band",
            "orig_year",
            "balance_band",
            "zip3",
        }
    )

    @staticmethod
    def _strat_cohort_clause(
        cohort: str | None,
    ) -> tuple[str, tuple[Any, ...], str | None]:
        cohort_filter = (cohort or "").strip()
        if cohort_filter.lower() in ("", "all", "*"):
            return "", (), None
        aliases = cohort_match_values(cohort_filter)
        display = canonical_cohort_label(cohort_filter)
        return " WHERE cohort = ANY(%s)", (aliases,), display

    @classmethod
    def _strat_bucket_expr(cls, dimension: str) -> tuple[str, str | None, bool]:
        """Return (bucket_sql, sort_sql|None, ordered)."""
        if dimension not in cls.STRAT_DIMENSIONS:
            raise ValueError(f"unsupported dimension: {dimension}")

        if dimension == "ltv_bucket":
            return (
                """
                CASE
                  WHEN original_ltv IS NULL THEN 'missing'
                  WHEN original_ltv < 0.60 THEN '<60'
                  WHEN original_ltv < 0.70 THEN '60-70'
                  WHEN original_ltv < 0.80 THEN '70-80'
                  WHEN original_ltv < 0.90 THEN '80-90'
                  ELSE '90+'
                END
                """,
                """
                CASE
                  WHEN original_ltv IS NULL THEN 99
                  WHEN original_ltv < 0.60 THEN 1
                  WHEN original_ltv < 0.70 THEN 2
                  WHEN original_ltv < 0.80 THEN 3
                  WHEN original_ltv < 0.90 THEN 4
                  ELSE 5
                END
                """,
                True,
            )
        if dimension == "cltv_bucket":
            return (
                """
                CASE
                  WHEN original_cltv IS NULL THEN 'missing'
                  WHEN original_cltv < 0.60 THEN '<60'
                  WHEN original_cltv < 0.70 THEN '60-70'
                  WHEN original_cltv < 0.80 THEN '70-80'
                  WHEN original_cltv < 0.90 THEN '80-90'
                  ELSE '90+'
                END
                """,
                """
                CASE
                  WHEN original_cltv IS NULL THEN 99
                  WHEN original_cltv < 0.60 THEN 1
                  WHEN original_cltv < 0.70 THEN 2
                  WHEN original_cltv < 0.80 THEN 3
                  WHEN original_cltv < 0.90 THEN 4
                  ELSE 5
                END
                """,
                True,
            )
        if dimension == "fico_band":
            return (
                """
                CASE
                  WHEN original_fico IS NULL THEN 'missing'
                  WHEN original_fico < 660 THEN '<660'
                  WHEN original_fico < 700 THEN '660-699'
                  WHEN original_fico < 740 THEN '700-739'
                  WHEN original_fico < 780 THEN '740-779'
                  ELSE '780+'
                END
                """,
                """
                CASE
                  WHEN original_fico IS NULL THEN 99
                  WHEN original_fico < 660 THEN 1
                  WHEN original_fico < 700 THEN 2
                  WHEN original_fico < 740 THEN 3
                  WHEN original_fico < 780 THEN 4
                  ELSE 5
                END
                """,
                True,
            )
        if dimension == "balance_band":
            return (
                """
                CASE
                  WHEN current_loan_amount IS NULL THEN 'missing'
                  WHEN current_loan_amount < 100000 THEN '<100k'
                  WHEN current_loan_amount < 200000 THEN '100-200k'
                  WHEN current_loan_amount < 300000 THEN '200-300k'
                  WHEN current_loan_amount < 400000 THEN '300-400k'
                  WHEN current_loan_amount < 500000 THEN '400-500k'
                  WHEN current_loan_amount < 750000 THEN '500-750k'
                  ELSE '750k+'
                END
                """,
                """
                CASE
                  WHEN current_loan_amount IS NULL THEN 99
                  WHEN current_loan_amount < 100000 THEN 1
                  WHEN current_loan_amount < 200000 THEN 2
                  WHEN current_loan_amount < 300000 THEN 3
                  WHEN current_loan_amount < 400000 THEN 4
                  WHEN current_loan_amount < 500000 THEN 5
                  WHEN current_loan_amount < 750000 THEN 6
                  ELSE 7
                END
                """,
                True,
            )
        if dimension == "orig_year":
            return (
                """
                CASE
                  WHEN origination_date IS NULL THEN 'missing'
                  ELSE EXTRACT(YEAR FROM origination_date)::int::text
                END
                """,
                """
                CASE
                  WHEN origination_date IS NULL THEN 9999
                  ELSE EXTRACT(YEAR FROM origination_date)::int
                END
                """,
                True,
            )
        if dimension == "zip3":
            # First 3 digits of postal_code (preserve leading zeros as text).
            return (
                """
                CASE
                  WHEN postal_code IS NULL
                    OR length(
                      regexp_replace(trim(postal_code), '[^0-9]', '', 'g')
                    ) < 3
                  THEN 'missing'
                  ELSE left(
                    regexp_replace(trim(postal_code), '[^0-9]', '', 'g'),
                    3
                  )
                END
                """,
                None,
                False,
            )
        # Direct column dimensions (state, documentation_type, …).
        return f"COALESCE({dimension}::text, 'missing')", None, False

    def stratification(
        self,
        dimension: str = "documentation_type",
        cohort: str | None = None,
    ) -> dict[str, Any]:
        """Bucket asf_tape by a categorical / derived dimension (not K-prototype)."""
        bucket_expr, sort_expr, ordered = self._strat_bucket_expr(dimension)
        where_sql, where_params, cohort_filter = self._strat_cohort_clause(cohort)

        wac_expr = """
            CASE
              WHEN COALESCE(SUM(current_loan_amount), 0) > 0
              THEN SUM(current_interest_rate * current_loan_amount)
                   / SUM(current_loan_amount)
              ELSE NULL
            END::float
        """

        if ordered:
            sql = f"""
                SELECT
                    {bucket_expr} AS bucket,
                    COUNT(*)::int AS loan_count,
                    COALESCE(SUM(current_loan_amount), 0)::float AS upb,
                    AVG(original_ltv)::float AS avg_ltv,
                    AVG(original_cltv)::float AS avg_cltv,
                    AVG(original_fico)::float AS avg_fico,
                    AVG(current_interest_rate)::float AS avg_rate,
                    {wac_expr} AS wac,
                    AVG(refinance_incentive)::float AS avg_refi_incentive,
                    MIN({sort_expr}) AS sort_key
                FROM public.asf_tape
                {where_sql}
                GROUP BY 1
                ORDER BY sort_key ASC NULLS LAST, bucket ASC
            """
        else:
            sql = f"""
                SELECT
                    {bucket_expr} AS bucket,
                    COUNT(*)::int AS loan_count,
                    COALESCE(SUM(current_loan_amount), 0)::float AS upb,
                    AVG(original_ltv)::float AS avg_ltv,
                    AVG(original_cltv)::float AS avg_cltv,
                    AVG(original_fico)::float AS avg_fico,
                    AVG(current_interest_rate)::float AS avg_rate,
                    {wac_expr} AS wac,
                    AVG(refinance_incentive)::float AS avg_refi_incentive
                FROM public.asf_tape
                {where_sql}
                GROUP BY 1
                ORDER BY upb DESC NULLS LAST, loan_count DESC
            """
        kpi_sql = f"""
            SELECT
                COUNT(*)::int AS tape_row_count,
                COALESCE(SUM(current_loan_amount), 0)::float AS tape_upb,
                CASE
                  WHEN COALESCE(SUM(current_loan_amount), 0) > 0
                  THEN SUM(current_interest_rate * current_loan_amount)
                       / SUM(current_loan_amount)
                  ELSE NULL
                END::float AS wac,
                CASE
                  WHEN COALESCE(SUM(current_loan_amount), 0) > 0
                  THEN SUM(remaining_term * current_loan_amount)
                       / SUM(current_loan_amount)
                  ELSE NULL
                END::float AS wam,
                CASE
                  WHEN COALESCE(
                    SUM(
                      CASE
                        WHEN loan_age_months IS NOT NULL AND loan_age_months >= 12
                        THEN current_loan_amount
                        ELSE 0
                      END
                    ),
                    0
                  ) > 0
                  THEN SUM(
                    CASE
                      WHEN loan_age_months IS NOT NULL AND loan_age_months >= 12
                      THEN current_interest_rate * current_loan_amount
                      ELSE 0
                    END
                  ) / SUM(
                    CASE
                      WHEN loan_age_months IS NOT NULL AND loan_age_months >= 12
                      THEN current_loan_amount
                      ELSE 0
                    END
                  )
                  ELSE NULL
                END::float AS seasoned_wac,
                BOOL_OR(
                  postal_code IS NOT NULL
                  AND length(
                    regexp_replace(trim(postal_code), '[^0-9]', '', 'g')
                  ) >= 3
                ) AS has_postal_code
            FROM public.asf_tape
            {where_sql}
        """
        with connect(self.require_url(), connect_timeout=60) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, where_params)
                cols = [d.name for d in cur.description]
                rows = [dict(zip(cols, tup)) for tup in cur.fetchall()]
                for row in rows:
                    row.pop("sort_key", None)
                cur.execute(kpi_sql, where_params)
                kpi_cols = [d.name for d in cur.description]
                kpi = dict(zip(kpi_cols, cur.fetchone()))
        return {
            "dimension": dimension,
            "cohort": cohort_filter or "all",
            "n_buckets": len(rows),
            "tape_row_count": int(kpi["tape_row_count"] or 0),
            "tape_upb": float(kpi["tape_upb"] or 0),
            "wac": kpi.get("wac"),
            "wam": kpi.get("wam"),
            "seasoned_wac": kpi.get("seasoned_wac"),
            "has_postal_code": bool(kpi.get("has_postal_code")),
            "rows": rows,
        }

    def list_strat_loans(
        self,
        dimension: str,
        bucket: str,
        *,
        cohort: str | None = None,
        limit: int = 2000,
    ) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
        """Loans matching a stratification bucket (Investor Tape–style drill)."""
        bucket_expr, _, _ = self._strat_bucket_expr(dimension)
        where_sql, where_params, cohort_filter = self._strat_cohort_clause(cohort)
        bucket_value = (bucket or "").strip()
        if not bucket_value:
            raise ValueError("bucket is required")

        cols = (
            "loan_id",
            "current_loan_amount",
            "current_interest_rate",
            "original_fico",
            "original_ltv",
            "original_cltv",
            "state",
            "postal_code",
            "documentation_type",
            "property_type",
            "occupancy",
            "loan_purpose",
            "remaining_term",
            "refinance_incentive",
            "cohort",
            "has_mi",
            "origination_date",
        )
        present = self.tape_columns()
        select_cols = tuple(c for c in cols if c in present or c == "loan_id")
        if "loan_id" not in select_cols:
            select_cols = ("loan_id",) + select_cols
        col_sql = ", ".join(select_cols)

        if where_sql:
            filter_sql = f"{where_sql} AND ({bucket_expr}) = %s"
            params: tuple[Any, ...] = where_params + (bucket_value,)
        else:
            filter_sql = f" WHERE ({bucket_expr}) = %s"
            params = (bucket_value,)

        count_sql = f"SELECT COUNT(*) FROM public.asf_tape{filter_sql}"
        data_sql = (
            f"SELECT {col_sql} FROM public.asf_tape"
            f"{filter_sql} ORDER BY loan_id LIMIT %s"
        )
        meta = {
            "dimension": dimension,
            "bucket": bucket_value,
            "cohort": cohort_filter or "all",
        }
        with connect(self.require_url(), connect_timeout=60) as conn:
            with conn.cursor() as cur:
                cur.execute(count_sql, params)
                total = int(cur.fetchone()[0])
                cur.execute(data_sql, params + (limit,))
                colnames = [d.name for d in cur.description]
                loans = [dict(zip(colnames, tup)) for tup in cur.fetchall()]
                for loan in loans:
                    od = loan.get("origination_date")
                    if isinstance(od, (date, datetime)):
                        loan["origination_date"] = od.isoformat()
        return relabel_records(loans), total, meta

    def cohort_stats(self) -> list[dict[str, Any]]:
        """Per K-prototype cohort pool stats for the Cohort tab grid.

        Groups by cluster-tape HLTV/LLTV labels (not Excel short names on asf_tape).
        """
        try:
            cluster_map = TapeRepository().load_cluster_map()
        except FileNotFoundError:
            cluster_map = {}

        with connect(self.require_url(), connect_timeout=60) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        loan_id,
                        COALESCE(cohort, 'unlabeled') AS cohort,
                        state,
                        original_fico,
                        original_ltv,
                        original_cltv,
                        current_loan_amount,
                        current_interest_rate,
                        remaining_term,
                        refinance_incentive,
                        originator_dti,
                        has_mi
                    FROM public.asf_tape
                    """
                )
                loan_cols = [d.name for d in cur.description]
                loan_rows = [dict(zip(loan_cols, tup)) for tup in cur.fetchall()]

        buckets: dict[str, dict[str, Any]] = {}
        for ln in loan_rows:
            lid = str(ln.get("loan_id") or "")
            key = cluster_map.get(lid) or canonical_cohort_label(ln.get("cohort"))
            if not key:
                key = "unlabeled"
            upb = float(ln.get("current_loan_amount") or 0.0)
            rate = float(ln.get("current_interest_rate") or 0.0)
            term = float(ln.get("remaining_term") or 0.0)
            slot = buckets.setdefault(
                key,
                {
                    "cohort": key,
                    "loan_count": 0,
                    "upb": 0.0,
                    "wac_num": 0.0,
                    "wam_num": 0.0,
                    # UPB-weighted sums / weight for averages (skip weight when field missing)
                    "ltv_sum": 0.0,
                    "cltv_sum": 0.0,
                    "fico_sum": 0.0,
                    "rate_sum": 0.0,
                    "ri_sum": 0.0,
                    "term_sum": 0.0,
                    "dti_sum": 0.0,
                    "ltv_w": 0.0,
                    "cltv_w": 0.0,
                    "fico_w": 0.0,
                    "rate_w": 0.0,
                    "ri_w": 0.0,
                    "term_w": 0.0,
                    "dti_w": 0.0,
                    "rec_upb": 0.0,
                    "rec_num": 0.0,
                    "lag_num": 0.0,
                },
            )
            slot["loan_count"] += 1
            slot["upb"] += upb
            slot["wac_num"] += rate * upb
            slot["wam_num"] += term * upb
            for field, sum_key, w_key in (
                ("original_ltv", "ltv_sum", "ltv_w"),
                ("original_cltv", "cltv_sum", "cltv_w"),
                ("original_fico", "fico_sum", "fico_w"),
                ("current_interest_rate", "rate_sum", "rate_w"),
                ("refinance_incentive", "ri_sum", "ri_w"),
                ("remaining_term", "term_sum", "term_w"),
                ("originator_dti", "dti_sum", "dti_w"),
            ):
                val = ln.get(field)
                if val is None:
                    continue
                try:
                    num = float(val)
                except (TypeError, ValueError):
                    continue
                slot[sum_key] += num * upb
                slot[w_key] += upb
            try:
                cohort_rate = recovery_for_cohort(key)[0]
            except KeyError:
                cohort_rate = 0.60
            rec, _src = resolve_loan_recovery_rate(
                has_mi=ln.get("has_mi"),
                original_fico=ln.get("original_fico"),
                original_ltv=ln.get("original_ltv"),
                cohort_recovery_rate=cohort_rate,
            )
            lag = recovery_lag_months_for_state(ln.get("state"))
            slot["rec_upb"] += upb
            slot["rec_num"] += rec * upb
            slot["lag_num"] += lag * upb

        out: list[dict[str, Any]] = []
        for key, slot in buckets.items():
            upb = float(slot["upb"])
            n = int(slot["loan_count"])
            row = {
                "cohort": key,
                "loan_count": n,
                "upb": upb,
                "wac": (slot["wac_num"] / upb) if upb else None,
                "wam": (slot["wam_num"] / upb) if upb else None,
                "avg_ltv": (slot["ltv_sum"] / slot["ltv_w"]) if slot["ltv_w"] else None,
                "avg_cltv": (slot["cltv_sum"] / slot["cltv_w"]) if slot["cltv_w"] else None,
                "avg_fico": (slot["fico_sum"] / slot["fico_w"]) if slot["fico_w"] else None,
                "avg_rate": (slot["rate_sum"] / slot["rate_w"]) if slot["rate_w"] else None,
                "avg_refi_incentive": (slot["ri_sum"] / slot["ri_w"]) if slot["ri_w"] else None,
                "avg_remaining_term": (slot["term_sum"] / slot["term_w"]) if slot["term_w"] else None,
                "avg_dti": (slot["dti_sum"] / slot["dti_w"]) if slot["dti_w"] else None,
            }
            if slot["rec_upb"] > 0:
                row["recovery"] = slot["rec_num"] / slot["rec_upb"]
                row["lag"] = slot["lag_num"] / slot["rec_upb"]
            out.append(row)
        out.sort(key=lambda r: float(r.get("upb") or 0), reverse=True)
        return relabel_records(out)
