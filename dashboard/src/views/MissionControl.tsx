import { useMemo } from "react";
import type * as echarts from "echarts";
import type { DeskState } from "../data/types";
import {
  allocation,
  creditPlan,
  dataNotes,
  limits,
  markerSets,
  performanceSeries,
  runSteps,
  streams,
  underwaterSeries,
} from "../data/metrics";
import { RULES } from "../data/rules";
import {
  fmtDate,
  fmtDateTime,
  fmtNum,
  fmtPct,
  fmtSignedUsd,
  fmtUsd,
  sleeveLabel,
} from "../data/format";
import { Chart, chartAxisCommon, chartTooltip } from "../components/Chart";
import { Panel } from "../components/Panel";
import { Num, Trace } from "../components/Trace";
import { wilson } from "../data/wilson";

export function MissionControl({
  state,
  onOpenDecision,
}: {
  state: DeskState;
  onOpenDecision: (id: string) => void;
}) {
  const perf = useMemo(() => performanceSeries(state), [state]);
  const underwater = useMemo(() => underwaterSeries(state), [state]);
  const markers = useMemo(() => markerSets(state), [state]);
  const alloc = useMemo(() => allocation(state), [state]);
  const streamData = useMemo(() => streams(state), [state]);
  const limitData = useMemo(() => limits(state), [state]);
  const credits = useMemo(() => creditPlan(state), [state]);
  const steps = useMemo(() => runSteps(state), [state]);
  const notes = useMemo(() => dataNotes(state), [state]);
  const hit = wilson(0, 0);

  const reportByTs = useMemo(() => {
    const map = new Map<string, NonNullable<DeskState["sessions"][number]["reportEv"]>>();
    for (const session of state.sessions) {
      if (session.reportEv) map.set(session.reportEv.ts, session.reportEv);
    }
    return map;
  }, [state]);

  const markersByDate = useMemo(() => {
    const map = new Map<string, { D: number; V: number; R: number }>();
    for (const set of markers) map.set(set.date, { D: set.drills, V: set.vetoes, R: set.ruleChanges });
    return map;
  }, [markers]);

  const performanceOption = useMemo<echarts.EChartsOption>(() => {
    const labels = perf.map((point) => point.label);
    const endLabel = (name: string, color: string, offset: number[]) => ({
      show: true,
      formatter: (params: { value?: unknown }) =>
        `${name} ${typeof params.value === "number" ? params.value.toFixed(1) : ""}`,
      color,
      fontSize: 10,
      fontFamily: "ui-monospace, monospace",
      offset,
    });
    const line = (
      name: string,
      key: "our" | "equalWeight" | "spy" | "follow" | "fade",
      color: string,
      width: number,
      dash: number[] | undefined,
      offset: number[],
    ) => ({
      name,
      type: "line" as const,
      data: perf.map((point) => Number(point[key].toFixed(3))),
      smooth: false,
      showSymbol: false,
      symbol: "circle",
      symbolSize: 4,
      lineStyle: { color, width, type: dash },
      itemStyle: { color },
      endLabel: endLabel(name, color, offset),
      emphasis: { disabled: true },
      z: width > 2 ? 6 : 2,
    });

    return {
      animation: false,
      grid: { left: 46, right: 92, top: 14, bottom: 52 },
      tooltip: {
        ...chartTooltip,
        trigger: "axis",
        confine: true,
        formatter: (raw: unknown) => {
          const params = raw as { dataIndex: number }[];
          const index = params[0]?.dataIndex ?? 0;
          const point = perf[index];
          const ev = reportByTs.get(point.ts);
          return [
            `<strong>${point.label}</strong>`,
            `Our book ${point.our.toFixed(2)}`,
            `SPY ${point.spy.toFixed(2)}`,
            `Equal weight ${point.equalWeight.toFixed(2)}`,
            `Follow-all ${point.follow.toFixed(2)}`,
            `Fade-all ${point.fade.toFixed(2)}`,
            ev ? `src: daily_report seq ${ev.seq} · ${ev.ts}` : "src: session start",
          ].join("<br/>");
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        ...chartAxisCommon,
        axisLabel: {
          ...chartAxisCommon.axisLabel,
          interval: 0,
          lineHeight: 15,
          formatter: (value: string, index: number) => {
            const date = perf[index]?.ts.slice(0, 10) ?? "";
            const set = index === 0 ? undefined : markersByDate.get(date);
            const bits: string[] = [];
            if (set?.D) bits.push("{D|D}");
            if (set?.V) bits.push("{V|V}");
            if (set?.R) bits.push("{R|R}");
            return `{d|${value}}${bits.length ? `\n${bits.join(" ")}` : ""}`;
          },
          rich: {
            d: { color: "#8b97ad", fontSize: 10, fontFamily: "ui-monospace, monospace" },
            D: { color: "#2dd4bf", fontSize: 10, fontWeight: "bold", fontFamily: "ui-monospace, monospace" },
            V: { color: "#f26b6b", fontSize: 10, fontWeight: "bold", fontFamily: "ui-monospace, monospace" },
            R: { color: "#f2c230", fontSize: 10, fontWeight: "bold", fontFamily: "ui-monospace, monospace" },
          },
        },
      },
      yAxis: {
        type: "value",
        scale: true,
        min: (value: { min: number }) => Math.floor((value.min - 0.15) * 10) / 10,
        max: (value: { max: number }) => Math.ceil((value.max + 0.15) * 10) / 10,
        ...chartAxisCommon,
        axisLabel: { ...chartAxisCommon.axisLabel, formatter: (value: number) => value.toFixed(1) },
        name: "index",
        nameTextStyle: { color: "#8b97ad", fontSize: 10 },
      },
      series: [
        line("Our book", "our", "#ff7a1a", 3.2, undefined, [0, -10]),
        line("Follow-all", "follow", "#8b97ad", 1.4, [10, 3, 2, 3], [0, -4]),
        line("SPY", "spy", "#8b97ad", 1.4, [2, 3], [0, 2]),
        line("Equal weight", "equalWeight", "#8b97ad", 1.4, [6, 4], [0, 9]),
        line("Fade-all", "fade", "#8b97ad", 1.4, [4, 2], [0, 17]),
      ],
    };
  }, [perf, markersByDate, reportByTs]);

  const underwaterOption = useMemo<echarts.EChartsOption>(() => {
    const labels = underwater.map((point) => point.label);
    return {
      animation: false,
      grid: { left: 46, right: 98, top: 16, bottom: 28 },
      tooltip: {
        ...chartTooltip,
        trigger: "axis",
        confine: true,
        formatter: (raw: unknown) => {
          const params = raw as { dataIndex: number }[];
          const point = underwater[params[0]?.dataIndex ?? 0];
          const ev = reportByTs.get(point.ts);
          return [
            `<strong>${point.label}</strong>`,
            `Equity ${fmtUsd(point.equity, 0)}`,
            `Drawdown ${point.drawdown.toFixed(2)}%`,
            ev ? `src: daily_report seq ${ev.seq} · ${ev.ts}` : "src: session start",
          ].join("<br/>");
        },
      },
      xAxis: { type: "category", data: labels, ...chartAxisCommon, axisLabel: { ...chartAxisCommon.axisLabel, interval: 0 } },
      yAxis: {
        type: "value",
        min: -7,
        max: 0,
        ...chartAxisCommon,
        axisLabel: { ...chartAxisCommon.axisLabel, formatter: (value: number) => `${value}%` },
      },
      series: [
        {
          name: "Drawdown from peak",
          type: "line",
          data: underwater.map((point) => Number(point.drawdown.toFixed(3))),
          smooth: false,
          showSymbol: true,
          symbolSize: 5,
          lineStyle: { color: "#f26b6b", width: 2 },
          itemStyle: { color: "#f26b6b" },
          areaStyle: { color: "rgba(242,107,107,0.16)" },
          markLine: {
            silent: true,
            symbol: "none",
            label: { position: "insideEndTop", fontSize: 10 },
            data: [
              { yAxis: -2, lineStyle: { color: "#fca5a5", type: [3, 3] }, label: { formatter: "-2% reduced", color: "#fca5a5" } },
              { yAxis: -4, lineStyle: { color: "#f26b6b", type: [3, 3] }, label: { formatter: "-4% exits only", color: "#f26b6b" } },
              { yAxis: -6, lineStyle: { color: "#c92a2a", type: [3, 3] }, label: { formatter: "-6% kill", color: "#c92a2a" } },
            ],
          },
          emphasis: { disabled: true },
        },
      ],
    };
  }, [underwater, reportByTs]);

  const allocationOption = useMemo<echarts.EChartsOption>(() => {
    const actual = alloc
      ? [alloc.weights.core, alloc.weights.drift, alloc.weights.bounce, alloc.weights.unclassified, alloc.weights.cash]
      : [0, 0, 0, 0, 0];
    const targetCore = RULES.coreWeight * 100;
    const targetSatellite = 25;
    const targetCash = 25;
    const seg = (value: number) => (value > 0.05 ? value : null);
    const percentLabel: echarts.LabelFormatterCallback = (params) => {
      const value = Number(params.value ?? 0);
      return value >= 5 ? `${value.toFixed(0)}%` : "";
    };
    const common = {
      type: "bar" as const,
      stack: "total",
      barWidth: 54,
      emphasis: { disabled: true },
      label: { show: true, fontSize: 10, formatter: percentLabel },
    };
    return {
      animation: false,
      grid: { left: 34, right: 16, top: 18, bottom: 26 },
      tooltip: {
        ...chartTooltip,
        trigger: "axis",
        confine: true,
        formatter: (raw: unknown) => {
          const params = raw as { seriesName: string; value: number | null; dataIndex: number }[];
          const title = params[0]?.dataIndex === 0 ? "Actual" : "Target";
          return [
            `<strong>${title}</strong>`,
            ...params
              .filter((item) => item.value != null)
              .map((item) => `${item.seriesName} ${Number(item.value).toFixed(1)}%`),
          ].join("<br/>");
        },
      },
      xAxis: { type: "category", data: ["Actual", "Target"], ...chartAxisCommon },
      yAxis: {
        type: "value",
        max: 100,
        ...chartAxisCommon,
        axisLabel: { ...chartAxisCommon.axisLabel, formatter: (value: number) => `${value}%` },
      },
      series: [
        { ...common, name: "Core", data: [seg(actual[0]), targetCore], itemStyle: { color: "#5b8def" }, label: { ...common.label, color: "#0c1322" } },
        { ...common, name: "Drift", data: [seg(actual[1]), null], itemStyle: { color: "#a78bfa" }, label: { ...common.label, color: "#0c1322" } },
        { ...common, name: "Bounce", data: [seg(actual[2]), null], itemStyle: { color: "#2dd4bf" }, label: { ...common.label, color: "#0c1322" } },
        {
          ...common,
          name: "Satellite (unrated)",
          data: [seg(actual[3]), null],
          itemStyle: { color: "#24314a", borderColor: "#8b97ad", borderWidth: 1 },
          label: { ...common.label, color: "#e8edf6" },
        },
        {
          ...common,
          name: "Satellite",
          data: [null, targetSatellite],
          itemStyle: { color: "#24314a", borderColor: "#8b97ad", borderWidth: 1 },
          label: { ...common.label, color: "#e8edf6" },
        },
        { ...common, name: "Cash", data: [seg(actual[4]), targetCash], itemStyle: { color: "#8b97ad" }, label: { ...common.label, color: "#0c1322" } },
      ],
    };
  }, [alloc]);

  const streamOption = useMemo<echarts.EChartsOption>(() => {
    const items = [
      ...streamData.bars.map((bar) => ({ label: bar.label, value: bar.value })),
      { label: "Total", value: streamData.total },
    ];
    const sourceOrders = state.orders.filter((order) => order.fill);
    return {
      animation: false,
      grid: { left: 64, right: 72, top: 12, bottom: 26 },
      tooltip: {
        ...chartTooltip,
        trigger: "item",
        confine: true,
        formatter: (raw: unknown) => {
          const params = raw as { name: string; value: number };
          return [
            `<strong>${params.name}</strong>`,
            fmtSignedUsd(Number(params.value), 2),
            sourceOrders.length ? `src: fills ${sourceOrders.map((order) => `seq ${order.fill!.ev.seq}`).join(", ")}` : "src: no fills",
          ].join("<br/>");
        },
      },
      xAxis: {
        type: "value",
        ...chartAxisCommon,
        axisLabel: {
          ...chartAxisCommon.axisLabel,
          formatter: (value: number) =>
            value < 0 ? `-$${fmtNum(Math.abs(value), 0)}` : `$${fmtNum(value, 0)}`,
        },
      },
      yAxis: { type: "category", data: items.map((item) => item.label), ...chartAxisCommon },
      series: [
        {
          type: "bar",
          data: items.map((item) => ({
            value: item.value,
            itemStyle: {
              color: item.value > 0 ? "#34c98a" : item.value < 0 ? "#f26b6b" : "#24314a",
              borderColor: item.value === 0 ? "#8b97ad" : "transparent",
              borderWidth: 1,
            },
            label: {
              show: true,
              position: "right" as const,
              formatter: () => fmtSignedUsd(item.value, 2),
              color: "#e8edf6",
              fontSize: 10,
              fontFamily: "ui-monospace, monospace",
            },
          })),
          barWidth: 16,
          emphasis: { disabled: true },
        },
      ],
    };
  }, [streamData, state.orders]);

  const hitOption = useMemo<echarts.EChartsOption>(() => {
    const hitData = hit ? [[hit.lo * 100, hit.hi * 100]] : [];
    return {
      animation: false,
      grid: { left: 22, right: 22, top: 24, bottom: 24 },
      tooltip: { ...chartTooltip, show: false },
      xAxis: {
        type: "value",
        min: 0,
        max: 100,
        ...chartAxisCommon,
        axisLabel: { ...chartAxisCommon.axisLabel, formatter: (value: number) => `${value}%` },
      },
      yAxis: { type: "value", min: -1, max: 1, show: false },
      graphic: hit
        ? []
        : [
            {
              type: "text",
              left: "center",
              top: "36%",
              style: {
                text: "Can't tell yet",
                fill: "#e8edf6",
                fontSize: 15,
                fontWeight: 600,
                fontFamily: "ui-monospace, monospace",
              },
            },
            {
              type: "text",
              left: "center",
              top: "52%",
              style: {
                text: "0 graded calls · Wilson interval unavailable",
                fill: "#8b97ad",
                fontSize: 11,
                fontFamily: "ui-monospace, monospace",
              },
            },
          ],
      series: [
        {
          type: "custom",
          silent: true,
          data: hitData,
          renderItem: (_params: unknown, api: any) => {
            const lo = api.coord([api.value(0), 0]);
            const hi = api.coord([api.value(1), 0]);
            const y = lo[1];
            return {
              type: "group",
              children: [
                { type: "line", shape: { x1: lo[0], y1: y, x2: hi[0], y2: y }, style: { stroke: "#ff7a1a", lineWidth: 2 } },
                { type: "line", shape: { x1: lo[0], y1: y - 6, x2: lo[0], y2: y + 6 }, style: { stroke: "#ff7a1a", lineWidth: 2 } },
                { type: "line", shape: { x1: hi[0], y1: y - 6, x2: hi[0], y2: y + 6 }, style: { stroke: "#ff7a1a", lineWidth: 2 } },
              ],
            };
          },
        },
        {
          type: "scatter",
          data: hit ? [[hit.p * 100, 0]] : [],
          symbolSize: 12,
          itemStyle: { color: "#ff7a1a" },
          emphasis: { disabled: true },
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: "#8b97ad", type: [4, 4] },
            label: {
              formatter: "50%",
              color: "#8b97ad",
              fontSize: 10,
              position: "insideEndTop",
              rotate: 0,
              distance: 2,
            },
            data: [{ xAxis: 50 }],
          },
        },
      ],
    };
  }, [hit]);

  const creditOption = useMemo<echarts.EChartsOption>(() => {
    const labels = credits.points.map((point) => point.label);
    const used = credits.points.map((point) => point.cumulative);
    const budget = credits.points.map(() => credits.budget);
    if (credits.projected != null) {
      labels.push(fmtDate(credits.finalTs));
      used.push(null as unknown as number);
      budget.push(credits.budget);
    }
    const pace = used.map((_value, index) =>
      index === used.length - 1 && credits.projected != null
        ? credits.projected
        : index === used.length - 2
          ? credits.used
          : null,
    );
    return {
      animation: false,
      grid: { left: 46, right: 104, top: 18, bottom: 42 },
      tooltip: {
        ...chartTooltip,
        trigger: "axis",
        confine: true,
        formatter: (raw: unknown) => {
          const params = raw as { dataIndex: number; seriesName: string; value: number | null }[];
          const index = params[0]?.dataIndex ?? 0;
          const point = credits.points[index];
          const ev = point ? reportByTs.get(point.ts) : undefined;
          const lines = [`<strong>${labels[index]}</strong>`];
          for (const item of params) {
            if (item.value != null) lines.push(`${item.seriesName} ${fmtNum(item.value, 1)}`);
          }
          if (ev) lines.push(`src: daily_report seq ${ev.seq} · ${ev.ts}`);
          return lines.join("<br/>");
        },
      },
      xAxis: { type: "category", data: labels, ...chartAxisCommon, axisLabel: { ...chartAxisCommon.axisLabel, interval: 0 } },
      yAxis: {
        type: "value",
        min: 0,
        max: 4000,
        interval: 1000,
        ...chartAxisCommon,
        axisLabel: { ...chartAxisCommon.axisLabel, formatter: (value: number) => fmtNum(value, 0) },
      },
      series: [
        {
          name: "Cumulative credits",
          type: "line",
          data: used,
          symbol: "circle",
          symbolSize: 6,
          lineStyle: { color: "#f2c230", width: 2.4 },
          itemStyle: { color: "#f2c230" },
          endLabel: {
            show: true,
            formatter: () => `${fmtNum(credits.used, 0)} used`,
            color: "#f2c230",
            fontSize: 10,
            offset: [0, -8],
          },
          emphasis: { disabled: true },
        },
        {
          name: "Pace projection",
          type: "line",
          data: pace,
          symbol: "circle",
          symbolSize: 5,
          lineStyle: { color: "#f2c230", width: 1.4, type: [6, 4], opacity: 0.7 },
          itemStyle: { color: "#f2c230" },
          endLabel: credits.projected != null
            ? {
                show: true,
                formatter: () => `pace ${fmtNum(credits.projected ?? 0, 0)}`,
                color: "#f2c230",
                fontSize: 10,
                offset: [8, 0],
                align: "left" as const,
                verticalAlign: "middle" as const,
              }
            : { show: false },
          emphasis: { disabled: true },
        },
        {
          name: "Budget",
          type: "line",
          data: budget,
          symbol: "none",
          lineStyle: { color: "#8b97ad", width: 1.2, type: [3, 3] },
          endLabel: {
            show: true,
            formatter: () => `${fmtNum(credits.budget, 0)} budget`,
            color: "#8b97ad",
            fontSize: 10,
            offset: [0, 4],
          },
          emphasis: { disabled: true },
        },
      ],
    };
  }, [credits, reportByTs]);

  const worst = underwater.reduce(
    (best, point) => (point.drawdown < best.drawdown ? point : best),
    { drawdown: 0, label: "—" } as { drawdown: number; label: string },
  );

  return (
    <>
      <div className="view-head">
        <div>
          <h1>Mission control</h1>
          <p className="view-sub">
            Every number below is rebuilt from <code>stateAt(events, seq)</code>. Hover a number for the
            event that produced it.
          </p>
        </div>
        <div className="view-status">
          <span className="live-pill">LIVE</span>
          {state.asOf ? (
            <span>
              event #{state.asOf.gseq} · file seq{" "}
              <Trace events={[state.asOf]}>{state.asOf.seq}</Trace> · {fmtDateTime(state.asOf.ts)}
            </span>
          ) : (
            <span>no events</span>
          )}
        </div>
      </div>

      <div className="mission-grid">
        <Panel
          className="span-12"
          title="Relative performance"
          question="Are we beating the simple alternatives?"
          id="panel-performance"
        >
          <Chart
            option={performanceOption}
            height={286}
            ariaLabel="Indexed performance of our book against SPY, equal weight, follow-all and fade-all"
            summary={`Indexed to 100: our book ${perf.at(-1)?.our.toFixed(1) ?? "—"}, SPY ${perf
              .at(-1)
              ?.spy.toFixed(1)}, equal weight ${perf.at(-1)?.equalWeight.toFixed(1)}, follow-all ${perf
              .at(-1)
              ?.follow.toFixed(1)}, fade-all ${perf.at(-1)?.fade.toFixed(1)}.`}
            footnote="Indexed to 100 at the first session start. Line-end labels replace a legend; grey comparison lines are told apart by dash pattern. D drill · V veto · R rule change."
          />
          <ul className="chart-sources">
            {state.sessions
              .filter((session) => session.reportEv)
              .map((session) => (
                <li key={session.runId}>
                  <Trace events={[session.reportEv]}>{fmtDate(session.reportEv!.ts)}</Trace>
                  <span className="muted"> daily_report seq {session.reportEv!.seq}</span>
                </li>
              ))}
          </ul>
        </Panel>

        <Panel
          className="span-7"
          title="Underwater"
          question="How deep is the drawdown?"
          id="panel-underwater"
        >
          <Chart
            option={underwaterOption}
            height={224}
            ariaLabel="Drawdown from running peak with tier lines at minus two, minus four and minus six percent"
            summary={`Worst close drawdown ${worst.drawdown.toFixed(2)}% (${worst.label}); tier lines -2 / -4 / -6%.`}
            footnote="Session-close points only, from daily_report; intraday lows are not in the event log. -2% reduces risk, -4% exits only, -6% kills new entries."
          />
        </Panel>

        <Panel
          className="span-5"
          title="Allocation"
          question="Is the money where the plan says?"
          id="panel-allocation"
        >
          <Chart
            option={allocationOption}
            height={224}
            ariaLabel="Stacked bars comparing actual allocation with the plan target"
            summary={alloc ? `Actual ${alloc.totalWeight.toFixed(1)}% of ${fmtUsd(alloc.equity, 0)}. Target: core 50% · satellite 25% · cash 25%.` : "Allocation unavailable."}
            footnote="Rules fix core 50% and a 25% satellite cap, but not the drift/bounce split, so the target shows one satellite segment. The actual bar keeps drift and bounce separate. MSFT and NVDA carry no sleeve class in the sample logs, so they show as satellite (unrated) in grey. Actual may not reach 100% because marks are last event prints."
          />
          {alloc ? (
            <ul className="position-list">
              {state.positions.map((position) => {
                const clickable = position.sleeve !== "core" && position.decisionId;
                return (
                  <li key={position.ticker}>
                    {clickable ? (
                      <button
                        type="button"
                        className="ticker-button"
                        onClick={() => onOpenDecision(position.decisionId!)}
                      >
                        {position.ticker}
                      </button>
                    ) : (
                      <span className="ticker-static">{position.ticker}</span>
                    )}
                    <span className={`sleeve sleeve-${position.sleeve}`}>{sleeveLabel(position.sleeve)}</span>
                    <Trace events={[position.markEv]} note="qty × last event print">
                      <span className="muted">{fmtUsd(position.qty * position.lastPrice, 0)}</span>
                    </Trace>
                    <Num
                      value={alloc.equity > 0 ? (position.qty * position.lastPrice * 100) / alloc.equity : 0}
                      format={(value) => fmtPct(value, 2)}
                      events={[position.markEv, position.entryEv]}
                      note="value at last event print ÷ reported equity"
                    />
                  </li>
                );
              })}
            </ul>
          ) : null}
        </Panel>

        <Panel
          className="span-6"
          title="Which stream made money?"
          question="Signed realized P&L by sleeve, after fees"
          id="panel-streams"
        >
          <Chart
            option={streamOption}
            height={214}
            ariaLabel="Signed horizontal bars for realized core, drift, bounce and total P&L"
            summary={`Drift ${fmtSignedUsd(streamData.bars[1].value, 2)}, bounce ${fmtSignedUsd(
              streamData.bars[2].value,
              2,
            )}, core ${fmtSignedUsd(streamData.bars[0].value, 2)}, total ${fmtSignedUsd(
              streamData.total,
              2,
            )}.`}
            footnote={streamData.note}
          />
        </Panel>

        <Panel
          className="span-6"
          title="Hit rate"
          question="Is the hit rate better than a coin?"
          id="panel-hitrate"
        >
          <Chart
            option={hitOption}
            height={214}
            ariaLabel="Wilson 95% interval for hit rate against a 50% line"
            summary="Can't tell yet: no graded calls, so the Wilson interval is unavailable."
            footnote="H1 becomes assessable only when outcome events exist. A constant 50% forecast is the coin comparison."
          />
        </Panel>

        <Panel
          className="span-7"
          title="Limit headroom"
          question="How close is each limit?"
          id="panel-limits"
        >
          <ul className="bullet-list">
            {limitData.map((item) => {
              const ratio = item.value == null ? 0 : Math.min(100, (item.value / item.max) * 100);
              const display =
                item.kind === "pct"
                  ? `${item.value == null ? "—" : item.value.toFixed(2)}% / ${item.max}%`
                  : item.kind === "ratio"
                    ? `${item.value == null ? "—" : item.value.toFixed(2)} / ${item.max.toFixed(2)}`
                    : `${item.value == null ? "—" : item.value} / ${item.max}`;
              return (
                <li key={item.key} className={`bullet${item.breach ? " breach" : ""}${item.value == null ? " na" : ""}`}>
                  <div className="bullet-head">
                    <span className="bullet-label">{item.label}</span>
                    <Trace events={[item.ev]} note={item.key === "correlation" ? "not computable from the event logs" : undefined}>
                      <span className="bullet-read num">{display}</span>
                    </Trace>
                  </div>
                  <div className="bullet-track" aria-hidden="true">
                    <div className="bullet-fill" style={{ width: `${ratio}%` }} />
                    <div className="bullet-limit" />
                  </div>
                  <p className="bullet-detail">{item.detail}</p>
                </li>
              );
            })}
          </ul>
          <p className="tiny">
            Bullet marks sit at the documented limit. Largest position counts satellite stocks only;
            core ETFs are exempt (docs/risk-desk.md).
          </p>
        </Panel>

        <Panel
          className="span-5"
          title="Credits"
          question="Will credits last?"
          id="panel-credits"
        >
          {credits.unavailable ? <p className="empty">Credit usage unavailable: rating events contain null credits. No total or pace is inferred.</p> : <Chart
            option={creditOption}
            height={244}
            ariaLabel="Cumulative credits on a linear scale from zero to 4000 against a 3500 credit budget and dashed pace projection"
            summary={`${fmtNum(credits.used, 0)} of ${fmtNum(credits.budget, 0)} credits used; ${
              credits.projected != null
                ? `pace projects ${fmtNum(credits.projected, 0)} by ${fmtDate(credits.finalTs)}.`
                : "no projection available."
            }`}
            footnote="Linear scale 0 to 4,000. Cumulative credits from daily_report; pace = credits used ÷ completed sessions × remaining weekdays to 27 Nov, assuming the current rate holds."
          />}
        </Panel>

        <Panel
          className="span-12"
          title="Today's run"
          question="Ordered steps from the latest session; yellow top border = agent, grey = code"
          id="panel-run"
        >
          <div className="run-head">
            <span className="chip">{state.liveSession?.runId ?? "no session"}</span>
            <span className="muted">
              {state.liveSession ? `${state.liveSession.date} · ${state.liveSession.events.length} events` : "—"}
            </span>
          </div>
          {steps.length > 0 ? (
            <ol className="run-strip">
              {steps.map((step) => (
                <li key={step.key} className={`run-step ${step.agent ? "agent" : "code"} status-${step.status}`}>
                  <div className="run-top">
                    <span className="run-label">{step.label}</span>
                    <span className={`run-status ${step.status}`}>{step.status}</span>
                  </div>
                  <p className="run-note">{step.note}</p>
                  {step.at ? (
                    <Trace events={[step.ev]}>
                      <span className="run-time num">{step.at.slice(11, 19)} UTC</span>
                    </Trace>
                  ) : (
                    <span className="run-time">no event</span>
                  )}
                </li>
              ))}
            </ol>
          ) : (
            <p className="empty">No session events loaded.</p>
          )}
        </Panel>

        <Panel className="span-12" title="Data notes" question="What the logs do not support" id="panel-notes">
          <ul className="data-notes">
            {notes.map((note) => (
              <li key={note.key}>
                <Trace events={[note.ev]}>{note.text}</Trace>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </>
  );
}
