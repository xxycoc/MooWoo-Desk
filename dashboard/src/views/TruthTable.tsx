import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import type { DeskState } from "../data/types";
import {
  RISK_METRICS,
  headToHead,
  riskView,
  truthView,
  type IntervalMetric,
  type RiskMetricKey,
} from "../data/stage2";
import { fmtRatio, fmtSignedPct } from "../data/format";
import { Panel } from "../components/Panel";
import { CHART_FONT, Chart, chartAxisCommon } from "../components/Chart";

const METRIC_LABEL: Record<RiskMetricKey, string> = {
  sharpe: "Sharpe",
  totalReturn: "Return",
  sortino: "Sortino",
  calmar: "Calmar",
  maxDrawdown: "Max drawdown",
};

function metricText(key: RiskMetricKey, value: number | null): string {
  if (value == null || !Number.isFinite(value)) return "unavailable";
  if (key === "totalReturn" || key === "maxDrawdown") return fmtSignedPct(value * 100, 2);
  return fmtRatio(value, 2);
}

function intervalText(key: RiskMetricKey, metric: IntervalMetric): string {
  if (metric.low == null || metric.high == null) return "95% interval unavailable";
  return `95% ${metricText(key, metric.low)} to ${metricText(key, metric.high)}`;
}

function calibrationOption(): EChartsOption {
  return {
    animation: false,
    grid: { left: 44, right: 18, top: 34, bottom: 42 },
    legend: {
      top: 0,
      left: 0,
      textStyle: { color: "#8b97ad", fontSize: 9, fontFamily: CHART_FONT },
      itemWidth: 12,
      itemHeight: 6,
    },
    xAxis: {
      type: "value",
      min: 0,
      max: 1,
      name: "confidence",
      nameLocation: "middle",
      nameGap: 24,
      nameTextStyle: { color: "#8b97ad", fontSize: 10, fontFamily: CHART_FONT },
      ...chartAxisCommon,
      axisLabel: {
        ...chartAxisCommon.axisLabel,
        formatter: (value: string | number) => `${Math.round(Number(value) * 100)}%`,
      },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 1,
      name: "hit rate",
      nameLocation: "middle",
      nameGap: 34,
      nameTextStyle: { color: "#8b97ad", fontSize: 10, fontFamily: CHART_FONT },
      ...chartAxisCommon,
      axisLabel: {
        ...chartAxisCommon.axisLabel,
        formatter: (value: string | number) => `${Math.round(Number(value) * 100)}%`,
      },
    },
    series: [
      {
        name: "Perfect calibration",
        type: "line",
        data: [
          [0, 0],
          [1, 1],
        ],
        showSymbol: false,
        lineStyle: { color: "#8b97ad", type: "dashed", width: 1 },
      },
      {
        name: "Debate",
        type: "line",
        data: [],
        showSymbol: false,
        lineStyle: { color: "#ff7a1a", width: 2 },
      },
      {
        name: "Quick",
        type: "line",
        data: [],
        showSymbol: false,
        lineStyle: { color: "#f2c230", width: 2 },
      },
    ],
    graphic: [
      {
        type: "text",
        left: 56,
        top: 40,
        silent: true,
        style: {
          text: "No graded calls to bin",
          fill: "#8b97ad",
          fontSize: 10,
          fontFamily: CHART_FONT,
          align: "left",
          lineHeight: 15,
        },
      },
    ],
  };
}

