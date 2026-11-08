#!/usr/bin/env python3
"""Materialize SIFMA PSA CPR + GFMI/SIFMA SDA CDR paths for scenario speeds.

Writes ``data/psa_sda_standards.csv`` and ``public/psa_sda_standards.csv``
(month 1–360 × PSA 75/100/125 CPR + SDA 50/100/200 CDR). Matches
``app/services/psa_prepay.py`` and ``app/services/sda_default.py``.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.services.psa_prepay import cpr_at_age  # noqa: E402
from app.services.sda_default import cdr_at_age  # noqa: E402

# Distinct multiples from Scenarios cohort speed schedule (src/scenarioSpeeds.js).
PSA_MULTIPLES = (50, 75, 100, 125, 150, 225)
SDA_MULTIPLES = (25, 75, 100, 150, 250, 300, 450)
MONTHS = 360


def build_rows() -> list[dict[str, str | int]]:
    rows: list[dict[str, str | int]] = []
    for m in range(1, MONTHS + 1):
        row: dict[str, str | int] = {"month": m}
        for p in PSA_MULTIPLES:
            row[f"psa_{p}_cpr"] = f"{cpr_at_age(m, p):.8f}"
        for s in SDA_MULTIPLES:
            row[f"sda_{s}_cdr"] = f"{cdr_at_age(m, s):.8f}"
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict[str, str | int]]) -> None:
    fields = (
        ["month"]
        + [f"psa_{p}_cpr" for p in PSA_MULTIPLES]
        + [f"sda_{s}_cdr" for s in SDA_MULTIPLES]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    rows = build_rows()
    for rel in ("data/psa_sda_standards.csv", "public/psa_sda_standards.csv"):
        path = REPO / rel
        write_csv(path, rows)
        print(f"wrote {path} ({len(rows)} months)")


if __name__ == "__main__":
    main()
