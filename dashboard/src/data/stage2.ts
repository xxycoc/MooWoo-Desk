import type {
  DecisionRecord,
  DeskState,
  LoadedEvent,
  RatingRecord,
  SessionSummary,
  SkipRecord,
  VerdictRecord,
} from "./types";
import { RULES } from "./rules";
import { UNIVERSE, marketCapFor } from "./universe";

export type PreVerdict = "supported" | "rejected" | "can't tell yet";

export interface ClassMeta {
  label: string;
  color: string;
  sign: 1 | -1 | 0;
}

export const CLASS_META: Record<string, ClassMeta> = {
  explained_up: { label: "Explained up", color: "#a78bfa", sign: 1 },
  explained_down: { label: "Explained down", color: "#f26b6b", sign: -1 },
  unexplained_up: { label: "Unexplained up", color: "#5b8def", sign: -1 },
  unexplained_down: { label: "Unexplained down", color: "#2dd4bf", sign: 1 },
};

const UNRATED: ClassMeta = { label: "Unrated", color: "#8b97ad", sign: 0 };
const SKIP_COLOR = "#8b97ad";

export function classMeta(cls: string | null | undefined): ClassMeta {
  return (cls && CLASS_META[cls]) || UNRATED;
}

export function skipForDecision(state: DeskState, decision: DecisionRecord): SkipRecord | null {
  return (
    state.skips.find(
      (skip) =>
        (skip.decisionId && skip.decisionId === decision.id) ||
        (!skip.decisionId && skip.runId === decision.runId && skip.ticker === decision.ticker),
    ) ?? null
  );
}

function decisionForRating(state: DeskState, rating: RatingRecord): DecisionRecord | null {
  return state.decisions[rating.decisionId ?? `${rating.runId}:${rating.ticker}`] ?? null;
}

/* ------------------------------------------------------------------ */
/* Mover radar                                                        */
/* ------------------------------------------------------------------ */

export interface RadarPoint {
  decisionId: string;
  ticker: string;
  cls: string | null;
  label: string;
  color: string;
  z: number;
  rvol: number;
  movePct: number;
  marketCap: number | null;
  picked: boolean;
  traded: boolean;
  skipped: boolean;
  status: string;
  detail: string;
  confidence: number | null;
  tier: string | null;
  screenEv: LoadedEvent;
  ratingEv: LoadedEvent | null;
}

export interface FunnelStep {
  key: string;
  label: string;
  value: number;
  drop: number | null;
  reason: string;
  note?: string;
}

export interface RadarView {
  session: SessionSummary;
  points: RadarPoint[];
  funnel: FunnelStep[];
  outOfScreenTrades: string[];
  caveat: string;
}

