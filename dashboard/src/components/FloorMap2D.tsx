import type { DeskState } from "../data/types";
import {
  CORE_TICKERS,
  FLOOR_DUCKS,
  FLOOR_ROLES,
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
const CODE = "#c3ccdc";

interface MapBlock {
  label: string;
  x: number;
  z: number;
  w: number;
  d: number;
  kind: "desk" | "room" | "booth" | "platform" | "lounge";
}

const BLOCKS: MapBlock[] = [
  { label: "Scheduler", x: -14.3, z: -8.1, w: 2.3, d: 1.5, kind: "desk" },
  { label: "Screener", x: -10.7, z: -8.0, w: 2.1, d: 1.4, kind: "desk" },
  { label: "Watcher", x: -15.2, z: -1.7, w: 1.0, d: 0.8, kind: "desk" },
  { label: "Research table", x: -7.2, z: -2.9, w: 2.9, d: 2.9, kind: "room" },
  { label: "Debate pit", x: 0, z: -3.1, w: 5.7, d: 2.3, kind: "room" },
  { label: "Quick kiosk", x: 5.2, z: -3.65, w: 1.9, d: 1.0, kind: "desk" },
  { label: "Trader", x: 7.9, z: -0.7, w: 2.35, d: 1.5, kind: "desk" },
  { label: "Risk booth", x: 11.0, z: 1.8, w: 3.5, d: 2.4, kind: "booth" },
  { label: "Rebalancer", x: 14.0, z: 4.2, w: 2.25, d: 1.4, kind: "desk" },
  { label: "Executor", x: 14.7, z: -7.6, w: 2.2, d: 1.3, kind: "desk" },
  { label: "Auditor", x: 16.0, z: 5.7, w: 2.7, d: 1.6, kind: "desk" },
  { label: "Coordinator", x: 0.8, z: 4.9, w: 4.3, d: 4.3, kind: "platform" },
  { label: "Lounge", x: -14.2, z: 6.7, w: 3.4, d: 1.6, kind: "lounge" },
];

function pctX(x: number): string {
  return `${((x + MAP_W / 2) / MAP_W) * 100}%`;
}

function pctZ(z: number): string {
  return `${((z + MAP_H / 2) / MAP_H) * 100}%`;
}

const NAME_SHIFT: Record<string, string> = {
  scheduler: "lift",
  bull: "lift",
  trader: "lift",
  screener: "drop",
  bear: "drop",
  risk: "drop",
};

function mapLabel(spec: (typeof FLOOR_DUCKS)[number]): string {
  if (spec.id.startsWith("analyst-")) return `A${spec.id.slice(-1)}`;
  switch (spec.role) {
    case "scheduler":
      return "Sched";
    case "screener":
      return "Screen";
    case "manager":
      return "Mgr";
    case "rebalancer":
      return "Rebal";
    case "executor":
      return "Exec";
    case "watcher":
      return "Watch";
    case "auditor":
      return "Audit";
    case "coordinator":
      return "Coord";
    default:
      return FLOOR_ROLES[spec.role].short;
  }
}

export function FloorMap2D({
  scene,
  state,
  statuses,
  duckEnabled,
  reason,
  onOpenDecision,
  onSelectRole,
}: {
  scene: FloorScene;
  state: DeskState;
  statuses: Record<FloorRole, FloorStatus>;
  duckEnabled: boolean;
  reason: string;
  onOpenDecision: (id: string) => void;
  onSelectRole: (role: FloorRole) => void;
}) {
  const card =
    scene.card &&
    scene.card.kind !== "drill" &&
    scene.card.kind !== "tier" &&
    scene.card.kind !== "halt" &&
    scene.card.kind !== "rule"
      ? scene.card
      : null;
  const banner =
    scene.card &&
    (scene.card.kind === "drill" ||
      scene.card.kind === "tier" ||
      scene.card.kind === "halt" ||
      scene.card.kind === "rule")
      ? scene.card
      : null;
  const cardX =
    card?.kind === "rating" ? 2.5 : card?.kind === "report" ? 8.5 : card?.kind === "outcome" ? 8 : 0;
  const cardZ =
    card?.kind === "rating" ? -0.2 : card?.kind === "report" ? 5.4 : card?.kind === "outcome" ? -9 : 0;
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
          <span className="floor2d-screen">
            <i>Equity</i>
            <strong>{state.equity == null ? "—" : fmtUsd(state.equity, 0)}</strong>
            <em className={`tier-${state.tier}`}>{state.tier.replaceAll("_", " ")}</em>
          </span>
          <span className="floor2d-boards">
            <span className="floor2d-board is-core">
              <i>Core</i>
              {corePositions.length === 0 ? (
                <em>flat</em>
              ) : (
                corePositions.slice(0, 5).map((position) => (
                  <b key={position.ticker} style={{ background: SLEEVE_COLORS.core }}>
                    {position.ticker}
                  </b>
                ))
              )}
            </span>
            <span className="floor2d-board is-satellite">
              <i>Satellite</i>
              {satellitePositions.length === 0 ? (
                <em>none</em>
              ) : (
                satellitePositions.slice(0, 4).map((position) => (
                  <b key={position.ticker} style={{ background: SLEEVE_COLORS[position.sleeve] }}>
                    {position.ticker}
                  </b>
                ))
              )}
            </span>
          </span>
        </div>

        {BLOCKS.map((block) => (
          <div
            key={block.label}
            className={`floor2d-block kind-${block.kind}${block.label === "Debate room" ? " is-debate" : ""}`}
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
                <i>{ticker.movePct >= 0 ? "+" : ""}{ticker.movePct.toFixed(1)}</i>
              </b>
            ))
          )}
        </div>

        <div className="floor2d-door" style={{ left: pctX(15.35), top: pctZ(-8.2) }} aria-hidden="true">
          Moomoo paper
        </div>
        <div className="floor2d-cabinet" style={{ left: pctX(15.35), top: pctZ(4.7) }} aria-hidden="true">
          Files
        </div>
        <div className="floor2d-plant" style={{ left: pctX(-16.1), top: pctZ(7.2) }} aria-hidden="true" />

        {FLOOR_DUCKS.map((spec) => {
          const status = statuses[spec.role];
          const actor = scene.actorId === spec.id;
          const body = FLOOR_ROLES[spec.role].agent ? AGENT : CODE;
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
              title={spec.label}
            >
              <span className="floor2d-duck-body" style={{ background: body }} aria-hidden="true">
                <span className="floor2d-eye" />
                <span className="floor2d-beak" />
              </span>
              <span className={`floor2d-name status-${status} ${NAME_SHIFT[spec.id] ?? ""}`}>
                <i className={`floor-tag-dot ${status}`} />
                {mapLabel(spec)}
              </span>
            </button>
          );
        })}

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

        {scene.speech.map((speech) => (
          <div
            key={speech.role}
            className={`floor2d-speech ${speech.role}`}
            style={{ left: pctX(speech.role === "bull" ? -2.6 : 2.6), top: pctZ(-2.2) }}
          >
            <strong>{speech.role === "bull" ? "Bull" : "Bear"}</strong>
            <span>{speech.text}</span>
          </div>
        ))}

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
