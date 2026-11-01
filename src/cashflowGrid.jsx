/**
 * Shared AG Grid theme, column helpers, and DataGrid wrapper for CashFlow.
 * Every tabular React view uses this — one look, one drill interaction,
 * CSV export + clipboard copy.
 */
import { useCallback, useMemo, useRef } from "react";
import { AgGridReact } from "ag-grid-react";
import { themeQuartz } from "ag-grid-community";

export const FONT = '"Source Sans 3", "Segoe UI", system-ui, sans-serif';

export const gridTheme = themeQuartz.withParams({
  backgroundColor: "#212026",
  foregroundColor: "#FCFCFC",
  headerBackgroundColor: "#0C0C0C",
  headerTextColor: "#808080",
  oddRowBackgroundColor: "#121212",
  rowHoverColor: "#1A1A1A",
  selectedRowBackgroundColor: "#2A2418",
  borderColor: "#323232",
  rowBorder: { style: "solid", width: 1, color: "#323232" },
  columnBorder: { style: "solid", width: 1, color: "#2A2A2A" },
  headerColumnBorder: false,
  fontFamily: FONT,
  fontSize: 11,
  headerFontSize: 10,
  headerFontWeight: 600,
  spacing: 4,
  headerHeight: 28,
  rowHeight: 24,
  borderRadius: 0,
  wrapperBorderRadius: 0,
  rangeSelectionBorderColor: "#FD9D24",
  iconSize: 12,
  headerColumnResizeHandleWidth: 2,
  /* Prefer dark OS/chrome scrollbars; App.css overrides WebKit thumb/track. */
  browserColorScheme: "dark",
});

export function fmtMoney(v) {
  if (v == null || Number.isNaN(Number(v))) return "";
  return Number(v).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function fmtPct(v, digits = 1) {
  if (v == null || Number.isNaN(Number(v))) return "";
  return `${(Number(v) * 100).toFixed(digits)}%`;
}

export function fmtNum(v, digits = 3) {
  if (v == null || Number.isNaN(Number(v))) return "";
  return Number(v).toFixed(digits);
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

/** PSA×SDA axis label used for Scenario column merge. */
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
 * Sort by PSA→SDA→cohort and stamp `_scenarioLabel` / `_scenarioSpan`
 * so adjacent same-axis rows can rowspan the Scenario column.
 */
export function withScenarioRowSpans(rows) {
  const sorted = [...(rows || [])].sort((a, b) => {
    const pa = Number(a.psa_multiple) || 0;
    const pb = Number(b.psa_multiple) || 0;
    if (pa !== pb) return pa - pb;
    const sa = Number(a.sda_multiple) || 0;
    const sb = Number(b.sda_multiple) || 0;
    if (sa !== sb) return sa - sb;
    return String(a.cohort || "").localeCompare(String(b.cohort || ""));
  });
  const out = sorted.map((r) => ({
    ...r,
    _scenarioLabel: scenarioAxisLabel(r),
    _scenarioSpan: 1,
  }));
  let i = 0;
  while (i < out.length) {
    let j = i + 1;
    while (j < out.length && out[j]._scenarioLabel === out[i]._scenarioLabel) {
      j += 1;
    }
    out[i]._scenarioSpan = j - i;
    for (let k = i + 1; k < j; k += 1) {
      out[k]._scenarioSpan = 0;
    }
    i = j;
  }
  return out;
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

/** Shared DataGrid — theme, drill, CSV export, clipboard copy. */
export function DataGrid({
  rowData,
  columnDefs,
  getRowId,
  onRowDrill,
  onGridReady,
  scheduleSave,
  persistLayout = false,
  className = "grid-wrap grid-wrap-fill",
  heightClass,
  exportName = "cashflow",
  showToolbar = true,
  gridProps = {},
}) {
  const defaultColDef = useMemo(() => ({ ...sharedDefaultColDef }), []);
  const apiRef = useRef(null);
  const wrapRef = useRef(null);

  const handleGridReady = useCallback(
    (e) => {
      apiRef.current = e.api;
      onGridReady?.(e);
    },
    [onGridReady]
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
        <div className="cf-grid-toolbar" role="toolbar" aria-label="Grid actions">
          <button type="button" className="linkish cf-grid-tool" onClick={exportCsv}>
            Export CSV
          </button>
          <button type="button" className="linkish cf-grid-tool" onClick={copyRows}>
            Copy
          </button>
          <span className="cf-grid-tool-hint">Ctrl+C copies selection</span>
        </div>
      )}
      <div className="cf-grid-host ag-theme-cashflow">
        <AgGridReact
          theme={gridTheme}
          rowData={rowData}
          columnDefs={columnDefs}
          defaultColDef={defaultColDef}
          columnTypes={sharedColTypes}
          suppressCellFocus
          animateRows={false}
          rowSelection="single"
          enableCellTextSelection
          ensureDomOrder
          getRowId={getRowId}
          onGridReady={handleGridReady}
          onRowClicked={onRowClicked}
          onRowDoubleClicked={onRowDoubleClicked}
          onColumnMoved={persistLayout ? scheduleSave : undefined}
          onColumnVisible={persistLayout ? scheduleSave : undefined}
          onColumnPinned={persistLayout ? scheduleSave : undefined}
          onColumnResized={persistLayout ? scheduleSave : undefined}
          onSortChanged={persistLayout ? scheduleSave : undefined}
          onFilterChanged={persistLayout ? scheduleSave : undefined}
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
    <nav className="drill-trail" aria-label="Analysis path">
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
