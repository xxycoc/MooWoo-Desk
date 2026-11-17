import type { FileVerifyResult } from "../data/verify";

export interface VerifyState {
  busy: boolean;
  ran: boolean;
  results: FileVerifyResult[];
  error: string | null;
}

export function VerifyPanel({
  state,
  onRun,
  onClose,
}: {
  state: VerifyState;
  onRun: () => void;
  onClose: () => void;
}) {
  return (
    <section className="verify-panel" id="verify-panel" aria-labelledby="verify-title">
      <div className="verify-head">
        <div>
          <h2 id="verify-title">Log integrity</h2>
          <p className="question">
            Recomputes canonical SHA-256 in this browser with Web Crypto, then checks each
            file&rsquo;s prevHash chain and file-local seq.
          </p>
        </div>
        <div className="verify-actions">
          <button type="button" className="button" onClick={onRun} disabled={state.busy}>
            {state.busy ? "Verifying…" : state.ran ? "Run again" : "Run verification"}
          </button>
          <button type="button" className="button ghost" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
      {state.error ? <p className="verify-error">{state.error}</p> : null}
      {!state.ran && !state.busy && !state.error ? (
        <p className="empty">Not checked yet. Run verification to test every loaded log.</p>
      ) : null}
      {state.results.length > 0 ? (
        <ul className="verify-list">
          {state.results.map((result) => (
            <li key={result.file} className={result.ok ? "verify-row ok" : "verify-row fail"}>
              <span className="verify-file">{result.file}</span>
              {result.ok ? (
                <span className="verify-result">
                  OK · {result.count} event{result.count === 1 ? "" : "s"} verified
                </span>
              ) : (
                <span className="verify-result">
                  BROKEN at seq {result.badSeq} · {result.reason} ({result.count}/{result.total}{" "}
                  verified)
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : null}
      <p className="verify-note">
        This checks integrity, not authentication: deleting a complete suffix or rebuilding the whole
        chain cannot be detected without a separately trusted terminal hash (docs/event-contract.md).
      </p>
    </section>
  );
}