export function radarView(state: DeskState, runId: string): RadarView | null {
  const session = state.sessions.find((candidate) => candidate.runId === runId);
  if (!session) return null;

  const points: RadarPoint[] = [];
  for (const decision of Object.values(state.decisions)) {
    if (decision.runId !== runId || !decision.screen) continue;
    const rating = decision.rating;
    const skip = skipForDecision(state, decision);
    const verdict = decision.verdicts[decision.verdicts.length - 1] ?? null;
    const traded = decision.fills.some((fill) => fill.runId === runId);
    const picked = decision.screen.picked;
    const skipped = Boolean(skip) || !picked;
    let status = "Picked, no ticket";
    if (traded) status = "Traded";
    else if (verdict?.verdict === "veto") status = "Vetoed";
    else if (!picked) status = "Not picked";
    else if (skip) status = "Skipped";
    else if (decision.intents.length > 0) status = "No fill";

    const detail = verdict?.firedRule
      ? `veto: ${verdict.firedRule}`
      : skip?.reason
        ? skip.reason
        : traded
          ? "fill logged in this session"
          : picked
            ? "no order intent or fill is logged"
            : "not in the screen's picked list";

    const meta = classMeta(rating?.cls);
    points.push({
      decisionId: decision.id,
      ticker: decision.ticker,
      cls: rating?.cls ?? null,
      label: meta.label,
      color: skipped ? SKIP_COLOR : meta.color,
      z: decision.screen.candidate.z,
      rvol: decision.screen.candidate.rvol,
      movePct: decision.screen.candidate.movePct,
      marketCap: marketCapFor(decision.ticker),
      picked,
      traded,
      skipped,
      status,
      detail,
      confidence: rating?.confidence ?? null,
      tier: rating?.tier ?? null,
      screenEv: decision.screen.ev,
      ratingEv: rating?.ev ?? null,
    });
  }

  points.sort(
    (a, b) =>
      Math.abs(b.z) - Math.abs(a.z) ||
      b.rvol - a.rvol ||
      a.ticker.localeCompare(b.ticker),
  );

  const pickedCount = points.filter((point) => point.picked).length;
  const tradedCount = points.filter((point) => point.traded).length;
  const notPicked = points.filter((point) => !point.picked);
  const pickedUntraded = points.filter((point) => point.picked && !point.traded);
  const outOfScreenTrades = Object.values(state.decisions)
    .filter(
      (decision) =>
        decision.runId === runId &&
        !decision.screen &&
        decision.fills.some((fill) => fill.runId === runId),
    )
    .map((decision) => decision.ticker);

  const funnel: FunnelStep[] = [
    {
      key: "all",
      label: "All names",
      value: UNIVERSE.allNames,
      drop: null,
      reason: "tickers in the frozen universe file",
      note: `config/universe-${UNIVERSE.date}.json`,
    },
    {
      key: "gated",
      label: "Gated universe",
      value: UNIVERSE.gated,
      drop: UNIVERSE.allNames - UNIVERSE.gated,
      reason: "failed at least one frozen universe gate (market cap, float, ADV, price, exchange, ADR)",
      note: "727 passing stocks, as preregistered.",
    },
    {
      key: "movers",
      label: "Movers",
      value: points.length,
      drop: UNIVERSE.gated - points.length,
      reason: "not in screen.candidates; no per-name screen reason is logged",
      note: "Candidates are shown exactly as logged; the configured screen gate is |z| >= 2.",
    },
    {
      key: "top15",
      label: "Top 15 (picked)",
      value: pickedCount,
      drop: points.length - pickedCount,
      reason: notPicked.length
        ? `not picked: ${notPicked.map((point) => `${point.ticker} (z ${point.z.toFixed(2)})`).join(", ")}`
        : "all candidates were picked",
      note: "The logged picked list may contain fewer than 15 names.",
    },
    {
      key: "traded",
      label: "Traded",
      value: tradedCount,
      drop: pickedCount - tradedCount,
      reason: pickedUntraded.length
        ? pickedUntraded.map((point) => `${point.ticker}: ${point.status.toLowerCase()}`).join("; ")
        : "every picked name has a fill",
      note: outOfScreenTrades.length
        ? `Out-of-screen fill(s) also logged: ${outOfScreenTrades.join(", ")}.`
        : undefined,
    },
  ];

  return {
    session,
    points,
    funnel,
    outOfScreenTrades,
    caveat:
      "Bubble size uses market cap from the frozen universe file, not from the screen event. Grey means skipped or not picked; the orange ring means a fill was logged in this session.",
  };
}

/* ------------------------------------------------------------------ */
/* Truth table                                                        */
/* ------------------------------------------------------------------ */

export interface Hypothesis {
  key: "H1" | "H2" | "H3";
  title: string;
  statement: string;
  verdict: PreVerdict;
  evidence: string[];
  rule: string;
}

export interface CallMatrixRow {
  cls: string;
  label: string;
  color: string;
  calls: number;
  skips: number;
  traded: number;
  up: number | null;
  flat: number | null;
  down: number | null;
  ungraded: number;
}

export interface ConfidenceBin {
  label: string;
  single: number;
  debate: number;
  quick: number;
  total: number;
}

export interface TruthView {
  calls: number;
  graded: number;
  skippedCalls: number;
  tradedCalls: number;
  brierReported: number | null;
  hypotheses: Hypothesis[];
  matrix: CallMatrixRow[];
  bins: ConfidenceBin[];
  caveat: string;
}

export function wilson95(hits: number, calls: number): [number, number] | null {
  if (calls <= 0) return null;
  const z = 1.96;
  const p = hits / calls;
  const denominator = 1 + (z * z) / calls;
  const centre = p + (z * z) / (2 * calls);
  const spread = z * Math.sqrt((p * (1 - p)) / calls + (z * z) / (4 * calls * calls));
  return [(centre - spread) / denominator, (centre + spread) / denominator];
}

