export type Sleeve = "core" | "drift" | "bounce" | "unclassified";

export interface RawEvent {
  v: number;
  runId: string;
  seq: number;
  ts: string;
  decisionId: string | null;
  type: string;
  drill: boolean;
  prevHash?: string;
  hash?: string;
  [key: string]: unknown;
}

export interface LoadedEvent extends RawEvent {
  /** Position in the combined, chronologically ordered corpus (1-based). */
  gseq: number;
  file: string;
  line: number;
}

export interface LoadedLog {
  file: string;
  rawText: string;
  events: LoadedEvent[];
}

export interface ScreenCandidate {
  ticker: string;
  movePct: number;
  z: number;
  rvol: number;
  earnings: unknown;
}

export interface TraceSource {
  runId: string;
  seq: number;
  type: string;
  ts: string;
}

export interface FillRecord {
  ev: LoadedEvent;
  runId: string;
  decisionId: string | null;
  ticker: string;
  orderId: string;
  status: string;
  filledQty: number;
  avgPrice: number;
  source: string;
}

export interface OrderRecord {
  ev: LoadedEvent;
  runId: string;
  decisionId: string | null;
  ticker: string;
  orderId: string;
  side: "BUY" | "SELL";
  qty: number;
  limitPrice: number;
  trdEnv: string | null;
  intent: IntentRecord | null;
  fill: FillRecord | null;
  appliedQty: number;
  feeCharged: boolean;
  feesPaid: number;
}

export interface IntentRecord {
  ev: LoadedEvent;
  runId: string;
  decisionId: string | null;
  ticker: string;
  side: "BUY" | "SELL";
  sleeve: string;
  qty: number;
  limitPrice: number;
  notional: number;
  stop: number | null;
  sizing: Record<string, unknown>;
  equityAt: number | null;
  cashAt: number | null;
  tierAt: string;
  verdict: VerdictRecord | null;
  order: OrderRecord | null;
}

export interface VerdictRecord {
  ev: LoadedEvent;
  runId: string;
  decisionId: string | null;
  ticker: string;
  verdict: "approve" | "resize" | "veto";
  rules: string[];
  firedRule: string | null;
  qtyAfter: number;
  intent: IntentRecord | null;
}

export interface RatingRecord {
  ev: LoadedEvent;
  runId: string;
  decisionId: string | null;
  ticker: string;
  cls: string;
  confidence: number;
  tier: string;
  credits: number | null;
  newsCutoff: string;
  setupScore: number;
  reason: string;
  transcriptRef: string;
  secondOpinion: boolean;
}

export interface ShadowRecord {
  ev: LoadedEvent;
  runId: string;
  decisionId: string | null;
  book: string;
  ticker: string;
  side: string;
  notional: number;
  price: number;
}

export interface SkipRecord {
  ev: LoadedEvent;
  runId: string;
  decisionId: string | null;
  ticker: string;
  cls: string | null;
  reason: string;
  source: "class_not_tradeable" | "logged_skip";
}

export interface CreditEntry {
  ev: LoadedEvent;
  runId: string;
  ts: string;
  decisionId: string | null;
  credits: number | null;
  tier: string;
}

export interface DrillRecord {
  ev: LoadedEvent;
  runId: string;
  date: string;
  name: string;
  expected: unknown;
  observed: unknown;
  pass: boolean;
}

export interface RuleChangeRecord {
  ev: LoadedEvent;
  runId: string;
  date: string;
  ruleId: string;
  effectiveFrom: string;
  before: unknown;
  after: unknown;
  triggerDecisionIds: string[];
}

export interface HaltRecord {
  ev: LoadedEvent;
  runId: string;
  ticker: string | null;
  scope: string;
  reason: string;
}

export interface TierChangeRecord {
  ev: LoadedEvent;
  runId: string;
  from: string;
  to: string;
  drawdownPct: number;
  peakEquity: number;
}

export interface PositionRecord {
  ticker: string;
  sleeve: Sleeve;
  qty: number;
  avgCost: number;
  feesIn: number;
  entryTs: string;
  entryPrice: number;
  stop: number | null;
  decisionId: string | null;
  lastPrice: number;
  lastMarkAt: string;
  entryEv: LoadedEvent;
  markEv: LoadedEvent;
  coreTargetWeight?: number;
  coreActualWeight?: number;
  realized: number;
}

export interface SessionSummary {
  runId: string;
  date: string;
  startTs: string;
  startEv: LoadedEvent;
  endTs: string | null;
  reportEv: LoadedEvent | null;
  startEquity: number;
  startCash: number;
  endEquity: number | null;
  pnlPct: number | null;
  baselinePct: number | null;
  shadowPct: { follow: number; fade: number; equal_weight: number } | null;
  brier: number | null;
  maxDrawdownPct: number | null;
  creditsUsed: number | null;
  ordersReported: number | null;
  vetoesReported: number | null;
  skipsReported: number | null;
  ordersSubmitted: number;
  vetoCount: number;
  skipCount: number;
  ratingCredits: number | null;
  events: LoadedEvent[];
}

export interface DecisionRecord {
  id: string;
  runId: string;
  ticker: string;
  date: string;
  screen: { candidate: ScreenCandidate; picked: boolean; ev: LoadedEvent } | null;
  rating: RatingRecord | null;
  intents: IntentRecord[];
  verdicts: VerdictRecord[];
  orders: OrderRecord[];
  fills: FillRecord[];
  stopHit: { ev: LoadedEvent; entry: number; stop: number; exitOrderId: string } | null;
  exitOrder: OrderRecord | null;
  exitFill: FillRecord | null;
  linkedExit: {
    stopHit: { ev: LoadedEvent; entry: number; stop: number; exitOrderId: string };
    order: OrderRecord | null;
    fill: FillRecord | null;
  } | null;
  shadows: ShadowRecord[];
  halt: HaltRecord | null;
  tierAt: string;
  warnings: string[];
}

export interface DeskState {
  asOf: LoadedEvent | null;
  gseq: number;
  totalEvents: number;
  equity: number | null;
  equityEv: LoadedEvent | null;
  cash: number | null;
  cashEv: LoadedEvent | null;
  sessionStartEquity: number | null;
  peakEquity: number | null;
  drawdownPct: number;
  tier: string;
  tierEv: LoadedEvent | null;
  halted: boolean;
  killActive: boolean;
  configHash: string | null;
  promptVersion: string | null;
  runConfigEv: LoadedEvent | null;
  liveSession: SessionSummary | null;
  sessions: SessionSummary[];
  positions: PositionRecord[];
  orders: OrderRecord[];
  intents: IntentRecord[];
  ratings: RatingRecord[];
  shadows: ShadowRecord[];
  skips: SkipRecord[];
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
  realizedBySleeve: Record<Sleeve, number>;
  feesPaid: number;
  decisions: Record<string, DecisionRecord>;
}

export interface RunStep {
  key: string;
  label: string;
  agent: boolean;
  status: "done" | "running" | "waiting";
  at: string | null;
  ev: LoadedEvent | null;
  note: string;
}
