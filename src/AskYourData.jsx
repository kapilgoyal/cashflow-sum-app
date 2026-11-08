/**
 * Ask Your Data — readable chat: metric tiles, light markdown, subtle meta.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiUrl } from "./apiBase";
import "./AskYourData.css";

const STARTER_CHIPS = [
  "What Is The Mort Ref Rate And Source?",
  "How Many Loans And Total UPB?",
  "Show Valuation Price And WAL",
  "What-If Z-Spread 150 Bp",
  "Is The Scenario Grid Cache Fresh?",
];

/** Light markdown → React nodes (bold / italics / strip leftovers). */
function formatAnswer(text) {
  const raw = (text || "").replace(/\r\n/g, "\n").trim();
  if (!raw) return null;
  const lines = raw.split("\n");
  return lines.map((line, li) => {
    const parts = [];
    const re = /(\*\*([^*]+)\*\*|\*([^*]+)\*|__([^_]+)__|_([^_]+)_)/g;
    let last = 0;
    let m;
    while ((m = re.exec(line)) !== null) {
      if (m.index > last) parts.push(line.slice(last, m.index));
      if (m[2] != null || m[4] != null) {
        parts.push(
          <strong key={`${li}-b-${m.index}`}>{m[2] ?? m[4]}</strong>
        );
      } else {
        parts.push(<em key={`${li}-i-${m.index}`}>{m[3] ?? m[5]}</em>);
      }
      last = m.index + m[0].length;
    }
    if (last < line.length) parts.push(line.slice(last));
    // Drop leftover lone ** / __ markers if model mismatched.
    const cleaned = parts.map((p) =>
      typeof p === "string" ? p.replace(/\*\*|__/g, "") : p
    );
    return (
      <span key={`ln-${li}`}>
        {li > 0 ? "\n" : null}
        {cleaned}
      </span>
    );
  });
}

function shortModel(model) {
  if (!model) return null;
  const s = String(model);
  const slash = s.lastIndexOf("/");
  return slash >= 0 ? s.slice(slash + 1) : s;
}

function MetricCards({ cards }) {
  if (!cards?.length) return null;
  return (
    <div className="ask-metrics" role="list" aria-label="Metrics">
      {cards.map((c, i) => (
        <div
          key={`${c.label}-${i}`}
          role="listitem"
          className={`ask-metric${c.kind === "error" ? " is-error" : ""}`}
          title={c.tool ? String(c.tool) : undefined}
        >
          <span className="ask-metric-label">{c.label}</span>
          <span className="ask-metric-value">{c.value}</span>
        </div>
      ))}
    </div>
  );
}

function ToolDrawer({ tools }) {
  if (!tools?.length) return null;
  return (
    <details className="ask-tool-drawer">
      <summary>Tool Trace ({tools.length})</summary>
      <pre>{JSON.stringify(tools, null, 2)}</pre>
    </details>
  );
}

function AssistantMeta({ model, elapsed, intent, tools }) {
  const bits = useMemo(() => {
    const out = [];
    const m = shortModel(model);
    if (m) out.push(m);
    if (elapsed != null && Number.isFinite(Number(elapsed))) {
      out.push(`${Math.round(Number(elapsed))} ms`);
    }
    if (intent) out.push(String(intent).replace(/_/g, " "));
    if (tools?.length) out.push(`${tools.length} tool${tools.length === 1 ? "" : "s"}`);
    return out;
  }, [model, elapsed, intent, tools]);
  if (!bits.length) return null;
  return (
    <span className="ask-sub" aria-label="Response meta">
      {bits.join(" · ")}
    </span>
  );
}