export function truthView(state: DeskState): TruthView {
  const ratings = state.ratings;
  const skippedCalls = ratings.filter((rating) => {
    const decision = decisionForRating(state, rating);
    return decision ? Boolean(skipForDecision(state, decision)) : false;
  }).length;
  const tradedCalls = ratings.filter((rating) => {
    const decision = decisionForRating(state, rating);
    return Boolean(decision && decision.fills.length > 0);
  }).length;
  const brierReported =
    [...state.sessions].reverse().find((session) => session.brier != null)?.brier ?? null;
  const graded = 0;

  const matrix: CallMatrixRow[] = Object.entries(CLASS_META).map(([cls, meta]) => {
    const rows = ratings.filter((rating) => rating.cls === cls);
    const skips = rows.filter((rating) => {
      const decision = decisionForRating(state, rating);
      return decision ? Boolean(skipForDecision(state, decision)) : false;
    }).length;
    const traded = rows.filter((rating) => {
      const decision = decisionForRating(state, rating);
      return Boolean(decision && decision.fills.length > 0);
    }).length;
    return {
      cls,
      label: meta.label,
      color: meta.color,
      calls: rows.length,
      skips,
      traded,
      up: null,
      flat: null,
      down: null,
      ungraded: rows.length,
    };
  });

  const hypotheses: Hypothesis[] = [
    {
      key: "H1",
      title: "Classification calls beat 50%",
      statement:
        "Graded calls, traded and skipped, are right more than half the time. The Wilson interval decides the verdict.",
      verdict: "can't tell yet",
      evidence: [
        `${graded} graded calls out of ${ratings.length} prelogged calls.`,
        `${skippedCalls} skip(s) are included in the call register.`,
        "No outcome event exists, so the Wilson 95% interval is unavailable.",
      ],
      rule: "Supported if the Wilson lower bound is above 50%; rejected if the upper bound is below 50%; otherwise can't tell yet.",
    },
    {
      key: "H2",
      title: "Value over simple rules",
      statement:
        "The LLM book must beat both follow-all and fade-all on the same rated decision IDs, entry opportunities, costs and exits.",
      verdict: "can't tell yet",
      evidence: [
        "0 matched decisions have observable entry and outcome returns.",
        `${state.shadows.length} daily shadow rows exist, but they are not paired decision books.`,
        "Both paired bootstrap intervals are unavailable, so H2 cannot be decided.",
      ],
      rule: "Supported only if both paired lower bounds are above zero; rejected if either upper bound is below zero; otherwise can't tell yet.",
    },
    {
      key: "H3",
      title: "Calibration",
      statement:
        "Pre-logged confidence should match the binary H1 outcome. The target is a Brier score below 0.25.",
      verdict: "can't tell yet",
      evidence: [
        "0 confidence-outcome pairs: there are no graded calls.",
        brierReported != null
          ? `daily_report reports Brier ${brierReported.toFixed(2)}, but with no graded calls that field is not an H3 computation.`
          : "No Brier score is reported.",
        "The session-cluster bootstrap interval is unavailable.",
      ],
      rule: "The point-estimate target is met below 0.25 and not met at or above 0.25. With no graded calls it is not assessable.",
    },
  ];

  const edges = [0, 0.2, 0.4, 0.6, 0.8, 1];
  const bins: ConfidenceBin[] = edges.slice(0, -1).map((low, index) => {
    const high = edges[index + 1];
    const rows = ratings.filter(
      (rating) => rating.confidence >= low && (index === edges.length - 2 ? rating.confidence <= high : rating.confidence < high),
    );
    return {
      label: `${Math.round(low * 100)}–${Math.round(high * 100)}%`,
      debate: rows.filter((rating) => rating.tier === "debate").length,
      single: rows.filter((rating) => rating.tier === "single").length,
      quick: rows.filter((rating) => rating.tier === "quick").length,
      total: rows.length,
    };
  });

  return {
    calls: ratings.length,
    graded,
    skippedCalls,
    tradedCalls,
    brierReported,
    hypotheses,
    matrix,
    bins,
    caveat:
      "The event contract has no outcome or grading event, so no call can move out of the ungraded column. Nothing here is inferred from prices.",
  };
}

/* ------------------------------------------------------------------ */
/* Risk-adjusted metrics                                               */
/* ------------------------------------------------------------------ */

export type RiskMetricKey = "sharpe" | "totalReturn" | "sortino" | "calmar" | "maxDrawdown";

export const RISK_METRICS: RiskMetricKey[] = [
  "sharpe",
  "totalReturn",
  "sortino",
  "calmar",
  "maxDrawdown",
];

