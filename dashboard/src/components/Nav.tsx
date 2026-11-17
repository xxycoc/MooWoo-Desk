export type ViewKey = "mission" | "risk";

export const VIEWS: { key: ViewKey; label: string; short: string }[] = [
  { key: "mission", label: "Mission control", short: "Mission" },
  { key: "risk", label: "Risk desk wall", short: "Risk desk" },
];

export function SideNav({ view, onSelect }: { view: ViewKey; onSelect: (view: ViewKey) => void }) {
  return (
    <aside className="sidebar">
      <p className="nav-label">Views</p>
      <nav aria-label="Views">
        <ul className="side-nav">
          {VIEWS.map((item) => (
            <li key={item.key}>
              <button
                type="button"
                className={view === item.key ? "nav-button active" : "nav-button"}
                aria-current={view === item.key ? "page" : undefined}
                onClick={() => onSelect(item.key)}
              >
                <span className="nav-mark" aria-hidden="true" />
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <div className="side-note">
        <p className="nav-label">Build</p>
        <p>
          Stage 1: shell, data layer, Mission control and Risk desk wall. Mover radar, Truth table and
          Debate room are Stage 2 and are not built here.
        </p>
      </div>
    </aside>
  );
}

export function BottomTabs({ view, onSelect }: { view: ViewKey; onSelect: (view: ViewKey) => void }) {
  return (
    <nav className="bottom-tabs" aria-label="Views">
      {VIEWS.map((item) => (
        <button
          key={item.key}
          type="button"
          className={view === item.key ? "tab-button active" : "tab-button"}
          aria-current={view === item.key ? "page" : undefined}
          onClick={() => onSelect(item.key)}
        >
          <span className="nav-mark" aria-hidden="true" />
          {item.short}
        </button>
      ))}
    </nav>
  );
}
