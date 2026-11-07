import { useEffect, useState } from "react";

type Box = { label: string; x: number; y: number; w: number; h: number; kind: "box" | "text" | "btn" | "media" };

const BOXES: Box[] = [
  { label: "sheet", x: 4.5, y: 6, w: 22, h: 5, kind: "text" },
  { label: "crt monitor", x: 40, y: 36, w: 20, h: 27, kind: "box" },
  { label: "screen", x: 43.5, y: 39.5, w: 11, h: 13, kind: "media" },
  { label: "tube glow", x: 45, y: 41, w: 8, h: 10, kind: "text" },
  { label: "chassis", x: 41, y: 55, w: 18, h: 6, kind: "btn" },
  { label: "click to enter", x: 58, y: 47, w: 9, h: 5, kind: "btn" },
  { label: "hint", x: 40, y: 90, w: 20, h: 3.5, kind: "text" },
];

const DURATION = 2400;
const ease = (t: number) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);

export function Preloader({ onDone }: { onDone: () => void }) {
  const [count, setCount] = useState(0);
  const [wipe, setWipe] = useState(false);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      onDone();
      return;
    }
    let loaded = document.readyState === "complete";
    const onLoad = () => (loaded = true);
    window.addEventListener("load", onLoad);
    const start = performance.now();
    let raf = 0;
    let timer = 0;
    const tick = (now: number) => {
      const t = Math.min((now - start) / DURATION, 1);
      let v = ease(t) * 100;
      if (!loaded) v = Math.min(v, 92);
      const c = Math.min(Math.floor(v + (t >= 1 && loaded ? 1 : 0)), 100);
      setCount(c);
      if (c >= 100) {
        timer = window.setTimeout(() => {
          setWipe(true);
          timer = window.setTimeout(onDone, 900);
        }, 250);
        return;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(timer);
      window.removeEventListener("load", onLoad);
    };
  }, [onDone]);

  const last = BOXES.length - 1;
  return (
    <div className={`pl-root${wipe ? " pl-wipe" : ""}`} aria-hidden>
      <div className="pl-guide" style={{ left: "4.5%" }} />
      <div className="pl-guide" style={{ left: "95.5%" }} />
      {BOXES.map((b, i) => (
        <div
          key={i}
          className={`pl-box pl-${b.kind}${count >= 4 + (i / last) * 72 ? " on" : ""}`}
          style={{ left: `${b.x}%`, top: `${b.y}%`, width: `${b.w}%`, height: `${b.h}%` }}
        >
          {b.kind === "media" && (
            <svg className="pl-cross" preserveAspectRatio="none" viewBox="0 0 100 100">
              <path d="M0 0 L100 100 M100 0 L0 100" vectorEffect="non-scaling-stroke" />
            </svg>
          )}
          <span className="pl-chip">{b.label}</span>
        </div>
      ))}
      <span className="pl-count">{String(count).padStart(3, "0")}</span>
      <span className="pl-note" style={{ left: 18 }}>sheet 01 · rio · setting out</span>
      <span className="pl-note" style={{ right: 18 }}>issue 01 · {typeof window === "undefined" ? 0 : window.innerWidth}px viewport</span>
    </div>
  );
}
