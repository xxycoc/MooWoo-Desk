import { useEffect, useState, type ReactNode } from "react";
import type { LoadedEvent } from "../data/types";

function sourceText(events: (LoadedEvent | null | undefined)[], note?: string): string {
  const lines = events
    .filter((event): event is LoadedEvent => Boolean(event))
    .slice(0, 3)
    .map((event) => `${event.runId} · seq ${event.seq} · ${event.type} · ${event.ts}`);
  if (note) lines.push(`note: ${note}`);
  return lines.join("\n");
}

export function Trace({
  events,
  note,
  children,
  className = "",
}: {
  events?: (LoadedEvent | null | undefined)[];
  note?: string;
  children: ReactNode;
  className?: string;
}) {
  const text = events ? sourceText(events, note) : note ? `note: ${note}` : "";
  return (
    <span
      className={`trace ${className}`.trim()}
      data-trace={text || undefined}
      tabIndex={text ? 0 : undefined}
      title={text || undefined}
    >
      {children}
    </span>
  );
}

export function Num({
  value,
  format,
  events,
  note,
  className = "",
}: {
  value: number | null | undefined;
  format: (value: number) => string;
  events?: (LoadedEvent | null | undefined)[];
  note?: string;
  className?: string;
}) {
  const display = value == null || !Number.isFinite(value) ? "—" : format(value);
  return (
    <Trace events={events} note={note} className={`num ${className}`.trim()}>
      {display}
    </Trace>
  );
}

export function TraceTooltip() {
  const [tip, setTip] = useState<{ text: string; x: number; y: number } | null>(null);

  useEffect(() => {
    const read = (element: Element | null): string | null => {
      const holder = element?.closest?.("[data-trace]") as HTMLElement | null;
      return holder?.getAttribute("data-trace") || null;
    };
    const onOver = (event: MouseEvent) => {
      const text = read(event.target as Element);
      if (!text) return;
      setTip({ text, x: event.clientX + 14, y: event.clientY + 16 });
    };
    const onOut = (event: MouseEvent) => {
      if (read(event.target as Element)) setTip(null);
    };
    const onFocus = (event: FocusEvent) => {
      const target = event.target as HTMLElement;
      const text = read(target);
      if (!text) return;
      const rect = target.getBoundingClientRect();
      setTip({ text, x: rect.left, y: rect.bottom + 6 });
    };
    const onBlur = () => setTip(null);
    const onScroll = () => setTip(null);

    document.addEventListener("mouseover", onOver);
    document.addEventListener("mouseout", onOut);
    document.addEventListener("focusin", onFocus);
    document.addEventListener("focusout", onBlur);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      document.removeEventListener("mouseover", onOver);
      document.removeEventListener("mouseout", onOut);
      document.removeEventListener("focusin", onFocus);
      document.removeEventListener("focusout", onBlur);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, []);

  if (!tip) return null;
  const x = Math.max(8, Math.min(tip.x, window.innerWidth - 300));
  const y = Math.max(8, Math.min(tip.y, window.innerHeight - 92));
  return (
    <div className="trace-tip" role="tooltip" style={{ left: x, top: y }}>
      {tip.text}
    </div>
  );
}
