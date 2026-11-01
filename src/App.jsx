import { useMemo, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
} from "ag-grid-community";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import "./App.css";

ModuleRegistry.registerModules([AllCommunityModule]);

const SAMPLE_LOANS = [
  { loanId: "LN-10021", fico: 742, cltv: 78.5, rate: 6.125, cohort: "A" },
  { loanId: "LN-10044", fico: 698, cltv: 85.0, rate: 6.875, cohort: "B" },
  { loanId: "LN-10058", fico: 715, cltv: 72.2, rate: 6.375, cohort: "A" },
  { loanId: "LN-10073", fico: 661, cltv: 90.1, rate: 7.250, cohort: "C" },
  { loanId: "LN-10089", fico: 731, cltv: 68.4, rate: 5.990, cohort: "A" },
  { loanId: "LN-10102", fico: 684, cltv: 82.7, rate: 6.750, cohort: "B" },
  { loanId: "LN-10118", fico: 705, cltv: 76.0, rate: 6.500, cohort: "B" },
  { loanId: "LN-10135", fico: 648, cltv: 88.9, rate: 7.125, cohort: "C" },
];

const CHART_DATA = [
  { cohort: "A", count: 3, avgRate: 6.16 },
  { cohort: "B", count: 3, avgRate: 6.71 },
  { cohort: "C", count: 2, avgRate: 7.19 },
];

const gridTheme = themeQuartz.withParams({
  backgroundColor: "#0B2A4A",
  foregroundColor: "#FFFFFF",
  headerBackgroundColor: "#163A5C",
  headerTextColor: "#B8C5D6",
  oddRowBackgroundColor: "#0A3A6B",
  rowHoverColor: "#12406A",
  selectedRowBackgroundColor: "#1A4F7C",
  borderColor: "#1E4A6E",
  rowBorder: true,
  fontFamily: '"IBM Plex Sans", "Segoe UI", sans-serif',
  fontSize: 11,
  headerFontSize: 10,
  spacing: 3,
  headerHeight: 28,
  rowHeight: 26,
});

export default function App() {
  const [a, setA] = useState("2");
  const [b, setB] = useState("3");
  const [sum, setSum] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const columnDefs = useMemo(
    () => [
      { field: "loanId", headerName: "Loan ID", flex: 1.1, minWidth: 100 },
      { field: "fico", headerName: "FICO", width: 72, type: "numericColumn" },
      {
        field: "cltv",
        headerName: "CLTV",
        width: 78,
        type: "numericColumn",
        valueFormatter: (p) =>
          p.value == null ? "" : `${Number(p.value).toFixed(1)}%`,
      },
      {
        field: "rate",
        headerName: "Rate",
        width: 78,
        type: "numericColumn",
        valueFormatter: (p) =>
          p.value == null ? "" : `${Number(p.value).toFixed(3)}%`,
      },
      { field: "cohort", headerName: "Cohort", width: 80 },
    ],
    []
  );

  const defaultColDef = useMemo(
    () => ({
      sortable: true,
      resizable: true,
      suppressMovable: true,
    }),
    []
  );

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

  return (
    <div className="app">
      <header className="topbar">
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

        <div className="panel-grid">
          <section className="section">
            <h2 className="section-title">Sample mortgage tape</h2>
            <div className="grid-wrap ag-theme-cashflow">
              <AgGridReact
                theme={gridTheme}
                rowData={SAMPLE_LOANS}
                columnDefs={columnDefs}
                defaultColDef={defaultColDef}
                suppressCellFocus
                animateRows={false}
              />
            </div>
          </section>

          <section className="section">
            <h2 className="section-title">Cohort avg rate</h2>
            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={CHART_DATA}
                  margin={{ top: 4, right: 8, left: -12, bottom: 0 }}
                >
                  <CartesianGrid
                    stroke="#1E4A6E"
                    strokeDasharray="3 3"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="cohort"
                    tick={{ fill: "#B8C5D6", fontSize: 11 }}
                    axisLine={{ stroke: "#1E4A6E" }}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fill: "#B8C5D6", fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    domain={[5.5, 7.5]}
                    tickFormatter={(v) => `${v}%`}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "#0B2A4A",
                      border: "1px solid #1E4A6E",
                      fontSize: 11,
                      color: "#FFFFFF",
                    }}
                    labelStyle={{ color: "#B8C5D6" }}
                    formatter={(value) => [`${Number(value).toFixed(2)}%`, "Avg rate"]}
                  />
                  <Bar dataKey="avgRate" fill="#E85A9B" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
