import type {
  CreditEntry,
  DecisionRecord,
  DeskState,
  DrillRecord,
  FillRecord,
  HaltRecord,
  IntentRecord,
  LoadedEvent,
  OrderRecord,
  PositionRecord,
  RatingRecord,
  RuleChangeRecord,
  SessionSummary,
  ShadowRecord,
  SkipRecord,
  Sleeve,
  TierChangeRecord,
  VerdictRecord,
} from "./types";
import { RULES, TRADEABLE_CLASSES, classMapsToSleeve } from "./rules";

const CAPITAL = 100000;

type Payload = Record<string, unknown>;

function obj(ev: LoadedEvent): Payload {
  return ev as unknown as Payload;
}
function num(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}
function str(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}
function list<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}
function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

interface Mutable {
  equity: number | null;
  equityEv: LoadedEvent | null;
  cash: number | null;
  cashEv: LoadedEvent | null;
  sessionStartEquity: number | null;
  peakEquity: number | null;
  tier: string;
  tierEv: LoadedEvent | null;
  halted: boolean;
  configHash: string | null;
  promptVersion: string | null;
  runConfigEv: LoadedEvent | null;
  positions: PositionRecord[];
  orders: OrderRecord[];
  intents: IntentRecord[];
  ratings: RatingRecord[];
  shadows: ShadowRecord[];
  skips: SkipRecord[];
  verdicts: VerdictRecord[];
  vetoes: VerdictRecord[];
  resizes: VerdictRecord[];
  approvals: VerdictRecord[];
  halts: HaltRecord[];
  drills: DrillRecord[];
  ruleChanges: RuleChangeRecord[];
  tierChanges: TierChangeRecord[];
  reflectionNotes: { ev: LoadedEvent; prompt: string; text: string; executionAction: string | null }[];
  credits: CreditEntry[];
  creditTotal: number | null;
  realized: Record<Sleeve, number>;
  feesPaid: number;
  decisions: Record<string, DecisionRecord>;
  sessions: Map<string, SessionSummary>;
}

function init(): Mutable {
  return {
    equity: null,
    equityEv: null,
    cash: null,
    cashEv: null,
    sessionStartEquity: null,
    peakEquity: null,
    tier: "normal",
    tierEv: null,
    halted: false,
    configHash: null,
    promptVersion: null,
    runConfigEv: null,
    positions: [],
    orders: [],
    intents: [],
    ratings: [],
    shadows: [],
    skips: [],
    verdicts: [],
    vetoes: [],
    resizes: [],
    approvals: [],
    halts: [],
    drills: [],
    ruleChanges: [],
    tierChanges: [],
    reflectionNotes: [],
    credits: [],
    creditTotal: 0,
    realized: { core: 0, drift: 0, bounce: 0, unclassified: 0 },
    feesPaid: 0,
    decisions: {},
    sessions: new Map(),
  };
}

function ensureSession(m: Mutable, ev: LoadedEvent): SessionSummary {
  let session = m.sessions.get(ev.runId);
  if (!session) {
    session = {
      runId: ev.runId,
      date: ev.ts.slice(0, 10),
      startTs: ev.ts,
      startEv: ev,
      endTs: null,
      reportEv: null,
      startEquity: m.sessionStartEquity ?? CAPITAL,
      startCash: m.cash ?? CAPITAL,
      endEquity: null,
      pnlPct: null,
      baselinePct: null,
      shadowPct: null,
      brier: null,
      maxDrawdownPct: null,
      creditsUsed: null,
      ordersReported: null,
      vetoesReported: null,
      skipsReported: null,
      ordersSubmitted: 0,
      vetoCount: 0,
      skipCount: 0,
      ratingCredits: 0,
      events: [],
    };
    m.sessions.set(ev.runId, session);
  }
  session.events.push(ev);
  return session;
}

function ensureDecision(m: Mutable, runId: string, ticker: string, ts: string, id?: string | null): DecisionRecord {
  const decisionId = id || `${runId}:${ticker}`;
  let d = m.decisions[decisionId];
  if (!d) {
    d = {
      id: decisionId,
      runId,
      ticker,
      date: ts.slice(0, 10),
      screen: null,
      rating: null,
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
      tierAt: m.tier,
      warnings: [],
    };
    m.decisions[decisionId] = d;
  }
  return d;
}

