import type {
  DeskState,
  LoadedEvent,
  RunStep,
  Sleeve,
} from "./types";
import { RULES } from "./rules";
import { fmtDate } from "./format";

export interface PerformancePoint {
  label: string;
  ts: string;
  our: number;
  spy: number;
  equalWeight: number;
  follow: number;
  fade: number;
}

export interface UnderwaterPoint {
  label: string;
  ts: string;
  equity: number;
  drawdown: number;
}

export interface MarkerSet {
  date: string;
  drills: number;
  vetoes: number;
  ruleChanges: number;
}

export function performanceSeries(state: DeskState): PerformancePoint[] {
  const first = state.sessions[0];
  const base = first?.startEquity || 100000;
  const points: PerformancePoint[] = [
    { label: "Start", ts: first?.startTs ?? "", our: 100, spy: 100, equalWeight: 100, follow: 100, fade: 100 },
  ];
  let spy = 100;
  let equalWeight = 100;
  let follow = 100;
  let fade = 100;
  for (const session of state.sessions) {
    if (!session.reportEv || !session.shadowPct || session.endEquity == null) continue;
    spy *= 1 + (session.baselinePct ?? 0) / 100;
    equalWeight *= 1 + session.shadowPct.equal_weight / 100;
    follow *= 1 + session.shadowPct.follow / 100;
    fade *= 1 + session.shadowPct.fade / 100;
    points.push({
      label: fmtDate(session.reportEv.ts),
      ts: session.reportEv.ts,
      our: (session.endEquity / base) * 100,
      spy,
      equalWeight,
      follow,
      fade,
    });
  }
  return points;
}

export function underwaterSeries(state: DeskState): UnderwaterPoint[] {
  const first = state.sessions[0];
  if (!first) return [];
  const points: UnderwaterPoint[] = [
    { label: "Start", ts: first.startTs, equity: first.startEquity, drawdown: 0 },
  ];
  let peak = first.startEquity;
  for (const session of state.sessions) {
    if (session.endEquity == null || !session.reportEv) continue;
    peak = Math.max(peak, session.endEquity);
    points.push({
      label: fmtDate(session.reportEv.ts),
      ts: session.reportEv.ts,
      equity: session.endEquity,
      drawdown: (session.endEquity / peak - 1) * 100,
    });
  }
  return points;
}

export function markerSets(state: DeskState): MarkerSet[] {
  const byDate = new Map<string, MarkerSet>();
  const ensure = (date: string) => {
    let set = byDate.get(date);
    if (!set) {
      set = { date, drills: 0, vetoes: 0, ruleChanges: 0 };
      byDate.set(date, set);
    }
    return set;
  };
  for (const drill of state.drills) ensure(drill.date).drills += 1;
  for (const veto of state.vetoes) ensure(veto.ev.ts.slice(0, 10)).vetoes += 1;
  for (const change of state.ruleChanges) ensure(change.date).ruleChanges += 1;
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
}

export interface Allocation {
  equity: number;
  values: Record<Sleeve | "cash", number>;
  weights: Record<Sleeve | "cash", number>;
  unclassifiedTickers: string[];
  totalWeight: number;
}

export function allocation(state: DeskState): Allocation | null {
  const equity = state.equity ?? state.sessionStartEquity;
  if (!equity) return null;
  const values: Record<Sleeve | "cash", number> = {
    core: 0,
    drift: 0,
    bounce: 0,
    unclassified: 0,
    cash: state.cash ?? 0,
  };
  const unclassifiedTickers: string[] = [];
  for (const position of state.positions) {
    const value = position.qty * position.lastPrice;
    values[position.sleeve] += value;
    if (position.sleeve === "unclassified") unclassifiedTickers.push(position.ticker);
  }
  const weights = Object.fromEntries(
    Object.entries(values).map(([key, value]) => [key, (value / equity) * 100]),
  ) as Record<Sleeve | "cash", number>;
  const totalWeight = Object.values(weights).reduce((sum, value) => sum + value, 0);
  return { equity, values, weights, unclassifiedTickers, totalWeight };
}

