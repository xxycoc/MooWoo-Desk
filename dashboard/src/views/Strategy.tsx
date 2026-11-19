import { useMemo } from "react";
import type { EChartsOption, LineSeriesOption } from "echarts";
import type { DeskState, LoadedEvent } from "../data/types";
import { benchmarkSeries, closedTradeScore, COLORS, equityPoints, sgtTime, START_CAPITAL, streamPnl } from "../data/dashboard";
import { fmtPct, fmtSignedUsd, fmtUsd } from "../data/format";
import { Chart, chartAxisCommon, chartTooltip } from "../components/Chart";
import { Panel } from "../components/Panel";
import { MoverRadar } from "./MoverRadar";
import { timeAxis } from "./Now";

export function Strategy({ state, events, onOpenDecision }: {
  state: DeskState; events: LoadedEvent[]; onOpenDecision: (id: string) => void;
}) {
  const equity = useMemo(() => equityPoints(events, true), [events]);
  const benchmarks = useMemo(() => benchmarkSeries(events), [events]);
  const streams = useMemo(() => streamPnl(state), [state]);
  const hit = useMemo(() => closedTradeScore(events), [events]);
  const underwater = useMemo(() => {
    let peak = START_CAPITAL;
    return equity.map((point) => {
      peak = Math.max(peak, point.equity);
      return { ...point, peak, drawdown: (point.equity / peak - 1) * 100 };
    });
  }, [equity]);
  const comparisonOption = useMemo<EChartsOption>(() => {
    const series: LineSeriesOption[] = [{ name: "Our book", type: "line", showSymbol: equity.length < 3, symbolSize: 7, data: equity.map((point) => [point.ts, point.equity / START_CAPITAL * 100]), itemStyle: { color: COLORS.book }, lineStyle: { width: 2.5 } }];
    benchmarks.forEach((benchmark, index) => {
      if (!benchmark.points.length) return;
      const start: [string, number][] = equity[0] && equity[0].ts < benchmark.points[0][0] ? [[equity[0].ts, 100]] : [];
      series.push({ name: benchmark.name, type: "line", showSymbol: true, symbol: ["circle", "rect", "triangle"][index], symbolSize: 5, data: [...start, ...benchmark.points], itemStyle: { color: ["#aab3c3", "#8b97ad", "#69778f"][index] }, lineStyle: { type: ["solid", "dashed", "dotted"][index] as "solid" | "dashed" | "dotted", width: 1.5 } });
    });
    return {
      grid: { left: 54, right: 18, top: 35, bottom: 48 },
      legend: { data: series.map((item) => item.name as string), textStyle: { color: "#8b97ad", fontSize: 11 }, itemWidth: 16, itemGap: 10 },
      tooltip: { ...chartTooltip, trigger: "axis", renderMode: "richText", confine: true, valueFormatter: (value) => Number(value).toFixed(2) },
      xAxis: timeAxis(), yAxis: { type: "value", scale: true, ...chartAxisCommon }, series,
    };
  }, [equity, benchmarks]);
  const streamOption = useMemo<EChartsOption>(() => ({
    grid: { left: 82, right: 60, top: 12, bottom: 30 },
    tooltip: { ...chartTooltip, trigger: "axis", renderMode: "richText", confine: true, valueFormatter: (value) => fmtSignedUsd(Number(value)) },
    xAxis: { type: "value", ...chartAxisCommon, splitNumber: 3 },
    yAxis: { type: "category", inverse: true, data: streams.map((row) => row.name), ...chartAxisCommon },
    series: [{ type: "bar", barMaxWidth: 20, data: streams.map((row) => ({ value: row.value, itemStyle: { color: row.color }, label: { show: true, position: row.value < 0 ? "left" : "right", color: "#e8edf6", fontSize: 10, formatter: fmtSignedUsd(row.value) } })), markLine: { silent: true, symbol: "none", label: { show: false }, data: [{ xAxis: 0 }], lineStyle: { color: "#8b97ad", type: "solid" } } }],
  }), [streams]);
  const interval = hit.interval;
  const hitMessage = !interval ? `Can't tell yet: ${hit.count} closed trades` : interval.lo > 0.5 ? `Above 50%: ${hit.wins} wins / ${hit.count} closed trades` : interval.hi < 0.5 ? `Below 50%: ${hit.wins} wins / ${hit.count} closed trades` : `Can't tell yet: ${hit.wins} wins / ${hit.count} closed trades`;
  const hitOption = useMemo<EChartsOption>(() => ({
    grid: { left: 26, right: 26, top: 30, bottom: 35 },
    xAxis: { type: "value", min: 0, max: 100, interval: 25, ...chartAxisCommon, axisLabel: { ...chartAxisCommon.axisLabel, formatter: "{value}%" } },
    yAxis: { type: "value", min: -1, max: 1, show: false },
    series: [
      { type: "line", silent: true, data: interval ? [[interval.lo * 100, 0], [interval.hi * 100, 0]] : [], symbol: "rect", symbolSize: [3, 18], lineStyle: { color: COLORS.book, width: 4 }, itemStyle: { color: COLORS.book }, markLine: { silent: true, symbol: "none", lineStyle: { color: "#8b97ad", type: "dashed" }, label: { show: false }, data: [{ xAxis: 50 }] } },
      { type: "scatter", silent: true, data: interval ? [[interval.p * 100, 0]] : [], symbolSize: 12, itemStyle: { color: COLORS.book } },
    ],
  }), [interval]);
  const drawdownOption = useMemo<EChartsOption>(() => ({
    grid: { left: 46, right: 18, top: 18, bottom: 48 },
    tooltip: { ...chartTooltip, trigger: "axis", renderMode: "richText", confine: true, valueFormatter: (value) => fmtPct(Number(value)) },
    xAxis: timeAxis(), yAxis: { type: "value", min: Math.min(-6.5, ...underwater.map((point) => point.drawdown)), max: 0, ...chartAxisCommon, axisLabel: { ...chartAxisCommon.axisLabel, formatter: "{value}%" } },
    series: [{ name: "Drawdown", type: "line", showSymbol: underwater.length < 3, data: underwater.map((point) => [point.ts, point.drawdown]), itemStyle: { color: COLORS.red }, areaStyle: { color: COLORS.red, opacity: 0.18 }, markLine: { silent: true, symbol: "none", label: { position: "insideEndTop", formatter: "{b}", fontSize: 10 }, data: [
      { yAxis: -2, name: "-2% reduced", lineStyle: { color: "#fca5a5", type: "dashed" }, label: { color: "#fca5a5" } },
      { yAxis: -4, name: "-4% exits only", lineStyle: { color: COLORS.red, type: "dashed" }, label: { color: COLORS.red } },
      { yAxis: -6, name: "-6% kill", lineStyle: { color: "#c92a2a", type: "dashed" }, label: { color: "#f26b6b" } },
    ] } }],
  }), [underwater]);
  const missing = benchmarks.filter((benchmark) => !benchmark.complete).map((benchmark) => benchmark.name);
  return <div className="desk-grid strategy-grid">
    <MoverRadar state={state} onOpenDecision={onOpenDecision} />
    <Panel className="wide" title="Are we beating the simple alternatives?" question="Indexed to 100 at the start. Our book is orange; comparisons are grey." id="comparison-title">
      {equity.length ? <Chart option={comparisonOption} height={220} ariaLabel="Book versus SPY, follow-all and fade-all, indexed to 100; missing benchmark data is not plotted" summary={`Our book: ${equity.length} logged snapshots. Comparisons use daily audit returns, not matched-decision evidence.`} /> : <p className="empty">Book history appears after the first equity snapshot.</p>}
      {missing.length > 0 && <p className="data-note">{missing.join(", ")}: missing data appears after the daily audit. No substitute lines are drawn.</p>}
    </Panel>
    <Panel title="Which stream made money?" question="Open P&L by sleeve, USD. Last logged marks, before fees." id="streams-title">
      <Chart option={streamOption} height={190} ariaLabel="Signed open profit and loss bars for core, drift, bounce and total" summary={streams.map((row) => `${row.name}: ${fmtSignedUsd(row.value)}`).join("; ")} />
    </Panel>
    <Panel title="Is the hit rate better than a coin?" question="Closed round trips, net of modelled fees. Wilson 95% interval." id="hit-title">
      <p className="hit-verdict">{hitMessage}</p>
      <Chart option={hitOption} height={155} ariaLabel="Wilson 95 percent hit-rate interval against the 50 percent coin baseline" summary={interval ? `Hit rate ${fmtPct(interval.p * 100, 1)}; interval ${fmtPct(interval.lo * 100, 1)} to ${fmtPct(interval.hi * 100, 1)}.` : "No closed trades: interval unavailable. The dashed line is 50%."} footnote="A trade counts only when its position is fully closed by recorded fills. Partial exits are included in that round trip's net P&L. Break-even trades are not wins. This is a trade scorecard, not a test of all analyst calls." />
    </Panel>
    <Panel className="wide" title="How deep is the drawdown?" question={`Below the logged equity peak${underwater.length ? ` of ${fmtUsd(underwater.at(-1)?.peak)}` : ""}. Red lines mark the risk tiers.`} id="drawdown-title">
      {underwater.length ? <Chart option={drawdownOption} height={200} ariaLabel="Underwater equity chart with risk tiers at minus 2, 4 and 6 percent" summary={`${fmtPct(underwater.at(-1)?.drawdown)} at ${sgtTime(underwater.at(-1)?.ts ?? null)}. Between-snapshot drawdowns are not observable.`} /> : <p className="empty">Drawdown appears after the first equity snapshot.</p>}
    </Panel>
  </div>;
}
