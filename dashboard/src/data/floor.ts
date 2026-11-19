import type { DeskState, LoadedEvent, Sleeve } from "./types";
import { classMapsToSleeve } from "./rules";

export type FloorRole =
  | "coordinator"
  | "analyst"
  | "executor"
  | "screener"
  | "risk"
  | "watcher"
  | "auditor";

export type FloorStatus = "idle" | "working" | "done" | "problem";

export type SceneKind =
  | "run_started"
  | "screen"
  | "rating"
  | "core_rebalance"
  | "order_intent"
  | "risk_verdict"
  | "order_submitted"
  | "fill"
  | "halt"
  | "reflection_note"
  | "daily_report"
  | "tier_changed"
  | "other";

export type SceneTone = "neutral" | "ok" | "warn" | "bad";

export interface FloorRoleSpec {
  label: string;
  short: string;
  agent: boolean;
  desk: string;
}

export const FLOOR_ROLES: Record<FloorRole, FloorRoleSpec> = {
  coordinator: { label: "Coordinator", short: "Coord", agent: true, desk: "Coordinator platform" },
  analyst: { label: "Analyst", short: "Analyst", agent: true, desk: "Research table" },
  executor: { label: "Executor", short: "Executor", agent: true, desk: "Paper door" },
  screener: { label: "Screener", short: "Screen", agent: false, desk: "Ticker board" },
  risk: { label: "Risk desk", short: "Risk", agent: false, desk: "Risk booth" },
  watcher: { label: "Watcher", short: "Watch", agent: false, desk: "Watch station" },
  auditor: { label: "Auditor", short: "Audit", agent: false, desk: "Filing cabinet" },
};

/** Core sleeve ETFs, the only names allowed on the core board. */
export const CORE_TICKERS = ["USMV", "XLP", "XLV", "IEF", "GLD"] as const;

export const FLOOR_ROLE_ORDER: FloorRole[] = [
  "coordinator",
  "analyst",
  "executor",
  "screener",
  "risk",
  "watcher",
  "auditor",
];

export interface FloorAgentSpec {
  id: string;
  role: FloorRole;
  label: string;
  x: number;
  z: number;
  rotation: number;
  scale: number;
}

export interface FloorStationSpec {
  id: string;
  role: FloorRole;
  label: string;
  x: number;
  z: number;
  tagY: number;
}

/** The desk has three ducks. Code steps are stations, not characters. */
export const FLOOR_AGENTS: FloorAgentSpec[] = [
  { id: "coordinator", role: "coordinator", label: "Coordinator", x: 0.8, z: 4.9, rotation: 0, scale: 1.12 },
  { id: "analyst", role: "analyst", label: "Analyst", x: -7.0, z: -1.6, rotation: Math.PI, scale: 1.1 },
  { id: "executor", role: "executor", label: "Executor", x: 14.7, z: -7.6, rotation: 0.5, scale: 1.1 },
];

export const FLOOR_STATIONS: FloorStationSpec[] = [
  { id: "screener", role: "screener", label: "Screener", x: -10.7, z: -8.0, tagY: 2.55 },
  { id: "risk", role: "risk", label: "Risk desk", x: 11.0, z: 1.8, tagY: 2.35 },
  { id: "watcher", role: "watcher", label: "Watcher", x: -14.6, z: -1.7, tagY: 2.35 },
  { id: "auditor", role: "auditor", label: "Auditor", x: 16.0, z: 5.7, tagY: 2.6 },
];

/** Home point; the mascot sits around the front-centre aisle from here. */
export const MASCOT_POSITION = { x: 4.5, z: 7.0 };

export const FLOOR_TARGETS = {
  analyst: { x: -7.2, z: -2.9 },
  risk: { x: 11.0, z: 1.8 },
  door: { x: 15.35, z: -8.4 },
  board: { x: 8.0, z: -10.2 },
  cabinet: { x: 16.3, z: 5.8 },
  coordinator: { x: 0.8, z: 4.9 },
  screen: { x: -10.7, z: -8.0 },
  aisle: { x: -13.6, z: -0.4 },
};

