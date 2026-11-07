import { useEffect, useId, useState } from "react";
import { AnimatePresence, motion, useMotionValue, useSpring } from "motion/react";

export const ARROW = "M2.7 4.6 Q2 2 4.6 2.7 L20 8.2 Q22.6 9.3 20.3 10.9 Q14.6 14.6 10.9 20.3 Q9.3 22.6 8.2 20 Z";

export function RioArrow({ size = 26 }: { size?: number }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden className="rio-arrow">
      <defs>
        <linearGradient id={`${id}f`} x1="3" y1="3" x2="18" y2="19" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#ffc078" />
          <stop offset="0.5" stopColor="#ff7a1a" />
          <stop offset="1" stopColor="#d9420b" />
        </linearGradient>
      </defs>
      <path d={ARROW} fill={`url(#${id}f)`} />
    </svg>
  );
}

type Mode = "default" | "link" | "text" | "media";

const LABELS: [string, string][] = [
  ["[data-cursor-label]", ""],
  [".nav-logo", "home"],
  [".nav a", "jump"],
  [".hero .btn", "start a lesson"],
  [".tv-screen", "rio's screen"],
  [".hero-logos", "your apps"],
  [".toggle-row", "switch billing"],
  [".plan .btn, .plan-dark .btn", "pick this plan"],
  [".plan, .plan-dark", "compare plans"],
  [".rf", "feature"],
  [".footer input", "your email"],
  [".footer a", "open"],
];

function labelFor(t: Element | null): string {
  if (!t) return "you";
  for (const [sel, text] of LABELS) {
    const el = t.closest(sel);
    if (el) return text || el.getAttribute("data-cursor-label") || "you";
  }
  return "you";
}

/** Rio ghost cursor: follows the pointer with a spring and reacts to what is hovered. */
export function GhostCursor() {
  const x = useMotionValue(-100);
  const y = useMotionValue(-100);
  const sx = useSpring(x, { stiffness: 900, damping: 50, mass: 0.4 });
  const sy = useSpring(y, { stiffness: 900, damping: 50, mass: 0.4 });
  const hx = useSpring(x, { stiffness: 180, damping: 22 });
  const hy = useSpring(y, { stiffness: 180, damping: 22 });
  const [mode, setMode] = useState<Mode>("default");
  const [down, setDown] = useState(false);
  const [on, setOn] = useState(false);
  const [label, setLabel] = useState("you");

  useEffect(() => {
    if (window.matchMedia("(pointer: coarse)").matches) return;
    setOn(true);
    document.documentElement.classList.add("has-ghost");
    const move = (e: PointerEvent) => {
      x.set(e.clientX);
      y.set(e.clientY);
      const t = e.target as HTMLElement;
      setLabel(labelFor(t));
      if (t.closest("a, button, .cap, .step, .faq-item, .work-card, .member, input")) setMode(t.closest("input") ? "text" : "link");
      else if (t.closest("img, video, .t-card")) setMode("media");
      else if (t.closest("h1, h2, h3, h4, p")) setMode("text");
      else setMode("default");
    };
    const d = () => setDown(true);
    const u = () => setDown(false);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerdown", d);
    window.addEventListener("pointerup", u);
    return () => {
      document.documentElement.classList.remove("has-ghost");
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerdown", d);
      window.removeEventListener("pointerup", u);
    };
  }, [x, y]);

  if (!on) return null;
  const halo = { default: 34, link: 64, text: 10, media: 88 }[mode];
  return (
    <>
      <motion.div className={`ghost-halo ghost-${mode}`} style={{ x: hx, y: hy }} animate={{ width: halo, height: halo, scale: down ? 0.8 : 1 }} transition={{ type: "spring", stiffness: 300, damping: 24 }}>
      </motion.div>
      <motion.div className="ghost-arrow" style={{ x: sx, y: sy }} animate={{ scale: down ? 0.85 : mode === "link" ? 1.15 : 1, rotate: mode === "link" ? -8 : 0 }} transition={{ type: "spring", stiffness: 500, damping: 28 }}>
        <RioArrow />
        <AnimatePresence mode="wait">
          <motion.span
            key={label}
            className="ghost-tag"
            initial={{ opacity: 0, y: 5, filter: "blur(4px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -5, filter: "blur(4px)" }}
            transition={{ duration: 0.16, ease: "easeOut" }}
          >
            {label}
          </motion.span>
        </AnimatePresence>
      </motion.div>
    </>
  );
}