function sleeveFor(intent: IntentRecord | null, rating: RatingRecord | null): Sleeve {
  if (intent?.sleeve === "core") return "core";
  return classMapsToSleeve(rating?.cls) ?? "unclassified";
}

function applyBuy(
  m: Mutable,
  ev: LoadedEvent,
  d: DecisionRecord,
  intent: IntentRecord | null,
  qty: number,
  price: number,
  fee: number,
) {
  if (qty <= 0) return;
  let pos = m.positions.find((p) => p.ticker === d.ticker);
  if (pos) {
    const nextQty = pos.qty + qty;
    pos.avgCost = (pos.avgCost * pos.qty + price * qty) / nextQty;
    pos.qty = nextQty;
    pos.feesIn += fee;
    pos.lastPrice = price;
    pos.lastMarkAt = ev.ts;
    pos.markEv = ev;
    if (intent?.stop != null && (pos.stop == null || intent.side === "BUY")) pos.stop = intent.stop;
    return;
  }
  pos = {
    ticker: d.ticker,
    sleeve: sleeveFor(intent, d.rating),
    qty,
    avgCost: price,
    feesIn: fee,
    entryTs: ev.ts,
    entryPrice: price,
    stop: intent?.stop ?? null,
    decisionId: d.id,
    lastPrice: price,
    lastMarkAt: ev.ts,
    entryEv: ev,
    markEv: ev,
    realized: 0,
  };
  m.positions.push(pos);
}

function applySell(
  m: Mutable,
  ev: LoadedEvent,
  d: DecisionRecord,
  qty: number,
  price: number,
  fee: number,
) {
  const pos = m.positions.find((p) => p.ticker === d.ticker);
  if (!pos) return;
  const closeQty = Math.min(qty, pos.qty);
  if (closeQty <= 0) return;
  const before = pos.qty;
  const buyFeeShare = before > 0 ? pos.feesIn * (closeQty / before) : 0;
  pos.feesIn -= buyFeeShare;
  const realized = (price - pos.avgCost) * closeQty - buyFeeShare - fee;
  pos.realized += realized;
  m.realized[pos.sleeve] += realized;
  pos.qty = before - closeQty;
  pos.lastPrice = price;
  pos.lastMarkAt = ev.ts;
  pos.markEv = ev;
  if (pos.qty <= 1e-9) {
    m.positions = m.positions.filter((p) => p !== pos);
  }
}

