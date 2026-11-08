/**
 * Cohort-level portfolio-manager analytics (static). Not loan-strats cut views.
 * Joins k-proto cluster-tape (cohort / FICO / CLTV / RI) with Investor Tape
 * (UPB / state / risk flags) by loan id.
 */
import { memo, useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { FONT, chartPct, fmtInt, fmtLtv, fmtUpbShort } from "./cashflowGrid";
import {
  CLUSTER_COLORS,
  CLUSTER_ORDER,
  cohortLabel,
} from "./cohortLabels";

const GRID = "#323232";
const MUTED = "#808080";
const TEXT = "#FCFCFC";
const TICK = { fill: MUTED, fontSize: 9, fontFamily: FONT };

const TIP_STYLE = {
  background: "#0C0C0C",
  border: "1px solid #323232",
  borderRadius: 0,
  fontSize: 11,
  color: TEXT,
  fontFamily: FONT,
};

/** Short axis ticks for the three live cluster names. */
const SHORT = {
  [CLUSTER_ORDER[0]]: "LLTV Weak",
  [CLUSTER_ORDER[1]]: "HLTV Strong",
  [CLUSTER_ORDER[2]]: "HLTV Weak",
};

function shortCohort(code) {
  return SHORT[code] || code;
}

/**
 * Precompute once per tape load; selection only filters which cohorts render.
 * @param {Array} clusterLoans — from /cluster-tape.json (loanId, cluster, fico, cltv, refinanceIncentive)
 * @param {Array} asfLoans — Investor Tape (loan_id, current_loan_amount, state, …)
 */
export function buildCohortPmCache(clusterLoans, asfLoans) {
  const by = Object.fromEntries(
    CLUSTER_ORDER.map((c) => [
      c,
      {
        cohort: c,
        upb: 0,
        loans: 0,
        lowFicoUpb: 0,
        highCltvUpb: 0,
        ficoNum: 0,
        ficoDen: 0,
        cltvNum: 0,
        cltvDen: 0,
        byState: new Map(),
      },
    ])
  );
  let poolUpb = 0;

  const asfById = new Map();
  for (const row of asfLoans || []) {
    const id = row.loan_id || row.loanId;
    if (id) asfById.set(String(id), row);
  }

  const source =
    Array.isArray(clusterLoans) && clusterLoans.length
      ? clusterLoans
      : asfLoans || [];

  for (const loan of source) {
    const id = String(loan.loanId || loan.loan_id || "");
    const asf = id ? asfById.get(id) : null;
    const code = cohortLabel(loan.cluster || loan.cohort);
    const slot = by[code];
    if (!slot) continue;

    const upb = Number(
      asf?.current_loan_amount ?? loan.current_loan_amount ?? loan.upb
    ) || 0;
    if (!(upb > 0)) continue;
    poolUpb += upb;
    slot.upb += upb;
    slot.loans += 1;

    const fico = Number(loan.fico ?? asf?.original_fico ?? loan.original_fico);
    const cltv = Number(
      loan.cltv ?? asf?.current_cltv ?? asf?.original_cltv ?? loan.original_cltv
    );
    if (Number.isFinite(fico)) {
      slot.ficoNum += fico * upb;
      slot.ficoDen += upb;
      if (fico < 660) slot.lowFicoUpb += upb;
    }
    if (Number.isFinite(cltv)) {
      slot.cltvNum += cltv * upb;
      slot.cltvDen += upb;
      if (cltv >= 0.8) slot.highCltvUpb += upb;
    }

    const st =
      String(asf?.state || loan.state || "")
        .trim()
        .toUpperCase() || "—";
    slot.byState.set(st, (slot.byState.get(st) || 0) + upb);
  }

  return { by, poolUpb };
}

function activeCodes(selected) {
  const all =
    selected?.length === CLUSTER_ORDER.length &&
    CLUSTER_ORDER.every((c) => selected.includes(c));
  return all
    ? [...CLUSTER_ORDER]
    : (selected || []).filter((c) => CLUSTER_ORDER.includes(c));
}

function ChartCard({ title, children }) {
  return (
    <div className="cohort-pm-card">
      <h3 className="cohort-pm-card-title">{title}</h3>
      <div className="cohort-pm-card-body">{children}</div>
    </div>
  );
}

const CohortPmCharts = memo(function CohortPmCharts({ cache, selected }) {
  const codes = useMemo(() => activeCodes(selected), [selected]);

  const creditRows = useMemo(() => {
    return codes.map((c) => {
      const s = cache?.by?.[c];
      const upb = s?.upb || 0;
      return {
        cohort: c,
        label: shortCohort(c),
        lowFicoPct: upb > 0 ? ((s?.lowFicoUpb || 0) / upb) * 100 : 0,
        highCltvPct: upb > 0 ? ((s?.highCltvUpb || 0) / upb) * 100 : 0,
        waFico: s?.ficoDen ? s.ficoNum / s.ficoDen : null,
        waCltv: s?.cltvDen ? s.cltvNum / s.cltvDen : null,
      };
    });
  }, [cache, codes]);

  const geoRows = useMemo(() => {
    const totals = new Map();
    for (const c of codes) {
      const stMap = cache?.by?.[c]?.byState;
      if (!stMap) continue;
      for (const [st, upb] of stMap) {
        totals.set(st, (totals.get(st) || 0) + upb);
      }
    }
    const top = [...totals.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 15)
      .map(([st]) => st);
    return top.map((st) => {
      const row = { state: st };
      for (const c of CLUSTER_ORDER) {
        row[c] = codes.includes(c)
          ? cache?.by?.[c]?.byState?.get(st) || 0
          : 0;
      }
      return row;
    });
  }, [cache, codes]);

  if (!cache?.poolUpb) {
    return (
      <p className="muted cohort-pm-empty">No Cohort Analytics Loaded.</p>
    );
  }

  return (
    <div className="cohort-pm-grid" aria-label="Cohort Portfolio Analytics">
      <ChartCard title="Geographic Concentration By State × Cohort">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={geoRows}
            layout="vertical"
            margin={{ top: 4, right: 8, left: 4, bottom: 4 }}
          >
            <CartesianGrid stroke={GRID} strokeDasharray="2 4" />
            <XAxis
              type="number"
              tick={TICK}
              tickFormatter={(v) => fmtUpbShort(v)}
            />
            <YAxis type="category" dataKey="state" tick={TICK} width={28} />
            <Tooltip
              contentStyle={TIP_STYLE}
              formatter={(v, name) => [fmtUpbShort(v), name]}
            />
            <Legend wrapperStyle={{ fontSize: 10, color: MUTED }} />
            {codes.map((c) => (
              <Bar
                key={c}
                dataKey={c}
                stackId="geo"
                fill={CLUSTER_COLORS[c]}
                isAnimationActive={false}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <ChartCard title="Credit Risk Layering By Cohort">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={creditRows}
            margin={{ top: 8, right: 8, left: 0, bottom: 4 }}
          >
            <CartesianGrid stroke={GRID} strokeDasharray="2 4" />
            <XAxis dataKey="label" tick={TICK} interval={0} />
            <YAxis
              tick={TICK}
              tickFormatter={(v) => `${Math.round(v)}%`}
              width={36}
            />
            <Tooltip
              contentStyle={TIP_STYLE}
              formatter={(v, name) => {
                if (name === "lowFicoPct") {
                  return [chartPct(v, { alreadyPercent: true }), "FICO <660 UPB"];
                }
                if (name === "highCltvPct") {
                  return [
                    chartPct(v, { alreadyPercent: true }),
                    "CLTV ≥80% UPB",
                  ];
                }
                return [v, name];
              }}
              labelFormatter={(label, payload) => {
                const p = payload?.[0]?.payload;
                if (!p) return label;
                const fico = p.waFico != null ? fmtInt(p.waFico) : "—";
                const cltv = p.waCltv != null ? fmtLtv(p.waCltv) : "—";
                return `${p.cohort} · WA FICO ${fico} · WA CLTV ${cltv}`;
              }}
            />
            <Legend wrapperStyle={{ fontSize: 10, color: MUTED }} />
            <Bar
              dataKey="lowFicoPct"
              name="FICO <660 UPB %"
              fill="#c51d46"
              maxBarSize={28}
            />
            <Bar
              dataKey="highCltvPct"
              name="CLTV ≥80% UPB %"
              fill="#D4A017"
              maxBarSize={28}
            />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  );
});

export default CohortPmCharts;