export interface IntervalMetric {
  value: number | null;
  low: number | null;
  high: number | null;
  valid: number;
}

export interface RiskBook {
  key: string;
  label: string;
  note: string;
  returns: number[];
  metrics: Record<RiskMetricKey, IntervalMetric>;
}

export interface RiskView {
  books: RiskBook[];
  sessions: number;
  resamples: number;
  seed: number;
  caveat: string;
}

interface MetricSet {
  sharpe: number | null;
  totalReturn: number | null;
  sortino: number | null;
  calmar: number | null;
  maxDrawdown: number | null;
}

const SEED = 20261117;
const RESAMPLES = 2000;

function metricSet(returns: number[]): MetricSet {
  const n = returns.length;
  if (n === 0) {
    return { sharpe: null, totalReturn: null, sortino: null, calmar: null, maxDrawdown: null };
  }
  const total = returns.reduce((product, value) => product * (1 + value), 1) - 1;
  const mean = returns.reduce((sum, value) => sum + value, 0) / n;
  const variance = n > 1 ? returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (n - 1) : 0;
  const sd = Math.sqrt(variance);
  const downside = Math.sqrt(returns.reduce((sum, value) => sum + Math.min(0, value) ** 2, 0) / n);

  let equity = 1;
  let peak = 1;
  let maxDrawdown = 0;
  for (const value of returns) {
    equity *= 1 + value;
    peak = Math.max(peak, equity);
    maxDrawdown = Math.min(maxDrawdown, equity / peak - 1);
  }

  const annualiser = Math.sqrt(252);
  const annualReturn = Math.pow(1 + total, 252 / n) - 1;
  return {
    sharpe: sd > 0 ? (mean / sd) * annualiser : null,
    totalReturn: total,
    sortino: downside > 0 ? (mean / downside) * annualiser : null,
    calmar: maxDrawdown < 0 && Number.isFinite(annualReturn) ? annualReturn / Math.abs(maxDrawdown) : null,
    maxDrawdown,
  };
}

function quantile(values: number[], q: number): number {
  if (values.length === 1) return values[0];
  const position = (values.length - 1) * q;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) return values[lower];
  return values[lower] + (values[upper] - values[lower]) * (position - lower);
}

function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function intervalFor(values: (number | null)[]): { low: number | null; high: number | null; valid: number } {
  const valid = values.filter((value): value is number => value != null && Number.isFinite(value)).sort((a, b) => a - b);
  if (valid.length === 0) return { low: null, high: null, valid: 0 };
  return {
    low: quantile(valid, 0.025),
    high: quantile(valid, 0.975),
    valid: valid.length,
  };
}

export function riskView(state: DeskState): RiskView {
  const sessions = state.sessions.filter(
    (session) =>
      session.reportEv != null &&
      session.endEquity != null &&
      session.baselinePct != null &&
      session.shadowPct != null,
  );

  const ourReturns: number[] = [];
  let previous = sessions[0]?.startEquity ?? 100000;
  for (const session of sessions) {
    if (session.endEquity == null) continue;
    ourReturns.push(session.endEquity / previous - 1);
    previous = session.endEquity;
  }
  const spyReturns = sessions.map((session) => (session.baselinePct ?? 0) / 100);
  const equalReturns = sessions.map((session) => (session.shadowPct?.equal_weight ?? 0) / 100);

  const books = [
    { key: "our", label: "Our book", returns: ourReturns, note: "Session-close account equity, including cash and costs." },
    { key: "spy", label: "SPY buy-and-hold", returns: spyReturns, note: "daily_report baselinePct, compounded." },
    {
      key: "equal",
      label: "Equal weight",
      returns: equalReturns,
      note: "daily_report shadowPct.equal_weight, compounded.",
    },
  ];

  const full = books.map((book) => metricSet(book.returns));
  const draws: Record<string, Record<RiskMetricKey, (number | null)[]>> = {};
  for (const book of books) {
    draws[book.key] = {
      sharpe: [],
      totalReturn: [],
      sortino: [],
      calmar: [],
      maxDrawdown: [],
    };
  }

  const rng = mulberry32(SEED);
  for (let draw = 0; draw < RESAMPLES; draw += 1) {
    const indices =
      sessions.length > 0
        ? Array.from({ length: sessions.length }, () => Math.floor(rng() * sessions.length))
        : [];
    books.forEach((book) => {
      const sample = indices.map((index) => book.returns[index]);
      const metrics = metricSet(sample);
      for (const key of RISK_METRICS) draws[book.key][key].push(metrics[key]);
    });
  }

  const result: RiskBook[] = books.map((book, index) => {
    const metrics = {} as Record<RiskMetricKey, IntervalMetric>;
    for (const key of RISK_METRICS) {
      const interval = intervalFor(draws[book.key][key]);
      metrics[key] = {
        value: full[index][key],
        low: interval.low,
        high: interval.high,
        valid: interval.valid,
      };
    }
    return { ...book, metrics };
  });

  return {
    books: result,
    sessions: sessions.length,
    resamples: RESAMPLES,
    seed: SEED,
    caveat:
      "95% intervals resample paired session-return vectors 2,000 times with seed 20261117 and rebuild equity paths. Undefined draws (zero denominator or zero drawdown) are excluded, not shown as infinity. Short-window ratios are descriptive and unstable.",
  };
}