export function TruthTable({ state }: { state: DeskState }) {
  const truth = useMemo(() => truthView(state), [state]);
  const risk = useMemo(() => riskView(state), [state]);
  const ourReturn = risk.books[0]?.metrics.totalReturn.value ?? null;
  const h2h = useMemo(() => headToHead(state, ourReturn), [state, ourReturn]);
  const option = useMemo(() => calibrationOption(), []);
  const maxAbs = Math.max(0.01, ...h2h.rows.map((row) => Math.abs(row.value ?? 0)));

  return (
    <>
      <div className="view-head">
        <div>
          <h1>Truth table</h1>
          <p className="view-sub">
            The preregistered scorecard, calibration, call matrix and risk-adjusted record. Verdicts
            use the exact rules in PREREGISTRATION.md.
          </p>
        </div>
        <div className="view-status">
          <span className="stamp untold">can't tell yet</span>
          <span>
            {truth.graded} graded · {truth.calls} prelogged · {truth.skippedCalls} skip
            {truth.skippedCalls === 1 ? "" : "s"}
          </span>
        </div>
      </div>

      <div className="truth-grid">
        <div className="span-12 hyp-grid">
          {truth.hypotheses.map((hypothesis) => (
            <article className="hyp-card" key={hypothesis.key}>
              <div className="hyp-top">
                <span className="hyp-key">{hypothesis.key}</span>
                <span className="stamp untold">{hypothesis.verdict}</span>
              </div>
              <h2>{hypothesis.title}</h2>
              <p className="hyp-statement">{hypothesis.statement}</p>
              <ul className="hyp-evidence">
                {hypothesis.evidence.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
              <p className="tiny">{hypothesis.rule}</p>
            </article>
          ))}
        </div>

        <Panel
          className="span-7"
          title="Calibration"
          question="Pre-logged confidence against actual hit rate; the diagonal is perfect"
          id="panel-calibration"
        >
          <div className="stat-strip">
            <div>
              <span>Reported Brier</span>
              <strong>{truth.brierReported != null ? truth.brierReported.toFixed(2) : "—"}</strong>
            </div>
            <div>
              <span>Target</span>
              <strong>&lt; 0.25</strong>
            </div>
            <div>
              <span>Graded calls</span>
              <strong>{truth.graded}</strong>
            </div>
          </div>
          <Chart
            option={option}
            height={260}
            ariaLabel="Calibration chart with confidence on the x axis and hit rate on the y axis. The diagonal is perfect calibration. No debate or quick points are plotted because there are no graded calls."
            summary="No confidence-outsome pairs exist, so neither classifier has a calibration line."
            footnote={`The daily_report Brier field (${truth.brierReported != null ? truth.brierReported.toFixed(2) : "—"}) is repeated fixture data, not an H3 computation: there are no graded calls. PREREGISTRATION.md requires a session-cluster bootstrap interval with 2,000 resamples and seed 20261117.`}
          />
          <div className="table-scroll">
            <table className="calls-table bins-table">
              <thead>
                <tr>
                  <th scope="col">Confidence bin</th>
                  <th scope="col">Debate</th>
                  <th scope="col">Quick</th>
                  <th scope="col">Total</th>
                  <th scope="col">Hit rate</th>
                </tr>
              </thead>
              <tbody>
                {truth.bins.map((bin) => (
                  <tr key={bin.label}>
                    <th scope="row">{bin.label}</th>
                    <td>{bin.debate}</td>
                    <td>{bin.quick}</td>
                    <td>{bin.total}</td>
                    <td className="na">—</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="tiny">
            The bins show where the pre-logged confidence sits. A hit rate is undefined until an
            outcome event grades a call.
          </p>
        </Panel>

        <Panel
          className="span-5"
          title="Call matrix"
          question="Predicted class against what the stock then did; skips included"
          id="panel-call-matrix"
        >
          <div className="table-scroll">
            <table className="calls-table">
              <thead>
                <tr>
                  <th scope="col">Class</th>
                  <th scope="col">Calls</th>
                  <th scope="col">Skips</th>
                  <th scope="col">Up</th>
                  <th scope="col">Flat</th>
                  <th scope="col">Down</th>
                  <th scope="col">Ungraded</th>
                </tr>
              </thead>
              <tbody>
                {truth.matrix.map((row) => (
                  <tr key={row.cls}>
                    <th scope="row">
                      <span className="matrix-class">
                        <span className="matrix-class-dot" style={{ background: row.color }} />
                        <span className="matrix-class-name">{row.label}</span>
                      </span>
                    </th>
                    <td>{row.calls}</td>
                    <td>{row.skips}</td>
                    <td className="na">—</td>
                    <td className="na">—</td>
                    <td className="na">—</td>
                    <td>{row.ungraded}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <th scope="row">Total</th>
                  <td>{truth.calls}</td>
                  <td>{truth.skippedCalls}</td>
                  <td className="na">—</td>
                  <td className="na">—</td>
                  <td className="na">—</td>
                  <td>{truth.calls}</td>
                </tr>
              </tfoot>
            </table>
          </div>
          <p className="tiny">{truth.caveat}</p>
        </Panel>

        <Panel
          className="span-6"
          title="Head to head"
          question="Reported books on the same mover set, where the logs allow it"
          id="panel-head-to-head"
        >
          <div className="h2h-list">
            {h2h.rows.map((row) => (
              <div className="h2h-row" key={row.key}>
                <span className="h2h-label">{row.label}</span>
                <div className="h2h-track" aria-hidden="true">
                  {row.value != null ? (
                    <span
                      className={row.value >= 0 ? "h2h-fill up" : "h2h-fill down"}
                      style={{ width: `${(Math.abs(row.value) / maxAbs) * 100}%` }}
                    />
                  ) : null}
                </div>
                <span className={`num h2h-value ${row.value == null ? "muted" : row.value >= 0 ? "up" : "down"}`}>
                  {row.value != null ? fmtSignedPct(row.value * 100, 2) : "not logged"}
                </span>
                <span className="tiny h2h-note">{row.note}</span>
              </div>
            ))}
          </div>
          <p className="tiny">{h2h.caveat}</p>
        </Panel>

        <Panel
          className="span-6"
          title="Risk-adjusted results"
          question="Sharpe first; 95% intervals from the preregistered bootstrap"
          id="panel-risk-metrics"
        >
          <div className="metric-books">
            {risk.books.map((book) => (
              <section className="metric-card" key={book.key}>
                <h3>{book.label}</h3>
                <p className="tiny">{book.note}</p>
                <dl className="metric-list">
                  {RISK_METRICS.map((key) => {
                    const metric = book.metrics[key];
                    return (
                      <div className="metric-row" key={key}>
                        <dt>{METRIC_LABEL[key]}</dt>
                        <dd className={`num metric-value ${metric.value == null ? "muted" : ""}`}>
                          {metricText(key, metric.value)}
                        </dd>
                        <dd className="metric-interval">{intervalText(key, metric)}</dd>
                      </div>
                    );
                  })}
                </dl>
              </section>
            ))}
          </div>
          <p className="tiny">
            {risk.sessions} session close{risk.sessions === 1 ? "" : "s"} · {risk.resamples.toLocaleString("en-US")}{" "}
            paired resamples · seed {risk.seed}. {risk.caveat}
          </p>
        </Panel>
      </div>
    </>
  );
}
