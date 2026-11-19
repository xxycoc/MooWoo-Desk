import { useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import type { DeskState } from "../data/types";
import { radarView, type RadarPoint } from "../data/stage2";
import { fmtNum } from "../data/format";
import { sgtTime } from "../data/dashboard";
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
      confine: true,
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
      min: Math.min(1, ...points.filter((point) => point.rvol > 0).map((point) => point.rvol)),
      max: Math.max(4, ...points.map((point) => point.rvol)) * 1.1,
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
              show: Boolean(point?.picked || point?.traded),
              position: "top",
              formatter: "{b}",
              color: "#e8edf6",
              fontSize: 10,
              fontFamily: CHART_FONT,
            },
          };
        }),
        labelLayout: { hideOverlap: true },
        emphasis: { label: { show: true } },
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

export function MoverRadar({ state, onOpenDecision }: {
  state: DeskState; onOpenDecision: (id: string) => void;
}) {
  const sessions = state.sessions.filter((session) => session.events.some((event) => event.type === "screen"));
  const latest = sessions.at(-1)?.runId ?? "";
  const [selected, setSelected] = useState("");
  const runId = sessions.some((session) => session.runId === selected) ? selected : latest;
  const radar = useMemo(() => runId ? radarView(state, runId) : null, [state, runId]);
  const points = useMemo(() => radar?.points.filter((point) => Number.isFinite(point.z) && Number.isFinite(point.rvol) && point.rvol > 0) ?? [], [radar]);
  const option = useMemo(() => bubbleOption(points), [points]);
  return <Panel className="wide" title="Mover radar" question="Which moves cleared the gates? Z-score against relative volume." id="radar-title"
    actions={sessions.length > 0 ? <label className="radar-select">Screen <select value={runId} onChange={(event) => setSelected(event.target.value)}>{[...sessions].reverse().map((session) => <option key={session.runId} value={session.runId}>{sgtTime(session.startTs)}</option>)}</select></label> : undefined}>
    {radar ? <>
      <Chart option={option} height={260} ariaLabel="Mover bubbles: z-score against RVOL on a log scale, with gate lines and orange rings for traded names" summary={points.length + " screened movers. Orange ring: traded. Bubble size: frozen market cap, not confidence."} onPointClick={(point) => { const data = point.data as BubbleDatum | undefined; if (data?.decisionId) onOpenDecision(data.decisionId); }} />
      <ul className="radar-legend" aria-label="Class colours">{[["Explained up", "#a78bfa"], ["Explained down", "#f26b6b"], ["Unexplained up", "#5b8def"], ["Unexplained down", "#2dd4bf"], ["Not rated / skipped", "#8b97ad"]].map(([label, color]) => <li key={label}><span className="legend-swatch" style={{ background: color }} />{label}</li>)}</ul>
      <details className="ranked-movers"><summary>Ranked movers · {radar.points.length} names · {radar.points.filter((point) => point.traded).length} traded</summary><ol>{radar.points.map((point) => <li key={point.decisionId}><button className="text-button" onClick={() => onOpenDecision(point.decisionId)}>{point.ticker}</button><span className="num">z {fmtNum(point.z)} · RVOL {fmtNum(point.rvol)}</span><span>{point.status}</span></li>)}</ol></details>
      {points.length !== radar.points.length && <p className="tiny">Non-positive or unavailable RVOL values cannot appear on a log axis; see the ranked list.</p>}
    </> : <p className="empty">Mover radar appears after the first screening run.</p>}
  </Panel>;
}