export interface HeadToHeadRow {
  key: string;
  label: string;
  value: number | null;
  note: string;
}

export function headToHead(state: DeskState, ourReturn: number | null): { rows: HeadToHeadRow[]; caveat: string } {
  const reported = state.sessions.filter((session) => session.shadowPct != null);
  const compound = (book: "follow" | "fade") =>
    reported.reduce((product, session) => product * (1 + (session.shadowPct?.[book] ?? 0) / 100), 1) - 1;

  return {
    rows: [
      {
        key: "our",
        label: "Our book",
        value: ourReturn,
        note: "Full account: core, satellite and cash.",
      },
      {
        key: "quick",
        label: "Quick classifier",
        value: null,
        note: "No quick-only shadow book is logged.",
      },
      {
        key: "follow",
        label: "Follow-all",
        value: reported.length > 0 ? compound("follow") : null,
        note: "daily_report shadowPct.follow, compounded by session.",
      },
      {
        key: "fade",
        label: "Fade-all",
        value: reported.length > 0 ? compound("fade") : null,
        note: "daily_report shadowPct.fade, compounded by session.",
      },
    ],
    caveat:
      "These are reported daily aggregates, not the matched decision books H2 requires. Our book includes core and cash; the quick classifier has no separate shadow series.",
  };
}

/* ------------------------------------------------------------------ */
/* Debate room                                                        */
/* ------------------------------------------------------------------ */

export type CheckStatus = "logged" | "missing" | "n/a";

export interface ProcessCheck {
  label: string;
  status: CheckStatus;
  note: string;
}

export interface DebateTimelineItem {
  ts: string;
  kind: string;
  title: string;
  detail: string;
  ev: LoadedEvent | null;
  cutoff?: boolean;
}

export interface DebateRecord {
  id: string;
  runId: string;
  ticker: string;
  date: string;
  rating: RatingRecord;
  screen: DecisionRecord["screen"];
  tier: string;
  manager: RatingRecord | null;
  quick: RatingRecord | null;
  riskVerdict: VerdictRecord | null;
  timeline: DebateTimelineItem[];
  evidenceCount: number;
  horizonSessions: number;
  wrong: string;
  outcome: string;
  agreement: { count: number; comparable: number; note: string };
  checklist: ProcessCheck[];
  reflection: { prompt: string; text: string; ev: LoadedEvent } | null;
}

function wrongCriterion(cls: string | null): string {
  const meta = classMeta(cls);
  if (meta.sign === 0) return "No directional call is logged, so there is no forecast to falsify.";
  const horizon = cls?.startsWith("explained") ? 5 : 3;
  const direction = meta.sign > 0 ? "positive" : "negative";
  return `A ${horizon}-session stock-minus-SPY excess return that is not ${direction}. Zero counts as wrong.`;
}

