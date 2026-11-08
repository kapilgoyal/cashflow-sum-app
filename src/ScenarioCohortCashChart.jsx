/**
 * Top Scenarios results row:
 *  Left  — Total cash · Cohort Avg (monthly)
 *  Right — Cumulative Principal Received (sched + prepay + recovery)
 *  WAL on schedule table; monthly Recovery in component strip.
 */
import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiUrl } from "./apiBase";
import { FONT } from "./cashflowGrid";
import {
  CLUSTER_COLORS,
  CLUSTER_ORDER,
  cohortLabel,
} from "./cohortLabels";

const POOL_COLOR = "#fd9d24";
const PRIN_FIELDS = ["scheduled_principal", "prepay", "recovery"];
const TICK = { fill: "#808080", fontSize: 8, fontFamily: FONT };
const AXIS = { stroke: "#464646" };

function moneyTick(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "";
  const abs = Math.abs(n);
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
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

function avgLabel(avg, c) {
  return avg[c] || avg[cohortLabel(c)];
}

function buildFieldRows(cohortAvg, field) {
  if (!cohortAvg || typeof cohortAvg !== "object") return [];
  const byCohort = {};
  let maxM = 0;
  for (const c of CLUSTER_ORDER) {
    const cell = avgLabel(cohortAvg, c);
    const map = new Map();
    for (const row of cell?.months || []) {
      const m = Number(row.month);
      if (!Number.isFinite(m)) continue;
      map.set(m, Number(row[field] || 0));
      if (m > maxM) maxM = m;
    }
    byCohort[c] = map;
  }
  if (!maxM) return [];

  const rows = [];
  for (let m = 1; m <= maxM; m += 1) {
    const out = { month: m, Pool: 0 };
    for (const c of CLUSTER_ORDER) {
      const v = Number(byCohort[c]?.get(m) || 0);
      out[c] = v;
      out.Pool += v;
    }
    rows.push(out);
  }
  let last = rows.length - 1;
  while (last > 0 && !(Number(rows[last]?.Pool) > 0.5)) last -= 1;
  return rows.slice(0, last + 1);
}

function buildCumulativePrincipalRows(cohortAvg) {
  if (!cohortAvg || typeof cohortAvg !== "object") return [];
  const byCohort = {};
  let maxM = 0;
  for (const c of CLUSTER_ORDER) {
    const cell = avgLabel(cohortAvg, c);
    const map = new Map();
    for (const row of cell?.months || []) {
      const m = Number(row.month);
      if (!Number.isFinite(m)) continue;
      let prin = 0;
      for (const f of PRIN_FIELDS) prin += Number(row[f] || 0);
      map.set(m, prin);
      if (m > maxM) maxM = m;
    }
    byCohort[c] = map;
  }
  if (!maxM) return [];

  const cum = Object.fromEntries(CLUSTER_ORDER.map((c) => [c, 0]));
  const rows = [];
  for (let m = 1; m <= maxM; m += 1) {
    const out = { month: m, Pool: 0 };
    for (const c of CLUSTER_ORDER) {
      cum[c] += Number(byCohort[c]?.get(m) || 0);
      out[c] = cum[c];
      out.Pool += cum[c];
    }
    rows.push(out);
  }
  let last = rows.length - 1;
  while (last > 1) {
    const delta = Number(rows[last].Pool) - Number(rows[last - 1].Pool);
    if (delta > 0.5) break;
    last -= 1;
  }
  return rows.slice(0, last + 1);
}

function poolFlowStats(data) {
  let m1 = 0;
  let peak = 0;
  let end = 0;
  for (const row of data) {
    const v = Number(row.Pool || 0);
    if (!Number.isFinite(v)) continue;
    if (Number(row.month) === 1) m1 = v;
    if (v > peak) peak = v;
    end = v;
  }
  return { m1, peak, end };
}

function CohortLines({ series }) {
  return (
    <>
      {series.map((s) => (
        <Line
          key={s.key}
          type="monotone"
          dataKey={s.key}
          name={s.label}
          stroke={s.color}
          strokeWidth={1.4}
          dot={false}
          isAnimationActive={false}
        />
      ))}
      <Line
        type="monotone"
        dataKey="Pool"
        name="Pool"
        stroke={POOL_COLOR}
        strokeWidth={1.15}
        strokeDasharray="4 3"
        dot={false}
        isAnimationActive={false}
      />
    </>
  );
}

function ChartFrame({
  title,
  titleTip,
  stat,
  loading,
  empty,
  data,
  horizon,
  monthTicks,
  series,
  yWidth = 48,
}) {
  return (
    <div className="scenario-component-chart" aria-label={title}>
      <div className="scenario-cash-head">
        <h4
          className="scenario-cash-title scenario-component-title"
          title={titleTip || title}
        >
          {title}
        </h4>
        <p className="scenario-component-stat">{stat}</p>
      </div>
      <div className="scenario-component-chart-body">
        {loading ? (
          <p className="muted strat-chart-empty">Calculating…</p>
        ) : empty || !data.length ? (
          <p className="muted strat-chart-empty">{empty || "No Data."}</p>
        ) : (
          <ResponsiveContainer width="100%" height="100%" minHeight={90}>
            <LineChart
              data={data}
              margin={{ top: 4, right: 6, left: 0, bottom: 0 }}
            >
              <CartesianGrid
                stroke="#323232"
                strokeDasharray="2 4"
                strokeOpacity={0.9}
              />
              <XAxis
                dataKey="month"
                type="number"
                domain={[1, horizon]}
                ticks={monthTicks}
                tick={TICK}
                axisLine={AXIS}
                tickLine={AXIS}
              />
              <YAxis
                tickFormatter={moneyTick}
                width={yWidth}
                tickCount={4}
                tick={TICK}
                axisLine={AXIS}
                tickLine={AXIS}
                domain={[0, "auto"]}
              />
              <Tooltip
                contentStyle={tipStyle()}
                labelStyle={{ color: "#808080" }}
                labelFormatter={(m) => `Month ${m}`}
                formatter={(v, name) => [moneyTick(v), name]}
              />
              <CohortLines series={series} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

export default function ScenarioCohortCashChart() {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        let res = await fetch(apiUrl("/api/cashflows/scenario-grid")).catch(
          () => null
        );
        if (!res || !res.ok) {
          res = await fetch("/scenario-grid-cashflow.json").catch(() => null);
        }
        if (!res || !res.ok) {
          throw new Error("27-scenario cashflow not loaded yet");
        }
        const data = await res.json();
        if (!cancelled) setPayload(data);
      } catch (err) {
        if (!cancelled) setError(err.message || String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const series = useMemo(
    () =>
      CLUSTER_ORDER.map((c) => ({
        key: c,
        label: cohortLabel(c),
        color: CLUSTER_COLORS[c],
      })),
    []
  );

  const totalData = useMemo(
    () => buildFieldRows(payload?.cohort_avg, "total_cash"),
    [payload]
  );
  const cumPrinData = useMemo(
    () => buildCumulativePrincipalRows(payload?.cohort_avg),
    [payload]
  );

  const horizon = Math.max(
    totalData.length ? totalData[totalData.length - 1].month : 0,
    cumPrinData.length ? cumPrinData[cumPrinData.length - 1].month : 0,
    payload?.horizon_months || 0,
    1
  );

  const totalStats = useMemo(() => poolFlowStats(totalData), [totalData]);
  const cumStats = useMemo(() => poolFlowStats(cumPrinData), [cumPrinData]);

  const monthTicks = [1, 60, 120, 180, 240, horizon]
    .filter((t) => t <= horizon)
    .filter((t, i, a) => a.indexOf(t) === i);

  const empty = error || null;

  return (
    <div
      className="scenario-avg-row"
      aria-label="Cohort Avg Total + Cumulative Principal"
    >
      <ChartFrame
        title="Total Cash"
        titleTip="Total Cashflow · Cohort Avg · 3 Cohorts + Pool"
        stat={
          loading
            ? "…"
            : totalData.length
              ? `M1 ${moneyTick(totalStats.m1)} · Pk ${moneyTick(totalStats.peak)}`
              : "—"
        }
        loading={loading}
        empty={empty}
        data={totalData}
        horizon={horizon}
        monthTicks={monthTicks}
        series={series}
        yWidth={48}
      />
      <ChartFrame
        title="Cum Prin"
        titleTip="Cumulative principal received · sched + prepay + recovery"
        stat={
          loading
            ? "…"
            : cumPrinData.length
              ? `M1 ${moneyTick(cumStats.m1)} · Σ ${moneyTick(cumStats.end)}`
              : "—"
        }
        loading={loading}
        empty={empty}
        data={cumPrinData}
        horizon={horizon}
        monthTicks={monthTicks}
        series={series}
        yWidth={48}
      />
    </div>
  );
}
