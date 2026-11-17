export type ViewKey = "mission" | "risk" | "radar" | "truth" | "debate";

export const VIEWS: { key: ViewKey; label: string; short: string }[] = [
  { key: "mission", label: "Mission control", short: "Mission" },
  { key: "risk", label: "Risk desk wall", short: "Risk" },
  { key: "radar", label: "Mover radar", short: "Radar" },
  { key: "truth", label: "Truth table", short: "Truth" },
  { key: "debate", label: "Debate room", short: "Debate" },
];

export function SideNav({ view }: { view: ViewKey }) {
  return (
    <aside className="sidebar">
      <p className="nav-label">Views</p>
      <nav aria-label="Views">
        <ul className="side-nav">
          {VIEWS.map((item) => (
            <li key={item.key}>
              <a
                href={`#${item.key}`}
                className={view === item.key ? "nav-button active" : "nav-button"}
                aria-current={view === item.key ? "page" : undefined}
              >
                <span className="nav-mark" aria-hidden="true" />
                {item.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <div className="side-note">
        <p className="nav-label">Build</p>
        <p>
          Stage 2: all five views are built from the static fixture logs. Outcome grading, bull/bear
          transcripts and the quick shadow book are not logged, so those cells say so. Stage 3 is not
          built.
        </p>
      </div>
    </aside>
  );
}

export function BottomTabs({ view }: { view: ViewKey }) {
  return (
    <nav className="bottom-tabs" aria-label="Views">
      {VIEWS.map((item) => (
        <a
          key={item.key}
          href={`#${item.key}`}
          className={view === item.key ? "tab-button active" : "tab-button"}
          aria-current={view === item.key ? "page" : undefined}
        >
          <span className="nav-mark" aria-hidden="true" />
          {item.short}
        </a>
      ))}
    </nav>
  );
}
