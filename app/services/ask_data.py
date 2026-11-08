"""Ask Your Data — intent router + Groq tools (numbers from tools only).

Features:
- Domain glossary in system prompt
- Intent → tool router + multi-tool playbooks
- Session memory (filters / scenario / Z-spread)
- Structured answer: summary, metric cards, assumptions, follow-ups
- Parallel tool calls; cached tape SQL aggregates; PMMS from market_rate_ref
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from app.repositories.env_load import load_dotenv
from app.services.market_rate_ref import get_pmms_ref
from app.services.qc_nl_translate import groq_api_key

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_TOOL_ROUNDS = 2
GROQ_TIMEOUT_SEC = 35
MAX_HISTORY_TURNS = 6

# Valid Groq chat models only — skip ids that 404 on this account (e.g. qwen3-32b).
_DEFAULT_MODELS = (
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-20b",
)

_SYSTEM = """You are Ask Your Data for this mortgage cashflow app.

Domain glossary:
- PMMS / Mort Ref: Freddie Mac Primary Mortgage Market Survey 30Y fixed — refinance benchmark (RI = note − PMMS). Not pool WAC. Tool: get_mortgage_ref_rate.
- WAC: UPB-weighted average coupon (loan notes), not the market ref.
- WAL: weighted-average life from returned principal only (sched + prepay + recovery); excludes interest, fees, defaults, losses.
- CRR: 1−(1−CPR)(1−CDR) annual — NOT recovery rate.
- Cohorts: k-prototypes HLTV/LLTV × Strong/Moderate/Weak RI.
- Scenarios: 27-cell grid. Stress paths like S03 = PSA Down / SDA Up (Avg-vs-Stress).
- Valuation Z-spread: continuous spread over Treasury curve; servicing 35 bp default. whatif_z_spread is sandbox-only.

