/**
 * Static excerpt from config/universe-2026-11-16.json.
 * Counts and caps are copied into the dashboard so the browser makes no network calls.
 */
export const UNIVERSE = {
  date: "2026-11-16",
  allNames: 918,
  gated: 727,
  passingListSha256: "c9233c06ef87c4d83f68688c06e5136c881b6f78bf643377fd5e8dd0482f5e4e",
  marketCaps: {
    AAPL: 5156453744640,
    MSFT: 3877587648512,
    NVDA: 3848065777664,
    KO: 430276247552,
  } as Record<string, number>,
};

export function marketCapFor(ticker: string): number | null {
  const value = UNIVERSE.marketCaps[ticker];
  return value != null && Number.isFinite(value) ? value : null;
}
