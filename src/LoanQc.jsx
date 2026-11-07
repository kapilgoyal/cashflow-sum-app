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

/**
 * Loan QC: Global NQM rules + draft English rules (translate → test → confirm).
 */
export default function LoanQc({ onDrillLoan }) {
  const [qcRows, setQcRows] = useState([]);
  const [qcLoading, setQcLoading] = useState(false);
  const [qcError, setQcError] = useState(null);
  const [qcStatusFilter, setQcStatusFilter] = useState("all");
  const [qcView, setQcView] = useState("grid");
  const [qcSelectedRule, setQcSelectedRule] = useState(null);
  const [qcDrillLoans, setQcDrillLoans] = useState([]);
  const [qcDrillTotal, setQcDrillTotal] = useState(0);
  const [qcDrillVisible, setQcDrillVisible] = useState(null);
  const [qcDrillLoading, setQcDrillLoading] = useState(false);
  const [qcDrillError, setQcDrillError] = useState(null);
  const [drillMode, setDrillMode] = useState("saved"); // saved | draft
  const [drillFailingOnly, setDrillFailingOnly] = useState(true);

  const [english, setEnglish] = useState("");
  const [predicate, setPredicate] = useState("");
  const [editCheckId, setEditCheckId] = useState(null);
  const [tested, setTested] = useState(false);
  const [draftStats, setDraftStats] = useState(null);
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
      .filter((r) => r.outcome === "pass" || r.outcome === "fail")
      .map((r) => ({
        ...r,
        scope: r.scope || (r.source === "custom" ? "Custom" : "Global"),
        status_label:
          r.outcome === "pass" ? "Pass" : r.outcome === "fail" ? "Fail" : "",
      }));
    // Custom (user) rules first, then Global
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
    const fail = qcActiveRows.filter((r) => r.outcome === "fail").length;
    const total = pass + fail;
    return { pass, fail, total };
  }, [qcActiveRows]);

  const qcFilteredRows = useMemo(() => {
    if (qcStatusFilter === "pass") {
      return qcActiveRows.filter((r) => r.outcome === "pass");
    }
    if (qcStatusFilter === "fail") {
      return qcActiveRows.filter((r) => r.outcome === "fail");
    }
    if (qcStatusFilter === "custom") {
      return qcActiveRows.filter((r) => r.scope === "Custom");
    }
    if (qcStatusFilter === "global") {
      return qcActiveRows.filter((r) => r.scope === "Global");
    }
    return qcActiveRows;
  }, [qcActiveRows, qcStatusFilter]);

  const qcChartData = useMemo(
    () => [
      { name: "Pass", value: qcSummary.pass, fill: "#1F8A44" },
      { name: "Fail", value: qcSummary.fail, fill: "#C62828" },
    ],
    [qcSummary.pass, qcSummary.fail]
  );

  const customCount = useMemo(
    () => qcActiveRows.filter((r) => r.scope === "Custom").length,
    [qcActiveRows]
  );
  const globalCount = useMemo(
    () => qcActiveRows.filter((r) => r.scope === "Global").length,
    [qcActiveRows]
  );

  const qcColumnDefs = useMemo(
    () => [
      {
        field: "scope",
        headerName: "Scope",
        flex: 0.7,
        minWidth: 100,
        cellClass: (p) =>
          p.value === "Custom" ? "qc-scope-custom" : "qc-scope-global",
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
        flex: 0.8,
        minWidth: 110,
        cellClass: (p) => {
          if (p.value === "Pass") return "qc-outcome-pass";
          if (p.value === "Fail") return "qc-outcome-fail";
          return "";
        },
      },
      {
        field: "pass_count",
        headerName: "Passed Loans",
        flex: 1.1,
        minWidth: 140,
        type: "numericColumn",
        filter: "agNumberColumnFilter",
        cellClass: "cf-num",
      },
      {
        field: "fail_count",
        headerName: "Failed Loans",
        flex: 1.1,
        minWidth: 140,
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

  const loadQcDrillLoans = useCallback(
    async (rule, failingOnly = true) => {
      if (!rule?.check_id) {
        setQcSelectedRule(null);
        setQcDrillLoans([]);
        setQcDrillTotal(0);
        setQcDrillError(null);
        return;
      }
      setDrillMode("saved");
      setDrillFailingOnly(failingOnly);
      setQcSelectedRule(rule);
      setQcDrillLoading(true);
      setQcDrillError(null);
      setQcDrillVisible(null);
      try {
        const res = await fetch(
          apiUrl(
            `/api/qc/results/${encodeURIComponent(rule.check_id)}/loans?failing_only=${failingOnly}&limit=2000`
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
    },
    []
  );

  const onQcRuleDrill = useCallback(
    (row) => {
      if (!row?.check_id) return;
      loadQcDrillLoans(row, true);
      if (row.source === "custom" || row.scope === "Custom") {
        setEditCheckId(row.check_id);
        setEnglish(row.nl_description || "");
        setPredicate(row.sql_predicate || "");
        setTested(true);
        setDraftStats({
          pass_count: row.pass_count,
          fail_count: row.fail_count,
          outcome: row.outcome,
          status_label: row.status_label,
        });
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
    const title =
      drillMode === "draft"
        ? english.trim() || "Draft Rule"
        : qcSelectedRule?.nl_description || "Loans";
    if (!title && !qcDrillLoans.length) return null;
    const total = qcDrillTotal || qcDrillLoans.length || 0;
    const shown =
      qcDrillVisible != null
        ? qcDrillVisible
        : qcDrillLoading
          ? null
          : qcDrillLoans.length;
    const side = drillFailingOnly ? "Failed" : "Passed";
    return (
      <p className="asf-grid-summary" aria-live="polite">
        <span className="asf-grid-summary-total">
          {title}
          {" · "}
          {side}
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
    drillMode,
    english,
    qcSelectedRule,
    qcDrillTotal,
    qcDrillLoans.length,
    qcDrillVisible,
    qcDrillLoading,
    drillFailingOnly,
  ]);

  const resetComposer = useCallback(() => {
    setEnglish("");
    setPredicate("");
    setEditCheckId(null);
    setTested(false);
    setDraftStats(null);
    setComposerMsg(null);
    setComposerErr(null);
    if (drillMode === "draft") {
      setQcDrillLoans([]);
      setQcDrillTotal(0);
      setDrillMode("saved");
    }
  }, [drillMode]);

  const detailText = (data) => {
    if (typeof data?.detail === "string") return data.detail;
    if (data?.detail) return JSON.stringify(data.detail);
    return null;
  };

  const onTranslate = useCallback(async () => {
    if (!english.trim()) {
      setComposerErr("Enter an English check first.");
      return;
    }
    setComposerBusy(true);
    setComposerErr(null);
    setComposerMsg(null);
    setTested(false);
    setDraftStats(null);
    try {
      const res = await fetch(apiUrl("/api/qc/translate"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ english: english.trim() }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(detailText(data) || `HTTP ${res.status}`);
      }
      setPredicate(data.sql_predicate || "");
      if (data.mode === "mock") setGroqConfigured(false);
      else if (data.mode === "groq") setGroqConfigured(true);
      setComposerMsg(
        data.warning ||
          (data.mode === "groq"
            ? `Translated · ${data.model || "Groq"}`
            : "Translated")
      );
    } catch (err) {
      setComposerErr(err.message || String(err));
    } finally {
      setComposerBusy(false);
    }
  }, [english]);

  const onTest = useCallback(
    async (failingOnly = true) => {
      if (!english.trim()) {
        setComposerErr("Enter an English check first.");
        return false;
      }
      setComposerBusy(true);
      setComposerErr(null);
      setComposerMsg(null);
      setQcView("grid");
      try {
        const res = await fetch(apiUrl("/api/qc/preview"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            english: english.trim(),
            sql_predicate: predicate.trim() || null,
            failing_only: failingOnly,
            limit: 2000,
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(detailText(data) || `HTTP ${res.status}`);
        }
        if (data.sql_predicate) setPredicate(data.sql_predicate);
        if (typeof data.groq_configured === "boolean") {
          setGroqConfigured(data.groq_configured);
        }
        setTested(true);
        setDraftStats({
          pass_count: data.pass_count,
          fail_count: data.fail_count,
          outcome: data.outcome,
          status_label: data.status_label,
          tape_row_count: data.tape_row_count,
        });
        setDrillMode("draft");
        setDrillFailingOnly(failingOnly);
        setQcSelectedRule({
          check_id: editCheckId || "draft",
          nl_description: english.trim(),
          sql_predicate: data.sql_predicate,
          source: "custom",
          scope: "Custom",
        });
        setQcDrillLoans(Array.isArray(data.loans) ? data.loans : []);
        setQcDrillTotal(data.total ?? (data.loans || []).length);
        setQcDrillError(null);
        const warn = data.warning ? ` · ${data.warning}` : "";
        setComposerMsg(
          `Tested · ${fmtInt(data.pass_count)} Passed · ${fmtInt(data.fail_count)} Failed${warn}`
        );
        return true;
      } catch (err) {
        setComposerErr(err.message || String(err));
        setTested(false);
        return false;
      } finally {
        setComposerBusy(false);
      }
    },
    [english, predicate, editCheckId]
  );

  const onConfirmSave = useCallback(async () => {
    if (!english.trim()) {
      setComposerErr("Enter an English check first.");
      return false;
    }
    if (!tested || !predicate.trim()) {
      setComposerErr("Test the rule before confirming.");
      return false;
    }
    setComposerBusy(true);
    setComposerErr(null);
    try {
      const url = editCheckId
        ? apiUrl(`/api/qc/checks/${encodeURIComponent(editCheckId)}`)
        : apiUrl("/api/qc/checks");
      const res = await fetch(url, {
        method: editCheckId ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          editCheckId
            ? {
                english: english.trim(),
                sql_predicate: predicate.trim(),
              }
            : {
                english: english.trim(),
                sql_predicate: predicate.trim(),
                check_id: null,
              }
        ),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(detailText(data) || `HTTP ${res.status}`);
      }
      const check = data.check || {};
      setEditCheckId(check.check_id || editCheckId);
      if (check.sql_predicate) setPredicate(check.sql_predicate);

      const runRes = await fetch(apiUrl("/api/qc/run"), { method: "POST" });
      const runData = await runRes.json().catch(() => ({}));
      if (!runRes.ok) {
        throw new Error(detailText(runData) || `HTTP ${runRes.status}`);
      }
      applyResultsPayload(runData);
      setComposerMsg("Confirmed · Saved And Run");
      const refreshed = (runData.results || []).find(
        (r) => r.check_id === (check.check_id || editCheckId)
      );
      if (refreshed) await loadQcDrillLoans(refreshed, true);
      return true;
    } catch (err) {
      setComposerErr(err.message || String(err));
      return false;
    } finally {
      setComposerBusy(false);
    }
  }, [
    english,
    tested,
    predicate,
    editCheckId,
    applyResultsPayload,
    loadQcDrillLoans,
  ]);

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
        throw new Error(detailText(data) || `HTTP ${res.status}`);
      }
      resetComposer();
      setComposerMsg("Deleted");
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
        throw new Error(detailText(data) || `HTTP ${res.status}`);
      }
      applyResultsPayload(data);
      setComposerMsg("Analysis Complete");
      if (qcSelectedRule?.check_id && drillMode === "saved") {
        const refreshed = (data.results || []).find(
          (r) => r.check_id === qcSelectedRule.check_id
        );
        if (refreshed) await loadQcDrillLoans(refreshed, drillFailingOnly);
      }
      return true;
    } catch (err) {
      setComposerErr(err.message || String(err));
      return false;
    } finally {
      setRunBusy(false);
    }
  }, [
    applyResultsPayload,
    loadQcDrillLoans,
    qcSelectedRule,
    drillMode,
    drillFailingOnly,
  ]);

  const showDrill =
    qcView === "grid" &&
    (drillMode === "draft" || !!qcSelectedRule) &&
    (qcDrillLoading ||
      !!qcDrillError ||
      qcDrillLoans.length > 0 ||
      !!draftStats);

  return (
    <section className="section section-fill section-qc">
      <div className="qc-toolbar">
        <div className="qc-kpi-strip" role="toolbar" aria-label="QC Filters">
          <button
            type="button"
            className={`qc-kpi${qcStatusFilter === "all" ? " is-active" : ""}`}
            onClick={() => setQcStatusFilter("all")}
          >
            <span className="qc-kpi-label">Total Rules</span>
            <span className="qc-kpi-value">{qcSummary.total}</span>
          </button>
          <button
            type="button"
            className={`qc-kpi${qcStatusFilter === "custom" ? " is-active" : ""}`}
            onClick={() => setQcStatusFilter("custom")}
          >
            <span className="qc-kpi-label">Custom</span>
            <span className="qc-kpi-value">{customCount}</span>
          </button>
          <button
            type="button"
            className={`qc-kpi${qcStatusFilter === "global" ? " is-active" : ""}`}
            onClick={() => setQcStatusFilter("global")}
          >
            <span className="qc-kpi-label">Global</span>
            <span className="qc-kpi-value">{globalCount}</span>
          </button>
          <button
            type="button"
            className={`qc-kpi qc-kpi-pass${qcStatusFilter === "pass" ? " is-active" : ""}`}
            onClick={() => setQcStatusFilter("pass")}
          >
            <span className="qc-kpi-label">Passed</span>
            <span className="qc-kpi-value">{qcSummary.pass}</span>
          </button>
          <button
            type="button"
            className={`qc-kpi qc-kpi-fail${qcStatusFilter === "fail" ? " is-active" : ""}`}
            onClick={() => setQcStatusFilter("fail")}
          >
            <span className="qc-kpi-label">Failed</span>
            <span className="qc-kpi-value">{qcSummary.fail}</span>
          </button>
        </div>
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
      </div>

      <div className="qc-composer">
        <div className="qc-composer-head">
          <h2 className="qc-composer-title">
            {editCheckId ? "Edit Custom Rule" : "New Custom Rule"}
          </h2>
          {groqConfigured === false ? (
            <span className="qc-composer-badge">Mock</span>
          ) : groqConfigured === true ? (
            <span className="qc-composer-badge is-live">Groq</span>
          ) : null}
        </div>
        <textarea
          id="qc-english"
          className="qc-composer-input"
          rows={2}
          placeholder="English Check — Example: Flag Loans With FICO Below 620"
          value={english}
          onChange={(e) => {
            setEnglish(e.target.value);
            setTested(false);
          }}
          disabled={composerBusy || runBusy}
        />
        {(predicate || tested) && (
          <textarea
            id="qc-predicate"
            className="qc-composer-input qc-composer-predicate"
            rows={2}
            placeholder="Translated Rule"
            value={predicate}
            onChange={(e) => {
              setPredicate(e.target.value);
              setTested(false);
            }}
            disabled={composerBusy || runBusy}
            spellCheck={false}
          />
        )}
        {draftStats ? (
          <div className="qc-draft-stats" role="status">
            <button
              type="button"
              className={`qc-draft-chip${drillFailingOnly === false ? " is-active" : ""}`}
              onClick={() => onTest(false)}
              disabled={composerBusy || runBusy}
            >
              Passed {fmtInt(draftStats.pass_count)}
            </button>
            <button
              type="button"
              className={`qc-draft-chip is-fail${drillFailingOnly ? " is-active" : ""}`}
              onClick={() => onTest(true)}
              disabled={composerBusy || runBusy}
            >
              Failed {fmtInt(draftStats.fail_count)}
            </button>
            <span
              className={
                draftStats.outcome === "pass"
                  ? "qc-outcome-pass"
                  : "qc-outcome-fail"
              }
            >
              {draftStats.status_label || ""}
            </span>
          </div>
        ) : null}
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
            onClick={() => onTest(true)}
            disabled={composerBusy || runBusy || !english.trim()}
          >
            Test
          </button>
          <button
            type="button"
            className="cf-btn"
            onClick={onConfirmSave}
            disabled={
              composerBusy || runBusy || !english.trim() || !tested || !predicate
            }
          >
            Confirm
          </button>
          <button
            type="button"
            className="cf-btn"
            onClick={onRunAnalysis}
            disabled={composerBusy || runBusy}
          >
            {runBusy ? "Running…" : "Run All"}
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
                New
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
          </p>
        ) : null}
      </div>

      {qcLoading ? (
        <p className="muted">Loading Loan QC…</p>
      ) : qcError ? (
        <StatusBanner tone="error">Loan QC: {qcError}</StatusBanner>
      ) : !qcActiveRows.length && drillMode !== "draft" ? (
        <p className="muted">
          Write An English Check, Test Against Loans, Then Confirm To Save.
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
          heightClass={showDrill ? "grid-wrap-qc-rules" : "grid-wrap-fill"}
          exportName="loan-qc"
        />
      )}

      {showDrill && (
        <div className="qc-drill">
          {qcDrillLoading ? (
            <p className="muted">Loading Loans…</p>
          ) : qcDrillError ? (
            <StatusBanner tone="error">{qcDrillError}</StatusBanner>
          ) : (
            <DataGrid
              rowData={qcDrillLoans}
              columnDefs={qcDrillColumnDefs}
              getRowId={(p) => String(p.data.loan_id)}
              onRowDrill={onDrillLoan}
              onRowStats={onQcDrillRowStats}
              toolbarStart={qcDrillToolbarStart}
              heightClass="grid-wrap-qc-drill"
              exportName="qc-loans"
            />
          )}
        </div>
      )}
    </section>
  );
}
