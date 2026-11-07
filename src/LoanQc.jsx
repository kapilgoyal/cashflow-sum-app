import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import {
  DataGrid,
  StatusBanner,
  fmtInt,
  fmtPct,
  fmtWac,
  intCol,
  moneyCol,
} from "./cashflowGrid";
import { apiUrl } from "./apiBase";
import { cohortLabel } from "./cohortLabels";

function qcStatusTone(outcomeOrLabel) {
  const v = String(outcomeOrLabel || "").toLowerCase();
  if (v === "pass") return "pass";
  if (v === "fail") return "fail";
  if (v === "warn" || v === "warning" || v === "skipped" || v === "skip") {
    return "warn";
  }
  return "";
}

function qcStatusLabel(outcome) {
  const tone = qcStatusTone(outcome);
  if (tone === "pass") return "Pass";
  if (tone === "fail") return "Fail";
  if (tone === "warn") return "Warn";
  return "";
}

/** Green / red / orange circle + Pass/Fail/Warn label. */
function QcStatusCell({ value, data }) {
  const tone = qcStatusTone(data?.outcome || value);
  const label = value || qcStatusLabel(data?.outcome) || "—";
  if (!tone) {
    return <span className="qc-status-cell">{label}</span>;
  }
  return (
    <span className={`qc-status-cell qc-status-${tone}`}>
      <span className="qc-status-dot" aria-hidden="true" />
      <span className="qc-status-text">{label}</span>
    </span>
  );
}

/**
 * Loan QC pane: NQM results + English custom rules (Groq → SQL → SQLite).
 */
