import type { DeskState, LoadedEvent, Sleeve } from "./types";
import { classMapsToSleeve } from "./rules";

export type FloorRole =
  | "scheduler"
  | "screener"
  | "analyst"
  | "bull"
  | "bear"
  | "manager"
  | "quick"
  | "trader"
  | "rebalancer"
  | "risk"
  | "executor"
  | "watcher"
  | "auditor"
  | "coordinator";

export type FloorStatus = "idle" | "working" | "done" | "problem";

export type SceneKind =
  | "run_started"
  | "screen"
  | "rating"
  | "order_intent"
  | "risk_verdict"
  | "order_submitted"
  | "fill"
  | "stop_hit"
  | "tier_changed"
  | "drill"
  | "outcome"
  | "daily_report"
  | "halt"
  | "rule_change"
  | "reflection_note"
  | "core_rebalance"
  | "shadow"
  | "other";

export type SceneTone = "neutral" | "ok" | "warn" | "bad";

export interface FloorRoleSpec {
  label: string;
  short: string;
  agent: boolean;
  desk: string;
}

export const FLOOR_ROLES: Record<FloorRole, FloorRoleSpec> = {
  scheduler: { label: "Scheduler", short: "Scheduler", agent: false, desk: "Scheduler" },
  screener: { label: "Screener", short: "Screener", agent: false, desk: "Screener" },
  analyst: { label: "Analyst", short: "Analyst", agent: true, desk: "Analysts" },
  bull: { label: "Bull", short: "Bull", agent: true, desk: "Debate table" },
  bear: { label: "Bear", short: "Bear", agent: true, desk: "Debate table" },
  manager: { label: "Manager", short: "Manager", agent: true, desk: "Debate table" },
  quick: { label: "Quick classifier", short: "Quick", agent: true, desk: "Quick kiosk" },
  trader: { label: "Trader", short: "Trader", agent: true, desk: "Trader" },
  rebalancer: { label: "Core rebalancer", short: "Rebalance", agent: false, desk: "Rebalancer" },
  risk: { label: "Risk desk", short: "Risk", agent: false, desk: "Risk booth" },
  executor: { label: "Executor", short: "Executor", agent: false, desk: "Moomoo paper" },
  watcher: { label: "Watcher", short: "Watcher", agent: false, desk: "Patrol" },
  auditor: { label: "Auditor", short: "Auditor", agent: false, desk: "Filing cabinet" },
  coordinator: { label: "Coordinator", short: "Coordinator", agent: true, desk: "Centre platform" },
};

/** Core sleeve ETFs, the only names allowed on the core board. */
export const CORE_TICKERS = ["USMV", "XLP", "XLV", "IEF", "GLD"] as const;

export const FLOOR_ROLE_ORDER: FloorRole[] = [
  "scheduler",
  "screener",
  "analyst",
  "bull",
  "bear",
  "manager",
  "quick",
  "trader",
  "rebalancer",
  "risk",
  "executor",
  "watcher",
  "auditor",
  "coordinator",
];

export interface FloorDuckSpec {
  id: string;
  role: FloorRole;
  label: string;
  x: number;
  z: number;
  rotation: number;
  scale: number;
}

/**
 * Standing positions. Desks, props and zone mats are placed around these points.
 * The pipeline reads left to right: intake, research, debate, decision, controls,
 * execution by the paper door, then back office in the front-right corner.
 */