Rules:
- Every number from a tool. Never invent rates, UPB, NPV, WAL, or counts.
- Prefer the fewest tools; honor the Intent / Playbook hints in the user message.
- Title Case. Brief. If recompute_required, quote the recompute hint from the tool.
- Use session memory (active Z-spread / scenario) when the user says "that" / "again" / follow-ups.
"""

_tape_cache: dict[str, Any] = {"key": None, "payload": None, "ts": 0.0}

# Intent id → (regex, playbook tool list, hint)
_PLAYBOOKS: list[tuple[str, re.Pattern[str], list[str], str]] = [
    (
        "pmms",
        re.compile(
            r"\b(pmms|mort\s*ref|ref(?:erence)?\s*rate|freddie|refinance\s*benchmark|"
            r"mortgage\s*ref|where.*(?:rate|number).*from|source.*(?:rate|pmms))\b",
            re.I,
        ),
        ["get_mortgage_ref_rate"],
        "Playbook pmms: call get_mortgage_ref_rate only.",
    ),
    (
        "whatif_z",
        re.compile(
            r"\b(what-?if|what if).*(z|spread)|\bz[\s-]*spread\s*(to|=|:)?\s*\d+|"
            r"\bat\s+\d+\s*bp\b",
            re.I,
        ),
        ["whatif_z_spread"],
        "Playbook whatif_z: call whatif_z_spread with z_spread_bp from the question or session.",
    ),
    (
        "valuation",
        re.compile(
            r"\b(valuation|npv|z-?spread|dv01|cs01|duration|price\s*pts?|wal)\b",
            re.I,
        ),
        ["get_valuation_kpis"],
        "Playbook valuation: call get_valuation_kpis (use session z_spread_bp if set).",
    ),
    (
        "tape",
        re.compile(r"\b(tape|how many loans|loan count|total upb|upb)\b", re.I),
        ["get_tape_summary"],
        "Playbook tape: call get_tape_summary.",
    ),
    (
        "qc",
        re.compile(r"\b(qc|quality check|failed rules|loan qc)\b", re.I),
        ["get_qc_rule_counts"],
        "Playbook qc: call get_qc_rule_counts.",
    ),
    (
        "scenarios",
        re.compile(r"\b(scenario|27|grid cache|s03|stress)\b", re.I),
        ["get_scenario_grid_status"],
        "Playbook scenarios: call get_scenario_grid_status.",
    ),
    (
        "valuation_plus_ref",
        re.compile(r"\b(valuation|price).*\b(ref|pmms|mort)\b|\b(ref|pmms).*\b(valuation|price)\b", re.I),
        ["get_valuation_kpis", "get_mortgage_ref_rate"],
        "Playbook valuation_plus_ref: call get_valuation_kpis and get_mortgage_ref_rate.",
    ),
]


def _match_playbook(question: str) -> tuple[str | None, list[str], str | None]:
    q = question or ""
    # More specific playbooks first (already ordered).
    for intent_id, pat, tools, hint in _PLAYBOOKS:
        if pat.search(q):
            return intent_id, list(tools), hint
    return None, [], None


def _extract_z_bp(text: str) -> float | None:
    m = re.search(
        r"(?:z[\s-]*spread|z)\s*(?:to|=|:)?\s*([+-]?\d+(?:\.\d+)?)\s*bp",
        text or "",
        re.I,
    )
    if m:
        return float(m.group(1))
    m2 = re.search(r"\bat\s+([+-]?\d+(?:\.\d+)?)\s*bp\b", text or "", re.I)
    if m2:
        return float(m2.group(1))
    return None


def _merge_session(
    session: dict[str, Any] | None,
    question: str,
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    """Persist lightweight UI/session context across follow-ups."""
    out = dict(session or {})
    z_q = _extract_z_bp(question)
    if z_q is not None:
        out["z_spread_bp"] = z_q
    for t in tools:
        name = t.get("name")
        res = t.get("result") or {}
        if not res.get("ok", True) and res.get("ok") is False:
            continue
        if name == "whatif_z_spread" and res.get("z_spread_bp") is not None:
            out["z_spread_bp"] = res["z_spread_bp"]
            out["last_whatif_price"] = res.get("price_pts")
        if name == "get_valuation_kpis" and res.get("z_spread_bp") is not None:
            out.setdefault("z_spread_bp", res["z_spread_bp"])
        if name == "get_scenario_grid_status":
            out["scenario_grid_fresh"] = res.get("cache_fresh")
            out["engine_version"] = res.get("engine_version")
        if name == "get_mortgage_ref_rate":
            out["pmms_as_of"] = res.get("as_of")
            out["pmms_rate_pct"] = res.get("rate_pct")
    # Optional filters echoed from client
    for k in ("cohort", "scenario_id", "filters"):
        if session and session.get(k) is not None:
            out[k] = session[k]
    return out


def _follow_ups(intent: str | None, session: dict[str, Any]) -> list[str]:
    base = {
        "pmms": [
            "What Is Pool WAC Vs Mort Ref?",
            "Show Valuation Price At Base Z-Spread",
        ],
        "valuation": [
            "What-If Z-Spread 150 Bp",
            "What Is The Mort Ref Rate Source?",
        ],
        "whatif_z": [
            "Compare To Base Valuation Price",
            "What Is WAL On The Pool?",
        ],
        "tape": [
            "How Many QC Rules Failed?",
            "Is The Scenario Grid Cache Fresh?",
        ],
        "qc": ["How Many Loans On The Tape?", "Show Valuation KPIs"],
        "scenarios": [
            "Explain S03 Stress Path",
            "Show Valuation Price",
        ],
    }
    chips = list(base.get(intent or "", ["What Is The Mort Ref Rate?", "Show Valuation KPIs"]))
    if session.get("z_spread_bp") is not None and intent != "whatif_z":
        chips.insert(0, f"What-If Z-Spread {float(session['z_spread_bp']):.0f} Bp")
    return chips[:4]


def _assumptions_line(session: dict[str, Any], tools: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    if session.get("z_spread_bp") is not None:
        parts.append(f"Session Z-Spread {float(session['z_spread_bp']):.0f} Bp")
    if session.get("cohort"):
        parts.append(f"Cohort {session['cohort']}")
    if session.get("scenario_id"):
        parts.append(f"Scenario {session['scenario_id']}")
    for t in tools:
        res = t.get("result") or {}
        if t.get("name") == "get_valuation_kpis" and res.get("servicing_bp") is not None:
            parts.append(f"Servicing {res['servicing_bp']:.0f} Bp")
        if t.get("name") == "get_mortgage_ref_rate" and res.get("as_of"):
            parts.append(f"PMMS As Of {res['as_of']}")
        if t.get("name") == "whatif_z_spread":
            parts.append("Sandbox What-If (No Prod Write)")
    return " · ".join(parts) if parts else "Tools-Only Numbers · No Invented Metrics"


_BLOCKED_MODELS = frozenset(
    {
        "qwen/qwen3-32b",  # frequently 404 model_not_found on Groq
    }
)


def _groq_models() -> list[str]:
    load_dotenv(overwrite=False)
    primary = (os.environ.get("GROQ_MODEL") or "").strip()
    extra = (os.environ.get("GROQ_MODEL_FALLBACKS") or "").strip()
    models: list[str] = []

    def _add(m: str, *, front: bool = False) -> None:
        if not m or m in _BLOCKED_MODELS or m in models:
            return
        if front:
            models.insert(0, m)
        else:
            models.append(m)

    # Working defaults first.
    for m in _DEFAULT_MODELS:
        _add(m)
    # Env overrides — skip blocked; prefer llama over broken env primary.
    env_list = [primary, *[x.strip() for x in extra.split(",") if x.strip()]]
    for m in env_list:
        if m in _BLOCKED_MODELS:
            continue
        if m == "openai/gpt-oss-20b":
            _add(m)  # keep as fallback, not first
        else:
            _add(m, front=True)
    # Deduped order: ensure llama-3.3-70b-versatile is tried early.
    if "llama-3.3-70b-versatile" in models:
        models = ["llama-3.3-70b-versatile"] + [
            m for m in models if m != "llama-3.3-70b-versatile"
        ]
    return models or ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]


def _tool_tape_summary(_: dict[str, Any]) -> dict[str, Any]:
    from app.repositories.asf_tape_repository import AsfTapeRepository
    from app.repositories.env_load import load_dotenv
    from app.repositories.tape_repository import resolve_default_tape_path

    load_dotenv()
    tape_path = resolve_default_tape_path()
    try:
        mtime = tape_path.stat().st_mtime if tape_path.exists() else 0.0
    except OSError:
        mtime = 0.0
    cache_key = f"{tape_path}:{mtime}"
    if _tape_cache["key"] == cache_key and _tape_cache["payload"]:
        return {**_tape_cache["payload"], "cached": True}

    repo = AsfTapeRepository()
    if repo.url:
        try:
            from app.repositories.connect import connect

            with connect(repo.require_url(), connect_timeout=20) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT COUNT(*)::int AS n,
                               COALESCE(SUM(current_loan_amount), 0)::float AS upb
                        FROM public.asf_tape
                        """
                    )
                    n, upb = cur.fetchone()
            payload = {
                "ok": True,
                "n_loans": int(n),
                "total_upb": round(float(upb), 2),
                "source": "asf_tape SQL aggregate",
                "cached": False,
            }
            _tape_cache.update(key=cache_key, payload=payload, ts=time.time())
            return payload
        except Exception as exc:  # noqa: BLE001
            sql_err = f"{type(exc).__name__}: {exc}"
    else:
        sql_err = "DATABASE_URL unset"

    from app.repositories.tape_repository import TapeRepository

    loans = TapeRepository(tape_path).load_all_loans()
    upb = sum(float(ln.current_balance or 0.0) for ln in loans)
    payload = {
        "ok": True,
        "n_loans": len(loans),
        "total_upb": round(upb, 2),
        "source": "tape xlsx",
        "sql_fallback_reason": sql_err,
        "cached": False,
    }
    _tape_cache.update(key=cache_key, payload=payload, ts=time.time())
    return payload


