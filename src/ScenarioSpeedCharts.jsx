/**
 * PSA CPR + SDA CDR paths — same tile style as Sched / Prepay / Recovery charts.
 */
import { useMemo } from "react";
import {
  CartesianGrid,
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

function seriesPeak(data, series) {
  let peak = 0;
  for (const row of data) {
    for (const s of series) {
      const v = Number(row[s.key] || 0);
      if (v > peak) peak = v;
    }
  }
  return peak;
}

function SpeedLineChart({ shortTitle, fullTitle, data, series, yLabel }) {
  const peak = useMemo(() => seriesPeak(data, series), [data, series]);

  return (
    <div className="scenario-component-chart" aria-label={fullTitle}>
      <div className="scenario-cash-head">
        <h4
          className="scenario-cash-title scenario-component-title"
          title={fullTitle}
        >
          {shortTitle}
        </h4>
        <p
          className="scenario-component-stat"
          title={`${series.length} paths · peak ${yLabel}`}
        >
          {data.length
            ? `${series.length} · Pk ${pctTick(peak)}`
            : "—"}
        </p>
      </div>
      <div className="scenario-component-chart-body">
        {!data.length || !series.length ? (
          <p className="muted strat-chart-empty">No Speed Paths Loaded.</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%" minHeight={90}>
            <LineChart
              data={data}
              margin={{ top: 2, right: 4, left: 0, bottom: 0 }}
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
                tick={{ fill: "#808080", fontSize: 8, fontFamily: FONT }}
                axisLine={{ stroke: "#464646" }}
                tickLine={{ stroke: "#464646" }}
              />
              <YAxis
                tickFormatter={pctTick}
                width={40}
                tickCount={4}
                tick={{ fill: "#808080", fontSize: 8, fontFamily: FONT }}
                axisLine={{ stroke: "#464646" }}
                tickLine={{ stroke: "#464646" }}
                domain={[0, "auto"]}
              />
              <Tooltip
                contentStyle={tipStyle()}
                labelStyle={{ color: "#808080" }}
                labelFormatter={(m) => `Month ${m}`}
                formatter={(v, name) => [pctTick(v), name]}
                itemSorter={(item) => -Number(item.value || 0)}
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
        shortTitle="PSA CPR"
        fullTitle={`PSA Speeds (CPR) · ${psaMultiples.length}`}
        data={chartData}
        series={psaSeries}
        yLabel="CPR"
      />
      <SpeedLineChart
        shortTitle="SDA CDR"
        fullTitle={`SDA / SDR Speeds (CDR) · ${sdaMultiples.length}`}
        data={chartData}
        series={sdaSeries}
        yLabel="CDR"
      />
    </aside>
  );
}