function apply(ev: LoadedEvent, m: Mutable) {
  const p = obj(ev);
  const session = ensureSession(m, ev);

  switch (ev.type) {
    case "run_started": {
      m.equity = num(p.equity);
      m.equityEv = ev;
      m.cash = num(p.cash);
      m.cashEv = ev;
      m.sessionStartEquity = m.equity;
      m.peakEquity = Math.max(m.peakEquity ?? -Infinity, m.equity);
      m.tier = str(p.tier, "normal");
      m.tierEv = ev;
      m.configHash = str(p.configHash) || null;
      m.promptVersion = str(p.promptVersion) || null;
      m.runConfigEv = ev;
      session.startTs = ev.ts;
      session.startEv = ev;
      session.startEquity = m.equity;
      session.startCash = m.cash;
      break;
    }

    case "screen": {
      const picked = list<string>(p.picked);
      for (const raw of list<Record<string, unknown>>(p.candidates)) {
        const ticker = str(raw.ticker);
        if (!ticker) continue;
        const d = ensureDecision(m, ev.runId, ticker, ev.ts);
        if (!d.screen) {
          d.screen = {
            candidate: {
              ticker,
              movePct: num(raw.movePct),
              z: num(raw.z),
              rvol: num(raw.rvol),
              earnings: raw.earnings,
            },
            picked: picked.includes(ticker),
            ev,
          };
        }
      }
      break;
    }

    case "rating": {
      const ticker = str(p.ticker);
      const d = ensureDecision(m, ev.runId, ticker, ev.ts, ev.decisionId);
      const secondOpinion = p.secondOpinion === true;
      const rating: RatingRecord = {
        ev,
        runId: ev.runId,
        decisionId: ev.decisionId,
        ticker,
        cls: str(p.class),
        confidence: num(p.confidence),
        tier: str(p.tier),
        credits: typeof p.credits === "number" ? p.credits : null,
        newsCutoff: str(p.newsCutoff),
        setupScore: num(p.setupScore),
        reason: str(p.reason),
        transcriptRef: str(p.transcriptRef),
        secondOpinion,
      };
      m.ratings.push(rating);
      d.rating = rating;
      const credits = rating.credits;
      m.creditTotal = credits == null || m.creditTotal == null ? null : m.creditTotal + credits;
      m.credits.push({
        ev,
        runId: ev.runId,
        ts: ev.ts,
        decisionId: ev.decisionId,
        credits,
        tier: rating.tier,
      });
      session.ratingCredits = credits == null || session.ratingCredits == null ? null : session.ratingCredits + credits;
      if (!secondOpinion && !TRADEABLE_CLASSES.has(rating.cls)) {
        const skip: SkipRecord = {
          ev,
          runId: ev.runId,
          decisionId: ev.decisionId,
          ticker,
          cls: rating.cls,
          reason: `${rating.cls} does not map to the long-only drift/bounce sleeves`,
          source: "class_not_tradeable",
        };
        m.skips.push(skip);
        session.skipCount += 1;
      }
      break;
    }

    case "shadow": {
      const ticker = str(p.ticker);
      const d = ensureDecision(m, ev.runId, ticker, ev.ts, ev.decisionId);
      const shadow: ShadowRecord = {
        ev,
        runId: ev.runId,
        decisionId: ev.decisionId,
        book: str(p.book),
        ticker,
        side: str(p.side),
        notional: num(p.notional),
        price: num(p.price),
      };
      m.shadows.push(shadow);
      d.shadows.push(shadow);
      break;
    }

    case "core_rebalance": {
      // Runtime rebalances are proposals. Only fills change holdings.
      if (p.dataset === "paper-ledger") break;
      const etf = str(p.etf);
      const side = str(p.side);
      const qty = Math.abs(num(p.qty));
      const targetWeight = num(p.targetWeight);
      const actualWeight = num(p.actualWeight);
      const equity = m.equity ?? m.sessionStartEquity ?? CAPITAL;
      const price = qty > 0 ? (actualWeight * equity) / qty : 0;
      const d = ensureDecision(m, ev.runId, etf, ev.ts, ev.decisionId);
      const existing = m.positions.find((pos) => pos.ticker === etf);
      if (side === "SELL") {
        if (existing) {
          const closeQty = Math.min(qty, existing.qty);
          existing.qty -= closeQty;
          existing.lastPrice = price;
          existing.lastMarkAt = ev.ts;
          existing.markEv = ev;
          if (existing.qty <= 1e-9) m.positions = m.positions.filter((pos) => pos !== existing);
        }
        if (m.cash != null) m.cash += qty * price;
      } else if (existing) {
        const nextQty = existing.qty + qty;
        existing.avgCost = (existing.avgCost * existing.qty + price * qty) / nextQty;
        existing.qty = nextQty;
        existing.lastPrice = price;
        existing.lastMarkAt = ev.ts;
        existing.markEv = ev;
        existing.coreTargetWeight = targetWeight;
        existing.coreActualWeight = actualWeight;
        if (m.cash != null) m.cash -= qty * price;
      } else {
        m.positions.push({
          ticker: etf,
          sleeve: "core",
          qty,
          avgCost: price,
          feesIn: 0,
          entryTs: ev.ts,
          entryPrice: price,
          stop: null,
          decisionId: d.id,
          lastPrice: price,
          lastMarkAt: ev.ts,
          entryEv: ev,
          markEv: ev,
          coreTargetWeight: targetWeight,
          coreActualWeight: actualWeight,
          realized: 0,
        });
        if (m.cash != null) m.cash -= qty * price;
      }
      m.cashEv = ev;
      break;
    }

    case "order_intent": {
      const ticker = str(p.ticker);
      const d = ensureDecision(m, ev.runId, ticker, ev.ts, ev.decisionId);
      const intent: IntentRecord = {
        ev,
        runId: ev.runId,
        decisionId: ev.decisionId,
        ticker,
        side: str(p.side) === "SELL" ? "SELL" : "BUY",
        sleeve: str(p.sleeve),
        qty: num(p.qty),
        limitPrice: num(p.limitPrice),
        notional: num(p.notional),
        stop: typeof p.stop === "number" && p.stop > 0 ? p.stop : null,
        sizing: asRecord(p.sizing),
        equityAt: m.equity,
        cashAt: m.cash,
        tierAt: m.tier,
        verdict: null,
        order: null,
      };
      m.intents.push(intent);
      d.intents.push(intent);
      break;
    }

    case "risk_verdict": {
      const ticker = str(p.ticker);
      const d = ensureDecision(m, ev.runId, ticker, ev.ts, ev.decisionId);
      const intent =
        [...m.intents].reverse().find(
          (candidate) =>
            candidate.runId === ev.runId &&
            candidate.decisionId === ev.decisionId &&
            candidate.verdict == null,
        ) ?? null;
      const rawVerdict = str(p.verdict);
      const verdict: VerdictRecord = {
        ev,
        runId: ev.runId,
        decisionId: ev.decisionId,
        ticker,
        verdict: rawVerdict === "veto" ? "veto" : rawVerdict === "resize" ? "resize" : "approve",
        rules: list<string>(p.rules),
        firedRule: typeof p.firedRule === "string" ? p.firedRule : null,
        qtyAfter: num(p.qtyAfter),
        intent,
      };
      if (intent) intent.verdict = verdict;
      m.verdicts.push(verdict);
      d.verdicts.push(verdict);
      if (verdict.verdict === "veto") {
        m.vetoes.push(verdict);
        session.vetoCount += 1;
      } else if (verdict.verdict === "resize") {
        m.resizes.push(verdict);
      } else {
        m.approvals.push(verdict);
      }
      break;
    }

    case "order_submitted": {
      const ticker = str(p.ticker);
      const orderId = str(p.orderId);
      const d = ensureDecision(m, ev.runId, ticker, ev.ts, ev.decisionId);
      const intent =
        [...m.intents]
          .reverse()
          .find(
            (candidate) =>
              candidate.runId === ev.runId && candidate.decisionId === ev.decisionId,
          ) ?? null;
      const isStopExit = d.stopHit?.exitOrderId === orderId;
      const order: OrderRecord = {
        ev,
        runId: ev.runId,
        decisionId: ev.decisionId,
        ticker,
        orderId,
        side: intent?.side ?? (isStopExit ? "SELL" : "BUY"),
        qty: num(p.qty),
        limitPrice: num(p.limitPrice),
        trdEnv: typeof p.trdEnv === "string" ? p.trdEnv : null,
        intent,
        fill: null,
        appliedQty: 0,
        feeCharged: false,
        feesPaid: 0,
      };
      m.orders.push(order);
      d.orders.push(order);
      if (intent) intent.order = order;
      if (isStopExit) d.exitOrder = order;
      session.ordersSubmitted += 1;
      break;
    }

    case "fill": {
      const ticker = str(p.ticker);
      const orderId = str(p.orderId);
      const d = ensureDecision(m, ev.runId, ticker, ev.ts, ev.decisionId);
      const order = m.orders.find((candidate) => candidate.orderId === orderId) ?? null;
      const fill: FillRecord = {
        ev,
        runId: ev.runId,
        decisionId: ev.decisionId,
        ticker,
        orderId,
        status: str(p.status),
        filledQty: num(p.filledQty),
        avgPrice: num(p.avgPrice),
        source: str(p.source),
      };
      d.fills.push(fill);
      if (order) order.fill = fill;
      const prevApplied = order?.appliedQty ?? 0;
      const cumulative = fill.filledQty;
      const addQty = Math.max(0, cumulative - prevApplied);
      const isStopExit = d.stopHit?.exitOrderId === orderId;
      const side = order?.side ?? (isStopExit ? "SELL" : "BUY");

      if (addQty > 0) {
        let fee = 0;
        if (!order || !order.feeCharged) fee += RULES.feePerOrder;
        if (side === "SELL") {
          const perShareNow = Math.min(RULES.feeSellCap, RULES.feePerShareSold * cumulative);
          const perShareBefore = Math.min(RULES.feeSellCap, RULES.feePerShareSold * prevApplied);
          fee += Math.max(0, perShareNow - perShareBefore);
        }
        if (order) {
          order.feeCharged = true;
          order.feesPaid += fee;
          order.appliedQty = Math.max(order.appliedQty, cumulative);
        }
        m.feesPaid += fee;
        if (side === "SELL") {
          applySell(m, ev, d, addQty, fill.avgPrice, fee);
          if (m.cash != null) m.cash += addQty * fill.avgPrice;
        } else {
          applyBuy(m, ev, d, order?.intent ?? null, addQty, fill.avgPrice, fee);
          if (m.cash != null) m.cash -= addQty * fill.avgPrice;
        }
        m.cashEv = ev;
      }
      if (order) order.appliedQty = Math.max(order.appliedQty, cumulative);
      if (side === "SELL" && isStopExit) d.exitFill = fill;
      break;
    }

    case "stop_hit": {
      const ticker = str(p.ticker);
      const d = ensureDecision(m, ev.runId, ticker, ev.ts, ev.decisionId);
      d.stopHit = {
        ev,
        entry: num(p.entry),
        stop: num(p.stop),
        exitOrderId: str(p.exitOrderId),
      };
      break;
    }

    case "tier_changed": {
      const peak = num(p.peakEquity, m.peakEquity ?? CAPITAL);
      m.peakEquity = Math.max(m.peakEquity ?? peak, peak);
      m.tier = str(p.to, m.tier);
      m.tierEv = ev;
      m.tierChanges.push({
        ev,
        runId: ev.runId,
        from: str(p.from),
        to: str(p.to),
        drawdownPct: num(p.drawdownPct),
        peakEquity: peak,
      });
      break;
    }

    case "halt": {
      const ticket = typeof p.ticker === "string" && p.ticker ? p.ticker : null;
      const halt: HaltRecord = {
        ev,
        runId: ev.runId,
        ticker: ticket,
        scope: str(p.scope),
        reason: str(p.reason),
      };
      m.halts.push(halt);
      if (halt.scope === "all") m.halted = true;
      if (ticket) {
        const d = ensureDecision(m, ev.runId, ticket, ev.ts, ev.decisionId);
        d.halt = halt;
      }
      break;
    }

    case "drill": {
      m.drills.push({
        ev,
        runId: ev.runId,
        date: ev.ts.slice(0, 10),
        name: str(p.name),
        expected: p.expected,
        observed: p.observed,
        pass: p.pass === true,
      });
      break;
    }

    case "rule_change": {
      m.ruleChanges.push({
        ev,
        runId: ev.runId,
        date: ev.ts.slice(0, 10),
        ruleId: str(p.ruleId),
        effectiveFrom: str(p.effectiveFrom),
        before: p.before,
        after: p.after,
        triggerDecisionIds: list<string>(p.triggerDecisionIds),
      });
      break;
    }

    case "reflection_note": {
      const note = { ev, prompt: str(p.prompt), text: str(p.text), executionAction: str(p.executionAction) || null };
      m.reflectionNotes.push(note);
      if (p.skipped === true || p.executionAction === "skip") {
        const ticker =
          typeof p.ticker === "string" && p.ticker ? p.ticker : (ev.decisionId?.split(":").slice(1).join(":") ?? "—");
        m.skips.push({
          ev,
          runId: ev.runId,
          decisionId: ev.decisionId,
          ticker,
          cls: null,
          reason: str(p.reason, "logged skip"),
          source: "logged_skip",
        });
        session.skipCount += 1;
      }
      break;
    }

    case "daily_report": {
      m.equity = num(p.equity);
      m.equityEv = ev;
      m.peakEquity = Math.max(m.peakEquity ?? m.equity, m.equity);
      session.endTs = ev.ts;
      session.reportEv = ev;
      session.endEquity = m.equity;
      session.pnlPct = num(p.pnlPct);
      session.baselinePct = num(p.baselinePct);
      const shadowPct = asRecord(p.shadowPct);
      session.shadowPct = {
        follow: num(shadowPct.follow),
        fade: num(shadowPct.fade),
        equal_weight: num(shadowPct.equal_weight),
      };
      session.brier = num(p.brier);
      session.maxDrawdownPct = num(p.maxDrawdownPct);
      session.creditsUsed = typeof p.creditsUsed === "number" ? p.creditsUsed : null;
      session.ordersReported = num(p.orders);
      session.vetoesReported = num(p.vetoes);
      session.skipsReported = num(p.skips);
      break;
    }

    default:
      break;
  }
}

