/**
 * Side-panel PSA CPR + SDA/SDR CDR paths from public/psa_sda_standards.csv.
 * Shows every scenario speed used in the grid (PSA 75/100/125, SDA 50/100/200).
 */
import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { FONT } from "./cashflowGrid";

const STANDARDS_URL = "/psa_sda_standards.csv";
/** Curve structure is visible by month 120; keep chart dense. */
const CHART_MONTHS = 120;

const PSA_SERIES = [
  { key: "psa_75_cpr", label: "75 PSA", color: "#4A5F7A" },
  { key: "psa_100_cpr", label: "100 PSA", color: "#FD9D24" },
  { key: "psa_125_cpr", label: "125 PSA", color: "#1F8A44" },
];

const SDA_SERIES = [
  { key: "sda_50_cdr", label: "50 SDA", color: "#4A5F7A" },
  { key: "sda_100_cdr", label: "100 SDA", color: "#FD9D24" },
  { key: "sda_200_cdr", label: "200 SDA", color: "#C51D46" },
];

function parseCsv(text) {
  const lines = String(text || "")
    .trim()
    .split(/\r?\n/)
    .filter(Boolean);
  if (lines.length < 2) return [];
  const headers = lines[0].split(",").map((h) => h.trim());
  const rows = [];
  for (let i = 1; i < lines.length; i += 1) {
    const cells = lines[i].split(",");
    const row = {};
    headers.forEach((h, idx) => {
      const raw = (cells[idx] ?? "").trim();
      row[h] = h === "month" ? Number(raw) : Number(raw);
    });
    rows.push(row);
  }
  return rows;
}

function pctTick(v) {
  if (v == null || Number.isNaN(Number(v))) return "";
  const pct = Number(v) * 100;
  if (pct >= 1) return `${pct.toFixed(1)}%`;
  if (pct >= 0.1) return `${pct.toFixed(2)}%`;
  return `${pct.toFixed(3)}%`;
}

function tipStyle() {
  return {
    background: "#FFFFFF",
    border: "1px solid #D0D7E2",
    borderRadius: 0,
    fontSize: 11,
    color: "#001A41",
    fontFamily: FONT,
  };
}

function SpeedLineChart({ title, data, series, yLabel }) {
  return (
    <div className="scenario-speed-panel">
      <div className="scenario-speed-head">
        <h3 className="scenario-speed-title">{title}</h3>
      </div>
      <div className="scenario-speed-chart">
        {!data.length ? (
          <p className="muted strat-chart-empty">No Speed Paths Loaded.</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={data}
              margin={{ top: 8, right: 10, left: 0, bottom: 4 }}
            >
              <CartesianGrid
                stroke="#D0D7E2"
                strokeDasharray="2 4"
                strokeOpacity={0.9}
              />
              <XAxis
                dataKey="month"
                type="number"
                domain={[1, CHART_MONTHS]}
                ticks={[1, 30, 60, 90, 120]}
                tick={{ fill: "#4A5F7A", fontSize: 10, fontFamily: FONT }}
                axisLine={{ stroke: "#8A9BB0" }}
                tickLine={{ stroke: "#8A9BB0" }}
                label={{
                  value: "Month",
                  position: "insideBottom",
                  offset: -2,
                  fill: "#4A5F7A",
                  fontSize: 10,
                  fontFamily: FONT,
                }}
              />
              <YAxis
                tickFormatter={pctTick}
                width={46}
                tick={{ fill: "#4A5F7A", fontSize: 10, fontFamily: FONT }}
                axisLine={{ stroke: "#8A9BB0" }}
                tickLine={{ stroke: "#8A9BB0" }}
                label={{
                  value: yLabel,
                  angle: -90,
                  position: "insideLeft",
                  offset: 8,
                  fill: "#4A5F7A",
                  fontSize: 10,
                  fontFamily: FONT,
                }}
              />
              <Tooltip
                contentStyle={tipStyle()}
                labelStyle={{ color: "#4A5F7A" }}
                labelFormatter={(m) => `Month ${m}`}
                formatter={(v, name) => [pctTick(v), name]}
              />
              <Legend
                verticalAlign="top"
                align="right"
                iconType="plainline"
                wrapperStyle={{
                  fontSize: 10,
                  fontFamily: FONT,
                  paddingBottom: 4,
                }}
              />
              {series.map((s) => (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.label}
                  stroke={s.color}
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

export default function ScenarioSpeedCharts() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(STANDARDS_URL);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const text = await res.text();
        if (cancelled) return;
        setRows(parseCsv(text));
        setError(null);
      } catch (e) {
        if (!cancelled) {
          setRows([]);
          setError(e?.message || "Load Failed");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const chartData = useMemo(
    () => (rows || []).filter((r) => Number(r.month) <= CHART_MONTHS),
    [rows]
  );

  return (
    <aside className="scenario-speed-rail" aria-label="Scenario Speeds">
      {error && (
        <p className="muted strat-chart-empty">Speeds: {error}</p>
      )}
      <SpeedLineChart
        title="PSA Speeds (CPR)"
        data={chartData}
        series={PSA_SERIES}
        yLabel="CPR"
      />
      <SpeedLineChart
        title="SDA / SDR Speeds (CDR)"
        data={chartData}
        series={SDA_SERIES}
        yLabel="CDR"
      />
    </aside>
  );
}
