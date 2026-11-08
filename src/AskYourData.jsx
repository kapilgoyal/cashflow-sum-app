/**
 * Ask Your Data — Bloomberg-style chat over real backend tools.
 * Metric cards from API; tool JSON collapsed; session memory + follow-ups.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { apiUrl } from "./apiBase";
import "./AskYourData.css";

const STARTER_CHIPS = [
  "What Is The Mort Ref Rate And Source?",
  "How Many Loans And Total UPB?",
  "Show Valuation Price And WAL",
  "What-If Z-Spread 150 Bp",
  "Is The Scenario Grid Cache Fresh?",
];

function MetricCards({ cards }) {
  if (!cards?.length) return null;
  return (
    <div className="ask-metrics" role="list" aria-label="Metrics">
      {cards.map((c, i) => (
        <div
          key={`${c.label}-${i}`}
          role="listitem"
          className={`ask-metric${c.kind === "error" ? " is-error" : ""}`}
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
            ? `Ready${data.model ? ` · ${data.model}` : ""}${
                data.elapsed_ms != null ? ` · ${data.elapsed_ms} ms` : ""
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
              sandbox Z-spread what-ifs. No invented numbers.
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
              {t.model ? <span className="ask-sub">{t.model}</span> : null}
              {t.elapsed != null ? (
                <span className="ask-sub">{t.elapsed} ms</span>
              ) : null}
              {t.intent ? <span className="ask-sub">{t.intent}</span> : null}
            </div>
            <div className="ask-bubble-text">{t.text}</div>
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