function finalize(m: Mutable, events: LoadedEvent[], seq: number): DeskState {
  const sessions = [...m.sessions.values()].sort((a, b) => a.startTs.localeCompare(b.startTs));
  const liveSession = sessions.length > 0 ? sessions[sessions.length - 1] : null;
  const equity = m.equity;
  const peak = Math.max(m.peakEquity ?? m.sessionStartEquity ?? 0, equity ?? 0);
  const drawdownPct = peak > 0 && equity != null ? (equity / peak - 1) * 100 : 0;

  for (const d of Object.values(m.decisions)) {
    if (d.rating && !TRADEABLE_CLASSES.has(d.rating.cls)) {
      if (d.intents.some((intent) => intent.side === "BUY")) {
        d.warnings.push(
          `Rating class ${d.rating.cls} does not map to a sleeve under docs/risk-desk.md, yet a buy intent exists.`,
        );
      }
    }
    for (const intent of d.intents) {
      if (intent.side === "BUY" && intent.notional > 0 && intent.notional < RULES.minEntryNotional) {
        d.warnings.push(
          `Buy notional $${intent.notional.toFixed(2)} is below the $${RULES.minEntryNotional.toLocaleString("en-US")} entry floor (below_min_notional).`,
        );
      }
      if (!intent.verdict) d.warnings.push("Order intent has no risk verdict event.");
    }
    for (const order of d.orders) {
      if (!order.fill) {
        d.warnings.push(`Order ${order.orderId} has no fill event; its fill status is unknown from this log.`);
      }
    }
    if (d.stopHit && !d.exitFill) {
      d.warnings.push(`Stop exit ${d.stopHit.exitOrderId} has no fill event.`);
    }

    if (d.fills.length > 0 && !d.exitFill) {
      const entryTs = d.fills[0].ev.ts;
      const later = Object.values(m.decisions)
        .filter((candidate) => candidate.ticker === d.ticker && candidate.stopHit && candidate.stopHit.ev.ts > entryTs)
        .sort((a, b) => (a.stopHit!.ev.ts < b.stopHit!.ev.ts ? -1 : 1));
      const target = later[0]?.stopHit;
      if (target) {
        const order = m.orders.find((candidate) => candidate.orderId === target.exitOrderId) ?? null;
        const fill =
          order?.fill ??
          m.decisions[later[0].id]?.fills.find((candidate) => candidate.orderId === target.exitOrderId) ??
          null;
        d.linkedExit = { stopHit: target, order, fill };
      }
    }
  }

  return {
    asOf: events.length > 0 ? events[events.length - 1] : null,
    gseq: seq,
    totalEvents: events.length,
    equity,
    equityEv: m.equityEv,
    cash: m.cash,
    cashEv: m.cashEv,
    sessionStartEquity: m.sessionStartEquity,
    peakEquity: peak,
    drawdownPct,
    tier: m.tier,
    tierEv: m.tierEv,
    halted: m.halted,
    killActive: m.halted || m.tier === "kill",
    configHash: m.configHash,
    promptVersion: m.promptVersion,
    runConfigEv: m.runConfigEv,
    liveSession,
    sessions,
    positions: [...m.positions].filter((pos) => pos.qty > 1e-9),
    orders: m.orders,
    intents: m.intents,
    ratings: m.ratings,
    shadows: m.shadows,
    skips: m.skips,
    vetoes: m.vetoes,
    resizes: m.resizes,
    approvals: m.approvals,
    halts: m.halts,
    drills: m.drills,
    ruleChanges: m.ruleChanges,
    tierChanges: m.tierChanges,
    reflectionNotes: m.reflectionNotes,
    credits: m.credits,
    creditTotal: m.creditTotal,
    realizedBySleeve: m.realized,
    feesPaid: m.feesPaid,
    decisions: m.decisions,
  };
}

/**
 * Pure rebuild of the full desk state after the event with global seq `seq`.
 * Pass the live seq (the corpus length) for the latest state.
 */
export function stateAt(events: LoadedEvent[], seq: number): DeskState {
  const window = events.filter((event) => event.gseq <= seq);
  const m = init();
  for (const event of window) apply(event, m);
  return finalize(m, window, seq);
}
