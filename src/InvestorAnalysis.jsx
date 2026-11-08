/**
 * Portfolio Manager Investor Analysis — Bloomberg Terminal dark surface.
 * UPB-weighted; decimals 0–1; omit sections without data; never invent PD.
 */
import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiUrl } from "./apiBase";
import {
  DataGrid,
  StatusBanner,
  fmtInt,
  fmtLtv,
  chartNum,
  chartPct,
  fmtNum,
  fmtPct,
  fmtUpbShort,
  fmtWac,
  ltvCol,
  moneyCol,
} from "./cashflowGrid";
import { StateChoropleth } from "./UsChoropleth";

/* Bloomberg Terminal palette (local to this view; parallel theme worker owns globals). */
const BB = {
  bg: "#000000",
  panel: "#212026",
  text: "#FCFCFC",
  muted: "#808080",
  accent: "#FD9D24",
  accentBright: "#FCA024",
  hairline: "#585858",
  empty: "#1A1A1A",
  up: "#40B065",
  down: "#C41E3A",
  font: '"IBM Plex Mono", "Consolas", "Courier New", monospace',
};

const MAP_PALETTE = {
  low: "#2A2418",
  high: "#FD9D24",
  empty: "#121212",
  stroke: "#303030",
};

const COHORT_COLORS = ["#FD9D24", "#40B065", "#5B8DEF", "#C41E3A"];

const tick = {
  fill: BB.muted,
  fontSize: 10,
  fontFamily: BB.font,
};

function Section({ title, viz, children }) {
  return (
    <section className="ia-panel">
      <header className="ia-panel-head">
        <h3 className="ia-panel-title">{title}</h3>
        {viz ? <span className="ia-panel-viz">{viz}</span> : null}
      </header>
      <div className="ia-panel-body">{children}</div>
    </section>
  );
}

