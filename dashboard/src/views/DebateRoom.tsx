import { useMemo, useState } from "react";
import type { DeskState } from "../data/types";
import {
  classMeta,
  debateRecords,
  defaultDebateId,
  finalDayLabel,
  type DebateRecord,
  type ProcessCheck,
} from "../data/stage2";
import { fmtDateTime, fmtPct } from "../data/format";
import { Panel } from "../components/Panel";

function CheckList({ checks }: { checks: ProcessCheck[] }) {
  if (checks.length === 0) {
    return <p className="tiny">No process rows can be built because the decision is not in state.</p>;
  }
  return (
    <ul className="check-list">
      {checks.map((check) => (
        <li key={check.label}>
          <span className={`check-status ${check.status}`}>{check.status}</span>
          <span className="check-label">{check.label}</span>
          <span className="check-note">{check.note}</span>
        </li>
      ))}
    </ul>
  );
}

function CallBlock({ record }: { record: DebateRecord }) {
  const manager = record.manager;
  const quick = record.quick;
  return (
    <div className="call-pair">
      <div className="call-card">
        <div className="call-head">
          <h3>{record.tier === "single" ? "Researcher-rater verdict" : "Manager verdict"}</h3>
          <span className={`stamp ${manager ? "ok" : "untold"}`}>{manager ? "logged" : "not logged"}</span>
        </div>
        {manager ? (
          <>
            <div className="call-class">
              <span className="legend-swatch" style={{ background: classMeta(manager.cls).color }} />
              {classMeta(manager.cls).label}
            </div>
            <div className="confidence">
              <span className="tiny">confidence</span>
              <div className="confidence-track">
                <div
                  className="confidence-fill"
                  style={{ width: `${Math.max(0, Math.min(1, manager.confidence)) * 100}%` }}
                />
              </div>
              <span className="num">{fmtPct(manager.confidence * 100, 1)}</span>
            </div>
            <p className="tiny">
              Setup {manager.setupScore}/5 · {manager.credits ?? "unavailable"} credit(s) · {fmtDateTime(manager.ev.ts)}
            </p>
            <p className="call-reason">{manager.reason}</p>
          </>
        ) : (
          <p className="tiny">
            This name used the {record.tier} tier. No debate-tier manager call is logged, and the
            bull/bear transcript is not in the event contract.
          </p>
        )}
      </div>
      <div className="call-card">
        <div className="call-head">
          <h3>Quick classifier</h3>
          <span className={`stamp ${quick ? "ok" : "untold"}`}>{quick ? "logged" : "not logged"}</span>
        </div>
        {quick ? (
          <>
            <div className="call-class">
              <span className="legend-swatch" style={{ background: classMeta(quick.cls).color }} />
              {classMeta(quick.cls).label}
            </div>
            <div className="confidence">
              <span className="tiny">confidence</span>
              <div className="confidence-track">
                <div
                  className="confidence-fill"
                  style={{ width: `${Math.max(0, Math.min(1, quick.confidence)) * 100}%` }}
                />
              </div>
              <span className="num">{fmtPct(quick.confidence * 100, 1)}</span>
            </div>
            <p className="tiny">
              Setup {quick.setupScore}/5 · {quick.credits ?? "unavailable"} credit(s) · {fmtDateTime(quick.ev.ts)}
            </p>
            <p className="call-reason">{quick.reason}</p>
          </>
        ) : (
          <p className="tiny">
            No quick-tier call is logged for this name. The primary call uses the {record.tier} tier.
          </p>
        )}
      </div>
    </div>
  );
}

