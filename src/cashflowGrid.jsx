/**
 * Shared AG Grid theme, column helpers, and DataGrid wrapper for CashFlow.
 * Every tabular React view uses this — one look, one drill interaction,
 * CSV export + clipboard copy.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import { themeQuartz } from "ag-grid-community";

export const FONT = '"Source Sans 3", "Segoe UI", system-ui, sans-serif';

const GRID_SCALE = {
  base: {
    fontSize: 11,
    headerFontSize: 10,
    headerHeight: 22,
    rowHeight: 20,
    spacing: 2,
    iconSize: 12,
  },
  lg: {
    fontSize: 13,
    headerFontSize: 12,
    headerHeight: 32,
    rowHeight: 28,
    spacing: 4,
    iconSize: 14,
  },
  xl: {
    fontSize: 15,
    headerFontSize: 13,
    headerHeight: 38,
    rowHeight: 34,
    spacing: 6,
    iconSize: 16,
  },
};

function readGridScale() {
  if (typeof window === "undefined") return "base";
  if (window.matchMedia("(min-width: 1600px)").matches) return "xl";
  if (window.matchMedia("(min-width: 1280px)").matches) return "lg";
  return "base";
}

function useGridScale() {
  const [scale, setScale] = useState(readGridScale);
  useEffect(() => {
    const mqLg = window.matchMedia("(min-width: 1280px)");
    const mqXl = window.matchMedia("(min-width: 1600px)");
    const apply = () => setScale(readGridScale());
    mqLg.addEventListener("change", apply);
    mqXl.addEventListener("change", apply);
    return () => {
      mqLg.removeEventListener("change", apply);
      mqXl.removeEventListener("change", apply);
    };
  }, []);
  return scale;
}

export const gridTheme = themeQuartz.withParams({
  backgroundColor: "#FFFFFF",
  foregroundColor: "#001A41",
  headerBackgroundColor: "#F4F6F9",
  headerTextColor: "#4A5F7A",
  oddRowBackgroundColor: "#F7F9FC",
  rowHoverColor: "#EEF2F7",
  selectedRowBackgroundColor: "#E8F0FE",
  borderColor: "#D0D7E2",
  /* No heavy outer frame — maximize usable area; keep light cell hairlines. */
  wrapperBorder: false,
  rowBorder: { style: "solid", width: 1, color: "#D0D7E2" },
  columnBorder: { style: "solid", width: 1, color: "#E4E9F0" },
  headerColumnBorder: false,
  fontFamily: FONT,
  fontSize: 11,
  headerFontSize: 10,
  headerFontWeight: 600,
  /* Tighter vertical density on small screens; large desktops scale up. */
  spacing: 2,
  headerHeight: 22,
  rowHeight: 20,
  borderRadius: 0,
  wrapperBorderRadius: 0,
  rangeSelectionBorderColor: "#FD9D24",
  iconSize: 12,
  headerColumnResizeHandleWidth: 2,
  /* Light OS/chrome scrollbars; App.css overrides WebKit thumb/track. */
  browserColorScheme: "light",
});

/** Whole-dollar money for analysis dashboards (no cents). */
export function fmtMoney(v) {
  if (v == null || Number.isNaN(Number(v))) return "";
  return Math.round(Number(v)).toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
}