def _tool_pmms(_: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, **get_pmms_ref()}


def _tool_valuation_kpis(args: dict[str, Any]) -> dict[str, Any]:
    from app.services.valuation import (
        DEFAULT_SERVICING_BP,
        DEFAULT_Z_SPREAD_BP,
        StaleCashflowCacheError,
        build_valuation,
    )

    try:
        payload = build_valuation(
            servicing_bp=float(args.get("servicing_bp") or DEFAULT_SERVICING_BP),
            z_spread_bp=float(args.get("z_spread_bp") or DEFAULT_Z_SPREAD_BP),
        )
    except StaleCashflowCacheError as exc:
        return {"ok": False, "error": str(exc), "recompute_required": True}
    return {
        "ok": True,
        "npv": payload.get("npv"),
        "price_pts": payload.get("price_pts"),
        "wal_years": payload.get("wal_years"),
        "duration": payload.get("duration"),
        "cs01": payload.get("cs01"),
        "dv01": payload.get("dv01"),
        "servicing_bp": payload.get("servicing_bp"),
        "z_spread_bp": payload.get("z_spread_bp"),
        "start_upb": payload.get("start_upb"),
        "curve_method": (payload.get("curve_meta") or {}).get("method"),
        "source": "build_valuation",
    }


def _tool_whatif_z_spread(args: dict[str, Any]) -> dict[str, Any]:
    from app.services.valuation import (
        DEFAULT_SERVICING_BP,
        StaleCashflowCacheError,
        build_valuation,
    )

    zs = args.get("z_spread_bp")
    if zs is None:
        return {"ok": False, "error": "z_spread_bp is required"}
    try:
        payload = build_valuation(
            servicing_bp=float(args.get("servicing_bp") or DEFAULT_SERVICING_BP),
            z_spread_bp=float(zs),
        )
    except StaleCashflowCacheError as exc:
        return {"ok": False, "error": str(exc), "recompute_required": True}
    return {
        "ok": True,
        "sandbox": True,
        "mutates_prod": False,
        "z_spread_bp": payload.get("z_spread_bp"),
        "npv": payload.get("npv"),
        "price_pts": payload.get("price_pts"),
        "note": "In-memory what-if only; no cache or DB write.",
    }


