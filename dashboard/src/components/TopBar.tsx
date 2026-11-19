import { useEffect, useState } from "react";
import type { DeskState } from "../data/types";
import { fmtHash, fmtSignedPct, fmtUsd, countdownText, signClass } from "../data/format";
import { Duck, DuckToggle } from "./Duck";
import { Num, Trace } from "./Trace";

const TIERS = [
  { key: "normal", label: "Normal", tone: "normal" },
  { key: "reduced", label: "Reduced", tone: "reduced" },
  { key: "exits_only", label: "Exits only", tone: "exits" },
  { key: "kill", label: "Kill", tone: "kill" },
];

function useNow(intervalMs: number): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);
  return now;
}

function etParts(now: Date): { weekday: string; minutes: number; clock: string } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  const hour = Number(get("hour"));
  const minute = Number(get("minute"));
  return {
    weekday: get("weekday"),
    minutes: hour * 60 + minute,
    clock: `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")} ET`,
  };
}

function usSession(now: Date): { label: string; tone: "open" | "pre" | "closed"; clock: string } {
  const { weekday, minutes, clock } = etParts(now);
  if (weekday === "Sat" || weekday === "Sun") return { label: "US closed", tone: "closed", clock };
  if (minutes < 4 * 60) return { label: "US closed", tone: "closed", clock };
  if (minutes < 9 * 60 + 30) return { label: "US pre-market", tone: "pre", clock };
  if (minutes < 16 * 60) return { label: "US regular open", tone: "open", clock };
  if (minutes < 20 * 60) return { label: "US after-hours", tone: "pre", clock };
  return { label: "US closed", tone: "closed", clock };
}

/** Next weekday 21:30 Asia/Singapore (SGT is UTC+8 all year). */
function nextRunAt(now: Date): number {
  const sgt = new Date(now.getTime() + 8 * 3600 * 1000);
  let candidate = Date.UTC(sgt.getUTCFullYear(), sgt.getUTCMonth(), sgt.getUTCDate(), 13, 30, 0, 0);
  for (let i = 0; i < 9; i += 1) {
    const weekday = new Date(candidate).getUTCDay();
    if (candidate > now.getTime() && weekday >= 1 && weekday <= 5) return candidate;
    candidate += 86400000;
  }
  return candidate;
}

export function TopBar({
  state,
  verifyOpen,
  verifyBusy,
  verifyTone,
  onToggleVerify,
  duckEnabled,
  onToggleDuck,
  floorMode,
}: {
  state: DeskState;
  verifyOpen: boolean;
  verifyBusy: boolean;
  verifyTone: "ok" | "fail" | "unchecked";
  onToggleVerify: () => void;
  duckEnabled: boolean;
  onToggleDuck: () => void;
  floorMode: boolean;
}) {
  const now = useNow(1000);
  const market = usSession(now);
  const remaining = nextRunAt(now) - now.getTime();
  const pnl = state.liveSession?.pnlPct ?? null;
  const activeTier = state.tier;
  const verifyLabel = verifyBusy
    ? "Checking"
    : verifyTone === "ok"
      ? "OK"
      : verifyTone === "fail"
        ? "Broken"
        : "Unchecked";

  return (
    <header className="topbar">
      <div className="topbar-inner">
        <div className="brand-block">
          <span className="brand">MooWoo Desk</span>
          {floorMode ? (
            <span className="duck-anchor" aria-hidden="true" />
          ) : (
            <Duck enabled={duckEnabled} verifyBusy={verifyBusy} verifyTone={verifyTone} />
          )}
          <span className="sim-badge">SIMULATED FUNDS</span>
        </div>

        <div className="market-block" aria-label="Market state and next run">
          <span className={`status-dot ${market.tone}`} aria-hidden="true" />
          <span className="market-label">{market.label}</span>
          <span className="market-clock num">{market.clock}</span>
          <span className="market-sep" aria-hidden="true">
            /
          </span>
          <span className="countdown">
            next run <span className="num">{countdownText(remaining)}</span>
            <span className="countdown-sub">21:30 SGT</span>
          </span>
        </div>

        <div className="topbar-stats">
          <div className="stat">
            <span className="stat-label">Equity</span>
            <Num
              value={state.equity}
              format={(value) => fmtUsd(value, 0)}
              events={[state.equityEv]}
              className="stat-value"
            />
          </div>
          <div className="stat">
            <span className="stat-label">Today</span>
            {pnl == null ? (
              <span className="stat-value num">—</span>
            ) : (
              <Num
                value={pnl}
                format={(value) => fmtSignedPct(value)}
                events={[state.liveSession?.reportEv]}
                className={`stat-value ${signClass(pnl)}`}
              />
            )}
          </div>
        </div>

        <div className="tier-block">
          <span className="tier-caption">Risk tier</span>
          <ol className="tier-scale" aria-label={`Risk tier: ${activeTier.replace("_", " ")}`}>
            {TIERS.map((tier) => (
              <li
                key={tier.key}
                className={`tier-step tier-${tier.tone}${tier.key === activeTier ? " active" : ""}`}
                aria-current={tier.key === activeTier ? "step" : undefined}
              >
                <span className="tier-name">{tier.label}</span>
              </li>
            ))}
          </ol>
        </div>

        <div className="topbar-meta">
          <span className="meta-item">
            config{" "}
            <Trace events={[state.runConfigEv]} note="configHash from run_started">
              <code>{fmtHash(state.configHash, 10)}</code>
            </Trace>
          </span>
          <span className="meta-item">
            prompt{" "}
            <Trace events={[state.runConfigEv]} note="promptVersion from run_started">
              <code>{state.promptVersion ?? "—"}</code>
            </Trace>
          </span>
          <DuckToggle enabled={duckEnabled} onToggle={onToggleDuck} />
          <button
            type="button"
            className={`verify-button tone-${verifyTone}`}
            aria-expanded={verifyOpen}
            aria-controls="verify-panel"
            onClick={onToggleVerify}
            disabled={verifyBusy}
          >
            <span className="verify-dot" aria-hidden="true" />
            Verify logs
            <span className="verify-state">{verifyLabel}</span>
          </button>
        </div>
      </div>
    </header>
  );
}