export default function AskYourData() {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [statusLine, setStatusLine] = useState("Checking Groq…");
  const [turns, setTurns] = useState([]);
  const [session, setSession] = useState({});
  const [followUps, setFollowUps] = useState(STARTER_CHIPS);
  const inputRef = useRef(null);
  const bottomRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(apiUrl("/api/ask-data/status"));
        const data = await res.json();
        if (!cancelled) {
          setStatusLine(
            data.groq_configured
              ? "Groq Ready · Tools Only"
              : "GROQ_API_KEY Missing — Set .env And Restart API"
          );
        }
      } catch {
        if (!cancelled) setStatusLine("API Unreachable");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [turns, busy]);

  useEffect(() => {
    inputRef.current?.focus?.();
  }, []);

  const historyPayload = useCallback(() => {
    return turns
      .filter((t) => t.role === "user" || t.role === "assistant")
      .map((t) => ({ role: t.role, content: t.text }))
      .slice(-12);
  }, [turns]);

  const submit = useCallback(
    async (text) => {
      const q = (text || question || "").trim();
      if (!q || busy) return;
      setQuestion("");
      setBusy(true);
      setStatusLine("Calling Tools…");
      setTurns((prev) => [...prev, { role: "user", text: q }]);
      abortRef.current?.abort?.();
      const ac = new AbortController();
      abortRef.current = ac;
      try {
        const res = await fetch(apiUrl("/api/ask-data/ask"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: ac.signal,
          body: JSON.stringify({
            question: q,
            history: historyPayload(),
            session,
          }),
        });
        const data = await res.json();
        if (data.session && typeof data.session === "object") {
          setSession(data.session);
        }
        if (Array.isArray(data.follow_ups) && data.follow_ups.length) {
          setFollowUps(data.follow_ups);
        }
        const cards = data.metrics || data.cards || [];
        setTurns((prev) => [
          ...prev,
          {
            role: "assistant",
            text: data.ok
              ? data.answer || data.summary || "See metrics."
              : data.error || "Ask failed.",
            ok: Boolean(data.ok),
            cards,
            assumptions: data.assumptions,
            tools: data.tools || [],
            model: data.model,
            elapsed: data.elapsed_ms,
            intent: data.intent,
          },
        ]);
        setStatusLine(
          data.ok
            ? `Ready${data.model ? ` · ${shortModel(data.model)}` : ""}${
                data.elapsed_ms != null
                  ? ` · ${Math.round(data.elapsed_ms)} ms`
                  : ""
              }`
            : "Error — See Message"
        );
      } catch (err) {
        if (err.name === "AbortError") return;
        setTurns((prev) => [
          ...prev,
          {
            role: "assistant",
            text: err.message || String(err),
            ok: false,
            cards: [],
            tools: [],
          },
        ]);
        setStatusLine("Request Failed");
      } finally {
        setBusy(false);
        queueMicrotask(() => inputRef.current?.focus?.());
      }
    },
    [busy, question, historyPayload, session]
  );

  return (
    <section
      className="section section-fill section-ask-data"
      aria-label="Ask Your Data"
    >
      <header className="ask-data-topbar">
        <h2 className="section-title">Ask Your Data</h2>
        <span className="ask-data-meta" aria-live="polite">
          {statusLine}
        </span>
      </header>

      <div className="ask-data-chips" role="group" aria-label="Suggestions">
        {(busy ? [] : followUps).map((ex) => (
          <button
            key={ex}
            type="button"
            className="ask-chip"
            disabled={busy}
            onClick={() => void submit(ex)}
          >
            {ex}
          </button>
        ))}
      </div>

      <div className="ask-data-thread" aria-live="polite">
        {!turns.length && !busy ? (
          <div className="ask-empty">
            <p className="ask-empty-title">Ask The Tape, Valuation, Or Scenarios</p>
            <p className="ask-empty-body">
              Answers use live tools only — Mort Ref (PMMS), UPB, Valuation KPIs,
              sandbox Z-spread what-ifs. Numbers show as metric tiles.
            </p>
          </div>
        ) : null}

        {turns.map((t, i) => (
          <article
            key={i}
            className={`ask-bubble ask-${t.role}${
              t.ok === false ? " is-error" : ""
            }`}
          >
            <div className="ask-bubble-head">
              <span className="ask-role">
                {t.role === "user" ? "You" : "Assistant"}
              </span>
              {t.role === "assistant" ? (
                <AssistantMeta
                  model={t.model}
                  elapsed={t.elapsed}
                  intent={t.intent}
                  tools={t.tools}
                />
              ) : null}
            </div>
            <div className="ask-bubble-text">
              {t.role === "assistant" ? formatAnswer(t.text) : t.text}
            </div>
            <MetricCards cards={t.cards} />
            {t.assumptions ? (
              <p className="ask-assumptions">{t.assumptions}</p>
            ) : null}
            <ToolDrawer tools={t.tools} />
          </article>
        ))}

        {busy ? (
          <div className="ask-bubble ask-assistant ask-loading" aria-busy="true">
            <div className="ask-bubble-head">
              <span className="ask-role">Assistant</span>
              <span className="ask-sub">Working…</span>
            </div>
            <div className="ask-loading-bar" />
            <p className="ask-bubble-text ask-loading-copy">
              Fetching tool metrics…
            </p>
          </div>
        ) : null}
        <div ref={bottomRef} />
      </div>

      <form
        className="ask-data-composer"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <textarea
          ref={inputRef}
          className="ask-data-input"
          rows={2}
          value={question}
          disabled={busy}
          placeholder="Ask about Mort Ref, tape UPB, Valuation, or Z-spread what-ifs…"
          aria-label="Ask a question"
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void submit();
            }
          }}
        />
        <button
          type="submit"
          className="btn ask-send"
          disabled={busy || !question.trim()}
        >
          Ask
        </button>
      </form>
    </section>
  );
}
