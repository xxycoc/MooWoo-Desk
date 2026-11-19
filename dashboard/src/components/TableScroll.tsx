import { useEffect, useId, useRef, useState, type ReactNode } from "react";

export function TableScroll({ label, children }: { label: string; children: ReactNode }) {
  const holder = useRef<HTMLDivElement>(null);
  const cueId = useId();
  const [overflowing, setOverflowing] = useState(false);

  useEffect(() => {
    const element = holder.current;
    if (!element) return;
    const measure = () => setOverflowing(element.scrollWidth > element.clientWidth + 1);
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    if (element.firstElementChild) observer.observe(element.firstElementChild);
    measure();
    return () => observer.disconnect();
  }, [children]);

  return <>
    <div ref={holder} className="table-scroll" role="region" aria-label={label}
      aria-describedby={overflowing ? cueId : undefined} tabIndex={overflowing ? 0 : undefined}>
      {children}
    </div>
    {overflowing && <p id={cueId} className="table-scroll-cue">Scroll sideways for all columns.</p>}
  </>;
}