function MatrixHeat({
  cells,
  rowKey,
  colKey,
  rows,
  cols,
  valueKey = "upb",
  formatCell,
  ariaLabel,
}) {
  const max = Math.max(1, ...cells.map((c) => Number(c[valueKey]) || 0));
  return (
    <div className="ia-heatmap" role="img" aria-label={ariaLabel}>
      <div className="ia-heatmap-corner" />
      {cols.map((c) => (
        <div key={`h-${c}`} className="ia-heatmap-axis">
          {c}
        </div>
      ))}
      {rows.map((r) => (
        <div key={r} className="ia-heatmap-row">
          <div className="ia-heatmap-axis ia-heatmap-y">{r}</div>
          {cols.map((c) => {
            const cell = cells.find((x) => x[rowKey] === r && x[colKey] === c);
            const v = cell ? Number(cell[valueKey]) || 0 : 0;
            const t = v / max;
            const bg =
              v > 0
                ? `rgba(253, 157, 36, ${0.12 + t * 0.88})`
                : BB.empty;
            return (
              <div
                key={`${r}-${c}`}
                className="ia-heatmap-cell"
                style={{
                  background: bg,
                  color: t > 0.55 ? BB.bg : BB.text,
                }}
                title={
                  cell
                    ? `${r} × ${c}: ${
                        formatCell
                          ? formatCell(cell)
                          : `${fmtUpbShort(cell.upb)} · ${fmtInt(cell.loan_count)}`
                      }`
                    : `${r} × ${c}: —`
                }
              >
                {cell?.loan_count ? cell.loan_count : ""}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

const largeLoanCols = [
  { headerName: "Cohort", field: "cohort_display", minWidth: 120 },
  moneyCol("upb", "UPB", 110),
  {
    headerName: "FICO",
    field: "original_fico",
    width: 72,
    valueFormatter: (p) => fmtInt(p.value),
    cellClass: "cf-num",
  },
  {
    headerName: "CLTV",
    field: "original_cltv",
    width: 72,
    valueFormatter: (p) => fmtPct(p.value, 0),
    cellClass: "cf-num",
  },
  { headerName: "State", field: "state", width: 64 },
  { headerName: "Occupancy", field: "occupancy", minWidth: 100 },
  { headerName: "Purpose", field: "loan_purpose", minWidth: 120 },
  { headerName: "Documentation", field: "documentation_type", minWidth: 140 },
];

export default function InvestorAnalysis() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [payload, setPayload] = useState(null);
  const [cohortFilter, setCohortFilter] = useState([]);
  const [hpaIdx, setHpaIdx] = useState(3); // default 0% among HPA_SHOCKS
  const [mapState, setMapState] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const qs =
          cohortFilter.length === 1
            ? `?cohort=${encodeURIComponent(cohortFilter[0])}`
            : cohortFilter.length > 1
              ? `?cohort=${encodeURIComponent(cohortFilter.join("|"))}`
              : "";
        const res = await fetch(apiUrl(`/api/asf/investor-analysis${qs}`));
        if (!res.ok) throw new Error(await res.text());
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
  }, [cohortFilter]);

  const sections = payload?.sections || {};
  const kpis = payload?.kpis || {};
  const cohortsMeta = payload?.cohorts || [];

  const scoreRows = sections.scorecard?.rows || [];
  const scoreChart = useMemo(() => {
    return [
      {
        metric: "WA FICO",
        ...Object.fromEntries(
          scoreRows.map((r) => [r.cohort_display, r.wa_fico])
        ),
      },
      {
        metric: "WA CLTV %",
        ...Object.fromEntries(
          scoreRows.map((r) => [
            r.cohort_display,
            r.wa_cltv != null ? r.wa_cltv * 100 : null,
          ])
        ),
      },
      {
        metric: "WAC %",
        ...Object.fromEntries(
          scoreRows.map((r) => [
            r.cohort_display,
            r.wac != null ? r.wac * 100 : null,
          ])
        ),
      },
      {
        metric: "WA RI",
        ...Object.fromEntries(
          scoreRows.map((r) => [r.cohort_display, r.wa_ri])
        ),
      },
    ];
  }, [scoreRows]);

  const hpaShocks = sections.hpa_stress?.shocks || [];
  useEffect(() => {
    if (!hpaShocks.length) return;
    const zero = hpaShocks.findIndex((s) => s.hpa === 0);
    if (zero >= 0) setHpaIdx(zero);
  }, [hpaShocks.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const hpaLine = useMemo(
    () =>
      hpaShocks.map((s) => ({
        hpa_pct: Math.round(s.hpa * 100),
        wa_cltv_pct: s.wa_cltv != null ? s.wa_cltv * 100 : null,
        high_share_pct:
          s.high_cltv_upb_share != null ? s.high_cltv_upb_share * 100 : null,
      })),
    [hpaShocks]
  );

  const activeHpa = hpaShocks[hpaIdx] || hpaShocks.find((s) => s.hpa === 0);

  const sevCohortBars = useMemo(
    () =>
      (sections.loss_severity?.by_cohort || []).map((r) => ({
        cohort: r.cohort_display,
        severity_pct: r.wa_severity != null ? r.wa_severity * 100 : null,
        recovery_pct: r.wa_recovery != null ? r.wa_recovery * 100 : null,
      })),
    [sections.loss_severity]
  );

  const tipStyle = {
    background: BB.panel,
    border: `1px solid ${BB.hairline}`,
    borderRadius: 0,
    fontSize: 11,
    color: BB.text,
    fontFamily: BB.font,
  };

  if (loading) return <p className="ia-muted">Loading Investor Analysis…</p>;
  if (error)
    return <StatusBanner tone="error">Investor Analysis: {error}</StatusBanner>;
  if (!payload) return null;

  const toggleCohort = (id) => {
    setCohortFilter((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  return (
    <section className="section section-fill section-investor-analysis">
      <div className="ia-topbar">
        <div className="ia-kpi-strip" role="toolbar" aria-label="Pool KPIs">
          <div className="ia-kpi">
            <span className="ia-kpi-label">Loans</span>
            <span className="ia-kpi-value">{fmtInt(kpis.loan_count)}</span>
          </div>
          <div className="ia-kpi">
            <span className="ia-kpi-label">UPB</span>
            <span className="ia-kpi-value">{fmtUpbShort(kpis.upb)}</span>
          </div>
          <div className="ia-kpi">
            <span className="ia-kpi-label">WAC</span>
            <span className="ia-kpi-value">
              {kpis.wac != null ? fmtWac(kpis.wac) : "—"}
            </span>
          </div>
          <div className="ia-kpi">
            <span className="ia-kpi-label">WA FICO</span>
            <span className="ia-kpi-value">
              {kpis.wa_fico != null ? fmtInt(kpis.wa_fico) : "—"}
            </span>
          </div>
          <div className="ia-kpi">
            <span className="ia-kpi-label">WA CLTV</span>
            <span className="ia-kpi-value">
              {kpis.wa_cltv != null ? fmtPct(kpis.wa_cltv, 0) : "—"}
            </span>
          </div>
          <div className="ia-kpi">
            <span className="ia-kpi-label">WA RI</span>
            <span className="ia-kpi-value">
              {kpis.wa_ri != null ? chartNum(kpis.wa_ri) : "—"}
            </span>
          </div>
        </div>
        <div className="ia-filters" role="group" aria-label="Cohort Filter">
          <button
            type="button"
            className={`ia-chip${!cohortFilter.length ? " is-active" : ""}`}
            onClick={() => setCohortFilter([])}
          >
            All Cohorts
          </button>
          {cohortsMeta.map((c) => (
            <button
              key={c.id}
              type="button"
              className={`ia-chip${
                cohortFilter.includes(c.id) ? " is-active" : ""
              }`}
              onClick={() => toggleCohort(c.id)}
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>

      <div className="ia-grid">
        {sections.scorecard?.available && (
          <Section title="Cohort Credit Quality" viz="Grouped Bars">
            <div className="ia-chart ia-chart-tall">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={scoreChart}
                  margin={{ top: 8, right: 12, left: 0, bottom: 4 }}
                >
                  <CartesianGrid stroke={BB.hairline} strokeDasharray="2 4" />
                  <XAxis dataKey="metric" tick={tick} />
                  <YAxis tick={tick} />
                  <Tooltip contentStyle={tipStyle} />
                  <Legend
                    wrapperStyle={{ fontFamily: BB.font, fontSize: 10, color: BB.muted }}
                  />
                  {scoreRows.map((r, i) => (
                    <Bar
                      key={r.cohort_display}
                      dataKey={r.cohort_display}
                      fill={COHORT_COLORS[i % COHORT_COLORS.length]}
                      maxBarSize={28}
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="ia-scorecard-table">
              <table>
                <thead>
                  <tr>
                    <th>Cohort</th>
                    <th>Loans</th>
                    <th>UPB</th>
                    <th>Share</th>
                    <th>WA FICO</th>
                    <th>WA CLTV</th>
                    <th>WAC</th>
                    <th>WA RI</th>
                  </tr>
                </thead>
                <tbody>
                  {scoreRows.map((r) => (
                    <tr key={r.cohort}>
                      <td>{r.cohort_display}</td>
                      <td className="ia-num">{fmtInt(r.loan_count)}</td>
                      <td className="ia-num">{fmtUpbShort(r.upb)}</td>
                      <td className="ia-num">
                        {r.upb_share != null ? fmtPct(r.upb_share, 1) : "—"}
                      </td>
                      <td className="ia-num">
                        {r.wa_fico != null ? fmtInt(r.wa_fico) : "—"}
                      </td>
                      <td className="ia-num">
                        {r.wa_cltv != null ? fmtPct(r.wa_cltv, 0) : "—"}
                      </td>
                      <td className="ia-num">
                        {r.wac != null ? fmtWac(r.wac) : "—"}
                      </td>
                      <td className="ia-num">
                        {r.wa_ri != null ? chartNum(r.wa_ri) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        )}

        {sections.fico_cltv?.available && (
          <Section title="FICO × CLTV" viz="Heatmap">
            <MatrixHeat
              cells={sections.fico_cltv.cells}
              rowKey="fico_band"
              colKey="cltv_band"
              rows={sections.fico_cltv.fico_bands}
              cols={sections.fico_cltv.cltv_bands}
              ariaLabel="FICO By CLTV Heatmap"
            />
          </Section>
        )}

        {sections.hpa_stress?.available && (
          <Section title="HPA Stress — CLTV Migration" viz="Line + Slider">
            <label className="ia-slider-label">
              HPA{" "}
              <strong>
                {activeHpa
                  ? `${activeHpa.hpa >= 0 ? "+" : ""}${Math.round(
                      activeHpa.hpa * 100
                    )}%`
                  : "0%"}
              </strong>
              <input
                type="range"
                className="ia-slider"
                min={0}
                max={Math.max(0, hpaShocks.length - 1)}
                step={1}
                value={hpaIdx}
                onChange={(e) => setHpaIdx(Number(e.target.value))}
                aria-label="HPA Shock"
              />
            </label>
            <div className="ia-chart">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={hpaLine}
                  margin={{ top: 8, right: 16, left: 0, bottom: 4 }}
                >
                  <CartesianGrid stroke={BB.hairline} strokeDasharray="2 4" />
                  <XAxis
                    dataKey="hpa_pct"
                    tick={tick}
                    tickFormatter={(v) => `${v}%`}
                    label={{
                      value: "HPA",
                      position: "insideBottom",
                      offset: -2,
                      fill: BB.muted,
                      fontSize: 10,
                      fontFamily: BB.font,
                    }}
                  />
                  <YAxis
                    yAxisId="cltv"
                    tick={tick}
                    tickFormatter={(v) => `${v}%`}
                  />
                  <YAxis
                    yAxisId="share"
                    orientation="right"
                    tick={tick}
                    tickFormatter={(v) => `${v}%`}
                  />
                  <Tooltip
                    contentStyle={tipStyle}
                    formatter={(v, name) => [
                      chartPct(v, { alreadyPercent: true }),
                      name === "wa_cltv_pct" ? "WA CLTV" : "≥80% CLTV UPB",
                    ]}
                    labelFormatter={(v) => `HPA ${v}%`}
                  />
                  <Legend
                    wrapperStyle={{
                      fontFamily: BB.font,
                      fontSize: 10,
                      color: BB.muted,
                    }}
                  />
                  <Line
                    yAxisId="cltv"
                    type="monotone"
                    dataKey="wa_cltv_pct"
                    name="WA CLTV"
                    stroke={BB.accent}
                    strokeWidth={2}
                    dot={{ r: 3, fill: BB.accent }}
                    isAnimationActive={false}
                  />
                  <Line
                    yAxisId="share"
                    type="monotone"
                    dataKey="high_share_pct"
                    name="≥80% CLTV UPB"
                    stroke={BB.down}
                    strokeWidth={2}
                    strokeDasharray="4 3"
                    dot={{ r: 3, fill: BB.down }}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            {activeHpa?.bands?.length ? (
              <div className="ia-chart ia-chart-short">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={activeHpa.bands.filter((b) => b.bucket !== "missing")}
                    margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid stroke={BB.hairline} strokeDasharray="2 4" />
                    <XAxis dataKey="bucket" tick={tick} />
                    <YAxis
                      tick={tick}
                      tickFormatter={(v) => fmtUpbShort(v)}
                    />
                    <Tooltip
                      contentStyle={tipStyle}
                      formatter={(v) => fmtUpbShort(v)}
                    />
                    <Bar dataKey="upb" fill={BB.accent} maxBarSize={36}>
                      {activeHpa.bands
                        .filter((b) => b.bucket !== "missing")
                        .map((b) => (
                          <Cell
                            key={b.bucket}
                            fill={
                              b.bucket === "80-90" || b.bucket === "90+"
                                ? BB.down
                                : BB.accent
                            }
                          />
                        ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : null}
          </Section>
        )}

        {sections.affordability?.available && (
          <Section title="Affordability / Documentation" viz="Histogram + Donut">
            <div className="ia-split">
              <div className="ia-chart">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={(sections.affordability.dti || []).filter(
                      (r) => r.bucket !== "missing"
                    )}
                    margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid stroke={BB.hairline} strokeDasharray="2 4" />
                    <XAxis dataKey="bucket" tick={tick} />
                    <YAxis
                      tick={tick}
                      tickFormatter={(v) => fmtUpbShort(v)}
                    />
                    <Tooltip
                      contentStyle={tipStyle}
                      formatter={(v) => fmtUpbShort(v)}
                      labelFormatter={(l) => `DTI ${l}`}
                    />
                    <Bar dataKey="upb" fill="#5B8DEF" maxBarSize={32} name="DTI UPB" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="ia-chart">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={sections.affordability.documentation || []}
                      dataKey="upb"
                      nameKey="bucket"
                      cx="50%"
                      cy="50%"
                      innerRadius="42%"
                      outerRadius="70%"
                      paddingAngle={1}
                      isAnimationActive={false}
                    >
                      {(sections.affordability.documentation || []).map(
                        (row, i) => (
                          <Cell
                            key={row.bucket}
                            fill={COHORT_COLORS[i % COHORT_COLORS.length]}
                          />
                        )
                      )}
                    </Pie>
                    <Tooltip
                      contentStyle={tipStyle}
                      formatter={(v) => fmtUpbShort(v)}
                    />
                    <Legend
                      wrapperStyle={{
                        fontFamily: BB.font,
                        fontSize: 10,
                        color: BB.muted,
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
            <p className="ia-meta">
              DTI Coverage{" "}
              {sections.affordability.dti_coverage?.pct != null
                ? fmtPct(sections.affordability.dti_coverage.pct, 0)
                : "—"}
              {" · "}
              DSCR Coverage{" "}
              {sections.affordability.dscr_coverage?.pct != null
                ? fmtPct(sections.affordability.dscr_coverage.pct, 0)
                : "—"}
            </p>
          </Section>
        )}

        {sections.mix?.available && (
          <Section
            title="Occupancy / Purpose / Large Loans"
            viz="Stacked Bars + Table"
          >
            <div className="ia-split">
              <div className="ia-chart">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={sections.mix.occupancy || []}
                    layout="vertical"
                    margin={{ top: 8, right: 8, left: 8, bottom: 0 }}
                  >
                    <CartesianGrid stroke={BB.hairline} strokeDasharray="2 4" />
                    <XAxis
                      type="number"
                      tick={tick}
                      tickFormatter={(v) => fmtUpbShort(v)}
                    />
                    <YAxis
                      type="category"
                      dataKey="bucket"
                      width={100}
                      tick={tick}
                    />
                    <Tooltip
                      contentStyle={tipStyle}
                      formatter={(v) => fmtUpbShort(v)}
                    />
                    <Bar dataKey="upb" fill={BB.up} maxBarSize={22} name="Occupancy" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="ia-chart">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={sections.mix.loan_purpose || []}
                    layout="vertical"
                    margin={{ top: 8, right: 8, left: 8, bottom: 0 }}
                  >
                    <CartesianGrid stroke={BB.hairline} strokeDasharray="2 4" />
                    <XAxis
                      type="number"
                      tick={tick}
                      tickFormatter={(v) => fmtUpbShort(v)}
                    />
                    <YAxis
                      type="category"
                      dataKey="bucket"
                      width={110}
                      tick={tick}
                    />
                    <Tooltip
                      contentStyle={tipStyle}
                      formatter={(v) => fmtUpbShort(v)}
                    />
                    <Bar
                      dataKey="upb"
                      fill={BB.accentBright}
                      maxBarSize={22}
                      name="Purpose"
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="ia-table-wrap">
              <DataGrid
                rowData={sections.mix.large_loans || []}
                columnDefs={largeLoanCols}
                heightClass="grid-wrap-ia-loans"
                getRowId={(p) =>
                  `${p.data.cohort_display}-${p.data.upb}-${p.data.state}-${p.data.original_fico}`
                }
              />
            </div>
          </Section>
        )}

        {sections.geo?.available && (
          <Section title="Geographic Concentration" viz="US Map">
            <div className="ia-geo">
              <StateChoropleth
                rows={sections.geo.states}
                metric="upb"
                selected={mapState}
                onSelect={(abbr) =>
                  setMapState((prev) => (prev === abbr ? null : abbr))
                }
                fmtTip={(v) => fmtUpbShort(v)}
                palette={MAP_PALETTE}
              />
              <ol className="ia-top-states">
                {(sections.geo.top_states || []).map((s) => (
                  <li key={s.bucket}>
                    <button
                      type="button"
                      className={`ia-top-state${
                        mapState === s.bucket ? " is-active" : ""
                      }`}
                      onClick={() =>
                        setMapState((prev) =>
                          prev === s.bucket ? null : s.bucket
                        )
                      }
                    >
                      <span>{s.bucket}</span>
                      <span className="ia-num">{fmtUpbShort(s.upb)}</span>
                    </button>
                  </li>
                ))}
              </ol>
            </div>
          </Section>
        )}

        {sections.ri_seasoning?.available && (
          <Section title="Refinance Incentive × Seasoning" viz="Heatmap">
            <MatrixHeat
              cells={sections.ri_seasoning.cells}
              rowKey="ri_band"
              colKey="age_band"
              rows={sections.ri_seasoning.ri_bands}
              cols={sections.ri_seasoning.age_bands}
              ariaLabel="RI By Seasoning Heatmap"
            />
          </Section>
        )}

        {sections.loss_severity?.available && (
          <Section title="Loss Severity (Assumptions)" viz="Bars + Heat">
            <p className="ia-meta">
              Urban/Freddie severity · pool WA severity{" "}
              {sections.loss_severity.pool_wa_severity != null
                ? fmtPct(sections.loss_severity.pool_wa_severity, 1)
                : "—"}
              {" · "}
              recovery{" "}
              {sections.loss_severity.pool_wa_recovery != null
                ? fmtPct(sections.loss_severity.pool_wa_recovery, 1)
                : "—"}
              {" · "}
              no PD
            </p>
            <div className="ia-chart">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={sevCohortBars}
                  margin={{ top: 8, right: 12, left: 0, bottom: 4 }}
                >
                  <CartesianGrid stroke={BB.hairline} strokeDasharray="2 4" />
                  <XAxis dataKey="cohort" tick={tick} />
                  <YAxis tick={tick} tickFormatter={(v) => `${v}%`} />
                  <Tooltip
                    contentStyle={tipStyle}
                    formatter={(v) => chartPct(v, { alreadyPercent: true })}
                  />
                  <Legend
                    wrapperStyle={{
                      fontFamily: BB.font,
                      fontSize: 10,
                      color: BB.muted,
                    }}
                  />
                  <Bar
                    dataKey="severity_pct"
                    name="WA Severity"
                    fill={BB.down}
                    maxBarSize={36}
                  />
                  <Bar
                    dataKey="recovery_pct"
                    name="WA Recovery"
                    fill={BB.up}
                    maxBarSize={36}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <MatrixHeat
              cells={sections.loss_severity.heatmap || []}
              rowKey="fico_band"
              colKey="cltv_band"
              rows={
                sections.fico_cltv?.fico_bands || [
                  "<660",
                  "660-699",
                  "700-739",
                  "740-779",
                  "780+",
                ]
              }
              cols={
                sections.fico_cltv?.cltv_bands || [
                  "<60",
                  "60-70",
                  "70-80",
                  "80-90",
                  "90+",
                ]
              }
              valueKey="wa_severity"
              formatCell={(c) =>
                `Severity ${fmtPct(c.wa_severity, 1)} · Recovery ${fmtPct(
                  c.wa_recovery,
                  1
                )} · ${fmtInt(c.loan_count)} Loans`
              }
              ariaLabel="Severity By FICO And CLTV"
            />
          </Section>
        )}
      </div>
    </section>
  );
}
