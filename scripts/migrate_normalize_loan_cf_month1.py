"""Safely normalize public.loan_cashflows_month1 + create enriched view.

Migrates existing rows; adds FK to securitization_scenarios.
No loan math changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.repositories.cashflow_schema import (  # noqa: E402
    LOAN_CF_MONTH1_ENRICHED_VIEW_SQL,
    LOAN_CF_MONTH1_TABLE_SQL,
    LOAN_MONTH_CF_ENRICHED_VIEW_SQL,
    LOAN_MONTH_CF_TABLE_SQL,
    MONTH1_DROPPED_COLS,
    MONTH1_FACT_COLS,
)
from app.repositories.env_load import load_dotenv, resolve_pg_url  # noqa: E402
from app.repositories.scenario_repository import CREATE_SQL as SCENARIO_SQL  # noqa: E402


def _existing_columns(cur, table: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table,),
    )
    return {r[0] for r in cur.fetchall()}


def migrate(cur) -> dict:
    cur.execute(SCENARIO_SQL)
    cur.execute("SELECT COUNT(*) FROM public.securitization_scenarios")
    n_scen = cur.fetchone()[0]
    if n_scen < 1:
        raise RuntimeError(
            "securitization_scenarios is empty — seed scenarios before migrate"
        )

    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='public' AND table_name='loan_cashflows_month1'
        )
        """
    )
    has_table = cur.fetchone()[0]
    before = 0
    if has_table:
        cur.execute("SELECT COUNT(*) FROM public.loan_cashflows_month1")
        before = int(cur.fetchone()[0])

    cur.execute("DROP VIEW IF EXISTS public.loan_cashflows_month1_enriched")
    cur.execute("DROP VIEW IF EXISTS public.loan_month_cf_enriched")

    cols = _existing_columns(cur, "loan_cashflows_month1") if has_table else set()
    needs_rebuild = (not has_table) or any(c in cols for c in MONTH1_DROPPED_COLS)

    if needs_rebuild:
        cur.execute("DROP TABLE IF EXISTS public.loan_cashflows_month1_norm")
        cur.execute(
            LOAN_CF_MONTH1_TABLE_SQL.replace(
                "CREATE TABLE IF NOT EXISTS loan_cashflows_month1",
                "CREATE TABLE loan_cashflows_month1_norm",
            )
        )
        if has_table and before > 0:
            cur.execute(
                """
                SELECT COUNT(*) FROM public.loan_cashflows_month1 l
                LEFT JOIN public.securitization_scenarios s
                  ON l.scenario_id = s.scenario_id
                WHERE s.scenario_id IS NULL
                """
            )
            orphans = int(cur.fetchone()[0])
            if orphans:
                raise RuntimeError(
                    f"cannot migrate: {orphans} orphan scenario_id rows in month1"
                )
            select_list = ", ".join(f"l.{c}" for c in MONTH1_FACT_COLS)
            cur.execute(
                f"""
                INSERT INTO public.loan_cashflows_month1_norm (
                    {", ".join(MONTH1_FACT_COLS)}
                )
                SELECT {select_list}
                FROM public.loan_cashflows_month1 l
                """
            )
            cur.execute("SELECT COUNT(*) FROM public.loan_cashflows_month1_norm")
            copied = int(cur.fetchone()[0])
            if copied != before:
                raise RuntimeError(
                    f"row count mismatch during migrate: before={before} copied={copied}"
                )
            cur.execute("DROP TABLE public.loan_cashflows_month1")
            cur.execute(
                "ALTER TABLE public.loan_cashflows_month1_norm "
                "RENAME TO loan_cashflows_month1"
            )
        else:
            cur.execute("DROP TABLE IF EXISTS public.loan_cashflows_month1")
            cur.execute(
                "ALTER TABLE public.loan_cashflows_month1_norm "
                "RENAME TO loan_cashflows_month1"
            )
    else:
        cur.execute(
            """
            SELECT 1 FROM information_schema.table_constraints
            WHERE table_schema='public'
              AND table_name='loan_cashflows_month1'
              AND constraint_type='FOREIGN KEY'
              AND constraint_name='loan_cashflows_month1_scenario_id_fkey'
            """
        )
        if cur.fetchone() is None:
            cur.execute(
                """
                ALTER TABLE public.loan_cashflows_month1
                ADD CONSTRAINT loan_cashflows_month1_scenario_id_fkey
                FOREIGN KEY (scenario_id)
                REFERENCES public.securitization_scenarios (scenario_id)
                """
            )

    cur.execute(LOAN_CF_MONTH1_ENRICHED_VIEW_SQL)

    # Keep existing loan_month_cf data if already normalized; else recreate empty.
    month_cf_cols = _existing_columns(cur, "loan_month_cf")
    if not month_cf_cols:
        cur.execute(
            LOAN_MONTH_CF_TABLE_SQL.replace(
                "CREATE TABLE IF NOT EXISTS loan_month_cf",
                "CREATE TABLE loan_month_cf",
            )
        )
    elif any(c in month_cf_cols for c in MONTH1_DROPPED_COLS) or "loss" in month_cf_cols:
        cur.execute("DROP TABLE IF EXISTS public.loan_month_cf CASCADE")
        cur.execute(
            LOAN_MONTH_CF_TABLE_SQL.replace(
                "CREATE TABLE IF NOT EXISTS loan_month_cf",
                "CREATE TABLE loan_month_cf",
            )
        )
    cur.execute(LOAN_MONTH_CF_ENRICHED_VIEW_SQL)

    cur.execute("SELECT COUNT(*) FROM public.loan_cashflows_month1")
    after = int(cur.fetchone()[0])
    cur.execute("SELECT COUNT(*) FROM public.loan_cashflows_month1_enriched")
    enriched = int(cur.fetchone()[0])
    cur.execute(
        """
        SELECT COUNT(*) FROM public.loan_cashflows_month1 l
        LEFT JOIN public.securitization_scenarios s ON l.scenario_id = s.scenario_id
        WHERE s.scenario_id IS NULL
        """
    )
    orphans_after = int(cur.fetchone()[0])
    final_cols = sorted(_existing_columns(cur, "loan_cashflows_month1"))

    return {
        "before": before,
        "after": after,
        "enriched": enriched,
        "orphans_after": orphans_after,
        "columns": final_cols,
        "rebuilt": needs_rebuild,
    }


def main() -> int:
    load_dotenv()
    url = resolve_pg_url()
    if not url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 1

    import psycopg

    with psycopg.connect(url, connect_timeout=60) as conn:
        with conn.cursor() as cur:
            result = migrate(cur)
        conn.commit()

    print("migration_ok", result)
    print("--- DDL: loan_cashflows_month1 ---")
    print(LOAN_CF_MONTH1_TABLE_SQL.strip())
    print("--- DDL: loan_cashflows_month1_enriched ---")
    print(LOAN_CF_MONTH1_ENRICHED_VIEW_SQL.strip())
    print("--- DDL: loan_month_cf ---")
    print(LOAN_MONTH_CF_TABLE_SQL.strip())
    print("--- DDL: loan_month_cf_enriched ---")
    print(LOAN_MONTH_CF_ENRICHED_VIEW_SQL.strip())

    ok = (
        result["after"] == result["before"]
        and result["enriched"] == result["after"]
        and result["orphans_after"] == 0
        and not any(c in result["columns"] for c in MONTH1_DROPPED_COLS)
    )
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
