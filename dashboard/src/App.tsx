import { useCallback, useEffect, useMemo, useState } from "react";
import { loadCorpus, type Corpus } from "./data/load";
import { stateAt } from "./data/state";
import { verifyLog, type FileVerifyResult } from "./data/verify";
import { TopBar } from "./components/TopBar";
import { BottomTabs, SideNav, VIEWS, type ViewKey } from "./components/Nav";
import { VerifyPanel, type VerifyState } from "./components/VerifyPanel";
import { TraceTooltip } from "./components/Trace";
import { DecisionDrawer } from "./components/Drawer";
import { MissionControl } from "./views/MissionControl";
import { RiskDesk } from "./views/RiskDesk";
import { MoverRadar } from "./views/MoverRadar";
import { TruthTable } from "./views/TruthTable";
import { DebateRoom } from "./views/DebateRoom";
import { TradingFloor } from "./views/TradingFloor";
import { readDuckPreference, writeDuckPreference } from "./components/Duck";

function viewFromHash(hash: string): ViewKey | null {
  if (hash === "#main") return null;
  const key = hash.startsWith("#") ? hash.slice(1) : hash;
  return VIEWS.find((item) => item.key === key)?.key ?? "mission";
}

export default function App() {
  const [corpus, setCorpus] = useState<Corpus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [view, setView] = useState<ViewKey>(() => viewFromHash(window.location.hash) ?? "mission");
  const [decisionId, setDecisionId] = useState<string | null>(null);
  const [verifyOpen, setVerifyOpen] = useState(false);
  const [verify, setVerify] = useState<VerifyState>({ busy: false, ran: false, results: [], error: null });
  const [duckEnabled, setDuckEnabled] = useState<boolean>(readDuckPreference);

  useEffect(() => {
    const controller = new AbortController();
    loadCorpus(controller.signal)
      .then((loaded) => setCorpus(loaded))
      .catch((err: unknown) => {
        if ((err as Error)?.name === "AbortError") return;
        setLoadError((err as Error).message);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const onHashChange = () => {
      const next = viewFromHash(window.location.hash);
      if (!next) return;
      setView(next);
      setDecisionId(null);
      window.scrollTo({ top: 0, left: 0 });
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const liveSeq = corpus?.events.length ?? 0;
  const state = useMemo(() => (corpus ? stateAt(corpus.events, liveSeq) : null), [corpus, liveSeq]);
  const toggleDuck = () =>
    setDuckEnabled((current) => {
      const next = !current;
      writeDuckPreference(next);
      return next;
    });

  const runVerify = useCallback(async () => {
    if (!corpus) return;
    setVerify((current) => ({ ...current, busy: true, error: null }));
    try {
      const results: FileVerifyResult[] = await Promise.all(
        corpus.logs.map((log) => verifyLog(log.file, log.rawText)),
      );
      setVerify({ busy: false, ran: true, results, error: null });
    } catch (err) {
      setVerify({ busy: false, ran: true, results: [], error: (err as Error).message });
    }
  }, [corpus]);

  useEffect(() => {
    if (corpus && !verify.ran && !verify.busy) void runVerify();
  }, [corpus, verify.ran, verify.busy, runVerify]);

  const verifyTone: "ok" | "fail" | "unchecked" =
    verify.busy || !verify.ran
      ? "unchecked"
      : verify.error || verify.results.some((result) => !result.ok)
        ? "fail"
        : "ok";

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
    <div className="app">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <TopBar
        state={state}
        verifyOpen={verifyOpen}
        verifyBusy={verify.busy}
        verifyTone={verifyTone}
        onToggleVerify={() => {
          const opening = !verifyOpen;
          setVerifyOpen(opening);
          if (opening) void runVerify();
        }}
        duckEnabled={duckEnabled}
        onToggleDuck={toggleDuck}
        floorMode={view === "floor"}
      />

      {verifyOpen ? (
        <div className="verify-wrap">
          <VerifyPanel state={verify} onRun={runVerify} onClose={() => setVerifyOpen(false)} />
        </div>
      ) : null}

      {corpus.errors.length > 0 ? (
        <div className="load-warning" role="alert">
          <strong>Some log lines could not be loaded.</strong> {corpus.errors.join(" · ")}
        </div>
      ) : null}

      <div className="shell">
        <SideNav view={view} />
        <main id="main" className="main" tabIndex={-1}>
          {view === "mission" ? (
            <MissionControl state={state} onOpenDecision={setDecisionId} />
          ) : view === "risk" ? (
            <RiskDesk state={state} onOpenDecision={setDecisionId} />
          ) : view === "radar" ? (
            <MoverRadar state={state} onOpenDecision={setDecisionId} />
          ) : view === "truth" ? (
            <TruthTable state={state} />
          ) : view === "debate" ? (
            <DebateRoom state={state} />
          ) : (
            <TradingFloor
              state={state}
              events={corpus.events}
              duckEnabled={duckEnabled}
              onOpenDecision={setDecisionId}
            />
          )}
          <footer className="app-footer">
            <span>MooWoo Desk · Stage 2 + trading floor</span>
            <span>Static fixture logs only. No API keys, no broker calls, no additional network data.</span>
            <span>SIMULATED FUNDS</span>
          </footer>
        </main>
      </div>

      <BottomTabs view={view} />

      <DecisionDrawer
        state={state}
        decisionId={decisionId}
        onClose={() => setDecisionId(null)}
        onOpenDecision={setDecisionId}
      />
      <TraceTooltip />
    </div>
  );
}