export interface StreamBar {
  key: Sleeve;
  label: string;
  value: number;
  available: boolean;
}

export function streams(state: DeskState): { bars: StreamBar[]; total: number; note: string } {
  const bars: StreamBar[] = [
    { key: "core", label: "Core", value: state.realizedBySleeve.core, available: false },
    { key: "drift", label: "Drift", value: state.realizedBySleeve.drift, available: true },
    { key: "bounce", label: "Bounce", value: state.realizedBySleeve.bounce, available: true },
  ];
  const total = state.realizedBySleeve.core + state.realizedBySleeve.drift + state.realizedBySleeve.bounce;
  const openUnclassified = state.positions.filter((position) => position.sleeve === "unclassified");
  const note =
    openUnclassified.length > 0
      ? `Realized, after FEES-01, at last event prints. Open unclassified satellite names (${openUnclassified
          .map((position) => position.ticker)
          .join(", ")}) are not marks and are excluded.`
      : "Realized, after FEES-01, at last event prints. Open positions are not marked beyond those prints.";
  return { bars, total, note };
}

export interface LimitItem {
  key: string;
  label: string;
  value: number | null;
  max: number;
  kind: "pct" | "ratio" | "count";
  detail: string;
  ev: LoadedEvent | null;
  breach: boolean;
}

export function limits(state: DeskState): LimitItem[] {
  const equity = state.equity ?? state.sessionStartEquity ?? 0;
  const satellites = state.positions.filter((position) => position.sleeve !== "core");
  const largest = satellites.reduce<{ value: number; ticker: string; ev: LoadedEvent } | null>(
    (best, position) => {
      const value = position.qty * position.lastPrice;
      if (!best || value > best.value) return { value, ticker: position.ticker, ev: position.markEv };
      return best;
    },
    null,
  );
  const satelliteValue = satellites.reduce((sum, position) => sum + position.qty * position.lastPrice, 0);
  const pnlPct = state.liveSession?.pnlPct ?? null;
  const lossPct = pnlPct != null ? Math.max(0, -pnlPct) : null;
  const orders = state.liveSession?.ordersSubmitted ?? 0;
  const lastOrderEv =
    [...state.orders].reverse().find((order) => order.runId === state.liveSession?.runId)?.ev ?? null;

  return [
    {
      key: "largest",
      label: "Largest satellite position",
      value: equity > 0 && largest ? (largest.value / equity) * 100 : 0,
      max: RULES.perNameCap * 100,
      kind: "pct",
      detail: largest
        ? `${largest.ticker} at ${(largest.value / equity * 100).toFixed(2)}% of equity`
        : "no satellite position open",
      ev: largest?.ev ?? null,
      breach: !!largest && largest.value / equity > RULES.perNameCap,
    },
    {
      key: "satellite",
      label: "Satellite stock total",
      value: equity > 0 ? (satelliteValue / equity) * 100 : 0,
      max: RULES.satelliteCap * 100,
      kind: "pct",
      detail: "core ETFs are exempt from this cap",
      ev: satellites[0]?.markEv ?? null,
      breach: equity > 0 && satelliteValue / equity > RULES.satelliteCap,
    },
    {
      key: "loss",
      label: "Today's loss",
      value: lossPct,
      max: RULES.dailyLossHalt * 100,
      kind: "pct",
      detail: pnlPct != null ? `session P&L ${pnlPct.toFixed(2)}%` : "no daily report yet",
      ev: state.liveSession?.reportEv ?? null,
      breach: lossPct != null && lossPct >= RULES.dailyLossHalt * 100,
    },
    {
      key: "correlation",
      label: "Max pair correlation",
      value: null,
      max: RULES.maxCorrelation,
      kind: "ratio",
      detail: "60 aligned daily returns are not in the event logs",
      ev: null,
      breach: false,
    },
    {
      key: "orders",
      label: "Orders this session",
      value: orders,
      max: RULES.maxOrdersPerSession,
      kind: "count",
      detail: `${orders} submitted · ${RULES.maxOrdersPerSession} allowed`,
      ev: lastOrderEv,
      breach: orders >= RULES.maxOrdersPerSession,
    },
  ];
}