function buildTimeline(decision: DecisionRecord, rating: RatingRecord): DebateTimelineItem[] {
  const items: DebateTimelineItem[] = [];
  if (decision.screen) {
    const candidate = decision.screen.candidate;
    items.push({
      ts: decision.screen.ev.ts,
      kind: "screen",
      title: "Screen",
      detail: `z ${candidate.z.toFixed(2)} · RVOL ${candidate.rvol.toFixed(2)} · move ${candidate.movePct.toFixed(2)}% · ${
        decision.screen.picked ? "picked" : "not picked"
      }`,
      ev: decision.screen.ev,
    });
  }
  if (rating.newsCutoff) {
    items.push({
      ts: rating.newsCutoff,
      kind: "cutoff",
      title: "News cutoff",
      detail: "No evidence published after this time may inform the call.",
      ev: null,
      cutoff: true,
    });
  }
  items.push({
    ts: rating.ev.ts,
    kind: "rating",
    title: rating.tier === "single" ? "Researcher-rater" : rating.tier === "debate" ? "Manager (debate tier)" : "Quick classifier",
    detail: `${rating.cls} · confidence ${(rating.confidence * 100).toFixed(1)}% · setup ${rating.setupScore}/5 · ${rating.credits ?? "unavailable"} credit(s)`,
    ev: rating.ev,
  });
  for (const intent of decision.intents) {
    items.push({
      ts: intent.ev.ts,
      kind: "intent",
      title: "Code order intent",
      detail: `${intent.side} ${intent.qty} @ ${intent.limitPrice.toFixed(2)} · ${intent.notional.toFixed(2)} notional · stop ${intent.stop?.toFixed(2) ?? "not recorded"}`,
      ev: intent.ev,
    });
  }
  for (const verdict of decision.verdicts) {
    items.push({
      ts: verdict.ev.ts,
      kind: "verdict",
      title: "Risk verdict",
      detail: `${verdict.verdict}${verdict.firedRule ? ` · ${verdict.firedRule}` : ""} · qty after ${verdict.qtyAfter}`,
      ev: verdict.ev,
    });
  }
  for (const order of decision.orders) {
    items.push({
      ts: order.ev.ts,
      kind: "order",
      title: "Order submitted",
      detail: `${order.side} ${order.qty} @ ${order.limitPrice.toFixed(2)} · ${order.orderId}`,
      ev: order.ev,
    });
  }
  for (const fill of decision.fills) {
    items.push({
      ts: fill.ev.ts,
      kind: "fill",
      title: "Fill",
      detail: `${fill.filledQty} @ ${fill.avgPrice.toFixed(2)} · ${fill.status} · ${fill.orderId}`,
      ev: fill.ev,
    });
  }
  if (decision.stopHit) {
    items.push({
      ts: decision.stopHit.ev.ts,
      kind: "stop",
      title: "Stop hit",
      detail: `entry ${decision.stopHit.entry.toFixed(2)} · stop ${decision.stopHit.stop.toFixed(2)} · ${decision.stopHit.exitOrderId}`,
      ev: decision.stopHit.ev,
    });
  }
  if (decision.halt) {
    items.push({
      ts: decision.halt.ev.ts,
      kind: "halt",
      title: "Halt",
      detail: `${decision.halt.scope} · ${decision.halt.reason}`,
      ev: decision.halt.ev,
    });
  }
  const priority: Record<string, number> = { cutoff: 0, screen: 1, rating: 2, intent: 3, verdict: 4, order: 5, fill: 6, stop: 7, halt: 8 };
  return items.sort((a, b) => a.ts.localeCompare(b.ts) || (priority[a.kind] ?? 9) - (priority[b.kind] ?? 9));
}

