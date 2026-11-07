"""Validate QC SQL predicates against asf_tape (failing-row WHERE fragments)."""

from __future__ import annotations

import re
from typing import Iterable

from app.repositories.asf_tape_schema import ASF_TAPE_COLUMNS

ALLOWED_COLUMNS = frozenset(ASF_TAPE_COLUMNS)

_FORBIDDEN = re.compile(
    r"\b("
    r"insert|update|delete|drop|alter|create|truncate|grant|revoke|"
    r"union|except|intersect|attach|detach|pragma|vacuum|"
    r"copy|call|execute|into|outfile|load_file"
    r")\b|;|--|/\*|\*/",
    re.I,
)

_IDENT = re.compile(r"\b([a-z_][a-z0-9_]*)\b", re.I)

# SQL / function keywords that are not tape columns.
_SQL_WORDS = frozenset(
    {
        "and",
        "or",
        "not",
        "is",
        "null",
        "true",
        "false",
        "in",
        "like",
        "between",
        "case",
        "when",
        "then",
        "else",
        "end",
        "coalesce",
        "nullif",
        "abs",
        "length",
        "trim",
        "lower",
        "upper",
        "cast",
        "as",
        "distinct",
        "from",
        "where",
        "select",
        "count",
        "avg",
        "min",
        "max",
        "sum",
        "round",
        "regexp_replace",
        "replace",
        "substr",
        "substring",
        "left",
        "right",
        "date",
        "datetime",
        "interval",
        "extract",
        "year",
        "month",
        "day",
        "integer",
        "int",
        "real",
        "double",
        "precision",
        "numeric",
        "text",
        "boolean",
        "bool",
        "now",
        "g",
    }
)


def extract_columns(predicate: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in _IDENT.finditer(predicate or ""):
        name = match.group(1).lower()
        if name in ALLOWED_COLUMNS and name not in seen:
            seen.add(name)
            found.append(name)
    return found


def validate_predicate(predicate: str) -> tuple[str, list[str]]:
    """Return cleaned predicate + required columns, or raise ValueError."""
    text = (predicate or "").strip().rstrip(";")
    if not text:
        raise ValueError("sql_predicate is empty")
    if len(text) > 2000:
        raise ValueError("sql_predicate is too long")
    if _FORBIDDEN.search(text):
        raise ValueError("sql_predicate contains forbidden SQL")
    # Reject nested queries / table references outside the WHERE fragment.
    lowered = text.lower()
    if " from " in f" {lowered} " or " select " in f" {lowered} ":
        raise ValueError("sql_predicate must be a WHERE fragment only")
    refs = extract_columns(text)
    unknown = []
    for match in _IDENT.finditer(text):
        name = match.group(1).lower()
        if name.isdigit() or name in _SQL_WORDS or name in ALLOWED_COLUMNS:
            continue
        # numeric-looking tokens already skipped; bare identifiers must be columns
        if re.fullmatch(r"[a-z_][a-z0-9_]*", name) and name not in ALLOWED_COLUMNS:
            unknown.append(name)
    if unknown:
        uniq = sorted(set(unknown))
        raise ValueError(
            "sql_predicate references unknown column(s): " + ", ".join(uniq)
        )
    if not refs:
        raise ValueError("sql_predicate must reference at least one asf_tape column")
    return text, refs


def assert_runnable(predicate: str, present_columns: Iterable[str]) -> None:
    cleaned, required = validate_predicate(predicate)
    missing = [c for c in required if c not in set(present_columns)]
    if missing:
        raise ValueError(
            "asf_tape lacks required field(s): " + ", ".join(missing)
        )
    _ = cleaned
