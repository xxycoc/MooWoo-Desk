import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { feedUrl, loadCorpus, type Corpus } from "./data/load";
import { stateAt } from "./data/state";
import { verifyLog, type FileVerifyResult } from "./data/verify";
import { TopBar } from "./components/TopBar";
import { Tabs, viewFromHash, type ViewKey } from "./components/Nav";
import { VerifyPanel, type VerifyState } from "./components/VerifyPanel";
import { TraceTooltip } from "./components/Trace";
import { DecisionDrawer } from "./components/Drawer";
import { readDuckPreference, writeDuckPreference } from "./components/Duck";
import { Now } from "./views/Now";
import { Strategy } from "./views/Strategy";
import { TradingFloor } from "./views/TradingFloor";
import { healthStatus, lastRuns, nextScheduledRun, sgtTime } from "./data/dashboard";

export default function App() {
  const [corpus, setCorpus] = useState<Corpus | null>(null);
  const corpusVersion = useRef(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [view, setView] = useState<ViewKey>(() => viewFromHash(window.location.hash));
  const [now, setNow] = useState(() => new Date());
  const [decisionId, setDecisionId] = useState<string | null>(null);
  const [duckEnabled, setDuckEnabled] = useState(readDuckPreference);
  const closeDecision = useCallback(() => setDecisionId(null), []);
  const toggleDuck = useCallback(() => {
    setDuckEnabled((current) => {
      writeDuckPreference(!current);
      return !current;
    });
  }, []);
  const [verifyOpen, setVerifyOpen] = useState(false);
  const [verify, setVerify] = useState<VerifyState>({ busy: false, ran: false, results: [], error: null });

  useEffect(() => {
    const controller = new AbortController();
    let loading = false;
    const refresh = async () => {
      if (loading) return;
      loading = true;
      try {
        const loaded = await loadCorpus(controller.signal);
        if (controller.signal.aborted) return;
        corpusVersion.current += 1;
        setCorpus(loaded);
        setLoadError(null);
        setVerify({ busy: false, ran: false, results: [], error: null });
      } catch (err) {
        if (controller.signal.aborted) return;
        setLoadError((err as Error).message);
      } finally {
        loading = false;
      }
    };
    void refresh();
    const timer = feedUrl ? window.setInterval(() => void refresh(), 60000) : undefined;
    return () => { controller.abort(); window.clearInterval(timer); };
  }, []);

  useEffect(() => {
    const onHashChange = () => {
      if (window.location.hash === "#main") return;
      const next = viewFromHash(window.location.hash);
      if (window.location.hash !== `#${next}`) window.history.replaceState(null, "", `#${next}`);
      setView(next);
      setDecisionId(null);
      window.scrollTo({ top: 0, left: 0 });
    };
    onHashChange();
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const liveSeq = corpus?.events.length ?? 0;
  const state = useMemo(() => (corpus ? stateAt(corpus.events, liveSeq) : null), [corpus, liveSeq]);
  const runs = useMemo(() => corpus && state ? lastRuns(corpus.events, state) : [], [corpus, state]);
  const next = useMemo(() => nextScheduledRun(now), [now]);
  const health = useMemo(() => healthStatus(corpus?.events ?? [], runs, now, corpus?.desk), [corpus, runs, now]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const runVerify = useCallback(async () => {
    if (!corpus) return;
    const version = corpusVersion.current;
    setVerify((current) => ({ ...current, busy: true, error: null }));
    try {
      const results: FileVerifyResult[] = await Promise.all(
        corpus.logs.map((log) => verifyLog(log.file, log.rawText)),
      );
      if (version !== corpusVersion.current) return;
      setVerify({ busy: false, ran: true, results, error: null });
    } catch (err) {
      if (version !== corpusVersion.current) return;
      setVerify({ busy: false, ran: true, results: [], error: (err as Error).message });
    }
  }, [corpus]);

  useEffect(() => {
    if (corpus && !verify.ran && !verify.busy) void runVerify();
  }, [corpus, verify.ran, verify.busy, runVerify]);

  const verifyTone: "ok" | "fail" | "unchecked" =
    verify.busy || !verify.ran
      ? "unchecked"
      : verify.error || verify.results.some((result) => result.ok === false)
        ? "fail"
        : verify.results.some((result) => result.scrubbed) ? "unchecked" : "ok";

  if (loadError) {
    return (
      <div className="boot">
        <div className="boot-box">
          <p className="sim-badge">SIMULATED FUNDS</p>
          <h1>MooWoo Desk</h1>
          <p className="boot-error">Could not load dashboard/data/index.json: {loadError}</p>
          <p className="tiny">Run the Vite dev server from dashboard/ so /data is served.</p>
        </div>
      </div>
    );
  }

  if (!corpus || !state) {
    return (
      <div className="boot">
        <div className="boot-box">
          <p className="sim-badge">SIMULATED FUNDS</p>
          <h1>MooWoo Desk</h1>
          <p className="muted">Loading event logs and rebuilding state…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="app option-b">
      <a className="skip-link" href="#main">Skip to content</a>
      <TopBar state={state} next={next} verifyBusy={verify.busy} verifyTone={verifyTone} duckEnabled={duckEnabled} onDuckToggle={toggleDuck} />
      <section className={"health-banner tone-" + health.tone} role="status" aria-label="Desk health">
        <strong><span className="health-dot" aria-hidden="true" />{health.message}</strong>
        <span>Last run: {runs[0] ? sgtTime(runs[0].at) + " · " + runs[0].kind : "Not recorded"}</span>
        <span>Next: {sgtTime(next.at)} · {next.kind}</span>
      </section>
      <Tabs view={view} />
      <p className="feed-status"><strong>{corpus.source === "feed" ? "Public live feed" : corpus.source === "bundled-fallback" ? "Feed unavailable · bundled fallback" : "Bundled snapshot"}</strong> · Last event {sgtTime(corpus.latestEventTs)}. {feedUrl ? "Checked every 60 seconds." : "Snapshot does not update automatically."} Health reflects this feed snapshot, not a broker heartbeat.</p>
      {corpus.errors.length > 0 && <div className="load-warning" role="alert"><strong>Some log lines could not be loaded.</strong> {corpus.errors.join(" · ")}</div>}
      {corpus.events.some((event) => event.dataset === "fixture") && <p className="load-warning">Includes FICTIONAL fixtures. Combined totals are not the real ledger.</p>}
      <main id="main" className="desk-main" tabIndex={-1} aria-label={view === "now" ? "Now" : view === "strategy" ? "Strategy" : "Floor"}>
        {view === "now" ? (
          <Now state={state} events={corpus.events} runs={runs} onOpenDecision={setDecisionId} />
        ) : view === "strategy" ? (
          <Strategy state={state} events={corpus.events} onOpenDecision={setDecisionId} />
        ) : (
          <TradingFloor
            state={state}
            events={corpus.events}
            duckEnabled={duckEnabled}
            health={health}
            onOpenDecision={setDecisionId}
          />
        )}
      </main>
      <footer className="desk-footer">
        <div className="footer-row"><span>Scrubbed event data. No broker calls or API keys.</span><button type="button" aria-expanded={verifyOpen} aria-controls="footer-verify" onClick={() => { setVerifyOpen(!verifyOpen); if (!verifyOpen) void runVerify(); }}>Verify logs</button></div>
        {verifyOpen && <div id="footer-verify"><VerifyPanel state={verify} onRun={runVerify} onClose={() => setVerifyOpen(false)} /></div>}
        <p><span className="agent-label">Agents: coordinator · analyst · executor.</span> Code: screener · risk desk · watcher · auditor.</p>
      </footer>
      <DecisionDrawer state={state} runs={runs} decisionId={decisionId} onClose={closeDecision} onOpenDecision={setDecisionId} />
      <TraceTooltip />
    </div>
  );
}
