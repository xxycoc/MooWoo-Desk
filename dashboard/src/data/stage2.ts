import type {
  DecisionRecord,
  DeskState,
  LoadedEvent,
  SessionSummary,
  SkipRecord,
} from "./types";
import { UNIVERSE, marketCapFor } from "./universe";

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
    const traded = decision.fills.some((fill) => fill.runId === runId && fill.filledQty > 0);
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
        decision.fills.some((fill) => fill.runId === runId && fill.filledQty > 0),
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
