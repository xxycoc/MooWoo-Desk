import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

const STORAGE_KEY = "moowoo-desk-duck";
const DUCK_W = 44;
const DUCK_H = 36;
const FOLLOW_OFFSET = 24;
const IDLE_MS = 8000;
const SLEEP_MS = 4000;

type Mode = "home" | "follow" | "return";
type Facing = "left" | "right";

interface Point {
  x: number;
  y: number;
}

export function readDuckPreference(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) !== "off";
  } catch {
    return true;
  }
}

export function writeDuckPreference(enabled: boolean): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, enabled ? "on" : "off");
  } catch {
    // Storage can be unavailable; the in-memory toggle still works.
  }
}

export function DuckToggle({ enabled, onToggle }: { enabled: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      className={`duck-toggle${enabled ? " is-on" : ""}`}
      aria-pressed={enabled}
      aria-label={`Desk duck ${enabled ? "on" : "off"}`}
      onClick={onToggle}
    >
      Duck {enabled ? "on" : "off"}
    </button>
  );
}

function hasFinePointer(): boolean {
  return !window.matchMedia("(hover: none), (pointer: coarse)").matches;
}

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function Duck({
  enabled,
  verifyBusy,
  verifyTone,
}: {
  enabled: boolean;
  verifyBusy: boolean;
  verifyTone: "ok" | "fail" | "unchecked";
}) {
  const anchorRef = useRef<HTMLSpanElement | null>(null);
  const layerRef = useRef<HTMLDivElement | null>(null);
  const homeRef = useRef<Point>({ x: 0, y: 0 });
  const positionRef = useRef<Point>({ x: 0, y: 0 });
  const targetRef = useRef<Point>({ x: 0, y: 0 });
  const modeRef = useRef<Mode>("home");
  const facingRef = useRef<Facing>("right");
  const walkingRef = useRef(false);
  const enabledRef = useRef(enabled);
  const fineRef = useRef(true);
  const reducedRef = useRef(false);
  const rafRef = useRef<number | null>(null);
  const idleRef = useRef<number | null>(null);
  const sleepRef = useRef<number | null>(null);
  const lastMoveRef = useRef(0);
  const previousBusyRef = useRef(verifyBusy);
  const hoppingRef = useRef(false);
  const hopTimerRef = useRef<number | null>(null);

  const [finePointer, setFinePointer] = useState(hasFinePointer);
  const [reducedMotion, setReducedMotion] = useState(prefersReducedMotion);
  const [ready, setReady] = useState(false);
  const [walking, setWalking] = useState(false);
  const [facing, setFacing] = useState<Facing>("right");
  const [sleeping, setSleeping] = useState(false);
  const [blinking, setBlinking] = useState(false);
  const [hopping, setHopping] = useState(false);

  const paint = useCallback(() => {
    const layer = layerRef.current;
    if (!layer) return;
    const { x, y } = positionRef.current;
    layer.style.transform = `translate3d(${x}px, ${y}px, 0)`;
  }, []);

  const cancelLoop = useCallback(() => {
    if (rafRef.current != null) {
      window.cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  const clearIdle = useCallback(() => {
    if (idleRef.current != null) {
      window.clearTimeout(idleRef.current);
      idleRef.current = null;
    }
  }, []);

  const clearSleep = useCallback(() => {
    if (sleepRef.current != null) {
      window.clearTimeout(sleepRef.current);
      sleepRef.current = null;
    }
  }, []);

  const scheduleSleep = useCallback(() => {
    clearSleep();
    if (!enabledRef.current || !fineRef.current || reducedRef.current || document.hidden) return;
    if (modeRef.current !== "home") return;
    sleepRef.current = window.setTimeout(() => {
      if (modeRef.current === "home" && enabledRef.current && !reducedRef.current) {
        setSleeping(true);
        setBlinking(false);
      }
    }, SLEEP_MS);
  }, [clearSleep]);

  const ensureLoop = useCallback(() => {
    if (rafRef.current != null) return;
    if (!enabledRef.current || !fineRef.current || reducedRef.current || document.hidden) return;

    const tick = () => {
      rafRef.current = null;
      if (!enabledRef.current || !fineRef.current || reducedRef.current || document.hidden) return;

      const current = positionRef.current;
      const target = targetRef.current;
      const dx = target.x - current.x;
      const dy = target.y - current.y;
      const distance = Math.hypot(dx, dy);

      if (distance < 0.4) {
        current.x = target.x;
        current.y = target.y;
        paint();
        if (walkingRef.current) {
          walkingRef.current = false;
          setWalking(false);
        }
        if (modeRef.current === "return") {
          modeRef.current = "home";
          scheduleSleep();
        }
        return;
      }

      const easing = modeRef.current === "return" ? 0.1 : 0.16;
      current.x += dx * easing;
      current.y += dy * easing;

      if (Math.abs(dx) > 0.3) {
        const next: Facing = dx < 0 ? "left" : "right";
        if (facingRef.current !== next) {
          facingRef.current = next;
          setFacing(next);
        }
      }
      if (!walkingRef.current) {
        walkingRef.current = true;
        setWalking(true);
      }
      paint();
      rafRef.current = window.requestAnimationFrame(tick);
    };

    rafRef.current = window.requestAnimationFrame(tick);
  }, [paint, scheduleSleep]);

  const beginReturn = useCallback(() => {
    clearIdle();
    setSleeping(false);
    if (modeRef.current === "home") {
      scheduleSleep();
      return;
    }
    modeRef.current = "return";
    targetRef.current = { ...homeRef.current };
    ensureLoop();
  }, [clearIdle, ensureLoop, scheduleSleep]);

  const followPointer = useCallback(
    (clientX: number, clientY: number) => {
      if (!enabledRef.current || !fineRef.current || reducedRef.current) return;

      const margin = 6;
      let x = clientX + FOLLOW_OFFSET;
      let y = clientY + FOLLOW_OFFSET;
      if (x + DUCK_W > window.innerWidth - margin) x = clientX - DUCK_W - FOLLOW_OFFSET;
      if (y + DUCK_H > window.innerHeight - margin) y = clientY - DUCK_H - FOLLOW_OFFSET;
      x = Math.max(margin, Math.min(x, window.innerWidth - DUCK_W - margin));
      y = Math.max(margin, Math.min(y, window.innerHeight - DUCK_H - margin));

      targetRef.current = { x, y };
      modeRef.current = "follow";
      lastMoveRef.current = Date.now();
      setSleeping(false);
      setBlinking(false);
      clearSleep();
      clearIdle();
      idleRef.current = window.setTimeout(beginReturn, IDLE_MS);
      ensureLoop();
    },
    [beginReturn, clearIdle, clearSleep, ensureLoop],
  );

  const measureHome = useCallback(() => {
    const anchor = anchorRef.current;
    if (!anchor) return;
    const rect = anchor.getBoundingClientRect();
    const home = {
      x: rect.left + (rect.width - DUCK_W) / 2,
      y: rect.top + (rect.height - DUCK_H) / 2,
    };
    homeRef.current = home;
    if (modeRef.current === "home") {
      positionRef.current = { ...home };
      targetRef.current = { ...home };
      paint();
    }
    setReady(true);
  }, [paint]);

  const park = useCallback(() => {
    cancelLoop();
    clearIdle();
    clearSleep();
    modeRef.current = "home";
    positionRef.current = { ...homeRef.current };
    targetRef.current = { ...homeRef.current };
    walkingRef.current = false;
    setWalking(false);
    setSleeping(false);
    setBlinking(false);
    paint();
  }, [cancelLoop, clearIdle, clearSleep, paint]);

  useEffect(() => {
    enabledRef.current = enabled;
    if (!enabled) {
      park();
      setReady(false);
    }
  }, [enabled, park]);

  useLayoutEffect(() => {
    if (!enabled) return;
    measureHome();
    const anchor = anchorRef.current;
    const observer = anchor && typeof ResizeObserver !== "undefined" ? new ResizeObserver(measureHome) : null;
    if (anchor && observer) observer.observe(anchor);
    window.addEventListener("resize", measureHome);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", measureHome);
    };
  }, [enabled, measureHome]);

  useEffect(() => {
    const fineQuery = window.matchMedia("(hover: none), (pointer: coarse)");
    const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => {
      setFinePointer(!fineQuery.matches);
      setReducedMotion(motionQuery.matches);
    };
    update();
    fineQuery.addEventListener("change", update);
    motionQuery.addEventListener("change", update);
    return () => {
      fineQuery.removeEventListener("change", update);
      motionQuery.removeEventListener("change", update);
    };
  }, []);

  useEffect(() => {
    fineRef.current = finePointer;
    if (!finePointer) park();
  }, [finePointer, park]);

  useEffect(() => {
    reducedRef.current = reducedMotion;
    if (reducedMotion) {
      park();
      if (hopTimerRef.current != null) {
        window.clearTimeout(hopTimerRef.current);
        hopTimerRef.current = null;
      }
      hoppingRef.current = false;
      setHopping(false);
    }
  }, [reducedMotion, park]);

  useEffect(() => {
    if (!enabled || !finePointer || reducedMotion) return;
    const onMove = (event: MouseEvent) => followPointer(event.clientX, event.clientY);
    window.addEventListener("mousemove", onMove, { passive: true });
    return () => window.removeEventListener("mousemove", onMove);
  }, [enabled, finePointer, reducedMotion, followPointer]);

  useEffect(() => {
    const onVisibility = () => {
      if (document.hidden) {
        cancelLoop();
        return;
      }
      if (!enabledRef.current || !fineRef.current || reducedRef.current) return;
      if (modeRef.current === "follow" && Date.now() - lastMoveRef.current >= IDLE_MS) {
        beginReturn();
      } else if (modeRef.current !== "home") {
        ensureLoop();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [beginReturn, cancelLoop, ensureLoop]);

  useEffect(() => {
    if (!enabled || reducedMotion) return;
    let cancelled = false;
    let blinkOff: number | null = null;
    let nextBlink: number | null = null;

    const schedule = () => {
      nextBlink = window.setTimeout(
        () => {
          if (cancelled) return;
          if (modeRef.current === "home" && !sleeping && !document.hidden) {
            setBlinking(true);
            blinkOff = window.setTimeout(() => {
              if (!cancelled) setBlinking(false);
            }, 140);
          }
          schedule();
        },
        3200 + Math.random() * 3000,
      );
    };
    schedule();

    return () => {
      cancelled = true;
      if (nextBlink != null) window.clearTimeout(nextBlink);
      if (blinkOff != null) window.clearTimeout(blinkOff);
    };
  }, [enabled, reducedMotion, sleeping]);

  useEffect(() => {
    const wasBusy = previousBusyRef.current;
    previousBusyRef.current = verifyBusy;
    if (!enabled || reducedMotion) return;
    if (!wasBusy || verifyBusy || verifyTone !== "ok" || hoppingRef.current) return;

    hoppingRef.current = true;
    setHopping(true);
    if (hopTimerRef.current != null) window.clearTimeout(hopTimerRef.current);
    hopTimerRef.current = window.setTimeout(() => {
      hoppingRef.current = false;
      setHopping(false);
      hopTimerRef.current = null;
    }, 480);
  }, [enabled, reducedMotion, verifyBusy, verifyTone]);

  useEffect(
    () => () => {
      cancelLoop();
      clearIdle();
      clearSleep();
      if (hopTimerRef.current != null) window.clearTimeout(hopTimerRef.current);
    },
    [cancelLoop, clearIdle, clearSleep],
  );

  if (!enabled) return null;

  return (
    <>
      <span className="duck-anchor" ref={anchorRef} aria-hidden="true" />
      <div
        ref={layerRef}
        className={[
          "duck-layer",
          ready ? "is-ready" : "",
          walking ? "is-walking" : "",
          sleeping ? "is-sleeping" : "",
          blinking ? "is-blinking" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        aria-hidden="true"
      >
        <div className={`duck-hop${hopping ? " is-hopping" : ""}`}>
          <div className={`duck-face${facing === "left" ? " is-left" : ""}`}>
            <svg
              className="duck-svg"
              viewBox="0 0 44 36"
              width={DUCK_W}
              height={DUCK_H}
              focusable="false"
            >
              <defs>
                <filter
                  id="duck-sticker-rim"
                  x="-10%"
                  y="-10%"
                  width="120%"
                  height="120%"
                  colorInterpolationFilters="sRGB"
                >
                  <feMorphology
                    in="SourceAlpha"
                    operator="dilate"
                    radius="1"
                    result="expanded"
                  />
                  <feFlood floodColor="#e8eef6" result="rim" />
                  <feComposite in="rim" in2="expanded" operator="in" result="outline" />
                  <feMerge>
                    <feMergeNode in="outline" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>
              <g
                filter="url(#duck-sticker-rim)"
                stroke="#171512"
                strokeWidth="1.7"
                strokeLinejoin="round"
                strokeLinecap="round"
              >
                <path
                  d="M9.4 21.6 C7 19.8 4.1 19.3 2.8 20.8 C3.4 22 4.7 22.6 6.3 22.7 C5.7 23.9 6 25.1 7 25.8 C8.5 25.2 9.7 24.1 10.8 22.8 Z"
                  fill="#f2c230"
                  strokeWidth="1.5"
                />
                <path
                  d="M21.8 8.9 C18.1 7.8 12.8 7.9 9.2 9.5 C10.2 10.4 12.5 10.9 15.5 10.9 C17.9 10.9 20.2 10.5 21.8 9.7 Z"
                  fill="#1b1916"
                />
                <path
                  d="M10.8 9.7 C14 10.6 18.2 10.5 20.8 9.5"
                  fill="none"
                  stroke="#4a4438"
                  strokeWidth="0.55"
                />
                <path
                  d="M7.4 19.9 C4.2 23.1 4.5 29.2 9.1 32.4 C13.5 35.4 26.1 35.6 31.3 32.6 C35.8 30 36.4 24.7 33.4 21.2 C29.8 17.2 21.4 15.7 15.4 16.7 C12 17.3 9.3 18.4 7.4 19.9 Z"
                  fill="#f2c230"
                />
                <path
                  d="M30 4.1 C25.3 4.1 21.7 7.5 21.6 12.2 C21.5 16.9 25.1 20.7 29.9 20.8 C34.7 20.9 38.3 17.2 38.4 12.5 C38.5 7.8 34.9 4.1 30 4.1 Z"
                  fill="#f2c230"
                />
                <path
                  d="M22 8.8 C22 5 24.9 2.6 29.4 2.4 C33.9 2.2 37.3 4.2 38.3 7.6 C38.6 8.6 38.5 9.4 38 10.1 C33.1 9.1 26.2 9.1 22 10.1 Z"
                  fill="#1b1916"
                />
                <path
                  d="M22.4 9.3 C27 8.5 33 8.5 37.8 9.3 C33.1 8.6 26.4 8.6 22.4 9.3 Z"
                  fill="#0f0e0c"
                  strokeWidth="0.4"
                />
                <path
                  d="M30.5 3.1 C30.2 5.1 30.5 7.4 31.1 9.4"
                  fill="none"
                  stroke="#4a4438"
                  strokeWidth="0.65"
                />
                <path
                  d="M25.5 3.8 C25.6 5.9 26 7.8 26.6 9.3"
                  fill="none"
                  stroke="#4a4438"
                  strokeWidth="0.65"
                />
                <path d="M37.7 7 37.1 9.3" fill="none" stroke="#6a6254" strokeWidth="0.7" />
                <circle
                  cx="29.4"
                  cy="2.6"
                  r="0.55"
                  fill="#3e3930"
                  stroke="#0f0e0c"
                  strokeWidth="0.35"
                />
                <path
                  d="M23.9 13.2 C22.8 12.9 21.8 13.1 21 13.7"
                  fill="none"
                  stroke="#0d0c0b"
                  strokeWidth="1.4"
                />
                <path
                  d="M23.4 12.4 C24.8 11.9 26.2 12 27.3 12.4 L27.8 13.2 C27 14.4 26.1 15 25 15 C24 15 23.4 14.5 23.4 13.7 C23.4 13.2 23.4 12.8 23.4 12.4 Z"
                  fill="#0d0c0b"
                  strokeWidth="0.75"
                />
                <path
                  d="M26.7 12.6 27.8 12.9 27.5 13.5 26.4 13.3 Z"
                  fill="#0d0c0b"
                  strokeWidth="0.5"
                />
                <path
                  d="M27.3 12 C30.8 11.3 34.8 11.4 38.1 12 C38.5 12.1 38.7 12.5 38.7 13 C38.7 15 37 16.5 34.6 16.5 C31.9 16.5 29.6 15.2 28.1 13.2 C27.7 12.8 27.4 12.4 27.3 12 Z"
                  fill="#0d0c0b"
                  strokeWidth="0.75"
                />
                <path
                  d="M32 13.2 C32.8 12.9 33.7 12.8 34.5 12.9"
                  fill="none"
                  stroke="#f4f7fb"
                  strokeWidth="0.85"
                />
                <path
                  d="M35.3 17.4 C38.2 16.9 41.2 17.7 42.8 19.3 C42.4 20.2 41.2 20.8 39.3 20.9 C37.3 21 35.5 20.1 34.8 18.6 Z"
                  fill="#ff7a1a"
                  strokeWidth="1.5"
                />
                <path
                  d="M36.5 20.6 C38.4 20.4 40.7 20.7 41.9 21.4 C40.6 22.4 38.5 22.6 36.6 21.9 C36.1 21.6 36.1 21 36.5 20.6 Z"
                  fill="#b5470e"
                  strokeWidth="0.6"
                />
                <path
                  d="M35.6 21.6 C37.7 21.4 40.1 21.8 41.4 22.7 C40 23.9 37.5 24 35.5 23.2 C34.8 22.8 34.9 22 35.6 21.6 Z"
                  fill="#ff7a1a"
                  strokeWidth="1.4"
                />
                <path
                  d="M37.8 18.3 C39.2 18 40.5 18.4 41.5 19.1"
                  fill="none"
                  stroke="#ffb164"
                  strokeWidth="0.75"
                />
                <path
                  d="M18.4 22.2 C21.8 21.4 26.3 22.8 28.3 25.9 C29.6 27.9 28.4 30.3 25.4 30.7 C22.1 31.1 18.7 28.3 18.2 24.7 Z"
                  fill="#f2c230"
                  strokeWidth="1.45"
                />
                <path
                  d="M20.2 23.4 C22.7 22.7 25.5 23.7 27 25.7"
                  fill="none"
                  stroke="#ffe06a"
                  strokeWidth="1.05"
                />
                <path
                  d="M20.6 27.7 C22.8 27.2 24.8 27.5 26.3 28.5"
                  fill="none"
                  stroke="#d6a817"
                  strokeWidth="0.55"
                />
                <path
                  d="M9.4 23.7 C8.8 26.7 10.5 29.8 13.4 31.2"
                  fill="none"
                  stroke="#ffe06a"
                  strokeWidth="1.2"
                />
                <path
                  d="M23.8 17.6 C24.7 18.9 26.2 19.6 28 19.6"
                  fill="none"
                  stroke="#ffe06a"
                  strokeWidth="1"
                />
              </g>
            </svg>

          </div>
        </div>
        {sleeping ? <span className="duck-zzz">z</span> : null}
      </div>
    </>
  );
}
