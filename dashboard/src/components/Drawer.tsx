import { useEffect, useRef, type ReactNode } from "react";
import type { DeskState } from "../data/types";
import {
  FIRED_RULE_TEXT,
  RULES,
  RULE_TEXT,
  TRADEABLE_CLASSES,
  classMapsToSleeve,
} from "../data/rules";
import { fmtDateTime, fmtNum, fmtPct, fmtRatio, fmtSignedUsd, fmtTime, fmtUsd, signClass } from "../data/format";
import { Num, Trace } from "./Trace";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="drawer-row">
      <span className="drawer-label">{label}</span>
      <span className="drawer-value">{children}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="drawer-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

interface EvidenceItem {
  id?: string;
  headline?: string;
  source?: string;
  publishedAt?: string;
}

export function DecisionDrawer({
  state,
  decisionId,
  onClose,
  onOpenDecision,
}: {
  state: DeskState;
  decisionId: string | null;
  onClose: () => void;
  onOpenDecision: (id: string) => void;
}) {
  const panelRef = useRef<HTMLElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!decisionId) return;
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;
      const focusables = panelRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
      previous?.focus?.();
    };
  }, [decisionId, onClose]);

  if (!decisionId) return null;
  const decision = state.decisions[decisionId];
  if (!decision) return null;

  const rating = decision.rating;
  const intent = decision.intents[decision.intents.length - 1] ?? null;
  const verdict = decision.verdicts[decision.verdicts.length - 1] ?? intent?.verdict ?? null;
  const stop = decision.stopHit ?? decision.linkedExit?.stopHit ?? null;
  const exit = decision.exitFill ?? decision.linkedExit?.fill ?? null;
  const entryFill = decision.fills.find((fill) => fill.orderId !== stop?.exitOrderId) ?? null;
  const position = state.positions.find((candidate) => candidate.ticker === decision.ticker) ?? null;
  const linkedExitDecision =
    decision.linkedExit != null
      ? Object.values(state.decisions).find(
          (candidate) => candidate.stopHit?.exitOrderId === decision.linkedExit?.stopHit.exitOrderId,
        ) ?? null
      : null;

  const stamp =
    verdict?.verdict === "veto"
      ? { text: "VETO", tone: "veto" }
      : verdict?.verdict === "resize"
        ? { text: "RESIZED", tone: "resize" }
        : verdict?.verdict === "approve"
          ? { text: "APPROVED", tone: "approve" }
          : { text: "NO RISK VERDICT", tone: "none" };

  const evidence = Array.isArray(rating?.ev.evidence) ? (rating?.ev.evidence as EvidenceItem[]) : [];
  const tierLabel =
    rating?.tier === "debate" ? "Manager (debate tier)" : rating?.tier === "quick" ? "Quick classifier" : "—";

  const entryPrice = stop?.entry ?? entryFill?.avgPrice ?? null;
  const exitQty = exit?.filledQty ?? 0;
  const grossPnl =
    entryPrice != null && exit ? (exit.avgPrice - entryPrice) * exitQty : null;
  const estimatedFees =
    exit != null
      ? RULES.feePerOrder +
        RULES.feePerOrder +
        Math.min(RULES.feeSellCap, RULES.feePerShareSold * exitQty)
      : null;
  const netPnl = grossPnl != null && estimatedFees != null ? grossPnl - estimatedFees : null;

  const capValue = intent?.equityAt != null ? RULES.perNameCap * intent.equityAt : null;

  return (
    <div
      className="drawer-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        ref={panelRef}
      >
        <header className="drawer-head">
          <div>
            <div className="drawer-kicker">
              <span className="drawer-ticker" id="drawer-title">
                {decision.ticker}
              </span>
              <span className={`stamp ${stamp.tone}`}>{stamp.text}</span>
              {rating ? <span className="chip">{rating.cls}</span> : null}
            </div>
            <p className="drawer-id">
              {decision.id} · {decision.runId}
            </p>
          </div>
          <button type="button" className="drawer-close" onClick={onClose} ref={closeRef} aria-label="Close decision drawer">
            ×
          </button>
        </header>

        <div className="drawer-body">
          {decision.warnings.length > 0 ? (
            <div className="callout warn" role="note">
              <strong>Desk checks</strong>
              <ul>
                {decision.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <Section title="Screen row">
            {decision.screen ? (
              <>
                <Row label="Ticker">{decision.screen.candidate.ticker}</Row>
                <Row label="Move">
                  <Num
                    value={decision.screen.candidate.movePct}
                    format={(value) => fmtPct(value, 2)}
                    events={[decision.screen.ev]}
                  />
                </Row>
                <Row label="z-score">
                  <Num
                    value={decision.screen.candidate.z}
                    format={(value) => fmtNum(value, 2)}
                    events={[decision.screen.ev]}
                  />
                </Row>
                <Row label="RVOL">
                  <Num
                    value={decision.screen.candidate.rvol}
                    format={(value) => fmtNum(value, 2)}
                    events={[decision.screen.ev]}
                  />
                </Row>
                <Row label="Earnings">
                  {decision.screen.candidate.earnings === true ? "yes" : "no"}
                </Row>
                <Row label="Picked">{decision.screen.picked ? "picked by the screen" : "not picked"}</Row>
              </>
            ) : (
              <p className="empty">No screen event for this decision in the loaded logs.</p>
            )}
          </Section>

          <Section title="Analyst facts">
            {rating ? (
              <>
                <p className="drawer-text">{rating.reason}</p>
                <Row label="Published">
                  <Trace events={[rating.ev]}>{fmtDateTime(rating.ev.ts)}</Trace>
                </Row>
                <Row label="News cutoff">
                  <Trace events={[rating.ev]}>{rating.newsCutoff}</Trace>
                </Row>
                <Row label="Transcript">
                  <code>{rating.transcriptRef}</code>
                </Row>
                {evidence.length > 0 ? (
                  <ul className="evidence-list">
                    {evidence.map((item, index) => (
                      <li key={item.id ?? index}>
                        <span className="evidence-headline">{item.headline ?? item.id}</span>
                        <span className="evidence-meta">
                          {item.source ?? "source?"}
                          {item.publishedAt ? ` · ${item.publishedAt}` : " · no publish time"}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="empty">
                    No evidence array is present on this rating event; the events carry the reason
                    only. Item IDs and publish times cannot be shown.
                  </p>
                )}
              </>
            ) : (
              <p className="empty">No rating event for this decision, so no analyst facts are logged.</p>
            )}
          </Section>

          <Section title="Bull / bear">
            <p className="empty">
              No bull or bear events exist in the v0 event contract. Nothing is available to show;
              this drawer does not invent a debate.
            </p>
          </Section>

          <Section title="Verdict">
            {rating ? (
              <>
                <Row label="Called by">{tierLabel}</Row>
                <Row label="Class">
                  <span className="chip">{rating.cls}</span>
                </Row>
                <Row label="Confidence">
                  <div className="confidence">
                    <div className="confidence-track">
                      <div
                        className="confidence-fill"
                        style={{ width: `${Math.max(0, Math.min(100, rating.confidence * 100))}%` }}
                      />
                    </div>
                    <Num
                      value={rating.confidence}
                      format={(value) => fmtPct(value * 100, 1)}
                      events={[rating.ev]}
                    />
                  </div>
                </Row>
                <Row label="Tier">{rating.tier}</Row>
                <Row label="Setup score">
                  <Num
                    value={rating.setupScore}
                    format={(value) => `${value} / 5`}
                    events={[rating.ev]}
                    note="logged only; never used for sizing"
                  />
                </Row>
                <Row label="Credits">
                  <Num value={rating.credits} format={(value) => fmtNum(value, 1)} events={[rating.ev]} />
                </Row>
                <Row label="Plan mapping">
                  {classMapsToSleeve(rating.cls)
                    ? `maps to the ${classMapsToSleeve(rating.cls)} sleeve`
                    : TRADEABLE_CLASSES.has(rating.cls)
                      ? "tradeable"
                      : "not tradeable; logged as a skip"}
                </Row>
              </>
            ) : (
              <p className="empty">No rating event: this decision was not classified.</p>
            )}
          </Section>

          <Section title="Sizing maths">
            {intent ? (
              <div className="maths">
                <Row label="Method">
                  <code>{String(intent.sizing.method ?? "n/a")}</code>
                </Row>
                <Row label="Tier at intent">{intent.tierAt}</Row>
                <Row label="Risk budget">
                  <Num
                    value={typeof intent.sizing.riskBudget === "number" ? intent.sizing.riskBudget : null}
                    format={(value) => fmtUsd(value, 2)}
                    events={[intent.ev]}
                  />
                </Row>
                <Row label="Qty × limit">
                  <Num value={intent.qty} format={(value) => fmtNum(value, 0)} events={[intent.ev]} />
                  {" × "}
                  <Num value={intent.limitPrice} format={(value) => fmtUsd(value, 2)} events={[intent.ev]} />
                </Row>
                <Row label="Notional">
                  <Num
                    value={intent.notional}
                    format={(value) => fmtUsd(value, 2)}
                    events={[intent.ev]}
                    note="notional from order_intent"
                  />
                  {intent.equityAt ? (
                    <span className="muted"> = {((intent.notional / intent.equityAt) * 100).toFixed(2)}% of equity at intent</span>
                  ) : null}
                </Row>
                <Row label="Stop">
                  <Num value={intent.stop} format={(value) => fmtUsd(value, 2)} events={[intent.ev]} />
                </Row>
                <Row label="Stop distance">
                  <Trace events={[intent.ev]} note="derived from limitPrice − stop">
                    {intent.stop == null ? "Not recorded" : fmtUsd(Math.abs(intent.limitPrice - intent.stop), 2)}
                  </Trace>
                </Row>
                <Row label="Implied risk">
                  <Trace events={[intent.ev]} note="derived: qty × stop distance; not a logged field">
                    {intent.stop == null ? "Not recorded" : fmtUsd(Math.abs(intent.qty * (intent.limitPrice - intent.stop)), 2)}
                  </Trace>
                </Row>
                <Row label="Per-name cap">
                  <Trace events={[intent.ev]} note="8% × equity at intent">
                    {fmtUsd(capValue, 2)}
                  </Trace>
                  {capValue != null ? (
                    <span className="muted">
                      {" "}
                      → {intent.notional <= capValue ? "within cap" : "above cap"}
                    </span>
                  ) : null}
                </Row>
                <Row label="Entry floor">
                  <Trace events={[intent.ev]} note="MIN_ENTRY_NOTIONAL from FEES-01">
                    {fmtUsd(RULES.minEntryNotional, 0)}
                  </Trace>
                  <span className="muted">
                    {" "}
                    → {intent.notional >= RULES.minEntryNotional ? "pass" : "below floor"}
                  </span>
                </Row>
                {verdict?.verdict === "resize" ? (
                  <p className="maths-note">
                    Resized to{" "}
                    <Num value={verdict.qtyAfter} format={(value) => fmtNum(value, 0)} events={[verdict.ev]} />{" "}
                    share(s) by <code>{verdict.firedRule}</code>.
                  </p>
                ) : null}
              </div>
            ) : (
              <p className="empty">No order intent logged for this decision; code issued no ticket.</p>
            )}
          </Section>

          <Section title="Risk verdict">
            {verdict ? (
              <>
                <Row label="Verdict">
                  <span className={`stamp ${stamp.tone}`}>{verdict.verdict}</span>
                </Row>
                <Row label="Qty after">
                  <Num value={verdict.qtyAfter} format={(value) => fmtNum(value, 0)} events={[verdict.ev]} />
                </Row>
                <Row label="Fired rule">
                  {verdict.firedRule ? (
                    <span className="fired">
                      <code>{verdict.firedRule}</code>
                      <span className="muted"> — {FIRED_RULE_TEXT[verdict.firedRule] ?? "see docs/risk-desk.md"}</span>
                    </span>
                  ) : (
                    "none; no gate fired"
                  )}
                </Row>
                <ul className="rule-list">
                  {verdict.rules.map((rule) => (
                    <li key={rule} className={rule === verdict.firedRule ? "rule fired" : "rule"}>
                      <span className="rule-id">{rule}</span>
                      <span className="rule-text">{RULE_TEXT[rule] ?? "checked by the risk desk"}</span>
                    </li>
                  ))}
                </ul>
                <p className="tiny">All gates are evaluated for evidence; the first failure is the fired rule.</p>
              </>
            ) : (
              <p className="empty">No risk verdict event for this decision.</p>
            )}
          </Section>

          <Section title="Order">
            {decision.orders.length > 0 ? (
              decision.orders.map((record) => (
                <div key={record.orderId} className="drawer-block">
                  <Row label="Order ID">
                    <code>{record.orderId}</code>
                  </Row>
                  <Row label="Side / qty">{record.side} {record.qty}</Row>
                  <Row label="Limit">
                    <Num value={record.limitPrice} format={(value) => fmtUsd(value, 2)} events={[record.ev]} />
                  </Row>
                  <Row label="Environment">{record.trdEnv ?? "—"}</Row>
                  <Row label="Submitted">
                    <Trace events={[record.ev]}>{fmtTime(record.ev.ts)}</Trace>
                  </Row>
                </div>
              ))
            ) : (
              <p className="empty">No order was submitted for this decision.</p>
            )}
          </Section>

          <Section title="Fill">
            {decision.fills.length > 0 ? (
              decision.fills.map((fill) => (
                <div key={`${fill.orderId}-${fill.ev.gseq}`} className="drawer-block">
                  <Row label="Order"><code>{fill.orderId}</code></Row>
                  <Row label="Status">{fill.status}</Row>
                  <Row label="Filled">
                    <Num value={fill.filledQty} format={(value) => fmtNum(value, 0)} events={[fill.ev]} /> @{" "}
                    <Num value={fill.avgPrice} format={(value) => fmtUsd(value, 2)} events={[fill.ev]} />
                  </Row>
                  <Row label="Source">{fill.source}</Row>
                </div>
              ))
            ) : (
              <p className="empty">No fill event; planning never pretends a fill happened.</p>
            )}
          </Section>

          <Section title="Stop">
            {stop ? (
              <>
                <Row label="Entry">
                  <Num value={stop.entry} format={(value) => fmtUsd(value, 2)} events={[stop.ev]} />
                </Row>
                <Row label="Stop">
                  <Num value={stop.stop} format={(value) => fmtUsd(value, 2)} events={[stop.ev]} />
                </Row>
                <Row label="Exit order"><code>{stop.exitOrderId}</code></Row>
                <Row label="Logged">
                  <Trace events={[stop.ev]}>{fmtDateTime(stop.ev.ts)}</Trace>
                </Row>
                {decision.linkedExit ? (
                  <p className="tiny">This stop was logged in a later session; it is linked from the entry decision.</p>
                ) : null}
              </>
            ) : position?.stop != null ? (
              <Row label="Open position stop">
                <Num value={position.stop} format={(value) => fmtUsd(value, 2)} events={[position.entryEv]} />
              </Row>
            ) : (
              <p className="empty">No stop event is logged for this decision.</p>
            )}
          </Section>

          <Section title="Exit">
            {exit ? (
              <>
                <Row label="Exit order"><code>{exit.orderId}</code></Row>
                <Row label="Exit fill">
                  <Num value={exit.filledQty} format={(value) => fmtNum(value, 0)} events={[exit.ev]} /> @{" "}
                  <Num value={exit.avgPrice} format={(value) => fmtUsd(value, 2)} events={[exit.ev]} />
                </Row>
                {entryPrice != null ? (
                  <>
                    <Row label="Reference entry">
                      <Trace events={[stop?.ev, entryFill?.ev]}>{fmtUsd(entryPrice, 2)}</Trace>
                    </Row>
                    <Row label="Gross P&L">
                      <Trace events={[exit.ev]} note="derived: (exit − entry) × filled qty">
                        {fmtSignedUsd(grossPnl ?? 0, 2)}
                      </Trace>
                    </Row>
                    <Row label="Est. fees">
                      <Trace events={[exit.ev]} note="derived: FEES-01 buy $0.99 + sell fee">
                        {fmtSignedUsd(-(estimatedFees ?? 0), 2)}
                      </Trace>
                    </Row>
                    <Row label="Net P&L">
                      <Trace events={[exit.ev]} note="derived after estimated FEES-01; not a logged field">
                        <span className={signClass(netPnl)}>{fmtSignedUsd(netPnl ?? 0, 2)}</span>
                      </Trace>
                    </Row>
                  </>
                ) : (
                  <p className="tiny">No entry print is linked, so P&amp;L is not derived.</p>
                )}
                {linkedExitDecision && linkedExitDecision.id !== decision.id ? (
                  <button
                    type="button"
                    className="button ghost small"
                    onClick={() => onOpenDecision(linkedExitDecision.id)}
                  >
                    Open exit decision {linkedExitDecision.id}
                  </button>
                ) : null}
              </>
            ) : position ? (
              <p className="empty">
                Still open at the last event print: {position.qty} share(s) at{" "}
                <Trace events={[position.markEv, position.entryEv]}>{fmtUsd(position.lastPrice, 2)}</Trace>.
                No exit is logged.
              </p>
            ) : (
              <p className="empty">No exit is logged for this decision.</p>
            )}
          </Section>

          <Section title="Rule references">
            <Row label="Per-name cap">{fmtPct(RULES.perNameCap * 100, 0)}</Row>
            <Row label="Satellite cap">{fmtPct(RULES.satelliteCap * 100, 0)}</Row>
            <Row label="Daily loss halt">{fmtPct(RULES.dailyLossHalt * 100, 1)}</Row>
            <Row label="Max correlation">{fmtRatio(RULES.maxCorrelation)}</Row>
            <Row label="Max orders">{RULES.maxOrdersPerSession}</Row>
            <p className="tiny">
              Thresholds mirror moowoo/config.py and docs/risk-desk.md. They are shown for reading
              the log, not recomputed by this dashboard.
            </p>
          </Section>
        </div>
      </aside>
    </div>
  );
}
