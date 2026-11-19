export type ViewKey = "now" | "strategy";

export function viewFromHash(hash: string): ViewKey {
  return ["#strategy", "#radar", "#truth", "#debate"].includes(hash) ? "strategy" : "now";
}

export function Tabs({ view }: { view: ViewKey }) {
  return <nav className="desk-tabs" aria-label="Dashboard views">
    <a href="#now" aria-current={view === "now" ? "page" : undefined}>Now</a>
    <a href="#strategy" aria-current={view === "strategy" ? "page" : undefined}>Strategy</a>
  </nav>;
}
