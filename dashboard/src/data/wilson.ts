export interface Interval {
  p: number;
  lo: number;
  hi: number;
  n: number;
}

/** 95% Wilson score interval for a binomial hit rate. Inputs are proportions 0..1. */
export function wilson(successes: number, n: number, z = 1.959963984540054): Interval | null {
  if (n <= 0) return null;
  const p = successes / n;
  const denom = 1 + (z * z) / n;
  const center = (p + (z * z) / (2 * n)) / denom;
  const half = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / denom;
  return { p, lo: Math.max(0, center - half), hi: Math.min(1, center + half), n };
}
