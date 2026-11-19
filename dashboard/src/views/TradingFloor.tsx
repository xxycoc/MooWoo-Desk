import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { DeskState, LoadedEvent, SessionSummary } from "../data/types";
import { stateAt } from "../data/state";
import {
  eventsForRole,
  floorStatuses,
  FLOOR_ROLE_ORDER,
  FLOOR_ROLES,
  sceneAt,
  type FloorRole,
  type FloorStatus,
} from "../data/floor";
import { fmtDate } from "../data/format";
import { runKind, sessionResult, todayResult } from "../data/dashboard";
import { FloorMap2D } from "../components/FloorMap2D";

const Floor3D = lazy(() => import("../components/Floor3D").then((module) => ({ default: module.Floor3D })));

const EMPTY_STATUSES = Object.fromEntries(
  FLOOR_ROLE_ORDER.map((role) => [role, "idle"]),
) as Record<FloorRole, FloorStatus>;

const SPEEDS = [1, 2, 4] as const;
type Speed = (typeof SPEEDS)[number];

function supportsWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function eventTicker(ev: LoadedEvent): string | null {
  const ticker = (ev as Record<string, unknown>).ticker;
  const etf = (ev as Record<string, unknown>).etf;
  return typeof ticker === "string" && ticker ? ticker : typeof etf === "string" && etf ? etf : null;
}

function chipLabel(session: SessionSummary): string {
  return `${fmtDate(session.startTs)} · ${runKind(session.events)}`;
}