def _tool_qc_counts(_: dict[str, Any]) -> dict[str, Any]:
    from app.repositories.asf_tape_repository import AsfTapeRepository
    from app.repositories.env_load import load_dotenv

    load_dotenv()
    repo = AsfTapeRepository()
    if not repo.url:
        return {"ok": False, "error": "DATABASE_URL not set for QC"}
    rows = repo.latest_results()
    failed = sum(1 for r in rows if (r.get("outcome") or "").lower() in ("fail", "failed"))
    loans_failed = sum(int(r.get("fail_count") or r.get("n_fail") or 0) for r in rows)
    return {
        "ok": True,
        "total_rules": len(rows),
        "failed_rules": failed,
        "loans_failed_sum": loans_failed,
        "source": "AsfTapeRepository.latest_results",
    }


def _tool_scenario_grid_status(_: dict[str, Any]) -> dict[str, Any]:
    from app.repositories.env_load import REPO_ROOT
    from app.repositories.tape_repository import resolve_default_tape_path
    from app.services.cache_keys import cache_is_fresh

    path = REPO_ROOT / "data" / "scenario-grid-cashflow.json"
    if not path.is_file():
        return {"ok": False, "error": "scenario-grid-cashflow.json missing"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    fresh = cache_is_fresh(payload, tape_path=resolve_default_tape_path())
    scenarios = payload.get("scenarios") or {}
    n_ok = sum(
        1 for m in scenarios.values() if (m or {}).get("status") in (None, "ok")
    )
    return {
        "ok": fresh and n_ok == 27,
        "cache_fresh": fresh,
        "n_scenarios": len(scenarios),
        "n_ok_or_legacy": n_ok,
        "engine_version": payload.get("engine_version"),
        "source": "data/scenario-grid-cashflow.json",
    }


TOOLS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "get_tape_summary": _tool_tape_summary,
    "get_mortgage_ref_rate": _tool_pmms,
    "get_valuation_kpis": _tool_valuation_kpis,
    "whatif_z_spread": _tool_whatif_z_spread,
    "get_qc_rule_counts": _tool_qc_counts,
    "get_scenario_grid_status": _tool_scenario_grid_status,
}

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "get_tape_summary",
            "description": "Loan count and total UPB.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_mortgage_ref_rate",
            "description": "Freddie Mac 30Y PMMS Mort Ref rate, source, as-of.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_valuation_kpis",
            "description": "Valuation NPV, price, WAL, duration, CS01, DV01.",
            "parameters": {
                "type": "object",
                "properties": {
                    "servicing_bp": {"type": "number"},
                    "z_spread_bp": {"type": "number"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "whatif_z_spread",
            "description": "Sandbox Z-spread reprice (no cache writes).",
            "parameters": {
                "type": "object",
                "properties": {
                    "z_spread_bp": {"type": "number"},
                    "servicing_bp": {"type": "number"},
                },
                "required": ["z_spread_bp"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_qc_rule_counts",
            "description": "QC rule totals and fails.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_scenario_grid_status",
            "description": "27-cell scenario-grid cache freshness.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

_METRIC_KEYS: dict[str, list[tuple[str, str, str]]] = {
    "get_mortgage_ref_rate": [
        ("rate_pct", "Mort Ref", "pct1"),
        ("source", "Source", "text"),
        ("as_of", "As Of", "text"),
        ("label", "Series", "text"),
    ],
    "get_tape_summary": [
        ("n_loans", "Loans", "int"),
        ("total_upb", "UPB", "money"),
    ],
    "get_valuation_kpis": [
        ("price_pts", "Price", "num1"),
        ("wal_years", "WAL", "num1"),
        ("duration", "Duration", "num1"),
        ("npv", "NPV", "money"),
        ("z_spread_bp", "Z-Spread", "bp"),
        ("cs01", "CS01", "money"),
        ("dv01", "DV01", "money"),
    ],
    "whatif_z_spread": [
        ("z_spread_bp", "What-If Z", "bp"),
        ("price_pts", "Price", "num1"),
        ("npv", "NPV", "money"),
    ],
    "get_qc_rule_counts": [
        ("total_rules", "Rules", "int"),
        ("failed_rules", "Failed", "int"),
        ("loans_failed_sum", "Loans Failed", "int"),
    ],
    "get_scenario_grid_status": [
        ("n_scenarios", "Scenarios", "int"),
        ("n_ok_or_legacy", "OK Cells", "int"),
        ("cache_fresh", "Cache Fresh", "bool"),
        ("engine_version", "Engine", "text"),
    ],
}


def metrics_from_tools(tools: list[dict[str, Any]]) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    for t in tools or []:
        name = t.get("name") or ""
        result = t.get("result") or {}
        if result.get("ok") is False:
            cards.append(
                {
                    "label": name,
                    "value": str(result.get("error") or "Tool error"),
                    "tool": name,
                    "kind": "error",
                }
            )
            continue
        for field, label, fmt in _METRIC_KEYS.get(name, []):
            if field not in result or result[field] is None:
                continue
            raw = result[field]
            if fmt == "pct1":
                val = f"{float(raw):.1f}%"
            elif fmt == "num1":
                val = f"{float(raw):.1f}"
            elif fmt == "int":
                val = f"{int(raw):,}"
            elif fmt == "money":
                val = f"${float(raw):,.0f}"
            elif fmt == "bp":
                val = f"{float(raw):.0f} bp"
            elif fmt == "bool":
                val = "Yes" if raw else "No"
            else:
                val = str(raw)
            cards.append({"label": label, "value": val, "tool": name, "kind": "metric"})
    return cards


def _run_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    fn = TOOLS.get(name)
    if not fn:
        return {"ok": False, "error": f"Unknown tool: {name}"}
    try:
        return fn(arguments or {})
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _run_playbook_tools(
    tool_names: list[str],
    *,
    question: str,
    session: dict[str, Any],
) -> list[dict[str, Any]]:
    """Execute playbook tools in parallel with session-aware args."""
    z_default = session.get("z_spread_bp")
    z_from_q = _extract_z_bp(question)
    z_use = z_from_q if z_from_q is not None else z_default

    def _args_for(name: str) -> dict[str, Any]:
        if name in ("whatif_z_spread", "get_valuation_kpis") and z_use is not None:
            return {"z_spread_bp": float(z_use)}
        if name == "whatif_z_spread" and z_use is None:
            return {"z_spread_bp": 100.0}
        return {}

    prepared = [(n, _args_for(n)) for n in tool_names]
    results: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(prepared)))) as pool:
        futs = {
            pool.submit(_run_tool, name, args): i
            for i, (name, args) in enumerate(prepared)
        }
        for fut in as_completed(futs):
            results[futs[fut]] = fut.result()
    out: list[dict[str, Any]] = []
    for i, (name, args) in enumerate(prepared):
        out.append(
            {
                "name": name,
                "arguments": args,
                "result": results.get(i) or {"ok": False, "error": "missing"},
            }
        )
    return out


def _run_tools_parallel(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared: list[tuple[str, str, dict[str, Any]]] = []
    for call in calls:
        fn = call.get("function") or {}
        name = fn.get("name") or ""
        raw_args = fn.get("arguments") or "{}"
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
        except json.JSONDecodeError:
            args = {}
        prepared.append((call.get("id") or "", name, args))

    results: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(prepared)))) as pool:
        futs = {
            pool.submit(_run_tool, name, args): i
            for i, (_cid, name, args) in enumerate(prepared)
        }
        for fut in as_completed(futs):
            results[futs[fut]] = fut.result()

    out: list[dict[str, Any]] = []
    for i, (cid, name, args) in enumerate(prepared):
        out.append(
            {
                "id": cid,
                "name": name,
                "arguments": args,
                "result": results.get(i) or {"ok": False, "error": "missing"},
            }
        )
    return out


