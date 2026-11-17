const usd0 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const usd2 = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const num0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const num2 = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function fmtUsd(value: number | null | undefined, digits: 0 | 2 = 0): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return digits === 2 ? usd2.format(value) : usd0.format(value);
}

export function fmtSignedUsd(value: number, digits: 0 | 2 = 2): string {
  const text = fmtUsd(Math.abs(value), digits);
  if (value > 0) return `+${text}`;
  if (value < 0) return `-${text}`;
  return text;
}

export function fmtPct(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

export function fmtSignedPct(value: number, digits = 2): string {
  if (!Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

export function fmtNum(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return digits === 0 ? num0.format(value) : num2.format(value);
}

export function fmtRatio(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

export function fmtHash(hash: string | null | undefined, take = 8): string {
  if (!hash) return "—";
  return hash.length > take ? `${hash.slice(0, take)}…` : hash;
}

const DATE_FMT = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", timeZone: "UTC" });
const TIME_FMT = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
  timeZone: "UTC",
});

export function fmtDate(ts: string | null | undefined): string {
  if (!ts) return "—";
  const date = new Date(ts);
  return Number.isNaN(date.valueOf()) ? "—" : DATE_FMT.format(date);
}

export function fmtTime(ts: string | null | undefined): string {
  if (!ts) return "—";
  const date = new Date(ts);
  return Number.isNaN(date.valueOf()) ? "—" : `${TIME_FMT.format(date)} UTC`;
}

export function fmtDateTime(ts: string | null | undefined): string {
  return ts ? `${fmtDate(ts)} ${fmtTime(ts)}` : "—";
}

export function countdownText(ms: number): string {
  if (ms <= 0) return "00:00:00";
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return [h, m, s].map((part) => String(part).padStart(2, "0")).join(":");
}

export function signClass(value: number | null | undefined): "up" | "down" | "flat" {
  if (value == null || !Number.isFinite(value) || value === 0) return "flat";
  return value > 0 ? "up" : "down";
}

export function sleeveLabel(sleeve: string): string {
  if (sleeve === "core") return "Core";
  if (sleeve === "drift") return "Drift";
  if (sleeve === "bounce") return "Bounce";
  return "satellite (unrated)";
}