export const SLEEVE_COLORS: Record<Sleeve, string> = {
  core: "#5b8def",
  drift: "#a78bfa",
  bounce: "#2dd4bf",
  unclassified: "#8b97ad",
};

export interface FloorCard {
  kind: "rating" | "report" | "tier" | "halt";
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

function runRoleOf(ev: LoadedEvent): FloorRole | null {
  const hint = `${typeof ev.runKind === "string" ? ev.runKind : ""} ${ev.runId}`;
  if (/audit/i.test(hint)) return "auditor";
  if (/watch/i.test(hint)) return "watcher";
  return null;
}

function mergeRoles(roles: FloorRole[], run: FloorRole | null): FloorRole[] {
  return run ? [...new Set([...roles, run])] : roles;
}

export function roleOfEvent(ev: LoadedEvent): FloorRole[] {
  const run = runRoleOf(ev);
  if (ev.type === "run_started") return [run ?? "coordinator"];
  switch (ev.type) {
    case "screen":
      return mergeRoles(["screener"], run);
    case "rating":
      return mergeRoles(["analyst"], run);
    case "core_rebalance":
    case "order_intent":
    case "risk_verdict":
      return mergeRoles(["risk"], run);
    case "order_submitted":
    case "fill":
      return mergeRoles(["executor"], run);
    case "reflection_note": {
      const action = str(payload(ev).executionAction);
      const roles: FloorRole[] = action === "prepared" || action === "dispatch_authorized" ? ["coordinator"] : [];
      return mergeRoles(roles, run);
    }
    case "halt":
      return [];
    case "daily_report":
    case "tier_changed":
      return mergeRoles([], run);
    default:
      return run ? [run] : [];
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
    case "core_rebalance":
      return 1700;
    case "order_intent":
      return 1900;
    case "risk_verdict":
      return 2200;
    case "order_submitted":
      return 1800;
    case "fill":
      return 1900;
    case "halt":
      return 2000;
    case "reflection_note":
      return 1700;
    case "daily_report":
      return 2400;
    case "tier_changed":
      return 1800;
    default:
      return 1200;
  }
}

function completedStatus(ev: LoadedEvent): FloorStatus {
  const p = payload(ev);
  if (ev.type === "risk_verdict" && str(p.verdict) === "veto") return "problem";
  if (ev.type === "halt") return "problem";
  if (ev.type === "tier_changed" && ["exits_only", "kill"].includes(str(p.to))) return "problem";
  return "done";
}

function sceneStatus(ev: LoadedEvent): FloorStatus {
  if (["run_started", "screen", "rating", "order_intent", "order_submitted"].includes(ev.type)) {
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
      body: `${Math.round(num(p.confidence) * 100)}% confidence · ${str(p.tier, "single")} tier`,
      tone: "neutral",
    };
  }
  if (ev.type === "daily_report") {
    return {
      kind: "report",
      title: "Daily report filed",
      body: `equity $${num(p.equity).toLocaleString("en-US")} · P&L ${num(p.pnlPct).toFixed(2)}%`,
      tone: "ok",
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
  if (ev.type === "halt") {
    return {
      kind: "halt",
      title: "HALT",
      body: `${str(p.scope, "run")} · ${str(p.reason, "halted")}`,
      tone: "bad",
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
      from: FLOOR_TARGETS.risk,
      to: FLOOR_TARGETS.door,
    };
  }
  if ((ev.type === "order_submitted" || ev.type === "fill") && ticker) {
    return {
      ticker,
      label: str(p.orderId, "order"),
      color: "#ff7a1a",
      from: { x: 14.7, z: -7.6 },
      to: FLOOR_TARGETS.door,
    };
  }
  return null;
}

function tileFor(ev: LoadedEvent, state: DeskState): FloorTileChange | null {
  const p = payload(ev);
  const decisionId = decisionIdOf(ev);
  const ticker = str(p.ticker) || str(p.etf);
  if (!ticker) return null;
  if (ev.type === "fill") {
    return { ticker, sleeve: sleeveForDecision(state, decisionId), decisionId, action: "add" };
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
  const runRole = runRoleOf(event);
  let title = "Event";
  let detail = event.type.replaceAll("_", " ");
  let tone: SceneTone = "neutral";
  let actorId: string | null = null;
  let actorTarget: { x: number; z: number } | null = null;
  const card = cardFor(event);
  let stamp: FloorScene["stamp"] = null;
  let screenTickers: FloorScene["screenTickers"] = [];

  switch (event.type) {
    case "run_started":
      if (runRole === "watcher") {
        title = "Watch started";
        detail = `equity $${num(p.equity).toLocaleString("en-US")} · ${str(p.tier, "normal")} tier · watch session`;
      } else if (runRole === "auditor") {
        title = "Audit started";
        detail = `equity $${num(p.equity).toLocaleString("en-US")} · ${str(p.tier, "normal")} tier · audit session`;
      } else {
        title = "Run started";
        detail = `equity $${num(p.equity).toLocaleString("en-US")} · ${str(p.tier, "normal")} tier · bell rung`;
      }
      actorId = runRole ? null : "coordinator";
      break;
    case "screen": {
      const picked = new Set(Array.isArray(p.picked) ? (p.picked as string[]) : []);
      screenTickers = screenTickersFor(event);
      title = "Screen";
      detail = `${recordList(p.candidates).length} names screened · picked ${[...picked].join(", ") || "none"}`;
      break;
    }
    case "rating": {
      const ticker = str(p.ticker);
      const cls = str(p.class).replaceAll("_", " ");
      title = "Rating";
      detail = `${ticker} · ${cls} · ${Math.round(num(p.confidence) * 100)}% confidence`;
      actorId = "analyst";
      actorTarget = FLOOR_TARGETS.analyst;
      break;
    }
    case "core_rebalance":
      title = "Core rebalance";
      detail = `${str(p.side, "BUY")} ${num(p.qty)} ${str(p.etf)} · target ${(num(p.targetWeight) * 100).toFixed(1)}%`;
      tone = "ok";
      break;
    case "order_intent":
      title = "Order intent";
      detail = `${str(p.side, "BUY")} ${num(p.qty)} ${str(p.ticker)} · $${num(p.notional).toLocaleString("en-US")} · ${str(p.sleeve)}`;
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
    case "halt":
      title = "Halt";
      detail = `${str(p.scope, "run")} · ${str(p.reason)}`;
      tone = "bad";
      break;
    case "reflection_note": {
      const action = str(p.executionAction);
      const ticker = str(p.ticker) || (event.decisionId?.split(":").slice(1).join(":") ?? "");
      if (action === "prepared") {
        title = "Execution prepared";
        detail = `${ticker || "ticket"} · prepared, awaiting dispatch`;
        tone = "warn";
        actorId = "coordinator";
      } else if (action === "dispatch_authorized") {
        title = "Dispatch authorized";
        detail = `${ticker || "ticket"} · exact ticket authorized`;
        tone = "ok";
        actorId = "coordinator";
      } else {
        title = "Reflection note";
        detail = str(p.prompt, "Reflection") + (str(p.text) ? ` · ${str(p.text)}` : "");
      }
      break;
    }
    case "daily_report":
      title = "Daily report";
      detail = `equity $${num(p.equity).toLocaleString("en-US")} · P&L ${num(p.pnlPct).toFixed(2)}%`;
      tone = "ok";
      break;
    case "tier_changed":
      title = "Risk tier changed";
      detail = `${str(p.from, "normal")} → ${str(p.to)} · drawdown ${num(p.drawdownPct).toFixed(1)}%`;
      tone = ["exits_only", "kill"].includes(str(p.to)) ? "bad" : "warn";
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
    card,
    stamp,
    slip: slipFor(event),
    tile: tileFor(event, state),
    decisionId: decisionIdOf(event),
    tier: state.tier,
    screenTickers,
  };
}

export function eventsForRole(events: LoadedEvent[], role: FloorRole): LoadedEvent[] {
  return events.filter((ev) => roleOfEvent(ev).includes(role));
}
