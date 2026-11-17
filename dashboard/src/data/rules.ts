export const RULES = {
  coreWeight: 0.5,
  satelliteCap: 0.25,
  satelliteCapStepUp: 0.4,
  cashFloor: 0.1,
  perNameCap: 0.08,
  dailyLossHalt: 0.015,
  tiers: { reduced: -0.02, exits_only: -0.04, kill: -0.06 },
  maxOrdersPerSession: 30,
  maxSpread: 0.0015,
  maxCorrelation: 0.8,
  correlationPeriod: 60,
  maxBouncePositions: 3,
  minEntryNotional: 2000,
  feePerOrder: 0.99,
  feePerShareSold: 0.000166,
  feeSellCap: 8.3,
  creditBudget: 3500,
  finalDay: "2026-11-27",
  runTimeSgt: "21:30",
} as const;

export const TRADEABLE_CLASSES = new Set(["explained_up", "unexplained_down"]);

export function classMapsToSleeve(cls: string | null | undefined): "drift" | "bounce" | null {
  if (cls === "explained_up") return "drift";
  if (cls === "unexplained_down") return "bounce";
  return null;
}

export const RULE_TEXT: Record<string, string> = {
  long_only: "long-only book; no short orders",
  cash: "keep the 10% cash floor after pending buys and fees",
  correlation: "60-day pair correlation ≤ 0.80 with open satellite names",
  tier_size: "reduced tier halves the permitted satellite size",
  position_qty: "sell quantity fits within held shares",
  daily_loss: "1.5% session loss halts new entries",
  per_name_cap: "satellite stock ≤ 8% of marked equity",
  satellite_cap: "all satellite stock ≤ 25% (or 40% after step-up)",
  max_orders: "at most 30 submitted orders per session",
  below_min_notional: "final buy notional must reach $2,000",
  duplicate_decision: "each decision ID tickets at most once",
  stale_price: "quote at most 60 seconds old",
  spread: "spread at most 0.15% of midpoint",
  first_minutes: "no entries in the first five regular minutes",
};

export const FIRED_RULE_TEXT: Record<string, string> = {
  correlation: "pair correlation > 0.80 over 60 aligned daily returns",
  tier_size: "reduced-tier sizing factor 0.5",
  per_name_cap: "satellite stock exposure > 8% of marked equity",
  satellite_cap: "satellite exposure > 25% (20% when regime is on)",
  cash_floor: "cash would fall below 10% of equity",
  daily_loss: "session loss reached 1.5%",
  max_orders: "30-order session limit reached",
  stale_price: "quote older than 60 seconds",
  spread: "spread wider than 0.15% of midpoint",
  below_min_notional: "resized buy fell below the $2,000 floor",
  duplicate_decision: "decision ID already ticketed",
  kill_or_halted: "tier is kill or the run is halted",
  exits_only: "tier is exits only",
  final_day: "no new entries on the final day",
  first_minutes: "inside the first five regular minutes",
  adv: "notional above 0.5% of 20-session average dollar volume",
  bounce_count: "more than three bounce positions",
  regime: "regime filter blocks the entry",
};
