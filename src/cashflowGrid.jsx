/**
 * Shared AG Grid theme, column helpers, and DataGrid wrapper for CashFlow.
 * Every tabular React view should use this — one look, one interaction pattern.
 */
import { useMemo } from "react";
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
  selectedRowBackgroundColor: "#1E1E22",
  borderColor: "#323232",
  rowBorder: { style: "solid", width: 1, color: "#323232" },
  columnBorder: { style: "solid", width: 1, color: "#2A2A2A" },
  headerColumnBorder: false,
  fontFamily: FONT,
  fontSize: 11,
  headerFontSize: 10,
  headerFontWeight: 600,
  spacing: 2,
  headerHeight: 22,
  rowHeight: 22,
  borderRadius: 0,
  wrapperBorderRadius: 0,
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

/** Shared default column behavior for every CashFlow grid. */
export const sharedDefaultColDef = {
  sortable: true,
  resizable: true,
  filter: true,
  floatingFilter: false,
  suppressMovable: false,
  cellStyle: {
    fontFamily: FONT,
    fontVariantNumeric: "tabular-nums",
  },
};

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

/**
 * Shared AG Grid shell — same theme, defaults, and chrome as Loans / Scenarios / CF.
 */
export function DataGrid({
  rowData,
  columnDefs,
  getRowId,
  className = "grid-wrap grid-wrap-tall ag-theme-cashflow",
  heightClass,
  defaultColDef,
  onGridReady,
  onColumnMoved,
  onColumnVisible,
  onColumnPinned,
  onColumnResized,
  onSortChanged,
  onFilterChanged,
  onRowClicked,
  rowSelection,
  ...rest
}) {
  const mergedDefault = useMemo(
    () => ({ ...sharedDefaultColDef, ...(defaultColDef || {}) }),
    [defaultColDef]
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
        defaultColDef={mergedDefault}
        suppressCellFocus
        animateRows={false}
        getRowId={getRowId}
        onGridReady={onGridReady}
        onColumnMoved={onColumnMoved}
        onColumnVisible={onColumnVisible}
        onColumnPinned={onColumnPinned}
        onColumnResized={onColumnResized}
        onSortChanged={onSortChanged}
        onFilterChanged={onFilterChanged}
        onRowClicked={onRowClicked}
        rowSelection={rowSelection}
        {...rest}
      />
    </div>
  );
}
