/**
 * Side-panel PSA CPR + SDA/SDR CDR paths for every distinct schedule speed.
 */
import { useMemo } from "react";
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
import {
  buildSpeedChartRows,
  distinctPsaMultiples,
  distinctSdaMultiples,
  seriesForMultiples,
} from "./scenarioSpeeds";

/** Curve structure is visible by month 120; keep chart dense. */
const CHART_MONTHS = 120;

function pctTick(v) {
  if (v == null || Number.isNaN(Number(v))) return "";
  const pct = Number(v) * 100;
  if (pct >= 1) return `${pct.toFixed(1)}%`;
  if (pct >= 0.1) return `${pct.toFixed(2)}%`;
  return `${pct.toFixed(3)}%`;
}

function tipStyle() {
  return {
    background: "#0C0C0C",
    border: "1px solid #323232",
    borderRadius: 0,
    fontSize: 11,
    color: "#FCFCFC",
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
        {!data.length || !series.length ? (
          <p className="muted strat-chart-empty">No Speed Paths Loaded.</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={data}
              margin={{ top: 8, right: 10, left: 0, bottom: 4 }}
            >
              <CartesianGrid
                stroke="#323232"
                strokeDasharray="2 4"
                strokeOpacity={0.9}
              />
              <XAxis
                dataKey="month"
                type="number"
                domain={[1, CHART_MONTHS]}
                ticks={[1, 30, 60, 90, 120]}
                tick={{ fill: "#808080", fontSize: 10, fontFamily: FONT }}
                axisLine={{ stroke: "#464646" }}
                tickLine={{ stroke: "#464646" }}
                label={{
                  value: "Month",
                  position: "insideBottom",
                  offset: -2,
                  fill: "#808080",
                  fontSize: 10,
                  fontFamily: FONT,
                }}
              />
              <YAxis
                tickFormatter={pctTick}
                width={46}
                tick={{ fill: "#808080", fontSize: 10, fontFamily: FONT }}
                axisLine={{ stroke: "#464646" }}
                tickLine={{ stroke: "#464646" }}
                label={{
                  value: yLabel,
                  angle: -90,
                  position: "insideLeft",
                  offset: 8,
                  fill: "#808080",
                  fontSize: 10,
                  fontFamily: FONT,
                }}
              />
              <Tooltip
                contentStyle={tipStyle()}
                labelStyle={{ color: "#808080" }}
                labelFormatter={(m) => `Month ${m}`}
                formatter={(v, name) => [pctTick(v), name]}
              />
              <Legend
                verticalAlign="top"
                align="right"
                iconType="plainline"
                wrapperStyle={{
                  fontSize: 9,
                  fontFamily: FONT,
                  fontWeight: 300,
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
                  strokeWidth={1.25}
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
  const psaMultiples = useMemo(() => distinctPsaMultiples(), []);
  const sdaMultiples = useMemo(() => distinctSdaMultiples(), []);
  const psaSeries = useMemo(
    () => seriesForMultiples("psa", psaMultiples),
    [psaMultiples]
  );
  const sdaSeries = useMemo(
    () => seriesForMultiples("sda", sdaMultiples),
    [sdaMultiples]
  );
  const chartData = useMemo(
    () => buildSpeedChartRows(CHART_MONTHS, psaMultiples, sdaMultiples),
    [psaMultiples, sdaMultiples]
  );

  return (
    <aside className="scenario-speed-rail" aria-label="Scenario Speeds">
      <SpeedLineChart
        title={`PSA Speeds (CPR) · ${psaMultiples.length}`}
        data={chartData}
        series={psaSeries}
        yLabel="CPR"
      />
      <SpeedLineChart
        title={`SDA / SDR Speeds (CDR) · ${sdaMultiples.length}`}
        data={chartData}
        series={sdaSeries}
        yLabel="CDR"
      />
    </aside>
  );
}