export function debateRecords(state: DeskState): DebateRecord[] {
  const records: DebateRecord[] = state.ratings.map((rating) => {
    const decision = decisionForRating(state, rating);
    if (!decision) {
      return {
        id: rating.decisionId ?? `${rating.runId}:${rating.ticker}`,
        runId: rating.runId,
        ticker: rating.ticker,
        date: rating.ev.ts.slice(0, 10),
        rating,
        screen: null,
        tier: rating.tier,
        manager: ["debate", "single"].includes(rating.tier) ? rating : null,
        quick: rating.tier === "quick" ? rating : null,
        riskVerdict: null,
        timeline: buildTimeline(
          {
            id: rating.decisionId ?? `${rating.runId}:${rating.ticker}`,
            runId: rating.runId,
            ticker: rating.ticker,
            date: rating.ev.ts.slice(0, 10),
            screen: null,
            rating,
            intents: [],
            verdicts: [],
            orders: [],
            fills: [],
            stopHit: null,
            exitOrder: null,
            exitFill: null,
            linkedExit: null,
            shadows: [],
            halt: null,
            tierAt: state.tier,
            warnings: [],
          },
          rating,
        ),
        evidenceCount: Array.isArray(rating.ev.evidence) ? rating.ev.evidence.length : 0,
        horizonSessions: rating.cls.startsWith("explained") ? 5 : 3,
        wrong: wrongCriterion(rating.cls),
        outcome: "Not logged",
        agreement: { count: 0, comparable: 0, note: "No paired classifier calls are logged for this name." },
        checklist: [],
        reflection: null,
      };
    }

    const riskVerdict = decision.verdicts[decision.verdicts.length - 1] ?? null;
    const manager = ["debate", "single"].includes(rating.tier) ? rating : null;
    const quick = rating.tier === "quick" ? rating : null;
    const managerSign = manager ? classMeta(manager.cls).sign : 0;
    const quickSign = quick ? classMeta(quick.cls).sign : 0;
    const comparable = managerSign !== 0 && quickSign !== 0 ? 1 : 0;
    const agreementCount = comparable > 0 && managerSign === quickSign ? 1 : 0;
    const evidenceCount = Array.isArray(rating.ev.evidence) ? rating.ev.evidence.length : 0;
    const reflection =
      [...state.reflectionNotes].reverse().find((note) => note.ev.runId === rating.runId) ?? null;
    const horizonSessions = rating.cls.startsWith("explained") ? 5 : 3;

    const checklist: ProcessCheck[] = [
      {
        label: "Decision ID prelogged",
        status: decision.id ? "logged" : "missing",
        note: decision.id,
      },
      {
        label: "News cutoff before publish",
        status: rating.newsCutoff && rating.newsCutoff <= rating.ev.ts ? "logged" : "missing",
        note: `${rating.newsCutoff || "—"} → ${rating.ev.ts}`,
      },
      {
        label: "Confidence recorded",
        status: "logged",
        note: `${(rating.confidence * 100).toFixed(1)}%`,
      },
      {
        label: "Evidence array",
        status: evidenceCount > 0 ? "logged" : "missing",
        note: evidenceCount > 0 ? `${evidenceCount} item(s)` : "0 items in these logs",
      },
      {
        label: "Screen metrics",
        status: decision.screen ? "logged" : "missing",
        note: decision.screen ? "z, RVOL and move are present" : "no screen row",
      },
      {
        label: rating.tier === "single" ? "Researcher-rater call" : "Manager call (debate tier)",
        status: manager ? "logged" : "n/a",
        note: manager ? `${rating.tier}-tier rating present` : "this name used the quick tier",
      },
      {
        label: "Quick call",
        status: quick ? "logged" : "n/a",
        note: quick ? "quick-tier rating present" : "no quick call for this name",
      },
      {
        label: "Code risk verdict",
        status: riskVerdict ? "logged" : "missing",
        note: riskVerdict ? riskVerdict.verdict : "no risk verdict event",
      },
      {
        label: "Exact order ticket",
        status: decision.orders.length > 0 ? "logged" : "missing",
        note:
          decision.orders.length > 0
            ? "order ID present; ticketHash is not in the loaded event fields"
            : "no order submitted",
      },
      {
        label: "Fill",
        status: decision.fills.length > 0 ? "logged" : "missing",
        note: decision.fills.length > 0 ? `${decision.fills.length} fill event(s)` : "no fill event",
      },
      {
        label: "Outcome graded",
        status: "missing",
        note: "no outcome event exists",
      },
      {
        label: "After-horizon review",
        status: "missing",
        note: `horizon is ${horizonSessions} session(s); no post-horizon event`,
      },
    ];

    return {
      id: decision.id,
      runId: rating.runId,
      ticker: rating.ticker,
      date: rating.ev.ts.slice(0, 10),
      rating,
      screen: decision.screen,
      tier: rating.tier,
      manager,
      quick,
      riskVerdict,
      timeline: buildTimeline(decision, rating),
      evidenceCount,
      horizonSessions,
      wrong: wrongCriterion(rating.cls),
      outcome: "Not logged",
      agreement: {
        count: agreementCount,
        comparable,
        note: comparable
          ? "Manager and quick calls have the same direction."
          : "No name has both a manager-tier and a quick-tier call in these logs.",
      },
      checklist,
      reflection,
    };
  });

  return records.sort((a, b) => b.date.localeCompare(a.date) || a.ticker.localeCompare(b.ticker));
}

export function defaultDebateId(records: DebateRecord[]): string | null {
  return (
    records.find((record) => record.manager && record.riskVerdict)?.id ??
    records.find((record) => record.manager)?.id ??
    records[0]?.id ??
    null
  );
}

export function finalDayLabel(): string {
  return RULES.finalDay;
}
