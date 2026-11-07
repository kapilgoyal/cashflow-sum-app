"""DATABASE_URL resolution + a sqlite3 adapter that speaks psycopg-shaped SQL.

Postgres/Neon URLs still go through psycopg unchanged. When DATABASE_URL is
unset, the prototype defaults to a file SQLite database.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from sqlalchemy.engine.url import make_url

from app.repositories.env_load import REPO_ROOT, load_dotenv

CONTAINER_SQLITE_PATH = Path("/data/cashflow.db")
LOCAL_SQLITE_PATH = REPO_ROOT / "data" / "cashflow.db"

_ARRAY_COLUMNS = frozenset({"required_columns"})
_BOOL_COLUMNS = frozenset({"has_mi", "state_varying_recovery_todo"})

_INFO_SCHEMA_RE = re.compile(
    r"FROM\s+information_schema\.columns\b.*?table_name\s*=\s*'(\w+)'",
    re.I | re.S,
)
_COPY_RE = re.compile(
    r"COPY\s+(?:public\.)?(\w+)\s*\((.*?)\)\s*FROM\s+STDIN",
    re.I | re.S,
)
_ALTER_COLUMN_RE = re.compile(r"ALTER\s+TABLE\s+\S+\s+ALTER\s+COLUMN\b", re.I)
_CREATE_OR_REPLACE_VIEW_RE = re.compile(
    r"CREATE\s+OR\s+REPLACE\s+VIEW\s+(?:public\.)?(\w+)\s+AS",
    re.I,
)
_EXTRACT_YEAR_RE = re.compile(
    r"EXTRACT\s*\(\s*YEAR\s+FROM\s+([^)]+)\)",
    re.I,
)
_NAMED_PLACEHOLDER_RE = re.compile(r"%\((\w+)\)s")


def configured_database_url() -> str | None:
    """Explicit env only (no sqlite default). Empty string counts as unset."""
    load_dotenv()
    for key in (
        "DATABASE_URL_UNPOOLED",
        "POSTGRES_URL_NON_POOLING",
        "DATABASE_URL",
        "NEON_DATABASE_URL",
    ):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return None


def default_sqlite_path() -> Path:
    """Prefer /data in a container; otherwise repo data/cashflow.db."""
    if _writable_dir(CONTAINER_SQLITE_PATH.parent):
        return CONTAINER_SQLITE_PATH
    LOCAL_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return LOCAL_SQLITE_PATH


def path_to_sqlite_url(path: Path | str) -> str:
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = (REPO_ROOT / resolved).resolve()
    else:
        resolved = resolved.resolve()
    # sqlite:/// + /abs/path → four slashes (SQLAlchemy absolute file).
    return "sqlite:///" + resolved.as_posix()


def default_sqlite_url() -> str:
    return path_to_sqlite_url(default_sqlite_path())


def resolve_database_url() -> str:
    """Env DATABASE_URL, or the prototype sqlite file."""
    return configured_database_url() or default_sqlite_url()


def is_postgres_url(url: str | None) -> bool:
    if not url:
        return False
    lowered = url.strip().lower()
    if lowered.startswith("postgres"):
        return True
    try:
        return make_url(url).get_backend_name() in {"postgresql", "postgres"}
    except Exception:  # noqa: BLE001
        return False


def is_sqlite_url(url: str | None) -> bool:
    if not url:
        return False
    if is_postgres_url(url):
        return False
    lowered = url.strip().lower()
    return (
        lowered.startswith("sqlite")
        or lowered.startswith("file:")
        or lowered.endswith(".db")
        or lowered.endswith(".sqlite")
        or lowered.endswith(".sqlite3")
    )


def dialect_name(url: str | None = None) -> str:
    resolved = url or resolve_database_url()
    if is_postgres_url(resolved):
        return "postgresql"
    return "sqlite"


def provider_hint(url: str | None = None) -> str:
    resolved = url or resolve_database_url()
    if is_postgres_url(resolved):
        if "neon.tech" in resolved:
            return "neon"
        return "postgres"
    return "sqlite"


def source_label(table: str, url: str | None = None) -> str:
    return f"{provider_hint(url)}.{table}"


def sqlite_path_from_url(url: str) -> Path:
    stripped = url.strip()
    if stripped.startswith("file:"):
        stripped = stripped[5:]
    if stripped.startswith("sqlite://"):
        database = make_url(stripped).database
        if not database:
            raise ValueError(f"sqlite URL missing path: {url}")
        path = Path(database)
    else:
        path = Path(stripped)
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return path


def ensure_sqlite_parent(url: str) -> Path | None:
    if not is_sqlite_url(url):
        return None
    path = sqlite_path_from_url(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def connect(url: str | None = None, connect_timeout: int = 30, **kwargs: Any):
    """psycopg connection for postgres; sqlite3 wrapper otherwise."""
    resolved = url or resolve_database_url()
    if is_postgres_url(resolved):
        import psycopg

        return psycopg.connect(
            resolved, connect_timeout=connect_timeout, **kwargs
        )
    path = ensure_sqlite_parent(resolved)
    assert path is not None
    timeout = float(kwargs.pop("timeout", connect_timeout) or 30)
    return SqliteConnection(path, timeout=timeout)


def adapt_sqlite_sql(
    sql: str, params: Any = None
) -> tuple[str, Any, list[str]]:
    """Translate a Postgres-ish statement to SQLite. Returns (sql, params, extras).

    ``extras`` are statements to run *before* the main SQL (DROP VIEW, …).
    """
    extras: list[str] = []
    text = sql.strip()
    if not text:
        return text, params, extras

    info = _INFO_SCHEMA_RE.search(text)
    if info:
        table = info.group(1)
        return (
            f"SELECT name AS column_name FROM pragma_table_info('{table}')",
            None,
            extras,
        )

    if _ALTER_COLUMN_RE.search(text):
        return "SELECT 1", None, extras

    view = _CREATE_OR_REPLACE_VIEW_RE.search(text)
    if view:
        name = view.group(1)
        extras.append(f"DROP VIEW IF EXISTS {name}")
        text = _CREATE_OR_REPLACE_VIEW_RE.sub(f"CREATE VIEW {name} AS", text, count=1)

    text = re.sub(r"\bpublic\.", "", text)
    text = re.sub(r"\bdouble precision\b", "REAL", text, flags=re.I)
    text = re.sub(r"\btimestamptz\b", "TEXT", text, flags=re.I)
    text = re.sub(r"\btext\[\]\b", "TEXT", text, flags=re.I)
    text = re.sub(r"\bboolean\b", "INTEGER", text, flags=re.I)
    text = re.sub(r"\bDEFAULT\s+TRUE\b", "DEFAULT 1", text, flags=re.I)
    text = re.sub(r"\bDEFAULT\s+FALSE\b", "DEFAULT 0", text, flags=re.I)
    text = re.sub(r"DEFAULT\s+'\{\}'", "DEFAULT '[]'", text)
    text = re.sub(
        r"\bDEFAULT\s+now\(\)", "DEFAULT (datetime('now'))", text, flags=re.I
    )
    text = re.sub(r"\bnow\(\)", "datetime('now')", text, flags=re.I)
    text = re.sub(r"::int::text", "", text, flags=re.I)
    text = re.sub(r"::integer::text", "", text, flags=re.I)
    text = re.sub(r"::int\b", "", text, flags=re.I)
    text = re.sub(r"::integer\b", "", text, flags=re.I)
    text = re.sub(r"::float\b", "", text, flags=re.I)
    text = re.sub(r"::double precision", "", text, flags=re.I)
    text = re.sub(r"::text\b", "", text, flags=re.I)
    text = _EXTRACT_YEAR_RE.sub(r"CAST(strftime('%Y', \1) AS INTEGER)", text)
    text = re.sub(
        r"\bTRUNCATE(?:\s+TABLE)?\s+(\w+)",
        r"DELETE FROM \1",
        text,
        flags=re.I,
    )
    # SQLite has no ADD COLUMN IF NOT EXISTS (Postgres does).
    text = re.sub(
        r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+",
        "ADD COLUMN ",
        text,
        flags=re.I,
    )

    text, params = _convert_placeholders(text, params)
    return text, params, extras


class _Col:
    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name


class _CopyWriter:
    def __init__(self, cursor: "SqliteCursor", table: str, columns: list[str]) -> None:
        self._cursor = cursor
        self._table = table
        self._columns = columns
        self._rows: list[Sequence[Any]] = []

    def write_row(self, row: Sequence[Any]) -> None:
        self._rows.append(tuple(_adapt_bind_value(v) for v in row))

    def __enter__(self) -> "_CopyWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        if exc_type is not None:
            return
        if not self._rows:
            return
        placeholders = ", ".join("?" for _ in self._columns)
        cols = ", ".join(self._columns)
        self._cursor._cur.executemany(  # noqa: SLF001
            f"INSERT INTO {self._table} ({cols}) VALUES ({placeholders})",
            self._rows,
        )


class SqliteCursor:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._cur = conn.cursor()
        self._colnames: list[str] = []

    def execute(self, sql: str, params: Any = None):
        for stmt in _split_statements(sql):
            adapted, bound, extras = adapt_sqlite_sql(stmt, params)
            for extra in extras:
                self._cur.execute(extra)
            if not adapted:
                continue
            try:
                if bound is None:
                    self._cur.execute(adapted)
                else:
                    self._cur.execute(adapted, bound)
            except sqlite3.OperationalError as exc:
                # Postgres ADD COLUMN IF NOT EXISTS — SQLite has no such clause.
                msg = str(exc).lower()
                if "duplicate column" in msg:
                    continue
                raise
            params = None  # extra statements in the same call are DDL
        desc = self._cur.description
        self._colnames = [d[0] for d in desc] if desc else []
        return self

    def executemany(self, sql: str, seq_of_params: Iterable[Any]):
        adapted, _, extras = adapt_sqlite_sql(sql, None)
        for extra in extras:
            self._cur.execute(extra)
        rows = [_adapt_param_row(p) for p in seq_of_params]
        self._cur.executemany(adapted, rows)
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        return self._adapt_fetched(row) if row is not None else None

    def fetchall(self):
        return [self._adapt_fetched(r) for r in self._cur.fetchall()]

    def fetchmany(self, size: int | None = None):
        rows = (
            self._cur.fetchmany(size)
            if size is not None
            else self._cur.fetchmany()
        )
        return [self._adapt_fetched(r) for r in rows]

    def copy(self, sql: str):
        text = str(sql)
        match = _COPY_RE.search(text)
        if not match:
            raise ValueError(f"sqlite adapter cannot parse COPY: {text[:200]}")
        table = match.group(1)
        columns = [c.strip() for c in match.group(2).split(",") if c.strip()]
        return _CopyWriter(self, table, columns)

    @property
    def description(self):
        if not self._cur.description:
            return None
        return [_Col(d[0]) for d in self._cur.description]

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount

    def close(self) -> None:
        self._cur.close()

    def __enter__(self) -> "SqliteCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self.close()

    def _adapt_fetched(self, row: Sequence[Any]) -> tuple:
        if not self._colnames:
            desc = self._cur.description
            self._colnames = [d[0] for d in desc] if desc else []
        out = []
        for name, value in zip(self._colnames, row):
            if name in _ARRAY_COLUMNS:
                value = _parse_array(value)
            elif name in _BOOL_COLUMNS:
                value = _parse_bool(value)
            out.append(value)
        return tuple(out)


class SqliteConnection:
    def __init__(self, path: Path, timeout: float = 30.0) -> None:
        self.path = path
        self._conn = sqlite3.connect(
            str(path),
            timeout=timeout,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.row_factory = None
        try:
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA busy_timeout = 30000")
        except sqlite3.DatabaseError:
            pass
        self._conn.create_function("now", 0, _sqlite_now)
        self._conn.create_function("regexp_replace", 3, _sqlite_regexp_replace3)
        self._conn.create_function("regexp_replace", 4, _sqlite_regexp_replace4)
        self._conn.create_function("left", 2, _sqlite_left)
        self._conn.create_aggregate("BOOL_OR", 1, _BoolOr)

    def cursor(self) -> SqliteCursor:
        return SqliteCursor(self._conn)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    def execute(self, sql: str, params: Any = None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def __enter__(self) -> "SqliteConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self.close()


class _BoolOr:
    def __init__(self) -> None:
        self.result = False

    def step(self, value: Any) -> None:
        if value:
            self.result = True

    def finalize(self) -> bool:
        return self.result


def _writable_dir(path: Path) -> bool:
    try:
        return path.is_dir() and os.access(path, os.W_OK)
    except OSError:
        return False


def _sqlite_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _sqlite_left(value: Any, n: Any) -> str | None:
    if value is None:
        return None
    try:
        count = int(n)
    except (TypeError, ValueError):
        return str(value)
    return str(value)[:count]


def _sqlite_regexp_replace3(value: Any, pattern: Any, repl: Any) -> str | None:
    return _sqlite_regexp_replace4(value, pattern, repl, "")


def _sqlite_regexp_replace4(
    value: Any, pattern: Any, repl: Any, flags: Any
) -> str | None:
    if value is None:
        return None
    text = str(value)
    pat = "" if pattern is None else str(pattern)
    replacement = "" if repl is None else str(repl)
    flag_s = "" if flags is None else str(flags)
    try:
        if "g" in flag_s:
            return re.sub(pat, replacement, text)
        return re.sub(pat, replacement, text, count=1)
    except re.error:
        return text


def _split_statements(sql: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    in_single = False
    i = 0
    length = len(sql)
    while i < length:
        ch = sql[i]
        if not in_single and sql.startswith("--", i):
            while i < length and sql[i] not in "\n\r":
                buf.append(sql[i])
                i += 1
            continue
        if ch == "'" and not in_single:
            in_single = True
            buf.append(ch)
        elif ch == "'" and in_single:
            if i + 1 < length and sql[i + 1] == "'":
                buf.append("''")
                i += 2
                continue
            in_single = False
            buf.append(ch)
        elif ch == ";" and not in_single:
            stmt = "".join(buf).strip()
            if stmt:
                parts.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts or [sql]


def _adapt_bind_value(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value))
    return value


def _adapt_param_row(params: Any) -> Any:
    if params is None:
        return params
    if isinstance(params, dict):
        return {k: _adapt_bind_value(v) for k, v in params.items()}
    return tuple(_adapt_bind_value(v) for v in params)


def _parse_array(value: Any) -> Any:
    if value is None or isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") or text.startswith("{"):
            try:
                parsed = json.loads(text.replace("{", "[").replace("}", "]"))
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
        if text in ("{}", "[]", ""):
            return []
    return value


def _parse_bool(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "t", "yes"}:
            return True
        if lowered in {"0", "false", "f", "no"}:
            return False
    return value


def _convert_placeholders(sql: str, params: Any) -> tuple[str, Any]:
    if params is None:
        if "%(" in sql:
            sql = _NAMED_PLACEHOLDER_RE.sub(r":\1", sql)
        sql = sql.replace("%s", "?")
        return sql, None

    if isinstance(params, dict):
        adapted = {k: _adapt_bind_value(v) for k, v in params.items()}
        return _NAMED_PLACEHOLDER_RE.sub(r":\1", sql), adapted

    seq = list(params)
    out: list[str] = []
    new_params: list[Any] = []
    idx = 0
    i = 0
    length = len(sql)
    while i < length:
        any_m = re.match(r"=\s*ANY\s*\(%s\)", sql[i:], flags=re.I)
        if any_m and idx < len(seq) and isinstance(seq[idx], (list, tuple)):
            values = list(seq[idx])
            if not values:
                out.append("IN (NULL) AND 0")
            else:
                out.append("IN (" + ", ".join("?" for _ in values) + ")")
                new_params.extend(_adapt_bind_value(v) for v in values)
            idx += 1
            i += any_m.end()
            continue
        all_m = re.match(r"<>\s*ALL\s*\(%s\)", sql[i:], flags=re.I)
        if all_m and idx < len(seq) and isinstance(seq[idx], (list, tuple)):
            values = list(seq[idx])
            if not values:
                out.append("NOT IN (NULL)")
            else:
                out.append("NOT IN (" + ", ".join("?" for _ in values) + ")")
                new_params.extend(_adapt_bind_value(v) for v in values)
            idx += 1
            i += all_m.end()
            continue
        if sql.startswith("%s", i):
            new_params.append(_adapt_bind_value(seq[idx]))
            out.append("?")
            idx += 1
            i += 2
            continue
        named = _NAMED_PLACEHOLDER_RE.match(sql[i:])
        if named:
            out.append(":" + named.group(1))
            i += named.end()
            continue
        out.append(sql[i])
        i += 1
    return "".join(out), tuple(new_params)