export function DebateRoom({ state }: { state: DeskState }) {
  const records = useMemo(() => debateRecords(state), [state]);
  const [selected, setSelected] = useState<string | null>(null);
  const fallback = defaultDebateId(records);
  const active = records.find((record) => record.id === selected) ?? records.find((record) => record.id === fallback) ?? null;

  if (!active) {
    return (
      <>
        <div className="view-head">
          <div>
            <h1>Debate room</h1>
            <p className="view-sub">No rating is logged in these sessions, so no debate room can be built.</p>
          </div>
        </div>
      </>
    );
  }

  const meta = classMeta(active.rating.cls);

  return (
    <>
      <div className="view-head">
        <div>
          <h1>Debate room</h1>
          <p className="view-sub">
            What was known before the call, the two sides, the verdict and the process record. The
            outcome appears only after the horizon and is not in the event contract yet.
          </p>
        </div>
        <div className="view-status">
          <span className="stamp untold">outcome not logged</span>
          <span>
            {active.date} · {active.ticker} · {active.tier}
          </span>
        </div>
      </div>

      <div className="debate-bar">
        <label htmlFor="debate-select">Decision</label>
        <select
          id="debate-select"
          value={active.id}
          onChange={(event) => setSelected(event.target.value)}
        >
          {records.map((record) => (
            <option key={record.id} value={record.id}>
              {record.date} · {record.ticker} · {record.tier} · {classMeta(record.rating.cls).label}
            </option>
          ))}
        </select>
        <span className="tiny">
          {records.length} rating{records.length === 1 ? "" : "s"} · horizon {active.horizonSessions} session
          {active.horizonSessions === 1 ? "" : "s"} · season ends {finalDayLabel()}
        </span>
      </div>

      <div className="debate-grid">
        <Panel
          className="span-7"
          title="Analyst facts"
          question="What was logged before the call; the news cutoff is the yellow line"
          id="panel-analyst-facts"
        >
          <div className="callout quick-facts">
            <div className="fact-row">
              <span className="fact-label">Ticker</span>
              <span className="mono-strong">{active.ticker}</span>
            </div>
            <div className="fact-row">
              <span className="fact-label">Class</span>
              <span>
                <span className="legend-swatch" style={{ background: meta.color }} />
                {meta.label}
              </span>
            </div>
            <div className="fact-row">
              <span className="fact-label">Screen</span>
              <span>
                z {active.screen?.candidate.z.toFixed(2) ?? "—"} · RVOL{" "}
                {active.screen?.candidate.rvol.toFixed(2) ?? "—"} · move{" "}
                {active.screen?.candidate.movePct.toFixed(2) ?? "—"}%
              </span>
            </div>
            <div className="fact-row">
              <span className="fact-label">Evidence</span>
              <span>
                {active.evidenceCount > 0
                  ? `${active.evidenceCount} item(s)`
                  : "0 items — no analyst evidence array is in these logs"}
              </span>
            </div>
            <div className="fact-row">
              <span className="fact-label">Reason</span>
              <span>{active.rating.reason}</span>
            </div>
          </div>
          <ol className="debate-timeline">
            {active.timeline.map((item, index) => (
              <li
                key={`${item.ts}-${item.kind}-${index}`}
                className={`timeline-item ${item.cutoff ? "cutoff" : ""}`}
              >
                <span className="timeline-time">{fmtDateTime(item.ts)}</span>
                <span className="timeline-kind">{item.kind}</span>
                <span className="timeline-title">{item.title}</span>
                <span className="timeline-detail">{item.detail}</span>
              </li>
            ))}
          </ol>
          <p className="tiny">
            The yellow cutoff row is the news cutoff; no evidence published after it may inform the
            call. Bull and bear transcripts are not event types, so they cannot appear on this
            timeline.
          </p>
        </Panel>

        <Panel
          className="span-5"
          title="Bull vs bear"
          question="The two sides, side by side"
          id="panel-bull-bear"
        >
          <div className="stance-pair">
            <div className="stance bull">
              <div className="stance-head">
                <h3>Bull case</h3>
                <span className="stamp untold">not logged</span>
              </div>
              <p className="tiny">Not logged yet; the next agent release records it</p>
            </div>
            <div className="stance bear">
              <div className="stance-head">
                <h3>Bear case</h3>
                <span className="stamp untold">not logged</span>
              </div>
              <p className="tiny">Not logged yet; the next agent release records it</p>
            </div>
          </div>
          <div className="agreement-box">
            <div className="agreement-num">
              {active.agreement.count} / {active.agreement.comparable}
            </div>
            <div>
              <div className="tiny">Manager and quick calls in agreement</div>
              <p className="tiny">{active.agreement.note}</p>
            </div>
          </div>
          <div className="callout warn">
            <strong>What would prove me wrong</strong>
            <p className="tiny">{active.wrong}</p>
          </div>
        </Panel>

        <Panel
          className="span-12"
          title="Verdicts"
          question="Manager, quick classifier and the code risk verdict"
          id="panel-verdicts"
        >
          <CallBlock record={active} />
          <div className="risk-call">
            <span className="tiny">Code risk verdict</span>
            {active.riskVerdict ? (
              <>
                <span className={`stamp ${active.riskVerdict.verdict === "approve" ? "ok" : active.riskVerdict.verdict === "veto" ? "bad" : "untold"}`}>
                  {active.riskVerdict.verdict}
                </span>
                <span className="tiny">
                  {active.riskVerdict.firedRule
                    ? `fired ${active.riskVerdict.firedRule}`
                    : "no rule fired"}{" "}
                  · qty after {active.riskVerdict.qtyAfter} · rules{" "}
                  {active.riskVerdict.rules.join(", ")}
                </span>
              </>
            ) : (
              <span className="stamp untold">not logged</span>
            )}
          </div>
        </Panel>

        <Panel
          className="span-12"
          title="After the horizon"
          question={`Outcome at ${active.horizonSessions} session(s), then the process checklist`}
          id="panel-outcome"
        >
          <div className="outcome-strip">
            <div>
              <span>Outcome</span>
              <strong>{active.outcome}</strong>
            </div>
            <div>
              <span>Grading horizon</span>
              <strong>
                {active.horizonSessions} session{active.horizonSessions === 1 ? "" : "s"}
              </strong>
            </div>
            <div>
              <span>Season end</span>
              <strong>{finalDayLabel()}</strong>
            </div>
            <div>
              <span>Graded calls in corpus</span>
              <strong>0</strong>
            </div>
          </div>
          <p className="tiny">
            The event contract has no outcome or grading event, so the post-horizon result is not
            inferred from prices. The checklist shows exactly which process fields are logged and
            which are missing.
          </p>
          <CheckList checks={active.checklist} />
          {active.reflection ? (
            <div className="reflection">
              <span className="reflection-prompt">{active.reflection.prompt}</span>
              <p>{active.reflection.text}</p>
              <span className="tiny">{fmtDateTime(active.reflection.ev.ts)}</span>
            </div>
          ) : (
            <p className="tiny">No reflection note is logged for this session.</p>
          )}
        </Panel>
      </div>
    </>
  );
}