export default function LoanQc({ onDrillLoan }) {
  const [qcRows, setQcRows] = useState([]);
  const [qcLoading, setQcLoading] = useState(false);
  const [qcError, setQcError] = useState(null);
  const [qcView, setQcView] = useState("grid");
  const [qcSelectedRule, setQcSelectedRule] = useState(null);
  const [qcDrillLoans, setQcDrillLoans] = useState([]);
  const [qcDrillTotal, setQcDrillTotal] = useState(0);
  const [qcDrillVisible, setQcDrillVisible] = useState(null);
  const [qcDrillLoading, setQcDrillLoading] = useState(false);
  const [qcDrillError, setQcDrillError] = useState(null);

  const [english, setEnglish] = useState("");
  const [predicate, setPredicate] = useState("");
  const [editCheckId, setEditCheckId] = useState(null);
  const [translateMeta, setTranslateMeta] = useState(null);
  const [composerBusy, setComposerBusy] = useState(false);
  const [composerMsg, setComposerMsg] = useState(null);
  const [composerErr, setComposerErr] = useState(null);
  const [groqConfigured, setGroqConfigured] = useState(null);
  const [runBusy, setRunBusy] = useState(false);

  const applyResultsPayload = useCallback((data) => {
    setQcRows(Array.isArray(data.results) ? data.results : []);
    if (typeof data.groq_configured === "boolean") {
      setGroqConfigured(data.groq_configured);
    }
  }, []);

  const refreshResults = useCallback(async () => {
    setQcLoading(true);
    setQcError(null);
    try {
      const res = await fetch(apiUrl("/api/qc/results"));
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`HTTP ${res.status}: ${detail}`);
      }
      const data = await res.json();
      applyResultsPayload(data);
    } catch (err) {
      setQcError(err.message || String(err));
      setQcRows([]);
    } finally {
      setQcLoading(false);
    }
  }, [applyResultsPayload]);

  useEffect(() => {
    refreshResults();
  }, [refreshResults]);

  const qcActiveRows = useMemo(() => {
    const rows = (qcRows || [])
      .filter((r) => r && r.source !== "demo")
      // Pass/Fail only — drop Warning/skipped rules from the grid
      .filter((r) => {
        const o = String(r.outcome || "").toLowerCase();
        return o === "pass" || o === "fail";
      })
      .map((r) => {
        const raw =
          r.scope || (r.source === "custom" ? "Custom" : "Standard");
        const scope =
          raw === "Global" || raw === "global" ? "Standard" : raw;
        return {
          ...r,
          scope,
          status_label: qcStatusLabel(r.outcome),
        };
      });
    // Custom rules first, then Standard
    return [...rows].sort((a, b) => {
      const as = a.scope === "Custom" ? 0 : 1;
      const bs = b.scope === "Custom" ? 0 : 1;
      if (as !== bs) return as - bs;
      return String(a.nl_description || "").localeCompare(
        String(b.nl_description || "")
      );
    });
  }, [qcRows]);

  const qcSummary = useMemo(() => {
    const pass = qcActiveRows.filter((r) => r.outcome === "pass").length;
    const failRules = qcActiveRows.filter((r) => r.outcome === "fail").length;
    const checks = qcActiveRows.length;
    const failedLoans = qcActiveRows.reduce(
      (s, r) => s + (Number(r.fail_count) || 0),
      0
    );
    return {
      pass,
      fail: failRules,
      checks,
      failedLoans,
      total: checks,
    };
  }, [qcActiveRows]);

  const qcFilteredRows = qcActiveRows;

  const qcChartData = useMemo(
    () => [
      { name: "Pass", value: qcSummary.pass, fill: "#1F8A44" },
      { name: "Fail", value: qcSummary.fail, fill: "#C62828" },
    ],
    [qcSummary.pass, qcSummary.fail]
  );

  const qcColumnDefs = useMemo(
    () => [
      {
        field: "scope",
        headerName: "Scope",
        width: 100,
        suppressSizeToFit: true,
        cellClass: (p) =>
          p.value === "Custom" ? "qc-scope-custom" : "qc-scope-standard",
      },
      {
        field: "nl_description",
        headerName: "Description",
        flex: 3,
        minWidth: 280,
      },
      {
        field: "status_label",
        headerName: "Status",
        width: 110,
        suppressSizeToFit: true,
        cellRenderer: QcStatusCell,
        cellClass: "qc-status-col",
      },
      {
        field: "pass_count",
        headerName: "Passed Loans",
        width: 140,
        suppressSizeToFit: true,
        type: "numericColumn",
        filter: "agNumberColumnFilter",
        cellClass: "cf-num",
      },
      {
        field: "fail_count",
        headerName: "Failed Loans",
        width: 140,
        suppressSizeToFit: true,
        type: "numericColumn",
        filter: "agNumberColumnFilter",
        cellClass: "cf-num",
      },
    ],
    []
  );

  const qcDrillColumnDefs = useMemo(
    () => [
      {
        field: "loan_id",
        headerName: "Loan ID",
        width: 100,
        pinned: "left",
        lockPinned: true,
        cellClass: "cf-id",
      },
      moneyCol("current_loan_amount", "UPB", 110),
      {
        field: "current_interest_rate",
        headerName: "Interest Rate",
        width: 96,
        valueFormatter: (p) => fmtWac(p.value),
        cellClass: "cf-num",
      },
      intCol("original_fico", "FICO", 72),
      {
        field: "original_ltv",
        headerName: "LTV",
        width: 72,
        valueFormatter: (p) => fmtPct(p.value, 1),
        cellClass: "cf-num",
      },
      {
        field: "original_cltv",
        headerName: "CLTV",
        width: 72,
        valueFormatter: (p) => fmtPct(p.value, 1),
        cellClass: "cf-num",
      },
      { field: "state", headerName: "State", width: 64 },
      { field: "postal_code", headerName: "Postal Code", width: 96 },
      {
        field: "documentation_type",
        headerName: "Documentation Type",
        flex: 1.2,
        minWidth: 140,
      },
      { field: "property_type", headerName: "Property Type", width: 110 },
      { field: "occupancy", headerName: "Occupancy", width: 100 },
      { field: "loan_purpose", headerName: "Loan Purpose", width: 110 },
      {
        field: "cohort",
        headerName: "Cohort",
        flex: 1.2,
        minWidth: 140,
        valueFormatter: (p) => cohortLabel(p.value),
      },
    ],
    []
  );

  const loadQcDrillLoans = useCallback(async (rule) => {
    if (!rule?.check_id) {
      setQcSelectedRule(null);
      setQcDrillLoans([]);
      setQcDrillTotal(0);
      setQcDrillError(null);
      return;
    }
    setQcSelectedRule(rule);
    setQcDrillLoading(true);
    setQcDrillError(null);
    setQcDrillVisible(null);
    try {
      const res = await fetch(
        apiUrl(
          `/api/qc/results/${encodeURIComponent(rule.check_id)}/loans?failing_only=true&limit=2000`
        )
      );
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`HTTP ${res.status}: ${detail}`);
      }
      const data = await res.json();
      setQcDrillLoans(Array.isArray(data.loans) ? data.loans : []);
      setQcDrillTotal(data.total ?? (data.loans || []).length);
    } catch (err) {
      setQcDrillError(err.message || String(err));
      setQcDrillLoans([]);
      setQcDrillTotal(0);
    } finally {
      setQcDrillLoading(false);
    }
  }, []);

  const onQcRuleDrill = useCallback(
    (row) => {
      if (!row?.check_id) return;
      loadQcDrillLoans(row);
      if (row.source === "custom") {
        setEditCheckId(row.check_id);
        setEnglish(row.nl_description || "");
        setPredicate(row.sql_predicate || "");
        setTranslateMeta(null);
        setComposerMsg(null);
        setComposerErr(null);
      }
    },
    [loadQcDrillLoans]
  );

  const onQcDrillRowStats = useCallback((stats) => {
    if (stats?.visible != null) setQcDrillVisible(stats.visible);
  }, []);

  const qcDrillToolbarStart = useMemo(() => {
    if (!qcSelectedRule) return null;
    const total = qcDrillTotal || qcDrillLoans.length || 0;
    const shown =
      qcDrillVisible != null
        ? qcDrillVisible
        : qcDrillLoading
          ? null
          : qcDrillLoans.length;
    return (
      <p className="asf-grid-summary" aria-live="polite">
        <span className="asf-grid-summary-total">
          {qcSelectedRule.nl_description || "Failed Loans"}
          {" · "}
          {fmtInt(total)} {total === 1 ? "Loan" : "Loans"}
        </span>
        {shown != null ? (
          <span
            className={
              shown !== total
                ? "asf-grid-summary-filter is-filtered"
                : "asf-grid-summary-filter"
            }
          >
            {" · "}
            {fmtInt(shown)} Shown
          </span>
        ) : null}
      </p>
    );
  }, [
    qcSelectedRule,
    qcDrillTotal,
    qcDrillLoans.length,
    qcDrillVisible,
    qcDrillLoading,
  ]);

  const resetComposer = useCallback(() => {
    setEnglish("");
    setPredicate("");
    setEditCheckId(null);
    setTranslateMeta(null);
    setComposerMsg(null);
    setComposerErr(null);
  }, []);

  const onTranslate = useCallback(async () => {
    if (!english.trim()) {
      setComposerErr("Enter an English check first.");
      return;
    }
    setComposerBusy(true);
    setComposerErr(null);
    setComposerMsg(null);
    try {
      const res = await fetch(apiUrl("/api/qc/translate"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ english: english.trim() }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || `HTTP ${res.status}`);
      }
      setPredicate(data.sql_predicate || "");
      setTranslateMeta({
        mode: data.mode,
        model: data.model,
        warning: data.warning,
      });
      if (typeof data.mode === "string" && data.mode === "mock") {
        setGroqConfigured(false);
      } else if (data.mode === "groq") {
        setGroqConfigured(true);
      }
      setComposerMsg(
        data.warning
          ? data.warning
          : data.mode === "groq"
            ? `Translated with ${data.model || "Groq"}`
            : "Translated"
      );
    } catch (err) {
      setComposerErr(err.message || String(err));
    } finally {
      setComposerBusy(false);
    }
  }, [english]);

  const onSave = useCallback(async () => {
    if (!english.trim()) {
      setComposerErr("Enter an English check first.");
      return false;
    }
    setComposerBusy(true);
    setComposerErr(null);
    setComposerMsg(null);
    try {
      const payload = {
        english: english.trim(),
        sql_predicate: predicate.trim() || null,
        check_id: editCheckId || null,
      };
      const url = editCheckId
        ? apiUrl(`/api/qc/checks/${encodeURIComponent(editCheckId)}`)
        : apiUrl("/api/qc/checks");
      const res = await fetch(url, {
        method: editCheckId ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          editCheckId
            ? {
                english: payload.english,
                sql_predicate: payload.sql_predicate,
              }
            : payload
        ),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : data.detail
              ? JSON.stringify(data.detail)
              : `HTTP ${res.status}`
        );
      }
      const check = data.check || {};
      setEditCheckId(check.check_id || editCheckId);
      if (check.sql_predicate) setPredicate(check.sql_predicate);
      if (typeof data.groq_configured === "boolean") {
        setGroqConfigured(data.groq_configured);
      }
      setTranslateMeta({
        mode: data.mode,
        model: data.model,
        warning: data.warning,
      });
      setComposerMsg(
        data.warning
          ? `Saved. ${data.warning}`
          : editCheckId
            ? "Custom Rule Updated"
            : "Custom Rule Saved"
      );
      return true;
    } catch (err) {
      setComposerErr(err.message || String(err));
      return false;
    } finally {
      setComposerBusy(false);
    }
  }, [english, predicate, editCheckId]);

  const onDelete = useCallback(async () => {
    if (!editCheckId) return;
    const deletingId = editCheckId;
    setComposerBusy(true);
    setComposerErr(null);
    try {
      const res = await fetch(
        apiUrl(`/api/qc/checks/${encodeURIComponent(deletingId)}`),
        { method: "DELETE" }
      );
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || `HTTP ${res.status}`);
      }
      resetComposer();
      setComposerMsg("Custom Rule Deleted");
      if (qcSelectedRule?.check_id === deletingId) {
        setQcSelectedRule(null);
        setQcDrillLoans([]);
      }
      await refreshResults();
    } catch (err) {
      setComposerErr(err.message || String(err));
    } finally {
      setComposerBusy(false);
    }
  }, [editCheckId, qcSelectedRule, refreshResults, resetComposer]);

  const onRunAnalysis = useCallback(async () => {
    setRunBusy(true);
    setComposerErr(null);
    try {
      const res = await fetch(apiUrl("/api/qc/run"), { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || `HTTP ${res.status}`);
      }
      applyResultsPayload(data);
      setComposerMsg("Analysis Complete");
      if (qcSelectedRule?.check_id) {
        const refreshed = (data.results || []).find(
          (r) => r.check_id === qcSelectedRule.check_id
        );
        if (refreshed) await loadQcDrillLoans(refreshed);
      }
      return true;
    } catch (err) {
      setComposerErr(err.message || String(err));
      return false;
    } finally {
      setRunBusy(false);
    }
  }, [applyResultsPayload, loadQcDrillLoans, qcSelectedRule]);

  const onSaveAndRun = useCallback(async () => {
    const saved = await onSave();
    if (saved) await onRunAnalysis();
  }, [onSave, onRunAnalysis]);

  return (
    <section className="section section-fill section-qc">
      <div className="qc-toolbar">
        <div
          className="cf-grid-toolbar-actions qc-view-toggle"
          role="toolbar"
          aria-label="QC View"
        >
          <button
            type="button"
            className={`linkish${qcView === "grid" ? " is-active" : ""}`}
            onClick={() => setQcView("grid")}
          >
            Grid
          </button>
          <button
            type="button"
            className={`linkish${qcView === "chart" ? " is-active" : ""}`}
            onClick={() => setQcView("chart")}
          >
            Chart
          </button>
        </div>
        <div className="qc-kpi-strip" role="status" aria-label="QC Summary">
          <div className="qc-kpi qc-kpi-checks">
            <span className="qc-kpi-label">QC Checks</span>
            <span className="qc-kpi-value">{fmtInt(qcSummary.checks)}</span>
          </div>
          <div className="qc-kpi qc-kpi-fail">
            <span className="qc-kpi-label">Total Failed</span>
            <span className="qc-kpi-value">
              {fmtInt(qcSummary.failedLoans)}
            </span>
          </div>
        </div>
      </div>

      <div className="qc-composer">
        <div className="qc-composer-head">
          <span className="qc-composer-title">
            {editCheckId ? "Edit Custom Rule" : "New Custom Rule"}
          </span>
          {groqConfigured === false ? (
            <span className="qc-composer-badge">Mock Translate</span>
          ) : groqConfigured === true ? (
            <span className="qc-composer-badge is-live">Groq Live</span>
          ) : null}
        </div>
        <label className="qc-composer-label" htmlFor="qc-english">
          English Check
        </label>
        <textarea
          id="qc-english"
          className="qc-composer-input"
          rows={2}
          placeholder="Example: Flag Loans With FICO Below 620"
          value={english}
          onChange={(e) => setEnglish(e.target.value)}
          disabled={composerBusy || runBusy}
        />
        <label className="qc-composer-label" htmlFor="qc-predicate">
          Runnable Rule
        </label>
        <textarea
          id="qc-predicate"
          className="qc-composer-input qc-composer-predicate"
          rows={2}
          placeholder="Translate To Preview The Rule"
          value={predicate}
          onChange={(e) => setPredicate(e.target.value)}
          disabled={composerBusy || runBusy}
          spellCheck={false}
        />
        <div className="qc-composer-actions">
          <button
            type="button"
            className="cf-btn"
            onClick={onTranslate}
            disabled={composerBusy || runBusy || !english.trim()}
          >
            Translate
          </button>
          <button
            type="button"
            className="cf-btn"
            onClick={onSave}
            disabled={composerBusy || runBusy || !english.trim()}
          >
            {editCheckId ? "Update" : "Save"}
          </button>
          <button
            type="button"
            className="cf-btn"
            onClick={onSaveAndRun}
            disabled={composerBusy || runBusy || !english.trim()}
          >
            Save &amp; Run
          </button>
          <button
            type="button"
            className="cf-btn"
            onClick={onRunAnalysis}
            disabled={composerBusy || runBusy}
          >
            {runBusy ? "Running…" : "Run Analysis"}
          </button>
          {editCheckId ? (
            <>
              <button
                type="button"
                className="cf-btn cf-btn-muted"
                onClick={onDelete}
                disabled={composerBusy || runBusy}
              >
                Delete
              </button>
              <button
                type="button"
                className="linkish"
                onClick={resetComposer}
                disabled={composerBusy || runBusy}
              >
                New Rule
              </button>
            </>
          ) : null}
        </div>
        {composerErr ? (
          <StatusBanner tone="error">{composerErr}</StatusBanner>
        ) : null}
        {composerMsg ? (
          <p className="qc-composer-note muted" role="status">
            {composerMsg}
            {translateMeta?.mode === "mock" && !composerMsg.includes("mock")
              ? " · Mock Mode"
              : null}
          </p>
        ) : null}
      </div>

      {qcLoading ? (
        <p className="muted">Loading Loan QC…</p>
      ) : qcError ? (
        <StatusBanner tone="error">Loan QC: {qcError}</StatusBanner>
      ) : !qcActiveRows.length ? (
        <p className="muted">
          No QC Results Yet. Save A Custom Rule Or Run Analysis Against The
          Tape.
        </p>
      ) : qcView === "chart" ? (
        <div className="qc-chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={qcChartData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={48}
                outerRadius={80}
                paddingAngle={2}
              >
                {qcChartData.map((entry) => (
                  <Cell key={entry.name} fill={entry.fill} />
                ))}
              </Pie>
              <Tooltip />
              <Legend verticalAlign="bottom" height={28} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <DataGrid
          rowData={qcFilteredRows}
          columnDefs={qcColumnDefs}
          getRowId={(p) => String(p.data.check_id)}
          onRowDrill={onQcRuleDrill}
          heightClass={
            qcSelectedRule ? "grid-wrap-qc-rules" : "grid-wrap-fill"
          }
          exportName="loan-qc"
        />
      )}

      {qcSelectedRule && qcView === "grid" && (
        <div className="qc-drill">
          {qcDrillLoading ? (
            <p className="muted">Loading Failed Loans…</p>
          ) : qcDrillError ? (
            <StatusBanner tone="error">
              Failed Loans: {qcDrillError}
            </StatusBanner>
          ) : (
            <DataGrid
              rowData={qcDrillLoans}
              columnDefs={qcDrillColumnDefs}
              getRowId={(p) => String(p.data.loan_id)}
              onRowDrill={onDrillLoan}
              onRowStats={onQcDrillRowStats}
              toolbarStart={qcDrillToolbarStart}
              heightClass="grid-wrap-qc-drill"
              exportName="qc-failed-loans"
            />
          )}
        </div>
      )}
    </section>
  );
}