export const FLOOR_DUCKS: FloorDuckSpec[] = [
  { id: "scheduler", role: "scheduler", label: "Scheduler", x: -14.3, z: -7.4, rotation: 0, scale: 1.1 },
  { id: "screener", role: "screener", label: "Screener", x: -10.7, z: -7.2, rotation: 0, scale: 1.1 },
  { id: "analyst-1", role: "analyst", label: "Analyst 1", x: -8.9, z: -2.2, rotation: 1.9, scale: 1.1 },
  { id: "analyst-2", role: "analyst", label: "Analyst 2", x: -5.5, z: -2.2, rotation: -1.9, scale: 1.1 },
  { id: "analyst-3", role: "analyst", label: "Analyst 3", x: -7.2, z: -4.9, rotation: 0, scale: 1.1 },
  { id: "bull", role: "bull", label: "Bull", x: -1.55, z: -2.45, rotation: 1.35, scale: 1.12 },
  { id: "bear", role: "bear", label: "Bear", x: 1.55, z: -2.45, rotation: -1.35, scale: 1.12 },
  { id: "manager", role: "manager", label: "Manager", x: 0, z: -4.9, rotation: 0, scale: 1.2 },
  { id: "quick", role: "quick", label: "Quick", x: 5.0, z: -2.0, rotation: 0.35, scale: 0.88 },
  { id: "trader", role: "trader", label: "Trader", x: 7.9, z: 0.2, rotation: 1.4, scale: 1.12 },
  { id: "rebalancer", role: "rebalancer", label: "Core rebalancer", x: 14.0, z: 3.4, rotation: 0.3, scale: 1.1 },
  { id: "risk", role: "risk", label: "Risk desk", x: 11.0, z: 0.4, rotation: -1.57, scale: 1.12 },
  { id: "executor", role: "executor", label: "Executor", x: 14.7, z: -6.7, rotation: 0.5, scale: 1.1 },
  { id: "watcher", role: "watcher", label: "Watcher", x: -14.2, z: -0.6, rotation: 0, scale: 1.1 },
  { id: "auditor", role: "auditor", label: "Auditor", x: 16.4, z: 7.2, rotation: -0.4, scale: 1.1 },
  { id: "coordinator", role: "coordinator", label: "Coordinator", x: 0.8, z: 4.9, rotation: 0, scale: 1.12 },
];

/** Home point; the mascot wanders around the front-centre aisle from here. */
export const MASCOT_POSITION = { x: 4.5, z: 7.0 };

export const FLOOR_TARGETS = {
  debate: { x: -0.5, z: -0.9 },
  quick: { x: 5.0, z: -2.0 },
  risk: { x: 10.7, z: 0.9 },
  door: { x: 15.35, z: -8.4 },
  board: { x: 8.0, z: -10.2 },
  cabinet: { x: 16.3, z: 5.8 },
  coordinator: { x: 0.8, z: 4.9 },
  aisle: { x: -13.6, z: -0.4 },
};

export const SLEEVE_COLORS: Record<Sleeve, string> = {
  core: "#5b8def",
  drift: "#a78bfa",
  bounce: "#2dd4bf",
  unclassified: "#8b97ad",
};

export interface FloorSpeech {
  role: "bull" | "bear";
  text: string;
}

export interface FloorCard {
  kind: "rating" | "report" | "drill" | "tier" | "outcome" | "stamp" | "halt" | "rule";
  title: string;
  body: string;
  tone: SceneTone;
}

export interface FloorSlip {
  ticker: string;
  label: string;
  color: string;
  from: { x: number; z: number };
  to: { x: number; z: number };
}

export interface FloorTileChange {
  ticker: string;
  sleeve: Sleeve;
  decisionId: string | null;
  action: "add" | "red" | "remove";
}

export interface FloorScene {
  kind: SceneKind;
  event: LoadedEvent;
  title: string;
  detail: string;
  tickerLine: string;
  tone: SceneTone;
  durationMs: number;
  activeRoles: FloorRole[];
  actorId: string | null;
  actorTarget: { x: number; z: number } | null;
  speech: FloorSpeech[];
  card: FloorCard | null;
  stamp: { label: string; rule: string | null; tone: SceneTone } | null;
  slip: FloorSlip | null;
  tile: FloorTileChange | null;
  decisionId: string | null;
  tier: string;
  screenTickers: { ticker: string; picked: boolean; movePct: number }[];
}

type Payload = Record<string, unknown>;

function payload(ev: LoadedEvent): Payload {
  return ev as unknown as Payload;
}