export interface CreditPoint {
  label: string;
  ts: string;
  cumulative: number;
}

export function creditPlan(state: DeskState): {
  unavailable: boolean;
  points: CreditPoint[];
  used: number;
  completedSessions: number;
  remainingSessions: number;
  pace: number;
  projected: number | null;
  budget: number;
  finalTs: string;
} {
  const unavailable = state.ratings.some((rating) => rating.credits == null);
  const points: CreditPoint[] = [];
  let cumulative = 0;
  for (const session of state.sessions) {
    const credits = session.creditsUsed ?? session.ratingCredits;
    if (credits == null || credits <= 0) continue;
    cumulative += credits;
    points.push({
      label: fmtDate(session.endTs ?? session.startTs),
      ts: session.endTs ?? session.startTs,
      cumulative,
    });
  }
  const completedSessions = points.length;
  const lastDate = points.length > 0 ? points[points.length - 1].ts.slice(0, 10) : "";
  const remainingSessions = lastDate ? weekdaysAfter(lastDate, RULES.finalDay) : 0;
  const pace = completedSessions > 0 ? cumulative / completedSessions : 0;
  const projected = completedSessions > 0 && remainingSessions > 0 ? cumulative + pace * remainingSessions : null;
  return {
    unavailable,
    points: unavailable ? [] : points,
    used: cumulative,
    completedSessions,
    remainingSessions,
    pace,
    projected: unavailable ? null : projected,
    budget: RULES.creditBudget,
    finalTs: `${RULES.finalDay}T21:00:00Z`,
  };
}

function weekdaysAfter(afterDate: string, finalDate: string): number {
  const cursor = new Date(`${afterDate}T00:00:00Z`);
  const end = new Date(`${finalDate}T00:00:00Z`);
  if (Number.isNaN(cursor.valueOf()) || Number.isNaN(end.valueOf())) return 0;
  let count = 0;
  while (cursor < end) {
    cursor.setUTCDate(cursor.getUTCDate() + 1);
    const day = cursor.getUTCDay();
    if (day >= 1 && day <= 5) count += 1;
  }
  return count;
}

interface StepSpec {
  key: string;
  label: string;
  agent: boolean;
  match: (event: LoadedEvent) => boolean;
  note: (events: LoadedEvent[]) => string;
}

export function runSteps(state: DeskState): RunStep[] {
  const session = state.liveSession;
  if (!session) return [];
  const events = session.events;
  const specs: StepSpec[] = [
    {
      key: "schedule",
      label: "Schedule",
      agent: false,
      match: (event) => event.type === "run_started",
      note: () => "run opened",
    },
    {
      key: "screen",
      label: "Screen",
      agent: false,
      match: (event) => event.type === "screen",
      note: () => `${events.filter((event) => event.type === "screen").length} screen row(s)`,
    },
    {
      key: "analysts",
      label: "Analysts",
      agent: true,
      match: (event) => event.type === "rating",
      note: (matched) => `${matched.length} rating(s)`,
    },
    {
      key: "debate",
      label: "Debate",
      agent: true,
      match: (event) => event.type === "rating" && event.tier === "debate",
      note: (matched) => `${matched.length} debate rating(s)`,
    },
    {
      key: "quick",
      label: "Quick",
      agent: true,
      match: (event) => event.type === "rating" && event.tier === "quick",
      note: (matched) => `${matched.length} quick rating(s)`,
    },
    {
      key: "risk",
      label: "Risk desk",
      agent: false,
      match: (event) => event.type === "risk_verdict",
      note: (matched) => `${matched.length} verdict(s)`,
    },
    {
      key: "executor",
      label: "Executor",
      agent: true,
      match: (event) => event.type === "order_submitted",
      note: (matched) => `${matched.length} submission(s)`,
    },
    {
      key: "watcher",
      label: "Watcher",
      agent: false,
      match: (event) => event.type === "stop_hit" || event.type === "halt",
      note: () => "stop and halt checks",
    },
    {
      key: "auditor",
      label: "Auditor",
      agent: true,
      match: (event) => event.type === "daily_report",
      note: () => "daily report logged",
    },
  ];

  const steps: RunStep[] = specs.map((spec) => {
    const matched = events.filter(spec.match);
    const last = matched.length > 0 ? matched[matched.length - 1] : null;
    return {
      key: spec.key,
      label: spec.label,
      agent: spec.agent,
      status: last ? "done" : "waiting",
      at: last?.ts ?? null,
      ev: last,
      note: spec.note(matched),
    };
  });

  const doneFlags = steps.map((step) => step.status === "done");
  for (let i = 0; i < steps.length; i += 1) {
    if (doneFlags[i]) continue;
    const earlierDone = doneFlags.slice(0, i).every(Boolean);
    const laterDone = doneFlags.slice(i + 1).some(Boolean);
    if (earlierDone && !laterDone) steps[i].status = "running";
  }
  return steps;
}

