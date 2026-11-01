"""Apply loan CF DDL and bulk-load SQLite → Neon (UNPOOLED preferred).

No loan math / scenario logic changes — storage only.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.repositories.cashflow_repository import CREATE_SQL  # noqa: E402
from app.repositories.scenario_repository import CREATE_SQL as SCENARIO_SQL  # noqa: E402

SQLITE_PATH = REPO_ROOT / "data" / "loan_cf_month1.sqlite"
COLS = (
    "scenario_id",
    "loan_id",
    "cohort",
    "psa_multiple",
    "sda_multiple",
    "pca_level",
    "sta_level",
    "month",
    "beginning_balance",
    "interest",
    "scheduled_principal",
    "default_amt",
    "prepay",
    "recovery",
    "ending_balance",
    "loan_age",
    "cpr",
    "smm",
    "cdr",
    "mdr",
)


def _load_dotenv() -> None:
    for name in (".env.local", ".env"):
        path = REPO_ROOT / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = val.strip().strip('"').strip("'")


def _resolve_urls() -> tuple[str | None, str | None]:
    pooled = os.environ.get("DATABASE_URL") or os.environ.get("NEON_DATABASE_URL")
    unpooled = os.environ.get("DATABASE_URL_UNPOOLED") or os.environ.get(
        "POSTGRES_URL_NON_POOLING"
    )
    return pooled, unpooled


def main() -> int:
    _load_dotenv()
    pooled, unpooled = _resolve_urls()
    url = unpooled or pooled
    if not url:
        print("ERROR: DATABASE_URL / DATABASE_URL_UNPOOLED not set", file=sys.stderr)
        return 1
    if not SQLITE_PATH.exists():
        print(f"ERROR: missing {SQLITE_PATH}", file=sys.stderr)
        return 1

    import psycopg
    from psycopg import sql

    with sqlite3.connect(SQLITE_PATH) as sconn:
        sqlite_count = sconn.execute(
            "SELECT COUNT(*) FROM loan_cashflows_month1"
        ).fetchone()[0]
        rows = sconn.execute(
            f"SELECT {', '.join(COLS)} FROM loan_cashflows_month1"
        ).fetchall()

    which = "UNPOOLED" if unpooled and url == unpooled else "POOLED"
    print(f"Connecting via {which} URL …")
    print(f"SQLite source rows: {sqlite_count}")

    with psycopg.connect(url, connect_timeout=30) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_SQL)
            cur.execute(SCENARIO_SQL)
            cur.execute("DELETE FROM loan_cashflows_month1")
            copy = sql.SQL(
                "COPY loan_cashflows_month1 ({}) FROM STDIN"
            ).format(sql.SQL(", ").join(map(sql.Identifier, COLS)))
            with cur.copy(copy) as copy_writer:
                for row in rows:
                    copy_writer.write_row(row)
            cur.execute("SELECT COUNT(*) FROM loan_cashflows_month1")
            neon_count = cur.fetchone()[0]
            cur.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_name IN (
                    'loan_cashflows_month1', 'securitization_scenarios'
                )
                ORDER BY table_schema, table_name
                """
            )
            tables = cur.fetchall()
        conn.commit()

    print(f"Neon COUNT(*): {neon_count}")
    print(f"match: {neon_count == sqlite_count}")
    print("tables:", tables)
    print("schema: public.loan_cashflows_month1 (+ public.securitization_scenarios DDL)")
    return 0 if neon_count == sqlite_count else 2


if __name__ == "__main__":
    raise SystemExit(main())
