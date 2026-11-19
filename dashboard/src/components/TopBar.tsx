import type { DeskState } from "../data/types";
import { sgtTime, START_CAPITAL, type ScheduledRun } from "../data/dashboard";
import { fmtSignedPct, fmtUsd, signClass } from "../data/format";
import { Duck, DuckToggle } from "./Duck";

export function TopBar({ state, next, verifyBusy, verifyTone, duckEnabled, onDuckToggle }: {
  state: DeskState; next: ScheduledRun; verifyBusy: boolean; verifyTone: "ok" | "fail" | "unchecked";
  duckEnabled: boolean; onDuckToggle: () => void;
}) {
  const change = state.equity == null ? null : (state.equity / START_CAPITAL - 1) * 100;
  return <header className="topbar">
    <div className="desk-top">
      <div className="desk-brand"><span className="brand">MooWoo Desk</span><span className="sim-badge">SIMULATED FUNDS</span></div>
      <Duck enabled={duckEnabled} verifyBusy={verifyBusy} verifyTone={verifyTone} />
      <div className="desk-balance num"><strong>{fmtUsd(state.equity)}</strong><span className={change == null ? "muted" : signClass(change)}>{change == null ? "Not recorded" : fmtSignedPct(change)}</span></div>
      <p className="desk-next"><span>Next scheduled run</span><strong>{next.kind} · {sgtTime(next.at)}</strong></p>
      <DuckToggle enabled={duckEnabled} onToggle={onDuckToggle} />
    </div>
  </header>;
}