function str(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function num(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function recordList(value: unknown): Payload[] {
  return Array.isArray(value)
    ? value.filter((item): item is Payload => !!item && typeof item === "object" && !Array.isArray(item))
    : [];
}

function shortValue(value: unknown, depth = 0): string {
  if (value == null) return "none";
  if (typeof value === "string") return value;
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (Array.isArray(value)) return value.map((item) => shortValue(item, depth + 1)).join(", ");
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return "empty";
    return entries
      .slice(0, 4)
      .map(([key, item]) => `${key}=${shortValue(item, depth + 1)}`)
      .join(" · ");
  }
  return String(value);
}

export function roleOfEvent(ev: LoadedEvent): FloorRole[] {
  switch (ev.type) {
    case "run_started":
      return ["scheduler", "coordinator"];
    case "screen":
      return ["screener"];
    case "rating": {
      const p = payload(ev);
      return str(p.tier) === "quick" ? ["quick", "manager"] : ["analyst", "bull", "bear", "manager"];
    }
    case "order_intent":
      return ["trader"];
    case "risk_verdict":
      return ["risk"];
    case "order_submitted":
    case "fill":
      return ["executor"];
    case "stop_hit":
      return ["watcher"];
    case "tier_changed":
      return ["risk", "coordinator"];
    case "halt":
      return ["watcher", "risk"];
    case "drill":
      return ["coordinator", "auditor"];
    case "outcome":
      return ["auditor"];
    case "daily_report":
      return ["auditor", "coordinator"];
    case "rule_change":
      return ["coordinator", "auditor"];
    case "reflection_note":
      return ["coordinator"];
    case "core_rebalance":
      return ["rebalancer"];
    case "shadow":
      return ["trader", "analyst"];
    default:
      return ["coordinator"];
  }
}

export function decisionIdOf(ev: LoadedEvent): string | null {
  if (ev.decisionId) return ev.decisionId;
  const p = payload(ev);
  const ticker = str(p.ticker) || str(p.etf);
  return ticker ? `${ev.runId}:${ticker}` : null;
}

export function sleeveForDecision(state: DeskState, decisionId: string | null): Sleeve {
  if (!decisionId) return "unclassified";
  const decision = state.decisions[decisionId];
  const intentSleeve = decision?.intents[decision.intents.length - 1]?.sleeve;
  if (intentSleeve === "core") return "core";
  return classMapsToSleeve(decision?.rating?.cls) ?? "unclassified";
}

function durationFor(type: string): number {
  switch (type) {
    case "run_started":
      return 2000;
    case "screen":
      return 2400;
    case "rating":
      return 2600;
    case "order_intent":
      return 1900;
    case "risk_verdict":
      return 2200;
    case "order_submitted":
      return 1800;
    case "fill":
      return 1900;
    case "stop_hit":
      return 2200;
    case "tier_changed":
      return 1800;
    case "drill":
      return 2400;
    case "outcome":
      return 1700;
    case "daily_report":
      return 2400;
    case "halt":
      return 2000;
    case "rule_change":
      return 1900;
    case "reflection_note":
      return 1700;
    case "core_rebalance":
      return 1500;
    case "shadow":
      return 1300;
    default:
      return 1200;
  }
}

function completedStatus(ev: LoadedEvent): FloorStatus {
  const p = payload(ev);
  if (ev.type === "risk_verdict" && str(p.verdict) === "veto") return "problem";
  if (ev.type === "stop_hit" || ev.type === "halt") return "problem";
  if (ev.type === "drill" && p.pass !== true) return "problem";
  if (ev.type === "outcome" && p.graded === true && p.right !== true) return "problem";
  if (ev.type === "tier_changed" && ["exits_only", "kill"].includes(str(p.to))) return "problem";
  return "done";
}

function sceneStatus(ev: LoadedEvent): FloorStatus {
  const p = payload(ev);
  if (ev.type === "risk_verdict" && str(p.verdict) === "veto") return "problem";
  if (ev.type === "stop_hit" || ev.type === "halt") return "problem";
  if (ev.type === "drill" && p.pass !== true) return "problem";
  if (ev.type === "outcome" && p.graded === true && p.right !== true) return "problem";
  if (ev.type === "tier_changed" && ["exits_only", "kill"].includes(str(p.to))) return "problem";
  if (["run_started", "screen", "rating", "order_intent", "order_submitted", "shadow"].includes(ev.type)) {
    return "working";
  }
  return completedStatus(ev);
}

export function floorStatuses(
  events: LoadedEvent[],
  index: number,
  current: FloorScene,
): Record<FloorRole, FloorStatus> {
  const statuses = Object.fromEntries(FLOOR_ROLE_ORDER.map((role) => [role, "idle"])) as Record<
    FloorRole,
    FloorStatus
  >;
  events.slice(0, index + 1).forEach((ev, i) => {
    const roles = roleOfEvent(ev);
    const status = i === index ? sceneStatus(ev) : completedStatus(ev);
    roles.forEach((role) => {
      statuses[role] = status;
    });
  });
  current.activeRoles.forEach((role) => {
    if (statuses[role] === "idle") statuses[role] = sceneStatus(current.event);
  });
  return statuses;
}

function cardFor(ev: LoadedEvent): FloorCard | null {
  const p = payload(ev);
  if (ev.type === "rating") {
    return {
      kind: "rating",
      title: str(p.class).replaceAll("_", " "),
      body: `${Math.round(num(p.confidence) * 100)}% confidence · ${str(p.tier, "debate")} tier`,
      tone: "neutral",
    };
  }
  if (ev.type === "drill") {
    return {
      kind: "drill",
      title: p.pass === true ? "DRILL PASS" : "DRILL FAIL",
      body: `${str(p.name, "drill")} · expected ${shortValue(p.expected)} · observed ${shortValue(p.observed)}`,
      tone: p.pass === true ? "ok" : "bad",
    };
  }
  if (ev.type === "tier_changed") {
    return {
      kind: "tier",
      title: `Tier ${str(p.to, "changed").replaceAll("_", " ")}`,
      body: `drawdown ${num(p.drawdownPct).toFixed(1)}% · from ${str(p.from, "normal")}`,
      tone: ["exits_only", "kill"].includes(str(p.to)) ? "bad" : "warn",
    };
  }
  if (ev.type === "daily_report") {
    return {
      kind: "report",
      title: "Daily report filed",
      body: `equity $${num(p.equity).toLocaleString("en-US")} · P&L ${num(p.pnlPct).toFixed(2)}% · ${num(p.vetoes)} vetoes`,
      tone: "ok",
    };
  }
  if (ev.type === "outcome") {
    if (p.graded !== true) {
      return { kind: "outcome", title: "Ungraded", body: str(p.reason, "not enough prices"), tone: "warn" };
    }
    return {
      kind: "outcome",
      title: p.right === true ? "Call right" : "Call wrong",
      body: `${str(p.ticker)} · excess ${(num(p.excess) * 100).toFixed(2)}%`,
      tone: p.right === true ? "ok" : "bad",
    };
  }
  if (ev.type === "halt") {
    return {
      kind: "halt",
      title: "HALT",
      body: `${str(p.scope, "run")} · ${str(p.reason, "halted")}`,
      tone: "bad",
    };
  }
  if (ev.type === "rule_change") {
    return {
      kind: "rule",
      title: "Rule change",
      body: `${str(p.ruleId)} · ${shortValue(p.before)} → ${shortValue(p.after)}`,
      tone: "warn",
    };
  }
  return null;
}

function slipFor(ev: LoadedEvent): FloorSlip | null {
  const p = payload(ev);
  const ticker = str(p.ticker);
  if (ev.type === "order_intent" && ticker) {
    return {
      ticker,
      label: `${str(p.side, "BUY")} ${str(p.qty, "?")}`,
      color: "#ff7a1a",
      from: { x: 8.4, z: 0.0 },
      to: FLOOR_TARGETS.risk,
    };
  }
  if ((ev.type === "order_submitted" || ev.type === "fill") && ticker) {
    return {
      ticker,
      label: str(p.orderId, "order"),
      color: "#ff7a1a",
      from: { x: 11.1, z: 0.8 },
      to: FLOOR_TARGETS.door,
    };
  }
  return null;
}

function tileFor(ev: LoadedEvent, state: DeskState): FloorTileChange | null {
  const p = payload(ev);
  const decisionId = decisionIdOf(ev);
  const ticker = str(p.ticker);
  if (!ticker) return null;
  if (ev.type === "fill") {
    return { ticker, sleeve: sleeveForDecision(state, decisionId), decisionId, action: "add" };
  }
  if (ev.type === "stop_hit") {
    return { ticker, sleeve: sleeveForDecision(state, decisionId), decisionId, action: "remove" };
  }
  if (ev.type === "outcome") {
    return { ticker, sleeve: sleeveForDecision(state, decisionId), decisionId, action: "red" };
  }
  return null;
}

function screenTickersFor(ev: LoadedEvent): FloorScene["screenTickers"] {
  const p = payload(ev);
  const picked = new Set(Array.isArray(p.picked) ? (p.picked as string[]) : []);
  return recordList(p.candidates)
    .map((candidate) => ({
      ticker: str(candidate.ticker),
      picked: picked.has(str(candidate.ticker)),
      movePct: num(candidate.movePct),
    }))
    .sort((a, b) => Number(b.picked) - Number(a.picked) || Math.abs(b.movePct) - Math.abs(a.movePct));
}

export function sceneAt(events: LoadedEvent[], index: number, state: DeskState): FloorScene {
  const event = events[Math.max(0, Math.min(index, events.length - 1))];
  const p = payload(event);
  const kind = (event.type as SceneKind) || "other";
  const roles = roleOfEvent(event);
  const tier = state.tier;
  let title = "Event";
  let detail = event.type.replaceAll("_", " ");
  let tone: SceneTone = "neutral";
  let actorId: string | null = null;
  let actorTarget: { x: number; z: number } | null = null;
  let speech: FloorSpeech[] = [];
  let card = cardFor(event);
  let stamp: FloorScene["stamp"] = null;
  let screenTickers: FloorScene["screenTickers"] = [];

  switch (event.type) {
    case "run_started":
      title = "Run started";
      detail = `Equity $${num(p.equity).toLocaleString("en-US")} · ${str(p.tier, "normal")} tier · bell rung`;
      actorId = "scheduler";
      break;
    case "screen": {
      const picked = new Set(Array.isArray(p.picked) ? (p.picked as string[]) : []);
      screenTickers = screenTickersFor(event);
      title = "Screen";
      detail = `${recordList(p.candidates).length} names screened · picked ${[...picked].join(", ") || "none"}`;
      actorId = "screener";
      break;
    }
    case "rating": {
      const ticker = str(p.ticker);
      const quick = str(p.tier) === "quick";
      const cls = str(p.class).replaceAll("_", " ");
      title = quick ? "Quick rating" : "Rating";
      detail = `${ticker} · ${cls} · ${Math.round(num(p.confidence) * 100)}% confidence`;
      tone = "neutral";
      actorId = quick ? "quick" : "analyst-1";
      actorTarget = quick ? FLOOR_TARGETS.quick : FLOOR_TARGETS.debate;
      const bull = str(p.bullSummary) || "…";
      const bear = str(p.bearSummary) || "…";
      if (!quick) {
        speech = [
          { role: "bull", text: bull },
          { role: "bear", text: bear },
        ];
      }
      break;
    }
    case "order_intent":
      title = "Order intent";
      detail = `${str(p.side, "BUY")} ${num(p.qty)} ${str(p.ticker)} · $${num(p.notional).toLocaleString("en-US")} · ${str(p.sleeve)}`;
      actorId = "trader";
      break;
    case "risk_verdict": {
      const verdict = str(p.verdict, "approve");
      title = verdict === "veto" ? "Risk veto" : verdict === "resize" ? "Risk resize" : "Risk approval";
      detail = `${str(p.ticker)} · ${verdict.toUpperCase()}${p.firedRule ? ` · ${str(p.firedRule)}` : " · all rules checked"}`;
      tone = verdict === "veto" ? "bad" : verdict === "resize" ? "warn" : "ok";
      stamp = {
        label: verdict.toUpperCase(),
        rule: p.firedRule ? str(p.firedRule) : null,
        tone,
      };
      actorId = "risk";
      break;
    }
    case "order_submitted":
      title = "Order submitted";
      detail = `${str(p.side, "BUY")} ${num(p.qty)} ${str(p.ticker)} · ${str(p.orderId)}`;
      actorId = "executor";
      actorTarget = FLOOR_TARGETS.door;
      break;
    case "fill":
      title = "Fill";
      detail = `${num(p.filledQty)} ${str(p.ticker)} at $${num(p.avgPrice).toFixed(2)} · ${str(p.status)}`;
      tone = str(p.status).toUpperCase().includes("FILL") ? "ok" : "warn";
      actorId = "executor";
      actorTarget = FLOOR_TARGETS.door;
      break;
    case "stop_hit":
      title = "Stop hit";
      detail = `${str(p.ticker)} · entry $${num(p.entry).toFixed(2)} · stop $${num(p.stop).toFixed(2)} · ${str(p.exitOrderId)}`;
      tone = "bad";
      actorId = "watcher";
      actorTarget = FLOOR_TARGETS.board;
      break;
    case "tier_changed":
      title = "Risk tier changed";
      detail = `${str(p.from, "normal")} → ${str(p.to)} · drawdown ${num(p.drawdownPct).toFixed(1)}%`;
      tone = ["exits_only", "kill"].includes(str(p.to)) ? "bad" : "warn";
      actorId = "risk";
      break;
    case "drill":
      title = p.pass === true ? "Drill passed" : "Drill failed";
      detail = `${str(p.name)} · expected ${shortValue(p.expected)} · observed ${shortValue(p.observed)}`;
      tone = p.pass === true ? "ok" : "bad";
      actorId = "coordinator";
      break;
    case "outcome":
      title = p.graded === true ? (p.right === true ? "Outcome right" : "Outcome wrong") : "Outcome ungraded";
      detail = p.graded === true
        ? `${str(p.ticker)} · excess ${(num(p.excess) * 100).toFixed(2)}% · ${str(p.class).replaceAll("_", " ")}`
        : `${str(p.ticker)} · ${str(p.reason, "not graded")}`;
      tone = p.graded !== true ? "warn" : p.right === true ? "ok" : "bad";
      actorId = "auditor";
      actorTarget = FLOOR_TARGETS.board;
      break;
    case "daily_report":
      title = "Daily report";
      detail = `equity $${num(p.equity).toLocaleString("en-US")} · P&L ${num(p.pnlPct).toFixed(2)}% · Brier ${num(p.brier).toFixed(2)}`;
      tone = "ok";
      actorId = "auditor";
      actorTarget = FLOOR_TARGETS.cabinet;
      break;
    case "halt":
      title = "Halt";
      detail = `${str(p.scope, "run")} · ${str(p.reason)}`;
      tone = "bad";
      actorId = "watcher";
      actorTarget = FLOOR_TARGETS.aisle;
      break;
    case "rule_change":
      title = "Rule change";
      detail = `${str(p.ruleId)} · ${shortValue(p.before)} → ${shortValue(p.after)}`;
      actorId = "coordinator";
      break;
    case "reflection_note":
      title = "Reflection note";
      detail = str(p.prompt, "Reflection") + (str(p.text) ? ` · ${str(p.text)}` : "");
      actorId = "coordinator";
      break;
    case "core_rebalance":
      title = "Core rebalance";
      detail = `${str(p.side, "BUY")} ${num(p.qty)} ${str(p.etf)} · target ${(num(p.targetWeight) * 100).toFixed(1)}%`;
      tone = "ok";
      actorId = "rebalancer";
      break;
    case "shadow":
      title = "Shadow book";
      detail = `${str(p.book)} ${str(p.side)} ${str(p.ticker)} · $${num(p.notional).toLocaleString("en-US")}`;
      actorId = "trader";
      break;
    default:
      break;
  }

  if (screenTickers.length === 0) {
    const lastScreen = events
      .slice(0, Math.max(0, Math.min(index, events.length - 1)) + 1)
      .reverse()
      .find((candidate) => candidate.type === "screen");
    if (lastScreen) screenTickers = screenTickersFor(lastScreen);
  }

  const tickerLine = `seq ${event.seq} · ${event.ts.slice(11, 16)}Z · ${title}: ${detail}`;

  return {
    kind,
    event,
    title,
    detail,
    tickerLine,
    tone,
    durationMs: durationFor(event.type),
    activeRoles: roles,
    actorId,
    actorTarget,
    speech,
    card,
    stamp,
    slip: slipFor(event),
    tile: tileFor(event, state),
    decisionId: decisionIdOf(event),
    tier,
    screenTickers,
  };
}

export function eventsForRole(events: LoadedEvent[], role: FloorRole): LoadedEvent[] {
  return events.filter((ev) => roleOfEvent(ev).includes(role));
}
