import { useCallback, useEffect, useMemo, useState } from "react";
import {
  DataGrid,
  PaneSpinner,
  StatusBanner,
  fmtInt,
  fmtPct,
  fmtWac,
  intCol,
  ltvCol,
  moneyCol,
  pushToast,
} from "./cashflowGrid";
import { apiUrl } from "./apiBase";
import { cohortLabel } from "./cohortLabels";

/**
 * Loan QC: Standard NQM rules + modal AI rules
 * (type English → Validate and Run → Pass/Fail → Save Rule).
 */
export default function LoanQc() {
  const [qcRows, setQcRows] = useState([]);
  const [qcLoading, setQcLoading] = useState(false);
  const [qcError, setQcError] = useState(null);
  const [qcSelectedRule, setQcSelectedRule] = useState(null);
  const [qcDrillLoans, setQcDrillLoans] = useState([]);
  const [qcDrillTotal, setQcDrillTotal] = useState(0);
  const [qcDrillVisible, setQcDrillVisible] = useState(null);
  const [qcDrillLoading, setQcDrillLoading] = useState(false);
  const [qcDrillError, setQcDrillError] = useState(null);
  const [drillMode, setDrillMode] = useState("saved"); // saved | draft
  const [drillFailingOnly, setDrillFailingOnly] = useState(true);

  const [composerOpen, setComposerOpen] = useState(false);
  const [english, setEnglish] = useState("");
  const [predicate, setPredicate] = useState("");
  const [editCheckId, setEditCheckId] = useState(null);
  const [tested, setTested] = useState(false);
  const [draftStats, setDraftStats] = useState(null);
  const [composerBusy, setComposerBusy] = useState(false);
  const [composerErr, setComposerErr] = useState(null);

  const applyResultsPayload = useCallback((data) => {
    setQcRows(Array.isArray(data.results) ? data.results : []);
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
      const msg = err.message || String(err);
      setQcError(msg);
      setQcRows([]);
      pushToast(`Loan QC: ${msg}`, "error");
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
        scope:
          r.scope === "Global"
            ? "Standard"
            : r.scope || (r.source === "custom" ? "Custom" : "Standard"),
        status_label:
          r.outcome === "pass" ? "Pass" : r.outcome === "fail" ? "Fail" : "",
      }));
    // Custom (user) rules first, then Standard
    return [...rows].sort((a, b) => {
      const as = a.scope === "Custom" ? 0 : 1;
      const bs = b.scope === "Custom" ? 0 : 1;
      if (as !== bs) return as - bs;
      return String(a.nl_description || "").localeCompare(
        String(b.nl_description || "")
      );
    });
  }, [qcRows]);

  const qcKpis = useMemo(() => {
    // Active rules only — skipped/warning rules are hidden for now.
    const rows = (qcRows || []).filter(
      (r) =>
        r &&
        r.source !== "demo" &&
        (r.outcome === "pass" || r.outcome === "fail")
    );
    const checks = rows.length;
    const rulesFailed = rows.filter(
      (r) => r.outcome === "fail" || (Number(r.fail_count) || 0) > 0
    ).length;
    const loansFailed = rows.reduce(
      (sum, r) => sum + (Number(r.fail_count) || 0),
      0
    );
    return { checks, rulesFailed, loansFailed };
  }, [qcRows]);

  const qcColumnDefs = useMemo(() => {
    // Fixed widths from full header label + filter/sort icons (do not shrink).
    const headerWidth = (label) =>
      Math.max(120, Math.ceil(String(label).length * 10 + 88));

    const scope = "Scope";
    const description = "Description";
    const status = "Status";
    const passed = "Passed Loans";
    const failed = "Failed Loans";
    const wScope = headerWidth(scope);
    const wStatus = headerWidth(status);
    const wPassed = headerWidth(passed);
    const wFailed = headerWidth(failed);

    return [
      {
        colId: "edit",
        headerName: "",
        width: 36,
        minWidth: 36,
        maxWidth: 36,
        flex: 0,
        pinned: "left",
        lockPinned: true,
        lockPosition: "left",
        sortable: false,
        filter: false,
        resizable: false,
        suppressMovable: true,
        suppressSizeToFit: true,
        cellClass: "qc-row-action-cell",
        cellStyle: {
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 0,
        },
        cellRenderer: (p) => {
          const row = p.data;
          if (!row?.check_id) return null;
          const isCustom =
            row.scope === "Custom" || row.source === "custom";
          // Standard: blank cell (Edit column still present for alignment).
          if (!isCustom) return null;
          return (
            <button
              type="button"
              className="qc-row-edit"
              title="Edit Rule"
              aria-label="Edit Rule"
              onClick={(e) => {
                e.stopPropagation();
                p.context?.onEditRule?.(row);
              }}
            >
              <svg
                width="12"
                height="12"
                viewBox="0 0 16 16"
                fill="none"
                aria-hidden="true"
                focusable="false"
              >
                <path
                  d="M3.5 12.5h9M4.2 9.8l6.2-6.2 1.8 1.8-6.2 6.2H4.2V9.8Z"
                  stroke="currentColor"
                  strokeWidth="1.3"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          );
        },
      },
      {
        colId: "delete",
        headerName: "",
        width: 36,
        minWidth: 36,
        maxWidth: 36,
        flex: 0,
        pinned: "left",
        lockPinned: true,
        lockPosition: "left",
        sortable: false,
        filter: false,
        resizable: false,
        suppressMovable: true,
        suppressSizeToFit: true,
        cellClass: "qc-row-action-cell",
        cellStyle: {
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 0,
        },
        cellRenderer: (p) => {
          const row = p.data;
          if (!row?.check_id) return null;
          return (
            <button
              type="button"
              className="qc-row-delete"
              title="Delete Rule"
              aria-label="Delete Rule"
              onClick={(e) => {
                e.stopPropagation();
                p.context?.onDeleteRule?.(row);
              }}
            >
              <svg
                width="12"
                height="12"
                viewBox="0 0 16 16"
                fill="none"
                aria-hidden="true"
                focusable="false"
              >
                <path
                  d="M3.5 4.5h9M6.5 4.5V3.2h3v1.3M5.2 4.5l.5 8.2h4.6l.5-8.2"
                  stroke="currentColor"
                  strokeWidth="1.3"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          );
        },
      },
      {
        field: "scope",
        headerName: scope,
        width: wScope,
        minWidth: wScope,
        maxWidth: wScope,
        flex: 0,
        suppressSizeToFit: true,
        cellClass: (p) =>
          p.value === "Custom" ? "qc-scope-custom" : "qc-scope-standard",
      },
      {
        field: "nl_description",
        headerName: description,
        flex: 1,
        minWidth: 240,
      },
      {
        field: "status_label",
        headerName: status,
        width: wStatus,
        minWidth: wStatus,
        maxWidth: wStatus,
        flex: 0,
        suppressSizeToFit: true,
        cellRenderer: (p) => {
          const label = p.value || "";
          const tone =
            label === "Pass" ? "pass" : label === "Fail" ? "fail" : "warn";
          if (!label) return null;
          return (
            <span className={`qc-status-cell qc-outcome-${tone}`}>
              <span className={`qc-status-dot is-${tone}`} aria-hidden="true" />
              {label}
            </span>
          );
        },
      },
      {
        field: "pass_count",
        headerName: passed,
        width: wPassed,
        minWidth: wPassed,
        maxWidth: wPassed,
        flex: 0,
        suppressSizeToFit: true,
        type: "numericColumn",
        filter: "agNumberColumnFilter",
        cellClass: "cf-num",
      },
      {
        field: "fail_count",
        headerName: failed,
        width: wFailed,
        minWidth: wFailed,
        maxWidth: wFailed,
        flex: 0,
        suppressSizeToFit: true,
        type: "numericColumn",
        filter: "agNumberColumnFilter",
        cellClass: "cf-num",
      },
    ];
  }, []);

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
      ltvCol("original_ltv", "LTV", 72),
      ltvCol("original_cltv", "CLTV", 72),
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
    async (rule, failingOnly = true, opts = {}) => {
      if (!rule?.check_id) {
        setQcSelectedRule(null);
        setQcDrillLoans([]);
        setQcDrillTotal(0);
        setQcDrillVisible(0);
        setQcDrillError(null);
        return;
      }
      if (opts.mode) setDrillMode(opts.mode);
      else setDrillMode("saved");
      setDrillFailingOnly(failingOnly);
      setQcSelectedRule(rule);
      setQcDrillLoading(true);
      setQcDrillError(null);
      // Clear immediately so a 0-row rule never shows the previous rule's loans.
      setQcDrillLoans([]);
      setQcDrillTotal(0);
      setQcDrillVisible(0);
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

  const openRuleComposer = useCallback(
    (row) => {
      if (!row?.check_id) return;
      const isCustom = row.source === "custom" || row.scope === "Custom";
      // Custom: PUT in place. Standard: open for edit/validate; Save creates a Custom copy.
      setEditCheckId(isCustom ? row.check_id : null);
      setEnglish(row.nl_description || "");
      setPredicate(row.sql_predicate || "");
      setTested(Boolean(row.sql_predicate));
      setDraftStats({
        pass_count: row.pass_count,
        fail_count: row.fail_count,
        outcome: row.outcome,
        status_label: row.status_label,
      });
      setComposerErr(null);
      setComposerOpen(true);
      void loadQcDrillLoans(row, true, { mode: "draft" });
    },
    [loadQcDrillLoans]
  );

  // Row click only selects/drills loan results — never opens the edit modal.
  const onQcRuleDrill = useCallback(
    (row) => {
      if (!row?.check_id) return;
      void loadQcDrillLoans(row, true);
    },
    [loadQcDrillLoans]
  );

  const onEditRule = useCallback(
    (row) => {
      openRuleComposer(row);
    },
    [openRuleComposer]
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

  const clearComposerFields = useCallback(() => {
    setEnglish("");
    setPredicate("");
    setEditCheckId(null);
    setTested(false);
    setDraftStats(null);
    setComposerErr(null);
  }, []);

  const resetComposer = useCallback(() => {
    clearComposerFields();
    if (drillMode === "draft") {
      setQcDrillLoans([]);
      setQcDrillTotal(0);
      setDrillMode("saved");
    }
  }, [clearComposerFields, drillMode]);

  const openNewComposer = useCallback(() => {
    clearComposerFields();
    setQcSelectedRule(null);
    setQcDrillLoans([]);
    setQcDrillTotal(0);
    setQcDrillError(null);
    setQcDrillVisible(null);
    setDrillMode("draft");
    setDrillFailingOnly(true);
    setComposerOpen(true);
  }, [clearComposerFields]);

  const closeComposer = useCallback(() => {
    if (composerBusy) return;
    resetComposer();
    setComposerOpen(false);
  }, [composerBusy, resetComposer]);

  useEffect(() => {
    if (!composerOpen) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") closeComposer();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [composerOpen, closeComposer]);

  const detailText = (data) => {
    if (typeof data?.detail === "string") return data.detail;
    if (data?.detail) return JSON.stringify(data.detail);
    return null;
  };

  const onRun = useCallback(
    async (failingOnly = true) => {
      if (!english.trim()) {
        setComposerErr("Enter an English check first.");
        return false;
      }
      setComposerBusy(true);
      setComposerErr(null);
      try {
        // Prefer fresh translate+test from English (one Run).
        // Reuse the generated predicate only on re-run without English changes
        // (predicate field is read-only; users edit English only).
        const res = await fetch(apiUrl("/api/qc/preview"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            english: english.trim(),
            sql_predicate: tested && predicate.trim() ? predicate.trim() : null,
            failing_only: failingOnly,
            limit: 2000,
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(detailText(data) || `HTTP ${res.status}`);
        }
        if (data.sql_predicate) setPredicate(data.sql_predicate);
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
        return true;
      } catch (err) {
        setComposerErr(err.message || String(err));
        setTested(false);
        return false;
      } finally {
        setComposerBusy(false);
      }
    },
    [english, predicate, tested, editCheckId]
  );

  const onConfirmSave = useCallback(async () => {
    if (!english.trim()) {
      setComposerErr("Enter an English check first.");
      return false;
    }
    if (!tested || !predicate.trim()) {
      setComposerErr("Validate and Run before saving.");
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
      const refreshed = (runData.results || []).find(
        (r) => r.check_id === (check.check_id || editCheckId)
      );
      if (refreshed) await loadQcDrillLoans(refreshed, true);
      clearComposerFields();
      setComposerOpen(false);
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
    clearComposerFields,
  ]);

  const onDeleteRule = useCallback(
    async (rule) => {
      const checkId = rule?.check_id || editCheckId;
      if (!checkId || checkId === "draft") return;
      const label = rule?.nl_description || english.trim() || "This Rule";
      if (!window.confirm(`Delete Rule?\n${label}`)) return;
      setComposerBusy(true);
      setComposerErr(null);
      setQcError(null);
      try {
        const res = await fetch(
          apiUrl(`/api/qc/checks/${encodeURIComponent(checkId)}`),
          { method: "DELETE" }
        );
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(detailText(data) || `HTTP ${res.status}`);
        }
        if (editCheckId === checkId || composerOpen) {
          resetComposer();
          setComposerOpen(false);
        }
        if (qcSelectedRule?.check_id === checkId) {
          setQcSelectedRule(null);
          setQcDrillLoans([]);
          setQcDrillTotal(0);
        }
        await refreshResults();
      } catch (err) {
        const msg = err.message || String(err);
        if (composerOpen) setComposerErr(msg);
        else setQcError(msg);
      } finally {
        setComposerBusy(false);
      }
    },
    [
      editCheckId,
      english,
      composerOpen,
      qcSelectedRule,
      refreshResults,
      resetComposer,
    ]
  );

  const qcGridContext = useMemo(
    () => ({ onDeleteRule, onEditRule }),
    [onDeleteRule, onEditRule]
  );

  // Keep drill shell mounted for a selected rule even when filter returns 0 rows
  // (empty AG Grid + headers), so we never hide the panel or leave stale loans.
  const showSavedDrill =
    !composerOpen && drillMode === "saved" && !!qcSelectedRule;

  // Always show Pass/Fail chips + AG Grid (headers / empty space) while the
  // composer is open — including before the first Validate and Run.
  const modalPassCount = draftStats?.pass_count ?? 0;
  const modalFailCount = draftStats?.fail_count ?? 0;
  const showModalResults = composerOpen;
  const showModalDrill = composerOpen;

  return (
    <section className="section section-fill section-qc">
      <div className="qc-toolbar">
        <div className="qc-toolbar-start">
          <button
            type="button"
            className="qc-new-rule-btn"
            onClick={openNewComposer}
            disabled={composerBusy}
            title="AI-Based"
          >
            <svg
              className="qc-new-rule-icon"
              width="12"
              height="12"
              viewBox="0 0 16 16"
              fill="none"
              aria-hidden="true"
              focusable="false"
            >
              <path
                d="M8 1.5 8.9 5.1 12.5 6 8.9 6.9 8 10.5 7.1 6.9 3.5 6 7.1 5.1Z"
                stroke="currentColor"
                strokeWidth="1.4"
                strokeLinejoin="miter"
              />
              <path
                d="M12.2 9.2 12.7 11.1 14.6 11.6 12.7 12.1 12.2 14 11.7 12.1 9.8 11.6 11.7 11.1Z"
                stroke="currentColor"
                strokeWidth="1.3"
                strokeLinejoin="miter"
              />
            </svg>
            <span>New AI Rule</span>
          </button>
        </div>
        <div className="qc-kpi-strip" aria-label="QC Summary">
          <div className="qc-kpi" aria-label="Total Rules" title="Total Rules">
            <span className="qc-kpi-label">Total Rules</span>
            <span className="qc-kpi-value">{fmtInt(qcKpis.checks)}</span>
          </div>
          <div
            className="qc-kpi"
            aria-label="Failed Rules"
            title="Failed Rules"
          >
            <span className="qc-kpi-label">Failed Rules</span>
            <span className="qc-kpi-value">{fmtInt(qcKpis.rulesFailed)}</span>
          </div>
          <div
            className="qc-kpi"
            aria-label="Loans Failed"
            title="Loans Failed"
          >
            <span className="qc-kpi-label">Loans Failed</span>
            <span className="qc-kpi-value">{fmtInt(qcKpis.loansFailed)}</span>
          </div>
        </div>
      </div>

      {qcLoading ? (
        <PaneSpinner label="Loading Loan QC…" />
      ) : !qcActiveRows.length ? (
        <p className="muted">
          Open New AI Rule, Validate and Run, Then Save Rule.
        </p>
      ) : (
        <DataGrid
          rowData={qcActiveRows}
          columnDefs={qcColumnDefs}
          getRowId={(p) => String(p.data.check_id)}
          onRowDrill={onQcRuleDrill}
          heightClass={
            showSavedDrill ? "grid-wrap-qc-rules" : "grid-wrap-fill"
          }
          exportName="loan-qc"
          showExportActions={false}
          gridProps={{ context: qcGridContext }}
        />
      )}

      {showSavedDrill && (
        <div
          className={`qc-drill${qcDrillLoading ? " is-loading" : ""}`}
          aria-busy={qcDrillLoading ? "true" : undefined}
        >
          {qcDrillError ? (
            <StatusBanner tone="error">{qcDrillError}</StatusBanner>
          ) : null}
          {qcDrillLoading && !qcDrillLoans.length ? (
            <PaneSpinner label="Loading QC Loans…" />
          ) : (
            <DataGrid
              rowData={qcDrillLoans}
              columnDefs={qcDrillColumnDefs}
              getRowId={(p) => String(p.data.loan_id)}
              onRowStats={onQcDrillRowStats}
              toolbarStart={qcDrillToolbarStart}
              heightClass="grid-wrap-qc-drill"
              exportName="qc-loans"
              showExportActions={false}
            />
          )}
        </div>
      )}

      {composerOpen ? (
        <div
          className="qc-modal-backdrop"
          role="presentation"
          onClick={closeComposer}
        >
          <div
            className="qc-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="qc-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="qc-composer-head qc-modal-head">
              <h2 id="qc-modal-title" className="qc-composer-title">
                {editCheckId || draftStats
                  ? "Edit AI Rule — English To QC Check"
                  : "New AI Rule — English To QC Check"}
              </h2>
              <button
                type="button"
                className="qc-modal-close"
                onClick={closeComposer}
                disabled={composerBusy}
                aria-label="Close"
                title="Close"
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 16 16"
                  fill="none"
                  aria-hidden="true"
                  focusable="false"
                >
                  <path
                    d="M4 4l8 8M12 4l-8 8"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="square"
                  />
                </svg>
              </button>
            </div>
            <div className="qc-field">
              <label className="qc-field-tag" htmlFor="qc-english">
                English Rule
              </label>
              <textarea
                id="qc-english"
                className="qc-composer-input"
                rows={2}
                placeholder="Type English — Example: Flag Loans With FICO Below 620"
                value={english}
                onChange={(e) => {
                  setEnglish(e.target.value);
                  setTested(false);
                  setPredicate("");
                  // Keep Pass/Fail chips + AG Grid shell after a prior Validate;
                  // clear rows so headers stay with "No Rows To Show" until re-run.
                  if (draftStats) {
                    setQcDrillLoans([]);
                    setQcDrillTotal(0);
                    setQcDrillVisible(0);
                    setQcDrillError(null);
                  }
                }}
                disabled={composerBusy}
                autoFocus
              />
            </div>
            <div className="qc-field">
              <label className="qc-field-tag" htmlFor="qc-predicate">
                SQL Predicate (read-only)
              </label>
              <textarea
                id="qc-predicate"
                className="qc-composer-input qc-composer-predicate"
                rows={2}
                placeholder="Translated QC Check"
                value={predicate}
                readOnly
                aria-readonly="true"
                tabIndex={0}
                disabled={composerBusy}
                spellCheck={false}
              />
            </div>
            <div className="qc-composer-actions">
              <button
                type="button"
                className="cf-btn"
                onClick={() => onRun(true)}
                disabled={composerBusy || !english.trim()}
              >
                {composerBusy && !tested ? "Running…" : "Validate and Run"}
              </button>
              <button
                type="button"
                className="cf-btn"
                onClick={onConfirmSave}
                disabled={
                  composerBusy || !english.trim() || !tested || !predicate
                }
              >
                Save Rule
              </button>
            </div>
            {composerErr ? (
              <StatusBanner tone="error">{composerErr}</StatusBanner>
            ) : null}

            {showModalResults ? (
              <div
                className="qc-results-panel"
                role="region"
                aria-label="Run Results"
              >
                <div className="qc-draft-stats" role="status">
                  <button
                    type="button"
                    className={`qc-draft-chip${
                      drillFailingOnly === false ? " is-active" : ""
                    }`}
                    onClick={() => onRun(false)}
                    disabled={composerBusy || !english.trim()}
                  >
                    Pass {fmtInt(modalPassCount)}
                  </button>
                  <button
                    type="button"
                    className={`qc-draft-chip is-fail${
                      drillFailingOnly ? " is-active" : ""
                    }`}
                    onClick={() => onRun(true)}
                    disabled={composerBusy || !english.trim()}
                  >
                    Fail {fmtInt(modalFailCount)}
                  </button>
                </div>
              </div>
            ) : null}

            {showModalDrill ? (
              <div className="qc-modal-drill">
                {qcDrillError ? (
                  <StatusBanner tone="error">{qcDrillError}</StatusBanner>
                ) : null}
                <DataGrid
                  rowData={qcDrillLoans}
                  columnDefs={qcDrillColumnDefs}
                  getRowId={(p) => String(p.data.loan_id)}
                  onRowStats={onQcDrillRowStats}
                  toolbarStart={qcDrillToolbarStart}
                  heightClass="grid-wrap-qc-modal-drill"
                  exportName="qc-loans"
                  showExportActions
                />
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
