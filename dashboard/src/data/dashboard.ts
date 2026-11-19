import type { DeskState, LoadedEvent, Sleeve } from "./types";
import { stateAt } from "./state";
import { wilson } from "./wilson";

export const START_CAPITAL = 100000;
export const COLORS = { book: "#ff7a1a", agent: "#f2c230", core: "#5b8def", drift: "#a78bfa", bounce: "#2dd4bf", unclassified: "#8b97ad", green: "#34c98a", red: "#f26b6b" };

const eastern = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
  weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});
const singapore = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Singapore", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

export function sgtTime(value: string | Date | number | null): string {
  if (value == null) return "Not recorded";
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? `${singapore.format(date)} SGT` : "Not recorded";
}

function etParts(date: Date) {
  const parts = eastern.formatToParts(date);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return { year: +get("year"), month: +get("month"), day: +get("day"), weekday: get("weekday"), minutes: +get("hour") * 60 + +get("minute") };
}

function closeMinute(date: ReturnType<typeof etParts>): number {
  return date.year === 2026 && date.month === 11 && date.day === 27 ? 13 * 60 : 16 * 60;
}

export function regularHours(now: Date): boolean {
  const parts = etParts(now);
  return !["Sat", "Sun"].includes(parts.weekday) && parts.minutes >= 9 * 60 + 30 && parts.minutes < closeMinute(parts);
}

export interface ScheduledRun { at: Date; kind: string }

export function nextScheduledRun(now: Date): ScheduledRun {
  const today = etParts(now);
  for (let offset = 0; offset < 8; offset += 1) {
    const noonUtc = new Date(Date.UTC(today.year, today.month - 1, today.day + offset, 12));
    const parts = etParts(noonUtc);
    if (["Sat", "Sun"].includes(parts.weekday)) continue;
    const close = closeMinute(parts);
    const slots = [{ minute: 9 * 60 + 35, kind: "Morning" }];
    for (let minute = 10 * 60; minute <= close - 30; minute += 30) slots.push({ minute, kind: "Watcher" });
    slots.push({ minute: close - 5, kind: "Close watcher" }, { minute: close + 10, kind: "Audit" });
    for (const slot of slots) {
      const at = new Date(noonUtc.getTime() + (slot.minute - parts.minutes) * 60 * 1000);
      if (at.getTime() > now.getTime()) return { at, kind: slot.kind };
    }
  }
  throw new Error("No scheduled weekday found");
}

export function runKind(events: LoadedEvent[]): string {
  const explicit = events.find((event) => typeof event.runKind === "string")?.runKind;
  const hint = `${explicit ?? ""} ${events[0]?.runId ?? ""} ${events.filter((event) => event.prompt === "Session runner").map((event) => event.text).join(" ")}`;
  if (/audit/i.test(hint)) return "Audit";
  if (/morning/i.test(hint)) return "Morning";
  if (/watch/i.test(hint)) {
    const parts = etParts(new Date(events[0].ts));
    return parts.minutes >= closeMinute(parts) - 5 ? "Close watcher" : "Watcher";
  }
  return "Unspecified";
}

export function isRestart(event: LoadedEvent): boolean {
  return event.type === "halt" && event.cleared === true && /^manual[ -]restart\b/i.test(String(event.reason ?? ""));
}

export interface RunRow {
  id: string; at: string; lastAt: string; kind: string; result: string;
  tone: "ok" | "warn" | "halt"; events: LoadedEvent[];
}

export function lastRuns(events: LoadedEvent[], state: DeskState): RunRow[] {
  const groups = new Map<string, LoadedEvent[]>();
  for (const event of events) {
    const rows = groups.get(event.runId) ?? [];
    rows.push(event);
    groups.set(event.runId, rows);
  }
  return [...groups].map(([id, rows]) => {
    const ordered = [...rows].sort((left, right) => Date.parse(left.ts) - Date.parse(right.ts) || left.seq - right.seq);
    const halt = [...ordered].reverse().find((event) => event.type === "halt");
    const abort = [...ordered].reverse().find((event) => event.type === "run_aborted" || /\bsession aborted\b/i.test(String(event.text ?? "")));
    const skip = ordered.find((event) => /calendar skip/i.test(String(event.text ?? event.reason ?? "")) || event.type === "calendar_skip");
    const bought = [...new Set(state.orders.filter((order) => order.runId === id && order.side === "BUY" && order.appliedQty > 0).map((order) => order.ticker))];
    let result = bought.length ? `bought ${bought.join(", ")}` : "ok";
    let tone: RunRow["tone"] = "ok";
    if (skip) result = "calendar skip";
    if (abort) { result = `aborted: ${String(abort.reason ?? abort.text ?? "reason not recorded")}`; tone = "warn"; }
    if (halt && !isRestart(halt)) { result = `halted: ${String(halt.reason ?? "reason not recorded")}`; tone = "halt"; }
    return { id, at: ordered[0].ts, lastAt: ordered[ordered.length - 1].ts, kind: runKind(ordered), result, tone, events: ordered };
  }).sort((left, right) => Date.parse(right.at) - Date.parse(left.at));
}

