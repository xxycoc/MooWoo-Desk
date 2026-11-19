import type { DeskState } from "../data/types";
import {
  CORE_TICKERS,
  FLOOR_AGENTS,
  FLOOR_ROLES,
  FLOOR_STATIONS,
  MASCOT_POSITION,
  SLEEVE_COLORS,
  type FloorRole,
  type FloorScene,
  type FloorStatus,
} from "../data/floor";
import { fmtUsd } from "../data/format";

const MAP_W = 36;
const MAP_H = 24;

const AGENT = "#f2c230";

interface MapBlock {
  label: string;
  x: number;
  z: number;
  w: number;
  d: number;
  kind: "room" | "platform" | "lounge";
}

const BLOCKS: MapBlock[] = [
  { label: "Research table", x: -7.2, z: -2.9, w: 3.3, d: 3.3, kind: "room" },
  { label: "Coordinator", x: 0.8, z: 4.9, w: 4.3, d: 4.3, kind: "platform" },
  { label: "Lounge", x: -14.2, z: 6.7, w: 3.4, d: 1.6, kind: "lounge" },
];

function pctX(x: number): string {
  return `${((x + MAP_W / 2) / MAP_W) * 100}%`;
}

function pctZ(z: number): string {
  return `${((z + MAP_H / 2) / MAP_H) * 100}%`;
}

