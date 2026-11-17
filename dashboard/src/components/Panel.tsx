import type { ReactNode } from "react";

export function Panel({
  title,
  question,
  actions,
  children,
  className = "",
  id,
}: {
  title: string;
  question?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section className={`panel ${className}`.trim()} aria-labelledby={id}>
      <header className="panel-head">
        <div>
          <h2 id={id}>{title}</h2>
          {question ? <p className="question">{question}</p> : null}
        </div>
        {actions ? <div className="panel-actions">{actions}</div> : null}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  );
}

export function SectionTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="section-title">
      <h3>{children}</h3>
      {aside}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}