def _chat_groq(
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    use_tools: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "temperature": 0,
        "messages": messages,
    }
    if use_tools:
        payload["tools"] = TOOL_SPECS
        payload["tool_choice"] = "auto"
    req = urllib.request.Request(
        GROQ_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "cashflow-sum-app-ask-data/1.3",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=GROQ_TIMEOUT_SEC) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _normalize_history(history: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for turn in history or []:
        role = (turn.get("role") or "").strip()
        content = (turn.get("content") or turn.get("text") or "").strip()
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content})
    if len(out) > MAX_HISTORY_TURNS * 2:
        out = out[-(MAX_HISTORY_TURNS * 2) :]
    return out


def _structured_payload(
    *,
    ok: bool,
    answer: str | None,
    tools: list[dict[str, Any]],
    intent: str | None,
    session: dict[str, Any],
    model: str | None,
    elapsed_ms: float,
    error: str | None = None,
    playbook_tools: list[str] | None = None,
) -> dict[str, Any]:
    metrics = metrics_from_tools(tools)
    return {
        "ok": ok,
        "answer": answer,
        "summary": answer,
        "metrics": metrics,
        "cards": metrics,
        "assumptions": _assumptions_line(session, tools),
        "follow_ups": _follow_ups(intent, session),
        "session": session,
        "intent": intent,
        "playbook_tools": playbook_tools or [],
        "model": model,
        "tools": tools,
        "elapsed_ms": elapsed_ms,
        "error": error,
    }