function pctText(pct: number, signed: boolean): string {
  return `${signed && pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

export function FloorMap2D({
  scene,
  state,
  statuses,
  duckEnabled,
  health,
  today,
  reason,
  onOpenDecision,
  onSelectRole,
}: {
  scene: FloorScene;
  state: DeskState;
  statuses: Record<FloorRole, FloorStatus>;
  duckEnabled: boolean;
  health: { tone: "ok" | "warn" | "halt"; message: string };
  today: { pct: number; source: "reported" | "marks" } | null;
  reason: string;
  onOpenDecision: (id: string) => void;
  onSelectRole: (role: FloorRole) => void;
}) {
  const card =
    scene.card && (scene.card.kind === "rating" || scene.card.kind === "report") ? scene.card : null;
  const banner =
    scene.card && (scene.card.kind === "tier" || scene.card.kind === "halt") ? scene.card : null;
  const cardX = card?.kind === "report" ? 16 : -7.2;
  const cardZ = card?.kind === "report" ? 3.6 : -5.4;
  const isCore = (ticker: string): boolean =>
    (CORE_TICKERS as readonly string[]).includes(ticker);
  const corePositions = state.positions.filter((position) => isCore(position.ticker));
  const satellitePositions = state.positions.filter((position) => !isCore(position.ticker));

  return (
    <div
      className="floor2d"
      role="img"
      aria-label={`Two-dimensional floor map for ${scene.title}. ${scene.detail}. ${reason}`}
    >
      <div className="floor2d-room">
        <div className="floor2d-wall" aria-hidden="true" />
        <div className="floor2d-back" aria-hidden="true">
          <span className="floor2d-wall-clock">Scheduler</span>
          <span className={`floor2d-screen tone-${health.tone}`}>
            <i>Equity</i>
            <strong>{state.equity == null ? "—" : fmtUsd(state.equity, 0)}</strong>
            <em className={`floor2d-today ${today == null || today.pct >= 0 ? "up" : "down"}`}>
              {today == null ? "today —" : `${pctText(today.pct, true)} today`}
            </em>
            <small className={`floor2d-health tone-${health.tone}`}>{health.message}</small>
          </span>
          <span className="floor2d-boards">
            <span className="floor2d-board is-core">
              <i>Core</i>
              {corePositions.length === 0 ? (
                <em>flat</em>
              ) : (
                corePositions.slice(0, 5).map((position) => (
                  <button
                    key={position.ticker}
                    type="button"
                    className="floor2d-holding is-core"
                    style={{ background: SLEEVE_COLORS.core }}
                    onClick={() => {
                      if (position.decisionId) onOpenDecision(position.decisionId);
                    }}
                    disabled={!position.decisionId}
                    aria-label={`${position.ticker} core position${position.decisionId ? ". Open decision." : ""}`}
                  >
                    {position.ticker}
                  </button>
                ))
              )}
            </span>
            <span className="floor2d-board is-satellite">
              <i>Satellite</i>
              {satellitePositions.length === 0 ? (
                <em>none</em>
              ) : (
                satellitePositions.slice(0, 4).map((position) => (
                  <button
                    key={position.ticker}
                    type="button"
                    className={`floor2d-holding satellite-${position.sleeve}`}
                    style={{ background: SLEEVE_COLORS[position.sleeve] }}
                    onClick={() => {
                      if (position.decisionId) onOpenDecision(position.decisionId);
                    }}
                    disabled={!position.decisionId}
                    aria-label={`${position.ticker} ${position.sleeve} position${position.decisionId ? ". Open decision." : ""}`}
                  >
                    {position.ticker}
                  </button>
                ))
              )}
            </span>
          </span>
        </div>

        {BLOCKS.map((block) => (
          <div
            key={block.label}
            className={`floor2d-block kind-${block.kind}`}
            style={{
              left: pctX(block.x - block.w / 2),
              top: pctZ(block.z - block.d / 2),
              width: `${(block.w / MAP_W) * 100}%`,
              height: `${(block.d / MAP_H) * 100}%`,
            }}
            aria-hidden="true"
          >
            <span>{block.label}</span>
          </div>
        ))}

        <div
          className="floor2d-ticker-board"
          style={{ left: pctX(-10.8), top: pctZ(-10.2) }}
          aria-hidden="true"
        >
          {scene.screenTickers.length === 0 ? (
            <em>awaiting screen</em>
          ) : (
            scene.screenTickers.slice(0, 6).map((ticker) => (
              <b key={ticker.ticker} className={ticker.picked ? "picked" : ""}>
                {ticker.ticker}
                <i>
                  {ticker.movePct >= 0 ? "+" : ""}
                  {ticker.movePct.toFixed(1)}
                </i>
              </b>
            ))
          )}
        </div>

        <div className="floor2d-plant" style={{ left: pctX(-16.1), top: pctZ(7.2) }} aria-hidden="true" />

        {FLOOR_STATIONS.map((spec) => {
          const status = statuses[spec.role];
          return (
            <button
              key={spec.id}
              type="button"
              className={`floor2d-station kind-${spec.role} status-${status}`}
              style={{
                left: pctX(spec.x),
                top: pctZ(spec.z),
              }}
              onClick={() => onSelectRole(spec.role)}
              aria-label={`${spec.label}, ${status}. Show handled events.`}
              title={`${spec.label} · ${FLOOR_ROLES[spec.role].desk}`}
            >
              <i className={`floor-tag-dot ${status}`} aria-hidden="true" />
              <span>{spec.label}</span>
            </button>
          );
        })}

        {FLOOR_AGENTS.map((spec) => {
          const status = statuses[spec.role];
          const actor = scene.actorId === spec.id;
          return (
            <button
              key={spec.id}
              type="button"
              className={`floor2d-duck${actor ? " is-actor" : ""}${status === "working" ? " is-working" : ""}`}
              style={{
                left: pctX(spec.x),
                top: pctZ(spec.z),
                transform: `translate(-50%, -50%) scale(${spec.scale})`,
              }}
              onClick={() => onSelectRole(spec.role)}
              aria-label={`${spec.label}, ${status}. Show handled events.`}
              title={`${spec.label} · ${FLOOR_ROLES[spec.role].desk}`}
            >
              <span className="floor2d-duck-body" style={{ background: AGENT }} aria-hidden="true">
                <span className="floor2d-eye" />
                <span className="floor2d-beak" />
              </span>
              <span className={`floor2d-name status-${status}`}>
                <i className={`floor-tag-dot ${status}`} />
                {spec.label}
              </span>
            </button>
          );
        })}

        {scene.kind === "halt" ? (
          <div
            className="floor2d-alarm"
            style={{ left: pctX(11), top: pctZ(0.4) }}
            role="status"
            aria-label={`Alarm: ${scene.title}. ${scene.detail}`}
          >
            <i aria-hidden="true" />
            <span>HALT</span>
          </div>
        ) : null}

        {duckEnabled ? (
          <span
            className="floor2d-duck mascot"
            style={{
              left: pctX(MASCOT_POSITION.x),
              top: pctZ(MASCOT_POSITION.z),
              transform: "translate(-50%, -50%)",
            }}
            aria-hidden="true"
          >
            <span className="floor2d-duck-body" style={{ background: AGENT }}>
              <span className="floor2d-eye" />
              <span className="floor2d-beak" />
            </span>
            <span className="floor2d-name status-idle">
              <i className="floor-tag-dot idle" />
              Mascot
            </span>
          </span>
        ) : null}

        {scene.stamp ? (
          <div
            className={`floor2d-stamp tone-${scene.stamp.tone}`}
            style={{ left: pctX(11.7), top: pctZ(1.4) }}
          >
            <strong>{scene.stamp.label}</strong>
            <span>{scene.stamp.rule ?? "rules checked"}</span>
          </div>
        ) : null}

        {card ? (
          <button
            type="button"
            className={`floor2d-card tone-${card.tone}`}
            style={{ left: pctX(cardX), top: pctZ(cardZ) }}
            onClick={() => {
              if (scene.decisionId) onOpenDecision(scene.decisionId);
            }}
            disabled={!scene.decisionId}
            aria-label={`${card.title}. ${card.body}${scene.decisionId ? ". Open decision." : ""}`}
          >
            <strong>{card.title}</strong>
            <span>{card.body}</span>
          </button>
        ) : null}

        {banner ? (
          <div className={`floor2d-banner tone-${banner.tone}`} role="status">
            <strong>{banner.title}</strong>
            <span>{banner.body}</span>
          </div>
        ) : null}
      </div>
      <p className="floor2d-hint">{reason}</p>
    </div>
  );
}