export function healthStatus(events: LoadedEvent[], runs: RunRow[], now: Date) {
  const ordered = [...events].sort((left, right) => Date.parse(left.ts) - Date.parse(right.ts) || left.gseq - right.gseq);
  const halt = [...ordered].reverse().find((event) => event.type === "halt");
  if (halt && !isRestart(halt)) return { tone: "halt", message: `HALTED: ${String(halt.reason ?? "reason not recorded")}` };
  if (runs[0]?.events.some((event) => event.type === "run_aborted" || /\bsession aborted\b/i.test(String(event.text ?? "")))) {
    return { tone: "warn", message: "Latest run aborted" };
  }
  const lastAt = ordered.at(-1)?.ts;
  if (regularHours(now) && (!lastAt || now.getTime() - Date.parse(lastAt) > 45 * 60 * 1000)) {
    return { tone: "warn", message: "No event for more than 45 minutes during US regular hours" };
  }
  return { tone: "ok", message: "Running normally" };
}

export function equityPoints(events: LoadedEvent[], includeAudit = false) {
  return events.filter((event) => (event.type === "run_started" || (includeAudit && event.type === "daily_report")) && typeof event.equity === "number" && Number.isFinite(event.equity))
    .map((event) => ({ ts: event.ts, equity: event.equity as number }));
}

export function streamPnl(state: DeskState) {
  const sleeves: Sleeve[] = ["core", "drift", "bounce"];
  const open = (sleeve: Sleeve) => state.positions.filter((position) => position.sleeve === sleeve).reduce((sum, position) => sum + (position.lastPrice - position.avgCost) * position.qty, 0);
  const rows = sleeves.map((sleeve) => ({ name: sleeve, value: open(sleeve), color: COLORS[sleeve] }));
  if (state.positions.some((position) => position.sleeve === "unclassified")) rows.push({ name: "unclassified", value: open("unclassified"), color: COLORS.unclassified });
  return [...rows, { name: "total", value: rows.reduce((sum, row) => sum + row.value, 0), color: COLORS.book }];
}

export function closedTradeScore(events: LoadedEvent[]) {
  const closed: number[] = [];
  for (const event of events) {
    if (event.type !== "fill") continue;
    const before = stateAt(events, event.gseq - 1);
    const position = before.positions.find((item) => item.ticker === event.ticker);
    if (!position) continue;
    const after = stateAt(events, event.gseq);
    if (after.positions.some((item) => item.ticker === position.ticker)) continue;
    closed.push(position.realized + after.realizedBySleeve[position.sleeve] - before.realizedBySleeve[position.sleeve]);
  }
  const wins = closed.filter((value) => value > 0).length;
  return { count: closed.length, wins, interval: wilson(wins, closed.length) };
}

export function benchmarkSeries(events: LoadedEvent[]) {
  const reports = new Map<string, LoadedEvent>();
  for (const event of events) {
    if (event.type !== "daily_report") continue;
    const date = etParts(new Date(event.ts));
    reports.set(`${date.year}-${date.month}-${date.day}`, event);
  }
  const definitions = [
    { name: "SPY", read: (event: LoadedEvent) => event.baselinePct },
    { name: "Follow-all", read: (event: LoadedEvent) => (event.shadowPct as Record<string, unknown> | undefined)?.follow },
    { name: "Fade-all", read: (event: LoadedEvent) => (event.shadowPct as Record<string, unknown> | undefined)?.fade },
  ];
  return definitions.map(({ name, read }) => {
    let index = 100;
    let complete = true;
    const points: [string, number][] = [];
    for (const report of reports.values()) {
      const value = read(report);
      if (typeof value !== "number" || !Number.isFinite(value)) { complete = false; continue; }
      if (!complete) continue;
      index *= 1 + value / 100;
      points.push([report.ts, index]);
    }
    return { name, points, complete: complete && points.length > 0 };
  });
}
