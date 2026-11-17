import { useEffect, useRef } from "react";
import * as echarts from "echarts";

export const CHART_FONT =
  'ui-monospace, "Cascadia Code", "SFMono-Regular", Menlo, Consolas, monospace';

export function Chart({
  option,
  height,
  ariaLabel,
  summary,
  footnote,
}: {
  option: echarts.EChartsOption;
  height: number;
  ariaLabel: string;
  summary: string;
  footnote?: string;
}) {
  const holder = useRef<HTMLDivElement | null>(null);
  const instance = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!holder.current) return;
    const chart = echarts.init(holder.current, undefined, { renderer: "canvas" });
    instance.current = chart;
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(holder.current);
    return () => {
      observer.disconnect();
      chart.dispose();
      instance.current = null;
    };
  }, []);

  useEffect(() => {
    instance.current?.setOption(
      {
        backgroundColor: "transparent",
        animation: false,
        textStyle: { fontFamily: CHART_FONT, color: "#8b97ad" },
        ...option,
      },
      { notMerge: true },
    );
  }, [option]);

  return (
    <figure className="chart-figure">
      <div
        ref={holder}
        className="chart-canvas"
        style={{ height }}
        role="img"
        aria-label={ariaLabel}
      />
      <figcaption className="chart-summary">{summary}</figcaption>
      {footnote ? (
        <details className="chart-more">
          <summary>About this chart</summary>
          <p className="chart-footnote">{footnote}</p>
        </details>
      ) : null}
    </figure>
  );
}

export const chartAxisCommon = {
  axisLine: { lineStyle: { color: "#24314a" } },
  axisTick: { show: false },
  axisLabel: { color: "#8b97ad", fontSize: 11, fontFamily: CHART_FONT },
  splitLine: { lineStyle: { color: "#1a2540" } },
} as const;

export const chartTooltip = {
  backgroundColor: "#0c1322",
  borderColor: "#24314a",
  borderWidth: 1,
  textStyle: { color: "#e8edf6", fontSize: 12, fontFamily: CHART_FONT },
  extraCssText: "box-shadow:none;border-radius:6px;",
} as const;