def ask(
    question: str,
    *,
    history: list[dict[str, Any]] | None = None,
    session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Intent-routed ask with playbooks, session memory, structured template."""
    text = (question or "").strip()
    if not text:
        return _structured_payload(
            ok=False,
            answer=None,
            tools=[],
            intent=None,
            session=dict(session or {}),
            model=None,
            elapsed_ms=0,
            error="question is required",
        )

    key = groq_api_key()
    if not key:
        return _structured_payload(
            ok=False,
            answer=None,
            tools=[],
            intent=None,
            session=dict(session or {}),
            model=None,
            elapsed_ms=0,
            error="GROQ_API_KEY is required. Set it in .env and restart the API.",
        )

    sess = dict(session or {})
    intent, playbook, hint = _match_playbook(text)
    t0 = time.perf_counter()
    trace: list[dict[str, Any]] = []

    # Fast path: deterministic playbook tools (no model round-trip for data).
    if playbook:
        trace = _run_playbook_tools(playbook, question=text, session=sess)
        sess = _merge_session(sess, text, trace)

    messages: list[dict[str, Any]] = [{"role": "system", "content": _SYSTEM}]
    messages.extend(_normalize_history(history))
    sess_note = ""
    if sess:
        sess_note = f"\nSession memory: {json.dumps(sess, default=str)}"
    tool_note = ""
    if trace:
        tool_note = (
            "\nPlaybook tool results (already fetched — do not re-call unless needed):\n"
            + json.dumps(
                [{"name": t["name"], "result": t["result"]} for t in trace],
                default=str,
            )
        )
    user_content = text
    if hint:
        user_content += f"\n\n({hint})"
    user_content += sess_note + tool_note
    messages.append({"role": "user", "content": user_content})

    used_model: str | None = None
    last_error: str | None = None

    for model in _groq_models():
        try:
            used_model = model
            # If playbook already filled metrics, one prose pass without tools.
            if trace:
                body = _chat_groq(key, model, messages, use_tools=False)
                msg = ((body.get("choices") or [{}])[0].get("message") or {})
                answer = (msg.get("content") or "").strip()
                elapsed = round((time.perf_counter() - t0) * 1000, 1)
                return _structured_payload(
                    ok=True,
                    answer=answer or "See metric cards.",
                    tools=trace,
                    intent=intent,
                    session=sess,
                    model=used_model,
                    elapsed_ms=elapsed,
                    playbook_tools=playbook,
                )

            for _round in range(MAX_TOOL_ROUNDS):
                body = _chat_groq(key, model, messages, use_tools=True)
                choice = (body.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                tool_calls = msg.get("tool_calls") or []
                if not tool_calls:
                    answer = (msg.get("content") or "").strip()
                    sess = _merge_session(sess, text, trace)
                    elapsed = round((time.perf_counter() - t0) * 1000, 1)
                    return _structured_payload(
                        ok=True,
                        answer=answer or "(No answer text.)",
                        tools=trace,
                        intent=intent,
                        session=sess,
                        model=used_model,
                        elapsed_ms=elapsed,
                        playbook_tools=playbook,
                    )
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.get("content"),
                        "tool_calls": tool_calls,
                    }
                )
                batch = _run_tools_parallel(tool_calls)
                for item in batch:
                    trace.append(
                        {
                            "name": item["name"],
                            "arguments": item["arguments"],
                            "result": item["result"],
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": item["id"],
                            "name": item["name"],
                            "content": json.dumps(item["result"]),
                        }
                    )
            messages.append(
                {
                    "role": "user",
                    "content": "Using only the tool results above, answer briefly.",
                }
            )
            body = _chat_groq(key, model, messages, use_tools=False)
            msg = ((body.get("choices") or [{}])[0].get("message") or {})
            answer = (msg.get("content") or "").strip()
            sess = _merge_session(sess, text, trace)
            elapsed = round((time.perf_counter() - t0) * 1000, 1)
            return _structured_payload(
                ok=True,
                answer=answer or "See metric cards.",
                tools=trace,
                intent=intent,
                session=sess,
                model=used_model,
                elapsed_ms=elapsed,
                playbook_tools=playbook,
            )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            last_error = f"{model}: HTTP {exc.code}: {detail}"
            if exc.code in (400, 403, 404):
                continue
            break
        except Exception as exc:  # noqa: BLE001
            last_error = f"{model}: {type(exc).__name__}: {exc}"
            continue

    # Playbook data may still be useful even if Groq failed.
    if trace:
        sess = _merge_session(sess, text, trace)
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        return _structured_payload(
            ok=True,
            answer="Model unavailable — metric cards from tools only.",
            tools=trace,
            intent=intent,
            session=sess,
            model=used_model,
            elapsed_ms=elapsed,
            error=last_error,
            playbook_tools=playbook,
        )

    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    return _structured_payload(
        ok=False,
        answer=None,
        tools=trace,
        intent=intent,
        session=sess,
        model=used_model,
        elapsed_ms=elapsed,
        error=last_error or "Groq ask failed",
        playbook_tools=playbook,
    )