export function TradingFloor({
  state,
  events,
  duckEnabled,
  health,
  onOpenDecision,
}: {
  state: DeskState;
  events: LoadedEvent[];
  duckEnabled: boolean;
  health: { tone: "ok" | "warn" | "halt"; message: string };
  onOpenDecision: (id: string) => void;
}) {
  const latest = state.sessions[state.sessions.length - 1] ?? null;
  const [mode, setMode] = useState<"live" | "replay">("live");
  const [selected, setSelected] = useState(latest?.runId ?? "");
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<Speed>(1);
  const [selectedRole, setSelectedRole] = useState<FloorRole | null>(null);

  const [reducedMotion, setReducedMotion] = useState(() =>
    window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const [webglOk, setWebglOk] = useState(supportsWebGL);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [stageWidth, setStageWidth] = useState(0);

  const session =
    mode === "live"
      ? latest
      : state.sessions.find((candidate) => candidate.runId === selected) ?? latest;
  const sessionEvents = session?.events ?? [];
  const safeIndex =
    mode === "live" ? Math.max(0, sessionEvents.length - 1) : Math.min(index, Math.max(0, sessionEvents.length - 1));
  const event = sessionEvents[safeIndex] ?? null;

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const measure = () => setStageWidth(stage.getBoundingClientRect().width);
    measure();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const observer = new ResizeObserver(measure);
    observer.observe(stage);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (mode === "replay") {
      setIndex((current) => Math.min(current, Math.max(0, sessionEvents.length - 1)));
    }
  }, [mode, sessionEvents.length]);

  useEffect(() => {
    if (!latest) return;
    if (!state.sessions.some((candidate) => candidate.runId === selected)) setSelected(latest.runId);
  }, [latest, selected, state.sessions]);

  const eventState = useMemo(
    () => (event ? stateAt(events, event.gseq) : state),
    [events, event, state],
  );
  const scene = useMemo(
    () => (event ? sceneAt(sessionEvents, safeIndex, eventState) : null),
    [sessionEvents, safeIndex, event, eventState],
  );
  const statuses = useMemo(
    () => (scene ? floorStatuses(sessionEvents, safeIndex, scene) : EMPTY_STATUSES),
    [sessionEvents, safeIndex, scene],
  );
  const roleEvents = useMemo(
    () => (selectedRole ? eventsForRole(sessionEvents, selectedRole) : []),
    [sessionEvents, selectedRole],
  );
  const today = useMemo(
    () => (session ? sessionResult(eventState, session.runId) ?? todayResult(eventState) : todayResult(eventState)),
    [eventState, session],
  );

  useEffect(() => {
    if (!playing || !scene || mode !== "replay" || sessionEvents.length === 0) return;
    if (safeIndex >= sessionEvents.length - 1) {
      setPlaying(false);
      return;
    }
    const delay = Math.max(300, scene.durationMs / speed);
    const timer = window.setTimeout(() => {
      setIndex((current) => Math.min(current + 1, sessionEvents.length - 1));
    }, delay);
    return () => window.clearTimeout(timer);
  }, [playing, scene, mode, safeIndex, speed, sessionEvents.length]);

  const openDecision = (id: string) => {
    setPlaying(false);
    onOpenDecision(id);
  };

  const pickSession = (runId: string) => {
    setSelected(runId);
    setMode(runId === latest?.runId ? "live" : "replay");
    setIndex(0);
    setPlaying(false);
  };

  const selectRole = (role: FloorRole) => {
    setSelectedRole((current) => (current === role ? null : role));
  };

  const togglePlay = () => {
    if (!scene) return;
    if (playing) {
      setPlaying(false);
      return;
    }
    if (mode === "live") {
      if (!latest) return;
      setSelected(latest.runId);
      setMode("replay");
      setIndex(0);
      setPlaying(true);
      return;
    }
    if (safeIndex >= sessionEvents.length - 1) setIndex(0);
    setPlaying(true);
  };

  const scrub = (nextIndex: number) => {
    if (session) setSelected(session.runId);
    setMode("replay");
    setPlaying(false);
    setIndex(nextIndex);
  };

  const nextEvent = () => {
    setPlaying(false);
    setIndex((current) => Math.min(current + 1, Math.max(0, sessionEvents.length - 1)));
  };

  if (!scene) {
    return (
      <div className="empty-state">
        <h1>Trading floor</h1>
        <p className="empty">No session events are loaded, so the office has no replay.</p>
      </div>
    );
  }

  const narrow = stageWidth > 0 && stageWidth < 640;
  const use2D = reducedMotion || !webglOk || narrow;
  const fallbackReason = reducedMotion
    ? "2D still-frame map: reduced motion is on."
    : !webglOk
      ? "2D fallback: WebGL is not available in this browser."
      : "2D fallback: the floor is narrower than 640 px. Rotate for the 3D office.";

  return (
    <>
      <div className="view-head floor-head">
        <div>
          <h1>Trading floor</h1>
          <p className="view-sub">
            The session replayed as a small voxel office. Three ducks run the desk; four code
            stations light from the event log. Drag to pan and wheel or pinch to zoom. Ducks are not
            order authority.
          </p>
        </div>
        <div className="floor-head-aside">
          <div className="floor-head-badges">
            <span className={`floor-mode-badge${use2D ? " is-2d" : ""}`}>
              {use2D ? "2D fallback" : "3D office"}
            </span>
            <span className={`floor-live-badge${mode === "live" ? " is-live" : ""}`}>
              {mode === "live" ? "Live" : "Replay"}
            </span>
          </div>
          <div className="session-bar" role="group" aria-label="Selected session">
            {state.sessions.slice().reverse().map((item) => (
              <button
                key={item.runId}
                type="button"
                className={item.runId === session?.runId ? "session-chip active" : "session-chip"}
                aria-pressed={item.runId === session?.runId}
                onClick={() => pickSession(item.runId)}
              >
                {chipLabel(item)}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className={`floor-stage-wrap ${use2D ? "is-2d" : "is-3d"}`} ref={stageRef}>
        {stageWidth === 0 ? (
          <div className="floor-stage-loading">Building the office…</div>
        ) : use2D ? (
          <FloorMap2D
            scene={scene}
            state={eventState}
            statuses={statuses}
            duckEnabled={duckEnabled}
            health={health}
            today={today}
            reason={fallbackReason}
            onOpenDecision={openDecision}
            onSelectRole={selectRole}
          />
        ) : (
          <Suspense fallback={<div className="floor-stage-loading">Building the 3D office…</div>}>
            <Floor3D
              scene={scene}
              state={eventState}
              statuses={statuses}
              duckEnabled={duckEnabled}
              health={health}
              today={today}
              calm={reducedMotion}
              onOpenDecision={openDecision}
              onSelectRole={selectRole}
              onUnsupported={() => setWebglOk(false)}
            />
          </Suspense>
        )}
      </div>

      <div className="floor-transport">
        <button
          type="button"
          className="floor-play"
          onClick={togglePlay}
          aria-label={playing ? "Pause replay" : "Play session replay"}
        >
          {playing ? "Pause" : "Play"}
        </button>
        <button
          type="button"
          className={`floor-live-button${mode === "live" ? " active" : ""}`}
          aria-pressed={mode === "live"}
          onClick={() => {
            setPlaying(false);
            setMode("live");
            setIndex(0);
          }}
        >
          Live
        </button>
        <div className="floor-speed" role="group" aria-label="Playback speed">
          {SPEEDS.map((value) => (
            <button
              key={value}
              type="button"
              className={speed === value ? "floor-speed-button active" : "floor-speed-button"}
              aria-pressed={speed === value}
              onClick={() => setSpeed(value)}
            >
              {value}x
            </button>
          ))}
        </div>
        <label className="floor-range-wrap">
          <span className="floor-range-label">Event</span>
          <input
            className="floor-range"
            type="range"
            min={0}
            max={Math.max(0, sessionEvents.length - 1)}
            value={safeIndex}
            step={1}
            onChange={(changeEvent) => scrub(Number(changeEvent.target.value))}
            aria-valuetext={`Event ${safeIndex + 1} of ${sessionEvents.length}: ${scene.title}`}
          />
        </label>
        <span className="floor-count num">
          {safeIndex + 1} / {sessionEvents.length}
        </span>
        <button
          type="button"
          className="floor-next"
          onClick={nextEvent}
          disabled={mode === "live" || safeIndex >= sessionEvents.length - 1}
        >
          Next event
        </button>
      </div>

      <div className="floor-legend" aria-label="Floor legend">
        <span>
          <i className="floor-tag-dot idle" /> idle
        </span>
        <span>
          <i className="floor-tag-dot working" /> working
        </span>
        <span>
          <i className="floor-tag-dot done" /> done
        </span>
        <span>
          <i className="floor-tag-dot problem" /> problem
        </span>
        <span className="floor-legend-sep" aria-hidden="true" />
        <span>
          <i className="legend-swatch" style={{ background: "#f2c230" }} /> agents
        </span>
        <span>
          <i className="legend-swatch" style={{ background: "#c3ccdc" }} /> code
        </span>
        <span>
          <i className="legend-swatch" style={{ background: "#5b8def" }} /> core
        </span>
        <span>
          <i className="legend-swatch" style={{ background: "#a78bfa" }} /> drift
        </span>
        <span>
          <i className="legend-swatch" style={{ background: "#2dd4bf" }} /> bounce
        </span>
        <span>
          <i className="legend-swatch" style={{ background: "#ff7a1a" }} /> orders
        </span>
        <span>
          <i className="legend-swatch" style={{ background: "#f26b6b" }} /> halts / risk
        </span>
      </div>

      <div className={`floor-ticker tone-${scene.tone}`} role="status" aria-live="polite">
        <span className="floor-ticker-label">Now</span>
        <strong>{scene.title}</strong>
        <span>{scene.detail}</span>
        <span className="floor-ticker-seq num">
          seq {scene.event.seq} · {scene.event.ts.slice(11, 16)}Z
        </span>
      </div>

      {selectedRole ? (
        <section className="floor-role-log" aria-label={`${FLOOR_ROLES[selectedRole].label} events`}>
          <header>
            <div>
              <h2>{FLOOR_ROLES[selectedRole].label}</h2>
              <p>
                {FLOOR_ROLES[selectedRole].desk} · {roleEvents.length} event
                {roleEvents.length === 1 ? "" : "s"} handled in {fmtDate(session?.startTs)}
              </p>
            </div>
            <button type="button" className="floor-role-clear" onClick={() => setSelectedRole(null)}>
              Clear
            </button>
          </header>
          {roleEvents.length === 0 ? (
            <p className="empty">No events for this role in the selected session.</p>
          ) : (
            <div className="floor-role-events">
              {roleEvents.map((roleEvent) => {
                const at = sessionEvents.findIndex((candidate) => candidate.gseq === roleEvent.gseq);
                const ticker = eventTicker(roleEvent);
                return (
                  <button
                    key={`${roleEvent.file}:${roleEvent.line}`}
                    type="button"
                    className={at === safeIndex ? "floor-role-event active" : "floor-role-event"}
                    onClick={() => {
                      setPlaying(false);
                      if (session) setSelected(session.runId);
                      setMode("replay");
                      setIndex(Math.max(0, at));
                    }}
                    aria-current={at === safeIndex ? "true" : undefined}
                  >
                    <span className="num">{roleEvent.ts.slice(11, 16)}Z</span>
                    <strong>{roleEvent.type.replaceAll("_", " ")}</strong>
                    <span>{ticker ?? roleEvent.decisionId ?? "—"}</span>
                    <span className="floor-role-seq num">seq {roleEvent.seq}</span>
                  </button>
                );
              })}
            </div>
          )}
        </section>
      ) : (
        <p className="floor-role-hint">
          Click a duck, a station tag or a wall position to list the events that role handled in this
          session. Wall positions open their decision.
        </p>
      )}
    </>
  );
}
