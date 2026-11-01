import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
} from "ag-grid-community";
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import "./App.css";

ModuleRegistry.registerModules([AllCommunityModule]);

const FONT = '"Source Sans 3", "Segoe UI", system-ui, sans-serif';

const CLUSTER_ORDER = ["HLTV-HRI", "HLTV-LRI", "LLTV-LRI"];
const CLUSTER_COLORS = {
  "HLTV-HRI": "#ff7f0e",
  "HLTV-LRI": "#2ca02c",
  "LLTV-LRI": "#1f77b4",
};
const CLUSTER_FALLBACK_COUNTS = {
  "LLTV-LRI": 339,
  "HLTV-HRI": 329,
  "HLTV-LRI": 375,
};

const LS_CLUSTER_KEY = "cashflow.clusterFilter";
const LS_GRID_KEY = "cashflow.agGridState";

const gridTheme = themeQuartz.withParams({
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

function readClusterFilter() {
  try {
    const v = localStorage.getItem(LS_CLUSTER_KEY);
    if (v === "all" || CLUSTER_ORDER.includes(v)) return v;
  } catch {
    /* ignore */
  }
  return "all";
}

function readGridState() {
  try {
    const raw = localStorage.getItem(LS_GRID_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") return parsed;
  } catch {
    /* ignore */
  }
  return null;
}

function saveGridState(api) {
  if (!api) return;
  try {
    const payload = {
      columnState: api.getColumnState(),
      filterModel: api.getFilterModel(),
      sortModel:
        typeof api.getSortModel === "function"
          ? api.getSortModel()
          : undefined,
    };
    // AG Grid v31+ may encode sort on columnState; drop empty sortModel
    if (!payload.sortModel) delete payload.sortModel;
    localStorage.setItem(LS_GRID_KEY, JSON.stringify(payload));
  } catch {
    /* ignore */
  }
}

function CustomLegend({ payload, activeCluster, onSelect, counts }) {
  if (!payload?.length) return null;
  const entries = payload.filter((e) => CLUSTER_ORDER.includes(e.value));
  return (
    <ul className="scatter-legend">
      {entries.map((entry) => {
        const code = entry.value;
        const selected = activeCluster === code;
        const n = counts?.[code] ?? CLUSTER_FALLBACK_COUNTS[code] ?? "?";
        return (
          <li key={code}>
            <button
              type="button"
              className={`scatter-legend-btn${selected ? " is-active" : ""}`}
              style={{ "--cluster-color": entry.color }}
              onClick={() => onSelect(code)}
              title={`Filter grid to ${code}`}
            >
              <span className="scatter-legend-swatch" />
              <span>
                {code} (n={n})
              </span>
            </button>
          </li>
        );
      })}
      <li>
        <button
          type="button"
          className={`scatter-legend-btn scatter-legend-all${
            activeCluster === "all" ? " is-active" : ""
          }`}
          onClick={() => onSelect("all")}
        >
          All
        </button>
      </li>
    </ul>
  );
}

/** Invisible marker so hull Scatter only draws the joint outline. */
function NullShape() {
  return null;
}

export default function App() {
  const [a, setA] = useState("2");
  const [b, setB] = useState("3");
  const [sum, setSum] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const [loans, setLoans] = useState([]);
  const [hulls, setHulls] = useState({});
  const [counts, setCounts] = useState(CLUSTER_FALLBACK_COUNTS);
  const [tapeError, setTapeError] = useState(null);
  const [tapeLoading, setTapeLoading] = useState(true);
  const [clusterFilter, setClusterFilter] = useState(readClusterFilter);

  const gridApiRef = useRef(null);
  const restoringRef = useRef(false);
  const saveTimerRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setTapeLoading(true);
      setTapeError(null);
      try {
        const res = await fetch("/cluster-tape.json");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (cancelled) return;
        setLoans(Array.isArray(data.loans) ? data.loans : []);
        setHulls(data.hulls || {});
        if (data.meta?.counts) setCounts(data.meta.counts);
      } catch (err) {
        if (!cancelled) {
          setTapeError(err.message || String(err));
          setLoans([]);
        }
      } finally {
        if (!cancelled) setTapeLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(LS_CLUSTER_KEY, clusterFilter);
    } catch {
      /* ignore */
    }
  }, [clusterFilter]);

  const columnDefs = useMemo(
    () => [
      { field: "loanId", headerName: "Loan ID", flex: 1.1, minWidth: 100 },
      {
        field: "fico",
        headerName: "FICO",
        width: 72,
        type: "numericColumn",
        filter: "agNumberColumnFilter",
      },
      {
        field: "cltv",
        headerName: "CLTV",
        width: 90,
        type: "numericColumn",
        filter: "agNumberColumnFilter",
        valueFormatter: (p) =>
          p.value == null ? "" : `${(Number(p.value) * 100).toFixed(1)}%`,
      },
      {
        field: "documentation",
        headerName: "Documentation",
        flex: 1.2,
        minWidth: 120,
        filter: true,
      },
      {
        field: "remainingTerm",
        headerName: "Remaining term",
        width: 110,
        type: "numericColumn",
        filter: "agNumberColumnFilter",
      },
      {
        field: "refinanceIncentive",
        headerName: "Refi incentive",
        width: 110,
        type: "numericColumn",
        filter: "agNumberColumnFilter",
        valueFormatter: (p) =>
          p.value == null ? "" : Number(p.value).toFixed(3),
      },
      {
        field: "cluster",
        headerName: "Cluster",
        width: 100,
        filter: true,
      },
    ],
    []
  );

  const defaultColDef = useMemo(
    () => ({
      sortable: true,
      resizable: true,
      filter: true,
      suppressMovable: false,
    }),
    []
  );

  const filteredLoans = useMemo(() => {
    if (clusterFilter === "all") return loans;
    return loans.filter((r) => r.cluster === clusterFilter);
  }, [loans, clusterFilter]);

  const scatterByCluster = useMemo(() => {
    const groups = Object.fromEntries(CLUSTER_ORDER.map((c) => [c, []]));
    for (const loan of loans) {
      if (!groups[loan.cluster]) continue;
      if (loan.cltv == null || loan.refinanceIncentive == null) continue;
      groups[loan.cluster].push({
        cltv: loan.cltv,
        incentive: loan.refinanceIncentive,
        loanId: loan.loanId,
        cluster: loan.cluster,
      });
    }
    return groups;
  }, [loans]);

  const hullSeries = useMemo(() => {
    const out = {};
    for (const code of CLUSTER_ORDER) {
      const pts = hulls[code];
      if (!Array.isArray(pts) || pts.length < 3) continue;
      out[code] = pts.map((p) => ({
        cltv: p.cltv,
        incentive: p.incentive,
      }));
    }
    return out;
  }, [hulls]);

  const scheduleSave = useCallback(() => {
    if (restoringRef.current) return;
    clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      saveGridState(gridApiRef.current);
    }, 200);
  }, []);

  const onGridReady = useCallback(
    (params) => {
      gridApiRef.current = params.api;
      const saved = readGridState();
      if (saved?.columnState?.length) {
        restoringRef.current = true;
        params.api.applyColumnState({
          state: saved.columnState,
          applyOrder: true,
        });
        if (saved.filterModel) {
          params.api.setFilterModel(saved.filterModel);
        }
        if (saved.sortModel && typeof params.api.setSortModel === "function") {
          params.api.setSortModel(saved.sortModel);
        }
        requestAnimationFrame(() => {
          restoringRef.current = false;
        });
      }
    },
    []
  );

  const selectCluster = useCallback((code) => {
    setClusterFilter((prev) => {
      if (code === "all") return "all";
      return prev === code ? "all" : code;
    });
  }, []);

  async function handleSum() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/sum", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ a: Number(a), b: Number(b) }),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      setSum(data.sum);
    } catch (err) {
      setSum(null);
      setError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  }

  const axisTick = {
    fill: "#808080",
    fontSize: 10,
    fontFamily: FONT,
  };

  const filterLabel =
    clusterFilter === "all" ? "All clusters" : clusterFilter;

  return (
    <div className="app">
      <header className="topbar">
        <img
          className="topbar-mark"
          src="/favicon.svg"
          alt=""
          width={16}
          height={16}
        />
        <span className="topbar-name">CashFlow</span>
        <span className="topbar-version">v0.1.0</span>
      </header>

      <main className="main">
        <section className="section">
          <h2 className="section-title">Sum demo</h2>
          <div className="sum-row">
            <div className="field">
              <label htmlFor="input-a">A</label>
              <input
                id="input-a"
                type="number"
                value={a}
                onChange={(e) => setA(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="input-b">B</label>
              <input
                id="input-b"
                type="number"
                value={b}
                onChange={(e) => setB(e.target.value)}
              />
            </div>
            <button
              type="button"
              className="btn"
              onClick={handleSum}
              disabled={loading}
            >
              {loading ? "Adding…" : "Add"}
            </button>
            {sum !== null && (
              <p className="result">
                Sum: <strong>{sum}</strong>
              </p>
            )}
            {error && <p className="error">Error: {error}</p>}
          </div>
        </section>

        <section className="section">
          <div className="section-head">
            <h2 className="section-title">K-Prototypes clusters</h2>
            <p className="section-meta">
              CLTV × refinance incentive · click legend or points to filter
            </p>
          </div>
          <div className="chart-wrap chart-wrap-tall">
            {tapeLoading ? (
              <p className="muted">Loading tape…</p>
            ) : tapeError ? (
              <p className="error">Tape: {tapeError}</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart margin={{ top: 8, right: 12, left: 4, bottom: 8 }}>
                  <CartesianGrid
                    stroke="#323232"
                    strokeDasharray="0"
                    vertical={false}
                  />
                  <XAxis
                    type="number"
                    dataKey="cltv"
                    name="ORIGINAL_CLTV"
                    tick={axisTick}
                    axisLine={{ stroke: "#323232" }}
                    tickLine={false}
                    tickFormatter={(v) => `${(Number(v) * 100).toFixed(0)}%`}
                    domain={["auto", "auto"]}
                    label={{
                      value: "ORIGINAL_CLTV",
                      position: "insideBottom",
                      offset: -2,
                      fill: "#808080",
                      fontSize: 10,
                      fontFamily: FONT,
                    }}
                  />
                  <YAxis
                    type="number"
                    dataKey="incentive"
                    name="Refinance incentive"
                    tick={axisTick}
                    axisLine={false}
                    tickLine={false}
                    domain={["auto", "auto"]}
                    width={48}
                    label={{
                      value: "Refinance incentive",
                      angle: -90,
                      position: "insideLeft",
                      offset: 4,
                      fill: "#808080",
                      fontSize: 10,
                      fontFamily: FONT,
                    }}
                  />
                  <ZAxis range={[36, 36]} />
                  <Tooltip
                    cursor={{ strokeDasharray: "3 3", stroke: "#464646" }}
                    contentStyle={{
                      background: "#212026",
                      border: "1px solid #323232",
                      borderRadius: 0,
                      fontSize: 11,
                      color: "#FCFCFC",
                      fontFamily: FONT,
                    }}
                    labelStyle={{ color: "#808080" }}
                    formatter={(value, name) => {
                      if (name === "cltv" || name === "ORIGINAL_CLTV") {
                        return [
                          `${(Number(value) * 100).toFixed(1)}%`,
                          "CLTV",
                        ];
                      }
                      if (
                        name === "incentive" ||
                        name === "Refinance incentive"
                      ) {
                        return [Number(value).toFixed(3), "Refi incentive"];
                      }
                      return [value, name];
                    }}
                  />
                  <Legend
                    content={(props) => (
                      <CustomLegend
                        {...props}
                        activeCluster={clusterFilter}
                        onSelect={selectCluster}
                        counts={counts}
                      />
                    )}
                  />
                  {CLUSTER_ORDER.map((code) =>
                    hullSeries[code] ? (
                      <Scatter
                        key={`hull-${code}`}
                        data={hullSeries[code]}
                        fill="none"
                        line={{
                          stroke: CLUSTER_COLORS[code],
                          strokeWidth: 1.25,
                          strokeOpacity:
                            clusterFilter === "all" || clusterFilter === code
                              ? 0.55
                              : 0.15,
                        }}
                        lineType="joint"
                        shape={NullShape}
                        legendType="none"
                        isAnimationActive={false}
                      />
                    ) : null
                  )}
                  {CLUSTER_ORDER.map((code) => (
                    <Scatter
                      key={code}
                      name={code}
                      data={scatterByCluster[code]}
                      fill={CLUSTER_COLORS[code]}
                      fillOpacity={
                        clusterFilter === "all" || clusterFilter === code
                          ? 0.75
                          : 0.15
                      }
                      shape="circle"
                      onClick={() => selectCluster(code)}
                      cursor="pointer"
                      isAnimationActive={false}
                    />
                  ))}
                </ComposedChart>
              </ResponsiveContainer>
            )}
          </div>
        </section>

        <section className="section">
          <div className="section-head">
            <h2 className="section-title">Loan tape</h2>
            <p className="section-meta">
              Filter: {filterLabel}
              {clusterFilter !== "all" && (
                <>
                  {" · "}
                  <button
                    type="button"
                    className="linkish"
                    onClick={() => selectCluster("all")}
                  >
                    Clear
                  </button>
                </>
              )}
            </p>
          </div>
          <div className="grid-wrap grid-wrap-tall ag-theme-cashflow">
            <AgGridReact
              theme={gridTheme}
              rowData={filteredLoans}
              columnDefs={columnDefs}
              defaultColDef={defaultColDef}
              suppressCellFocus
              animateRows={false}
              onGridReady={onGridReady}
              onColumnMoved={scheduleSave}
              onColumnVisible={scheduleSave}
              onColumnPinned={scheduleSave}
              onColumnResized={scheduleSave}
              onSortChanged={scheduleSave}
              onFilterChanged={scheduleSave}
              getRowId={(p) => String(p.data.loanId)}
            />
          </div>
        </section>
      </main>
    </div>
  );
}
