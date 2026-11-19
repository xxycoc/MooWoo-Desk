import { useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import type { DeskState, LoadedEvent } from "../data/types";
import { COLORS, equityPoints, sgtTime, START_CAPITAL, type RunRow } from "../data/dashboard";
import { fmtNum, fmtPct, fmtSignedPct, fmtSignedUsd, fmtUsd, signClass } from "../data/format";
import { Chart, chartAxisCommon, chartTooltip } from "../components/Chart";
import { Panel } from "../components/Panel";
import { TableScroll } from "../components/TableScroll";

export function timeAxis() {
  return { type: "time" as const, ...chartAxisCommon, axisLabel: { ...chartAxisCommon.axisLabel, fontSize: 9, hideOverlap: true, formatter: (value: number) => sgtTime(value).replace(", ", "\n") }, splitNumber: 2 };
}

export function Now({ state, events, runs, onOpenDecision }: {
  state: DeskState; events: LoadedEvent[]; runs: RunRow[]; onOpenDecision: (id: string) => void;
}) {
  const [shown, setShown] = useState(10);
  const points = useMemo(() => equityPoints(events), [events]);
  const equityOption = useMemo<EChartsOption>(() => ({
    grid: { left: 66, right: 16, top: 12, bottom: 46 },
    tooltip: { ...chartTooltip, trigger: "axis", renderMode: "richText", confine: true, valueFormatter: (value) => fmtUsd(Number(value), 2) },
    xAxis: timeAxis(), yAxis: { type: "value", scale: true, splitNumber: 3, ...chartAxisCommon, axisLabel: { ...chartAxisCommon.axisLabel, formatter: (value: number) => fmtNum(value, 0) } },
    series: [{ name: "Equity (USD)", type: "line", data: points.map((point) => [point.ts, point.equity]), showSymbol: points.length < 3, symbolSize: 7, lineStyle: { color: COLORS.book, width: 2 }, itemStyle: { color: COLORS.book } }],
  }), [points]);
  const invested = state.positions.reduce((sum, position) => sum + position.qty * position.lastPrice, 0);
  const openPnl = state.positions.reduce((sum, position) => sum + (position.lastPrice - position.avgCost) * position.qty, 0);
  const change = state.equity == null ? null : (state.equity / START_CAPITAL - 1) * 100;
  return <div className="desk-grid now-grid">
    <section className="panel wide account-panel" aria-label="Book overview">
      <dl className="desk-kpis">
        <div><dt>Equity</dt><dd>{fmtUsd(state.equity)}</dd></div>
        <div><dt>Return <small>vs $100,000 start</small></dt><dd className={change == null ? "muted" : signClass(change)}>{change == null ? "Not recorded" : fmtSignedPct(change)}</dd></div>
        <div><dt>Invested</dt><dd>{state.equity ? fmtPct(invested / state.equity * 100, 1) : "Not recorded"}</dd></div>
        <div><dt>Open P&amp;L</dt><dd className={signClass(openPnl)}>{fmtSignedUsd(openPnl)}</dd></div>
      </dl>
      {points.length ? <Chart option={equityOption} height={150} ariaLabel="Equity over time from run started events, in US dollars" summary={`${points.length} run-start snapshots. Last: ${sgtTime(points.at(-1)?.ts ?? null)}. Not streaming market prices.`} /> : <p className="empty">Equity history appears after a run-start snapshot.</p>}
    </section>
    <Panel className="wide" title="Positions" question="Last logged marks, not live quotes. Open P&L excludes fees." id="positions-title">
      <TableScroll label="Positions table">
        <table className="positions-table"><thead><tr>{["Ticker", "Sleeve", "Qty", "Cost", "Last", "P&L", "Stop"].map((name) => <th key={name} scope="col">{name}</th>)}</tr></thead>
          <tbody>{state.positions.map((position) => <tr key={position.ticker}>
            <th scope="row"><button className="text-button ticker" onClick={() => onOpenDecision(position.decisionId ?? `${position.entryEv.runId}:${position.ticker}`)}>{position.ticker}</button></th>
            <td><span className={`sleeve-tag ${position.sleeve}`}>{position.sleeve}</span></td>
            <td className="num" data-label="Qty">{fmtNum(position.qty, 0)}</td><td className="num" data-label="Cost">{fmtUsd(position.avgCost, 2)}</td>
            <td className="num" data-label="Last"><span title={`Mark: ${sgtTime(position.lastMarkAt)}`}>{fmtUsd(position.lastPrice, 2)}</span></td>
            <td data-label="P&L" className={`num ${signClass((position.lastPrice - position.avgCost) * position.qty)}`}>{fmtSignedUsd((position.lastPrice - position.avgCost) * position.qty)}</td>
            <td className="num" data-label="Stop">{position.stop != null && position.stop > 0 ? fmtUsd(position.stop, 2) : "—"}</td>
          </tr>)}{!state.positions.length && <tr><td colSpan={7}>No open positions in these logs.</td></tr>}</tbody>
        </table>
      </TableScroll>
    </Panel>
    <Panel className="wide" title="Last runs" question="Newest first. Open a run for its events and ticker decisions." id="runs-title">
      <TableScroll label="Last runs table">
        <table className="runs-table"><thead><tr><th scope="col">Time (SGT)</th><th scope="col">Run kind</th><th scope="col">Result</th></tr></thead>
          <tbody>{runs.slice(0, shown).map((run) => <tr key={run.id} onClick={() => onOpenDecision(`run:${run.id}`)}>
            <th scope="row"><button className="text-button" onClick={(event) => { event.stopPropagation(); onOpenDecision(`run:${run.id}`); }} aria-label={`Open ${run.kind} run at ${sgtTime(run.at)}`}>{sgtTime(run.at)}</button></th>
            <td>{run.kind}</td><td className={`run-result tone-${run.tone}`}>{run.result}</td>
          </tr>)}{!runs.length && <tr><td colSpan={3}>No runs recorded.</td></tr>}</tbody>
        </table>
      </TableScroll>
      <div className="runs-more"><span>{Math.min(shown, runs.length)} of {runs.length} runs · “ok” means no logged failure, not a broker reconciliation.</span>{shown < runs.length && <button type="button" onClick={() => setShown((count) => count + 10)}>Show more</button>}</div>
    </Panel>
  </div>;
}
