import { useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import type { DeskState } from "../data/types";
import { radarView, type RadarPoint } from "../data/stage2";
import { fmtDate, fmtNum, fmtPct } from "../data/format";
import { Panel } from "../components/Panel";
import { CHART_FONT, Chart, chartAxisCommon, chartTooltip } from "../components/Chart";

interface BubbleDatum {
  name: string;
  value: [number, number, number];
  decisionId: string;
  ticker: string;
  clsLabel: string;
  status: string;
  detail: string;
  z: number;
  rvol: number;
  movePct: number;
  marketCap: number | null;
  confidence: number | null;
  color: string;
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function fmtCap(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return "not logged";
  if (value >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
  if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
  return `$${value.toLocaleString("en-US")}`;
}

function bubbleOption(points: RadarPoint[]): EChartsOption {
  const maxCap = Math.max(1, ...points.map((point) => point.marketCap ?? 0));
  const minZ = Math.floor(Math.min(-2.2, ...points.map((point) => point.z)));
  const maxZ = Math.ceil(Math.max(2.2, ...points.map((point) => point.z)));
  const data: BubbleDatum[] = points.map((point) => ({
    name: point.ticker,
    value: [point.z, point.rvol, point.marketCap ?? 0],
    decisionId: point.decisionId,
    ticker: point.ticker,
    clsLabel: point.label,
    status: point.status,
    detail: point.detail,
    z: point.z,
    rvol: point.rvol,
    movePct: point.movePct,
    marketCap: point.marketCap,
    confidence: point.confidence,
    color: point.color,
  }));

  return {
    animation: false,
    grid: { left: 48, right: 20, top: 30, bottom: 48 },
    tooltip: {
      ...chartTooltip,
      trigger: "item",
      formatter: (params: unknown) => {
        const dataPoint = (params as { data?: BubbleDatum }).data;
        if (!dataPoint) return "";
        const confidence =
          dataPoint.confidence == null ? "" : `<br/>confidence ${(dataPoint.confidence * 100).toFixed(1)}%`;
        return [
          `<strong>${escapeHtml(dataPoint.ticker)}</strong> · ${escapeHtml(dataPoint.clsLabel)}`,
          `z ${dataPoint.z.toFixed(2)} · RVOL ${dataPoint.rvol.toFixed(2)} · move ${dataPoint.movePct.toFixed(2)}%`,
          `market cap ${fmtCap(dataPoint.marketCap)}${confidence}`,
          `${escapeHtml(dataPoint.status)} — ${escapeHtml(dataPoint.detail)}`,
          "click for the decision drawer",
        ].join("<br/>");
      },
    },
    xAxis: {
      type: "value",
      min: minZ,
      max: maxZ,
      interval: 1,
      name: "move z-score",
      nameLocation: "middle",
      nameGap: 26,
      nameTextStyle: { color: "#8b97ad", fontSize: 10, fontFamily: CHART_FONT },
      ...chartAxisCommon,
      splitLine: { show: true, lineStyle: { color: "#1a2540" } },
      axisLabel: { ...chartAxisCommon.axisLabel, formatter: (value: string | number) => Number(value).toFixed(0) },
    },
    yAxis: {
      type: "log",
      logBase: 10,
      min: 1,
      max: 4,
      splitNumber: 4,
      name: "RVOL (log)",
      nameLocation: "middle",
      nameGap: 36,
      nameTextStyle: { color: "#8b97ad", fontSize: 10, fontFamily: CHART_FONT },
      ...chartAxisCommon,
      axisLabel: { ...chartAxisCommon.axisLabel, formatter: (value: string | number) => Number(value).toFixed(1) },
    },
    series: [
      {
        type: "scatter",
        name: "Screened stocks",
        cursor: "pointer",
        data: data.map((item) => {
          const point = points.find((candidate) => candidate.decisionId === item.decisionId);
          const size =
            item.marketCap != null ? 12 + 27 * Math.sqrt(item.marketCap / maxCap) : 16;
          return {
            ...item,
            symbolSize: size,
            itemStyle: {
              color: item.color,
              borderColor: point?.traded ? "#ff7a1a" : "transparent",
              borderWidth: point?.traded ? 2.5 : 0,
              opacity: point?.skipped ? 0.62 : 0.95,
            },
            label: {
              show: true,
              position: "top",
              formatter: "{b}",
              color: "#e8edf6",
              fontSize: 10,
              fontFamily: CHART_FONT,
            },
          };
        }),
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: "#8b97ad", type: "dashed", width: 1, opacity: 0.65 },
          label: {
            color: "#8b97ad",
            fontSize: 9,
            fontFamily: CHART_FONT,
            distance: 3,
          },
          data: [
            { xAxis: -2, label: { formatter: "|z| = 2", position: "insideEndTop", rotate: 0 } },
            { xAxis: 2, label: { formatter: "|z| = 2", position: "insideEndTop", rotate: 0 } },
            { yAxis: 2, label: { formatter: "RVOL 2 · drift min", position: "insideStartTop" } },
            { yAxis: 3, label: { formatter: "RVOL 3 · bounce max", position: "insideStartTop" } },
          ],
        },
      },
    ],
  };
}

export function MoverRadar({
  state,
  onOpenDecision,
}: {
  state: DeskState;
  onOpenDecision: (id: string) => void;
}) {
  const latest = state.sessions[state.sessions.length - 1]?.runId ?? "";
  const [selected, setSelected] = useState(latest);
  const runId = state.sessions.some((session) => session.runId === selected) ? selected : latest;
  const radar = useMemo(() => (runId ? radarView(state, runId) : null), [state, runId]);
  const option = useMemo(() => (radar ? bubbleOption(radar.points) : null), [radar]);

  if (!radar) {
    return <p className="empty">No screened session is loaded.</p>;
  }

  const summary = radar.points
    .map(
      (point) =>
        `${point.ticker} z ${point.z.toFixed(1)}, RVOL ${point.rvol.toFixed(1)} (${point.status.toLowerCase()})`,
    )
    .join("; ");

  return (
    <>
      <div className="view-head">
        <div>
          <h1>Mover radar</h1>
          <p className="view-sub">
            Every screened stock in the selected session. The bubble sits at its move z-score and
            relative volume; the ring marks a name we traded.
          </p>
        </div>
        <div className="session-bar" role="group" aria-label="Selected session">
          {state.sessions.map((session) => (
            <button
              key={session.runId}
              type="button"
              className={session.runId === runId ? "session-chip active" : "session-chip"}
              aria-pressed={session.runId === runId}
              onClick={() => setSelected(session.runId)}
            >
              {fmtDate(session.startTs)}
            </button>
          ))}
        </div>
      </div>

      <div className="radar-grid">
        <Panel
          className="span-8"
          title="Screened movers"
          question="Move z-score against relative volume; gate lines are fixed by the preregistration"
          id="panel-radar"
        >
          {option ? (
            <Chart
              option={option}
              height={330}
              ariaLabel={`Bubble chart of ${radar.points.length} screened stocks. X is move z-score, Y is relative volume on a log scale. Gate lines are at absolute z 2, RVOL 2 and RVOL 3.`}
              summary={`${radar.points.length} screened names in ${fmtDate(radar.session.startTs)}: ${summary}.`}
              footnote={`${radar.caveat} Market caps come from config/universe-2026-11-16.json because the screen event carries no market cap. Gate lines: |z| = 2, RVOL = 2 (drift minimum) and RVOL = 3 (bounce maximum).`}
              onPointClick={(point) => {
                const dataPoint = point.data as BubbleDatum | undefined;
                if (dataPoint?.decisionId) onOpenDecision(dataPoint.decisionId);
              }}
            />
          ) : null}
          <ul className="radar-legend" aria-label="Bubble legend">
            <li>
              <span className="legend-swatch" style={{ background: "#a78bfa" }} /> Explained up
            </li>
            <li>
              <span className="legend-swatch" style={{ background: "#f26b6b" }} /> Explained down
            </li>
            <li>
              <span className="legend-swatch" style={{ background: "#5b8def" }} /> Unexplained up
            </li>
            <li>
              <span className="legend-swatch" style={{ background: "#2dd4bf" }} /> Unexplained down
            </li>
            <li>
              <span className="legend-swatch grey" /> Skip / not picked
            </li>
            <li>
              <span className="legend-ring" /> Traded
            </li>
          </ul>
          <p className="tiny">
            Bubble size follows market cap. The chart is an accessible alternative to the ranked list
            below; both open the decision drawer.
          </p>
        </Panel>

        <Panel
          className="span-4"
          title="Universe funnel"
          question="How the frozen universe narrows to traded names"
          id="panel-funnel"
        >
          <ol className="funnel">
            {radar.funnel.map((step) => (
              <li key={step.key} className="funnel-step">
                <div className="funnel-head">
                  <span>{step.label}</span>
                  <span className="funnel-count">{step.value.toLocaleString("en-US")}</span>
                </div>
                <div className="funnel-track" aria-hidden="true">
                  <span
                    className="funnel-fill"
                    style={{
                      width: `${Math.max(2, (Math.log10(step.value + 1) / Math.log10(radar.funnel[0].value + 1)) * 100)}%`,
                    }}
                  />
                </div>
                {step.drop != null ? (
                  <p className="funnel-drop">
                    −{step.drop.toLocaleString("en-US")} · {step.reason}
                  </p>
                ) : null}
                {step.note ? <p className="tiny">{step.note}</p> : null}
              </li>
            ))}
          </ol>
          <p className="tiny">
            The bar is log-scaled so the small stages remain visible. The fixture logs a three-name
            screen, not a full 727-name scan; the 727 denominator is the preregistered gated universe.
          </p>
        </Panel>

        <Panel
          className="span-12"
          title="Ranked screened names"
          question="Sorted by absolute move z-score; click a row to open its decision"
          id="panel-movers"
        >
          <div className="rank-list">
            {radar.points.map((point, index) => (
              <button
                key={point.decisionId}
                type="button"
                className="rank-row"
                onClick={() => onOpenDecision(point.decisionId)}
                aria-label={`Rank ${index + 1}, ${point.ticker}, ${point.label}, z ${point.z.toFixed(2)}, RVOL ${point.rvol.toFixed(2)}, ${point.status}; open decision`}
              >
                <span className="rank-num">{index + 1}</span>
                <span className="rank-ticker">{point.ticker}</span>
                <span className="rank-class" style={{ color: point.skipped ? "#8b97ad" : point.color }}>
                  {point.label}
                </span>
                <span className="num rank-metric">z {fmtNum(point.z, 2)}</span>
                <span className="num rank-metric">RVOL {fmtNum(point.rvol, 2)}</span>
                <span className={`num rank-metric ${point.movePct >= 0 ? "up" : "down"}`}>
                  {fmtPct(point.movePct, 2)}
                </span>
                <span
                  className={
                    point.traded ? "rank-status traded" : point.skipped ? "rank-status skipped" : "rank-status"
                  }
                >
                  {point.status}
                </span>
              </button>
            ))}
          </div>
          <p className="tiny">
            Class colours match the chart. A skipped name is grey even when its class is known.{" "}
            {radar.outOfScreenTrades.length > 0
              ? `Out-of-screen fill(s) also exist for ${radar.outOfScreenTrades.join(", ")}; they have no screen bubble.`
              : ""}
          </p>
        </Panel>
      </div>
    </>
  );
}
