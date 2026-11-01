/**
 * Shared AG Grid theme, column helpers, and DataGrid wrapper for CashFlow.
 * Every tabular React view uses this — one look, one drill interaction.
 */
import { useCallback, useMemo } from "react";
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

/** Shared DataGrid — one theme, selection, click-to-drill. */
export function DataGrid({
  rowData,
  columnDefs,
  getRowId,
  onRowDrill,
  onGridReady,
  scheduleSave,
  persistLayout = false,
  className = "grid-wrap grid-wrap-fill ag-theme-cashflow",
  heightClass,
}) {
  const defaultColDef = useMemo(() => ({ ...sharedDefaultColDef }), []);

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

  const wrapClass = heightClass
    ? `grid-wrap ${heightClass} ag-theme-cashflow`
    : className;

  return (
    <div className={wrapClass}>
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
        onGridReady={onGridReady}
        onRowClicked={onRowClicked}
        onRowDoubleClicked={onRowDoubleClicked}
        onColumnMoved={persistLayout ? scheduleSave : undefined}
        onColumnVisible={persistLayout ? scheduleSave : undefined}
        onColumnPinned={persistLayout ? scheduleSave : undefined}
        onColumnResized={persistLayout ? scheduleSave : undefined}
        onSortChanged={persistLayout ? scheduleSave : undefined}
        onFilterChanged={persistLayout ? scheduleSave : undefined}
      />
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