export interface CorrelationMatrix {
  names: string[];
  cells: (number | null)[][];
  note: string;
}

export function correlationMatrix(state: DeskState): CorrelationMatrix {
  const names = state.positions.filter((position) => position.sleeve !== "core").map((position) => position.ticker);
  const cells = names.map((row) => names.map((col) => (row === col ? 1 : null)));
  return {
    names,
    cells,
    note:
      names.length < 2
        ? "Fewer than two open satellite positions."
        : "No aligned 60-day return series exists in the event logs, so off-diagonal cells are not computed. Cells above 0.80 would be outlined.",
  };
}

export interface DataNote {
  key: string;
  text: string;
  ev: LoadedEvent | null;
}

export function dataNotes(state: DeskState): DataNote[] {
  const notes: DataNote[] = [
    {
      key: "fixture",
      text: "Static paper-trading events; included fixtures are explicitly labelled. Core rebalance proposals are not fills.",
      ev: state.sessions[0]?.startEv ?? null,
    },
    {
      key: "marks",
      text: `Equity is the reported figure (${state.equity != null ? `$${state.equity.toLocaleString("en-US")}` : "n/a"}); position values use the last event print, not a market mark.`,
      ev: state.equityEv,
    },
    {
      key: "shadows",
      text: "SPY, equal-weight, follow-all and fade-all lines come from daily_report fields, compounded day by day. Missing reports do not establish returns.",
      ev: state.liveSession?.reportEv ?? null,
    },
    {
      key: "hitrate",
      text: "Graded outcomes are not available in this snapshot; no hit rate is inferred.",
      ev: null,
    },
    {
      key: "correlation",
      text: "Open-position correlation needs 60 aligned daily returns, which the event logs do not carry.",
      ev: null,
    },
    {
      key: "skips",
      text: "Skips include primary ratings whose class does not map to the drift or bounce sleeves, plus reflection_note events marked skipped.",
      ev: state.skips[0]?.ev ?? null,
    },
  ];
  const markBased =
    state.cash != null
      ? state.cash + state.positions.reduce((sum, position) => sum + position.qty * position.lastPrice, 0)
      : null;
  if (markBased != null && state.equity != null) {
    const diff = markBased - state.equity;
    notes.splice(2, 0, {
      key: "reconcile",
      text: `Mark-based equity is $${markBased.toLocaleString("en-US", { maximumFractionDigits: 0 })} versus reported $${state.equity.toLocaleString(
        "en-US",
        { maximumFractionDigits: 0 },
      )} (${diff >= 0 ? "+" : "-"}$${Math.abs(diff).toLocaleString("en-US", { maximumFractionDigits: 0 })}). Event prints and broker snapshot marks may differ.`,
      ev: state.cashEv,
    });
  }
  return notes;
}