/** Compact UPB for KPI chips / chart tips. */
export function fmtUpbShort(v) {
  if (v == null || Number.isNaN(Number(v))) return "";
  const n = Math.round(Number(v));
  const abs = Math.abs(n);
  if (abs >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `$${(n / 1e3).toFixed(0)}k`;
  return `$${n.toLocaleString()}`;
}

/** Integer counts (loans, months, FICO). */
export function fmtInt(v) {
  if (v == null || Number.isNaN(Number(v))) return "";
  return Math.round(Number(v)).toLocaleString();
}

/**
 * Fraction → percent. Default 1 decimal (LTV/DTI/rates).
 * Pass digits=2 for WAC; digits=0 for whole %.
 */
export function fmtPct(v, digits = 1) {
  if (v == null || Number.isNaN(Number(v))) return "";
  const pct = Number(v) * 100;
  if (digits <= 0) return `${Math.round(pct)}%`;
  const fixed = pct.toFixed(digits);
  // Drop trailing zeros: 80.0% → 80%, 6.50% → 6.5%
  const trimmed = fixed.replace(/\.?0+$/, "");
  return `${trimmed}%`;
}

/** WAC / coupon rates — ~1 decimal; drop trailing .0. */
export function fmtWac(v) {
  if (v == null || Number.isNaN(Number(v))) return "";
  const pct = Number(v) * 100;
  const fixed = pct.toFixed(1);
  return `${fixed.replace(/\.?0+$/, "")}%`;
}

/** General numeric; trims trailing zeros. Default 1 dp for rates/RI. */
export function fmtNum(v, digits = 1) {
  if (v == null || Number.isNaN(Number(v))) return "";
  if (digits <= 0) return fmtInt(v);
  const fixed = Number(v).toFixed(digits);
  return fixed.replace(/\.?0+$/, "");
}

const PCA = { 75: "Down", 100: "Base", 125: "Up" };
const STA = { 50: "Down", 100: "Base", 200: "Up" };

export function pcaLabel(row) {
  if (!row) return "";
  return row.pca_level || PCA[row.psa_multiple] || row.psa_multiple || "";
}

export function staLabel(row) {
  if (!row) return "";
  return row.sta_level || STA[row.sda_multiple] || row.sda_multiple || "";
}

/** PSA×SDA axis label (legacy helper for CF drill labels). */
export function scenarioAxisLabel(row) {
  if (!row) return "";
  const psa = row.psa_multiple ?? "";
  const sda = row.sda_multiple ?? "";
  return `PSA ${psa} / SDA ${sda}`;
}

export function scenarioAxisKey(row) {
  if (!row) return "";
  return `${row.psa_multiple}|${row.sda_multiple}`;
}

/**
 * Stamp contiguous rowSpans for a key field.
 * First cell of a run gets span N; followers get 0 (blank + no rowspan).
 */
function stampRowSpans(rows, keyFn, spanField) {
  let i = 0;
  while (i < rows.length) {
    const key = keyFn(rows[i]);
    let j = i + 1;
    while (j < rows.length && keyFn(rows[j]) === key) j += 1;
    rows[i][spanField] = j - i;
    for (let k = i + 1; k < j; k += 1) rows[k][spanField] = 0;
    i = j;
  }
}

/**
 * Sort Cohort → PSA → SDA and stamp `_cohortSpan` / `_psaSpan` for
 * Bloomberg-style merged cells (no redundant Scenario axis column).
 */
export function withCohortPsaRowSpans(rows) {
  const sorted = [...(rows || [])].sort((a, b) => {
    const ca = String(a.cohort || "");
    const cb = String(b.cohort || "");
    if (ca !== cb) return ca.localeCompare(cb);
    const pa = Number(a.psa_multiple) || 0;
    const pb = Number(b.psa_multiple) || 0;
    if (pa !== pb) return pa - pb;
    return (Number(a.sda_multiple) || 0) - (Number(b.sda_multiple) || 0);
  });
  const out = sorted.map((r) => ({
    ...r,
    _cohortSpan: 1,
    _psaSpan: 1,
  }));
  stampRowSpans(out, (r) => String(r.cohort || ""), "_cohortSpan");
  stampRowSpans(
    out,
    (r) => `${r.cohort || ""}|${r.psa_multiple ?? ""}`,
    "_psaSpan"
  );
  return out;
}

/** @deprecated Prefer withCohortPsaRowSpans (cohort-first grid). */
export function withScenarioRowSpans(rows) {
  return withCohortPsaRowSpans(rows);
}

export const sharedDefaultColDef = {
  sortable: true,
  resizable: true,
  filter: true,
  floatingFilter: false,
  suppressHeaderFilterButton: false,
  suppressMovable: false,
  wrapHeaderText: false,
  autoHeaderHeight: false,
  cellStyle: {
    fontFamily: FONT,
    fontVariantNumeric: "tabular-nums",
  },
  headerClass: "cf-grid-header",
};

export const sharedColTypes = {
  money: {
    type: "numericColumn",
    filter: "agNumberColumnFilter",
    valueFormatter: (p) => fmtMoney(p.value),
    cellClass: "cf-num",
    width: 104,
  },
  int: {
    type: "numericColumn",
    filter: "agNumberColumnFilter",
    cellClass: "cf-num",
    width: 72,
  },
  id: {
    width: 88,
    cellClass: "cf-id",
  },
};

export function moneyCol(field, headerName, width = 104) {
  return {
    field,
    headerName,
    width,
    type: "numericColumn",
    filter: "agNumberColumnFilter",
    valueFormatter: (p) => fmtMoney(p.value),
    cellClass: "cf-num",
  };
}

export function intCol(field, headerName, width = 72) {
  return {
    field,
    headerName,
    width,
    type: "numericColumn",
    filter: "agNumberColumnFilter",
    valueFormatter: (p) => fmtInt(p.value),
    cellClass: "cf-num",
  };
}

function escapeTsv(v) {
  if (v == null) return "";
  const s = String(v);
  if (/[\t\n\r"]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function rowsToTsv(api, rows) {
  const cols = (api.getColumns?.() || api.getAllDisplayedColumns?.() || [])
    .filter((c) => {
      const id = c.getColId?.() || c.colId;
      return id && id !== "ag-Grid-ControlsColumn" && !String(id).startsWith("_");
    });
  const headers = cols.map(
    (c) => c.getColDef?.()?.headerName || c.getColId?.() || ""
  );
  const lines = [headers.join("\t")];
  for (const row of rows) {
    const cells = cols.map((c) => {
      const field = c.getColDef?.()?.field;
      const getter = c.getColDef?.()?.valueGetter;
      let val;
      if (typeof getter === "function") {
        try {
          val = getter({ data: row, node: { data: row }, colDef: c.getColDef() });
        } catch {
          val = field ? row[field] : "";
        }
      } else if (field) {
        val = row[field];
      } else {
        val = "";
      }
      const fmt = c.getColDef?.()?.valueFormatter;
      if (typeof fmt === "function" && val !== "" && val != null) {
        try {
          val = fmt({ value: val, data: row });
        } catch {
          /* keep raw */
        }
      }
      return escapeTsv(val);
    });
    lines.push(cells.join("\t"));
  }
  return lines.join("\n");
}

function IconExportCsv({ size = 16 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M8 2v8.5M5.5 8.5 8 11l2.5-2.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M3 13.5h10"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconCopy({ size = 16 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      focusable="false"
    >
      <rect
        x="5.25"
        y="5.25"
        width="7.5"
        height="8.5"
        rx="1"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <path
        d="M10.75 5.25V3.75A1.5 1.5 0 0 0 9.25 2.25H3.75A1.5 1.5 0 0 0 2.25 3.75v7.5A1.5 1.5 0 0 0 3.75 12.75h1.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Shared DataGrid — theme, drill, CSV export, clipboard copy. */
export function DataGrid({
  rowData,
  columnDefs,
  getRowId,
  onRowDrill,
  onGridReady,
  onRowStats,
  scheduleSave,
  persistLayout = false,
  className = "grid-wrap grid-wrap-fill",
  heightClass,
  exportName = "cashflow",
  showToolbar = true,
  toolbarStart = null,
  gridProps = {},
}) {
  const defaultColDef = useMemo(() => ({ ...sharedDefaultColDef }), []);
  const apiRef = useRef(null);
  const wrapRef = useRef(null);
  const onRowStatsRef = useRef(onRowStats);
  onRowStatsRef.current = onRowStats;
  const gridScale = useGridScale();
  const scaledTheme = useMemo(
    () => gridTheme.withParams(GRID_SCALE[gridScale] || GRID_SCALE.base),
    [gridScale]
  );
  const iconSize = gridScale === "xl" ? 18 : gridScale === "lg" ? 16 : 14;

  const emitRowStats = useCallback((api) => {
    const cb = onRowStatsRef.current;
    if (!cb || !api) return;
    const loaded = api.getDisplayedRowCount
      ? (() => {
          let n = 0;
          api.forEachNode?.(() => {
            n += 1;
          });
          return n;
        })()
      : Array.isArray(rowData)
        ? rowData.length
        : 0;
    let visible = 0;
    if (typeof api.getDisplayedRowCount === "function") {
      visible = api.getDisplayedRowCount();
    } else {
      api.forEachNodeAfterFilterAndSort?.((n) => {
        if (n?.data) visible += 1;
      });
    }
    cb({ loaded, visible });
  }, [rowData]);

  const handleGridReady = useCallback(
    (e) => {
      apiRef.current = e.api;
      emitRowStats(e.api);
      onGridReady?.(e);
    },
    [onGridReady, emitRowStats]
  );

  const handleFilterOrModel = useCallback(
    (e) => {
      emitRowStats(e?.api || apiRef.current);
    },
    [emitRowStats]
  );

  const onRowClicked = useCallback(
    (e) => {
      if (!onRowDrill || !e?.data) return;
      if (e.event?.target?.closest?.(".ag-header")) return;
      onRowDrill(e.data, e);
    },
    [onRowDrill]
  );

  const onRowDoubleClicked = useCallback(
    (e) => {
      if (!onRowDrill || !e?.data) return;
      onRowDrill(e.data, e);
    },
    [onRowDrill]
  );

  const collectRows = useCallback(() => {
    const api = apiRef.current;
    if (!api) return [];
    const selected = api.getSelectedRows?.() || [];
    if (selected.length) return selected;
    const out = [];
    api.forEachNodeAfterFilterAndSort?.((n) => {
      if (n?.data) out.push(n.data);
    });
    return out;
  }, []);

  const exportCsv = useCallback(() => {
    const api = apiRef.current;
    if (!api) return;
    api.exportDataAsCsv({
      fileName: `${exportName}.csv`,
      processCellCallback: (p) => {
        if (p.value == null) return "";
        return p.value;
      },
    });
  }, [exportName]);

  const copyRows = useCallback(async () => {
    const api = apiRef.current;
    if (!api) return;
    const rows = collectRows();
    if (!rows.length) return;
    const tsv = rowsToTsv(api, rows);
    try {
      await navigator.clipboard.writeText(tsv);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = tsv;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
  }, [collectRows]);

  const onKeyDown = useCallback(
    (e) => {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "c") return;
      const sel = window.getSelection?.()?.toString?.();
      if (sel && sel.length > 0) return; /* native text copy */
      e.preventDefault();
      copyRows();
    },
    [copyRows]
  );

  const wrapClass = heightClass
    ? `grid-wrap ${heightClass}`
    : className.replace(/\bag-theme-cashflow\b/g, "").trim() ||
      "grid-wrap grid-wrap-fill";

  return (
    <div
      className={wrapClass}
      ref={wrapRef}
      tabIndex={0}
      onKeyDown={onKeyDown}
    >
      {showToolbar && (
        <div className="cf-grid-toolbar" role="toolbar" aria-label="Grid Actions">
          {toolbarStart ? (
            <div className="cf-grid-toolbar-start">{toolbarStart}</div>
          ) : (
            <div className="cf-grid-toolbar-start" aria-hidden="true" />
          )}
          <div className="cf-grid-toolbar-actions">
            <button
              type="button"
              className="cf-grid-icon-btn"
              onClick={exportCsv}
              title="Export CSV"
              aria-label="Export CSV"
            >
              <IconExportCsv size={iconSize} />
            </button>
            <button
              type="button"
              className="cf-grid-icon-btn"
              onClick={copyRows}
              title="Copy (Ctrl+C)"
              aria-label="Copy Rows To Clipboard"
            >
              <IconCopy size={iconSize} />
            </button>
          </div>
        </div>
      )}
      <div className="cf-grid-host ag-theme-cashflow">
        <AgGridReact
          theme={scaledTheme}
          rowData={rowData}
          columnDefs={columnDefs}
          defaultColDef={defaultColDef}
          columnTypes={sharedColTypes}
          suppressCellFocus
          animateRows={false}
          rowSelection="single"
          enableCellTextSelection
          ensureDomOrder
          enableBrowserTooltips
          tooltipShowDelay={400}
          getRowId={getRowId}
          onGridReady={handleGridReady}
          onRowClicked={onRowClicked}
          onRowDoubleClicked={onRowDoubleClicked}
          onColumnMoved={persistLayout ? scheduleSave : undefined}
          onColumnVisible={persistLayout ? scheduleSave : undefined}
          onColumnPinned={persistLayout ? scheduleSave : undefined}
          onColumnResized={persistLayout ? scheduleSave : undefined}
          onSortChanged={persistLayout ? scheduleSave : undefined}
          onFilterChanged={(e) => {
            handleFilterOrModel(e);
            if (persistLayout) scheduleSave?.(e);
          }}
          onModelUpdated={handleFilterOrModel}
          onRowDataUpdated={handleFilterOrModel}
          {...gridProps}
        />
      </div>
    </div>
  );
}

/** Breadcrumb trail for drill-down analysis. */
export function DrillTrail({ crumbs, onJump }) {
  if (!crumbs?.length) return null;
  return (
    <nav className="drill-trail" aria-label="Analysis Path">
      {crumbs.map((c, i) => {
        const last = i === crumbs.length - 1;
        return (
          <span key={`${c.id}-${i}`} className="drill-crumb">
            {i > 0 && <span className="drill-sep">›</span>}
            {last || !c.jumpable ? (
              <span className="drill-current">{c.label}</span>
            ) : (
              <button
                type="button"
                className="linkish drill-link"
                onClick={() => onJump?.(c)}
              >
                {c.label}
              </button>
            )}
          </span>
        );
      })}
    </nav>
  );
}

/** Compact Bloomberg-style status strip (not a browser blue alert). */
export function StatusBanner({ tone = "muted", children }) {
  if (!children) return null;
  return <p className={`status-banner status-banner-${tone}`}>{children}</p>;
}
