import { useMemo } from "react";
import type { DeskState } from "../data/types";
import { correlationMatrix } from "../data/metrics";
import { FIRED_RULE_TEXT, RULES, RULE_TEXT } from "../data/rules";
import { fmtDate, fmtDateTime, fmtPct, fmtRatio, fmtUsd } from "../data/format";
import { Panel } from "../components/Panel";
import { Num, Trace } from "../components/Trace";

function showValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (value == null) return "—";
  return JSON.stringify(value);
}

export function RiskDesk({
  state,
  onOpenDecision,
}: {
  state: DeskState;
  onOpenDecision: (id: string) => void;
}) {
  const intents = useMemo(() => [...state.intents].reverse(), [state.intents]);
  const matrix = useMemo(() => correlationMatrix(state), [state]);
  const drills = useMemo(() => [...state.drills].reverse(), [state.drills]);
  const halts = useMemo(() => [...state.halts].reverse(), [state.halts]);
  const tierChanges = useMemo(() => [...state.tierChanges].reverse(), [state.tierChanges]);

  return (
    <>
      <div className="view-head">
        <div>
          <h1>Risk desk wall</h1>
          <p className="view-sub">
            Every order intent, the rule that fired, the open-position correlation grid and the drill
            record. Click an intent to open its decision.
          </p>
        </div>
        <div className="view-status">
          <span className={`live-pill ${state.killActive ? "danger" : ""}`}>
            {state.killActive ? "KILL ACTIVE" : "DESK ARMED"}
          </span>
          <span>
            tier <strong>{state.tier.replace("_", " ")}</strong> · {state.vetoes.length} veto
            {state.vetoes.length === 1 ? "" : "es"} · {state.drills.length} drill
            {state.drills.length === 1 ? "" : "s"} logged
          </span>
        </div>
      </div>

      <div className="risk-grid">
        <Panel
          className="span-8"
          title="Order intents"
          question="Every intent, stamped by the risk verdict, with the first rule that fired"
          id="panel-intents"
        >
          {intents.length === 0 ? (
            <p className="empty">No order intents in the loaded logs.</p>
          ) : (
            <ol className="intent-feed">
              {intents.map((intent) => {
                const verdict = intent.verdict;
                const tone =
                  verdict?.verdict === "veto"
                    ? "veto"
                    : verdict?.verdict === "resize"
                      ? "resize"
                      : verdict?.verdict === "approve"
                        ? "approve"
                        : "pending";
                const stampText =
                  verdict?.verdict === "veto"
                    ? "VETO"
                    : verdict?.verdict === "resize"
                      ? "RESIZED"
                      : verdict?.verdict === "approve"
                        ? "APPROVED"
                        : "NO VERDICT";
                const clickable = Boolean(intent.decisionId && state.decisions[intent.decisionId]);
                return (
                  <li key={`${intent.runId}-${intent.ev.seq}`} className="intent-item">
                    <div className="intent-row">
                      <button
                        type="button"
                        className={`stamp ${tone}`}
                        disabled={!clickable}
                        onClick={() => intent.decisionId && onOpenDecision(intent.decisionId)}
                        aria-label={`${stampText} ${intent.ticker} ${intent.side}; open decision`}
                      >
                        {stampText}
                      </button>
                      <div className="intent-main">
                        <div className="intent-line">
                          <button
                            type="button"
                            className="intent-ticker ticker-button"
                            disabled={!clickable}
                            onClick={() => intent.decisionId && onOpenDecision(intent.decisionId)}
                          >
                            {intent.ticker}
                          </button>
                          <span className="intent-side">{intent.side}</span>
                          <Trace events={[intent.ev]} note="order_intent qty and limit">
                            <span className="num">
                              {intent.qty} @ {fmtUsd(intent.limitPrice, 2)}
                            </span>
                          </Trace>
                          <Trace events={[intent.ev]} note="order_intent notional">
                            <span className="muted">{fmtUsd(intent.notional, 2)}</span>
                          </Trace>
                          <span className="muted">{intent.sleeve}</span>
                        </div>
                        <span className="intent-rule">
                          {verdict?.firedRule ? (
                            <>
                              <code>{verdict.firedRule}</code>{" "}
                              <span className="muted">
                                — {FIRED_RULE_TEXT[verdict.firedRule] ?? "see docs/risk-desk.md"}
                              </span>
                            </>
                          ) : verdict ? (
                            <span className="muted">
                              no gate fired; checked {verdict.rules.length}: {verdict.rules.join(", ")}
                            </span>
                          ) : (
                            <span className="muted">no risk verdict event</span>
                          )}
                        </span>
                        {verdict && verdict.rules.length > 0 ? (
                          <span className="intent-rules">
                            {verdict.rules.map((rule) => (
                              <span key={rule} className={rule === verdict.firedRule ? "rule-pill fired" : "rule-pill"}>
                                {rule}
                              </span>
                            ))}
                          </span>
                        ) : null}
                      </div>
                      <div className="intent-side-meta">
                        <span className="muted">
                          <Trace events={[intent.ev]}>{fmtDate(intent.ev.ts)}</Trace>
                        </span>
                        <span className="num muted">
                          qty after <Num value={verdict?.qtyAfter} format={(value) => String(value)} events={[verdict?.ev]} />
                        </span>
                        <button
                          type="button"
                          className="mono-link"
                          disabled={!clickable}
                          onClick={() => intent.decisionId && onOpenDecision(intent.decisionId)}
                        >
                          {clickable ? "open decision" : "no decision"}
                        </button>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
          <p className="tiny">
            Stamps come from <code>risk_verdict.verdict</code>; the fired rule is the earliest failing
            gate. Approved intents list every gate checked. Sells bypass entry gates.
          </p>
        </Panel>

        <Panel
          className="span-4"
          title="Correlation grid"
          question="Open satellite names; cells above 0.80 would be outlined"
          id="panel-correlation"
        >
          {matrix.names.length < 2 ? (
            <p className="empty">{matrix.note}</p>
          ) : (
            <div className="table-scroll">
              <table className="matrix">
                <thead>
                  <tr>
                    <th scope="col">name</th>
                    {matrix.names.map((name) => (
                      <th scope="col" key={name}>
                        {name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {matrix.names.map((row, rowIndex) => (
                    <tr key={row}>
                      <th scope="row">{row}</th>
                      {matrix.names.map((col, colIndex) => {
                        const value = matrix.cells[rowIndex][colIndex];
                        const breach = row !== col && value != null && value > RULES.maxCorrelation;
                        return (
                          <td
                            key={col}
                            className={row === col ? "self" : value == null ? "na" : breach ? "breach" : ""}
                          >
                            {row === col ? "1.00" : value == null ? "n/a" : value.toFixed(2)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="tiny">{matrix.note}</p>
          <p className="tiny">
            Threshold <strong>{fmtRatio(RULES.maxCorrelation)}</strong> over{" "}
            {RULES.correlationPeriod} aligned daily returns; core ETFs are exempt.
          </p>
        </Panel>

        <Panel
          className="span-7"
          title="Drill board"
          question="Marked drills only; expected versus observed"
          id="panel-drills"
        >
          {drills.length === 0 ? (
            <p className="empty">No drill events in the loaded logs.</p>
          ) : (
            <div className="table-scroll">
              <table className="drill-table">
                <thead>
                  <tr>
                    <th scope="col">Date</th>
                    <th scope="col">Drill</th>
                    <th scope="col">Expected</th>
                    <th scope="col">Observed</th>
                    <th scope="col">Result</th>
                  </tr>
                </thead>
                <tbody>
                  {drills.map((drill) => (
                    <tr key={`${drill.runId}-${drill.ev.seq}`}>
                      <td>
                        <Trace events={[drill.ev]}>{drill.date}</Trace>
                      </td>
                      <td>
                        <code>{drill.name}</code>
                      </td>
                      <td>
                        <Trace events={[drill.ev]}>{showValue(drill.expected)}</Trace>
                      </td>
                      <td>
                        <Trace events={[drill.ev]}>{showValue(drill.observed)}</Trace>
                      </td>
                      <td>
                        <span className={drill.pass ? "stamp approve" : "stamp veto"}>
                          {drill.pass ? "PASS" : "FAIL"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="tiny">
            A drill event requires <code>drill=true</code>; consumers must never route marked events to
            a broker. Unlogged planned checks are not shown as passes.
          </p>
        </Panel>

        <Panel
          className="span-5"
          title="Kill switch"
          question="Tier, latches and the last restart reason"
          id="panel-kill"
        >
          <div className={`kill-status ${state.killActive ? "danger" : "ok"}`}>
            <span className="kill-label">Kill switch</span>
            <strong>{state.killActive ? "TRIGGERED · LIQUIDATE" : "ARMED · NOT TRIGGERED"}</strong>
            <span className="kill-tier">
              tier <strong>{state.tier.replace("_", " ")}</strong> · drawdown{" "}
              <Num
                value={state.drawdownPct}
                format={(value) => fmtPct(value, 2)}
                events={[state.equityEv, state.tierEv]}
                note="reported equity from running peak"
              />
            </span>
            <span className="kill-thresholds">
              reduce at -2% · exits only at -4% · kill at -6%
            </span>
          </div>

          <div className="kill-block">
            <h3 className="mini-title">Last restart reason</h3>
            <p className="empty">No restart event is present in the fixtures; nothing is assumed.</p>
          </div>

          <div className="kill-block">
            <h3 className="mini-title">Halt events</h3>
            {halts.length === 0 ? (
              <p className="empty">No halt events in the loaded logs.</p>
            ) : (
              <ul className="halt-list">
                {halts.map((halt) => (
                  <li key={`${halt.runId}-${halt.ev.seq}`}>
                    <span className={`stamp ${halt.scope === "all" ? "veto" : "resize"}`}>{halt.scope}</span>
                    <span className="halt-main">
                      <strong>{halt.ticker ?? "run-wide"}</strong>{" "}
                      <span className="muted">{halt.reason}</span>
                    </span>
                    <Trace events={[halt.ev]}>
                      <span className="halt-time">{fmtDate(halt.ev.ts)}</span>
                    </Trace>
                  </li>
                ))}
              </ul>
            )}
            <p className="tiny">Daily loss is a separate session latch; ticker halts do not stop exits.</p>
          </div>

          <div className="kill-block">
            <h3 className="mini-title">Tier changes</h3>
            {tierChanges.length === 0 ? (
              <p className="empty">No tier_changed events; tier comes from run_started.</p>
            ) : (
              <ul className="tier-history">
                {tierChanges.map((change) => (
                  <li key={change.ev.seq}>
                    <span className="num">
                      {change.from} → {change.to}
                    </span>
                    <span className="muted">
                      <Num
                        value={change.drawdownPct}
                        format={(value) => fmtPct(value, 2)}
                        events={[change.ev]}
                      />{" "}
                      drawdown
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Panel>

        <Panel className="span-12" title="Rule reference" question="Thresholds used by the wall" id="panel-rule-ref">
          <ul className="rule-reference">
            {["long_only", "cash", "correlation", "tier_size", "position_qty", "daily_loss", "per_name_cap", "satellite_cap", "max_orders"].map(
              (rule) => (
                <li key={rule}>
                  <code>{rule}</code> <span className="muted">{RULE_TEXT[rule]}</span>
                </li>
              ),
            )}
          </ul>
          <p className="tiny">
            Thresholds mirror <code>moowoo/config.py</code>, <code>docs/risk-desk.md</code> and
            <code> PREREGISTRATION.md</code>. Last session start{" "}
            {state.liveSession ? fmtDateTime(state.liveSession.startTs) : "—"}.
          </p>
        </Panel>
      </div>
    </>
  );
}
