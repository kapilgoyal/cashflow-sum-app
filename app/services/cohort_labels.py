"""User-visible cohort display labels.

Compact Title Case: HLTV/LLTV acronyms + Strong/Moderate/Weak RI.
Does not change k-proto assignment (cluster ids 0/1/2) or recovery math.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

HLTV_STRONG_RI = "HLTV Strong RI"
HLTV_MODERATE_RI = "HLTV Moderate RI"
HLTV_WEAK_RI = "HLTV Weak RI"
LLTV_STRONG_RI = "LLTV Strong RI"
LLTV_MODERATE_RI = "LLTV Moderate RI"
LLTV_WEAK_RI = "LLTV Weak RI"

COHORT_DISPLAY_LABELS = (
    HLTV_STRONG_RI,
    HLTV_MODERATE_RI,
    HLTV_WEAK_RI,
    LLTV_STRONG_RI,
    LLTV_MODERATE_RI,
    LLTV_WEAK_RI,
)

# Existing k=3 clusters (ids 0 / 1 / 2). Python names are internal.
COHORT_LOW_LTV_WEAK = LLTV_WEAK_RI
COHORT_HIGH_LTV_STRONG = HLTV_STRONG_RI
COHORT_HIGH_LTV_WEAK = HLTV_WEAK_RI

# Historical / long / plus-sign aliases → canonical display. Same cluster
# identity stays on one label (cluster 0 is LLTV Weak RI, not a new chip).
_ALIAS_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        HLTV_STRONG_RI,
        (
            "high LTV and strong refinance incentive",
            "High LTV + Strong RI",
            "High LTV Strong RI",
            "strong RI",
            "HLTV-HRI",
            "HLTV HRI",
        ),
    ),
    (
        HLTV_MODERATE_RI,
        (
            "high LTV and moderate refinance incentive",
            "High LTV + Moderate RI",
            "High LTV Moderate RI",
        ),
    ),
    (
        HLTV_WEAK_RI,
        (
            "high LTV and weak refinance incentive",
            "High LTV + Weak RI",
            "High LTV Weak RI",
            "weak RI",
            "HLTV-LRI",
            "HLTV LRI",
        ),
    ),
    (
        LLTV_STRONG_RI,
        (
            "low LTV and strong refinance incentive",
            "Low LTV + Strong RI",
            "Low LTV Strong RI",
        ),
    ),
    (
        LLTV_MODERATE_RI,
        (
            "low LTV and moderate refinance incentive",
            "Low LTV + Moderate RI",
            "Low LTV Moderate RI",
        ),
    ),
    (
        LLTV_WEAK_RI,
        (
            "low LTV and weak refinance incentive",
            "Low LTV + Weak RI",
            "Low LTV Weak RI",
            "moderate RI",
            "LLTV-LRI",
            "LLTV LRI",
        ),
    ),
)

_ALIAS_TO_CANONICAL: dict[str, str] = {}
_CANONICAL_TO_ALIASES: dict[str, tuple[str, ...]] = {}
for _canon, _aliases in _ALIAS_GROUPS:
    packed = (_canon, *_aliases)
    _CANONICAL_TO_ALIASES[_canon] = packed
    for _alias in packed:
        _ALIAS_TO_CANONICAL[_alias] = _canon
        _ALIAS_TO_CANONICAL[_alias.casefold()] = _canon

_REPLACE_PAIRS: tuple[tuple[str, str], ...] = tuple(
    sorted(
        (
            (alias, canon)
            for canon, aliases in _ALIAS_GROUPS
            for alias in aliases
            if alias != canon
        ),
        key=lambda pair: -len(pair[0]),
    )
)


def canonical_cohort_label(raw: Any) -> str:
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return s
    return _ALIAS_TO_CANONICAL.get(s) or _ALIAS_TO_CANONICAL.get(s.casefold()) or s


def cohort_match_values(raw: Any) -> list[str]:
    """Stored values that should match a UI/API cohort filter."""
    s = "" if raw is None else str(raw).strip()
    if not s:
        return []
    canon = canonical_cohort_label(s)
    aliases = _CANONICAL_TO_ALIASES.get(canon, (canon,))
    out: list[str] = []
    seen: set[str] = set()
    for item in (s, canon, *aliases):
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def relabel_cohort_text(text: Any) -> Any:
    if not isinstance(text, str) or not text:
        return text
    out = text
    for alias, canon in _REPLACE_PAIRS:
        out = out.replace(alias, canon)
    return out


def relabel_record(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    if "cohort" in out and out["cohort"] is not None:
        out["cohort"] = canonical_cohort_label(out["cohort"])
    if "cluster" in out and out["cluster"] is not None:
        out["cluster"] = canonical_cohort_label(out["cluster"])
    if isinstance(out.get("note"), str):
        out["note"] = relabel_cohort_text(out["note"])
    recovery = out.get("recovery_by_cohort")
    if isinstance(recovery, dict):
        out["recovery_by_cohort"] = {
            canonical_cohort_label(k): v for k, v in recovery.items()
        }
    return out


def relabel_records(rows: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    return [relabel_record(r) or {} for r in (rows or [])]


def relabel_payload(payload: Any) -> Any:
    """Walk JSON-shaped data and rewrite displayed cohort strings."""
    if isinstance(payload, list):
        return [relabel_payload(item) for item in payload]
    if not isinstance(payload, dict):
        return payload
    out = relabel_record(payload) or {}
    for key, val in list(out.items()):
        if key == "recovery_by_cohort" and isinstance(val, dict):
            continue
        if isinstance(val, (dict, list)):
            out[key] = relabel_payload(val)
        elif key in {"applies_to", "notes"} and isinstance(val, str):
            out[key] = relabel_cohort_text(val)
    return out
