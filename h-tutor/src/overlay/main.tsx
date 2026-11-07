import React, { useEffect, useRef, useState } from "react";
import ReactDOM from "react-dom/client";
import { listen } from "@tauri-apps/api/event";
import { MotionConfig, motion, useMotionTemplate, useSpring, useTransform, useVelocity } from "motion/react";
import "@fontsource-variable/geist";
import "./overlay.css";

/** `rect`: the real UI element under the point (accessibility), when known. */
type Pointer = { x: number; y: number; label: string; rect: [number, number, number, number] | null };
type Mode = "hidden" | "thinking" | "shown" | "hit";

/** The label is only a reminder: it fades out after a few seconds. */
const LABEL_MS = 4000;
const MOVE = { stiffness: 260, damping: 30, mass: 0.8 };
const TRAIL = { stiffness: 140, damping: 24, mass: 0.8 };

/** Rounded triangle pointing up-left, the back edge curved in. Tip at (2, 2). */
const ARROW = "M2.7 4.6 Q2 2 4.6 2.7 L20 8.2 Q22.6 9.3 20.3 10.9 Q14.6 14.6 10.9 20.3 Q9.3 22.6 8.2 20 Z";

function Arrow({ id }: { id: string }) {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" aria-hidden>
      <defs>
        <linearGradient id={`${id}-fill`} x1="3" y1="3" x2="18" y2="19" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="var(--g1)" />
          <stop offset="0.5" stopColor="var(--g2)" />
          <stop offset="1" stopColor="var(--g3)" />
        </linearGradient>
        {/* Fine grey grain, kept inside the shape. */}
        <filter id={`${id}-grain`} x="0" y="0" width="100%" height="100%">
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7" stitchTiles="stitch" />
          <feColorMatrix type="saturate" values="0" />
          <feComposite operator="in" in2="SourceGraphic" />
        </filter>
      </defs>
      <path d={ARROW} fill={`url(#${id}-fill)`} />
      <path d={ARROW} fill="white" filter={`url(#${id}-grain)`} className="ghost__grain" />
    </svg>
  );
}

function Overlay() {
  const [mode, setMode] = useState<Mode>("hidden");
  const [ptr, setPtr] = useState<Pointer | null>(null);
  const [showLabel, setShowLabel] = useState(false);
  const placed = useRef(false);

  const x = useSpring(0, MOVE);
  const y = useSpring(0, MOVE);
  const tx = useSpring(0, TRAIL);
  const ty = useSpring(0, TRAIL);
  const vx = useVelocity(x);
  const vy = useVelocity(y);
  const speed = useTransform(() => Math.hypot(vx.get(), vy.get()));
  const blur = useTransform(speed, [0, 2500], [0, 2.2], { clamp: true });
  const filter = useMotionTemplate`blur(${blur}px)`;
  const trailOpacity = useTransform(speed, [80, 1600], [0, 0.55], { clamp: true });
  const trailFilter = useMotionTemplate`blur(${useTransform(speed, [0, 2500], [2, 7], { clamp: true })}px)`;

  useEffect(() => {
    let labelTimer: number | undefined;
    const offs = [
      listen<Pointer>("pointer:show", (e) => {
        const p = e.payload;
        // First appearance lands in place (it fades in); later ones glide.
        const move = placed.current ? "set" : "jump";
        placed.current = true;
        x[move](p.x);
        y[move](p.y);
        tx[move](p.x);
        ty[move](p.y);
        setPtr(p);
        setMode("shown");
        setShowLabel(true);
        clearTimeout(labelTimer);
        labelTimer = window.setTimeout(() => setShowLabel(false), LABEL_MS);
      }),
      listen("pointer:thinking", () => setMode((m) => (m === "shown" ? "thinking" : m))),
      listen("pointer:hit", () => setMode("hit")),
      listen("pointer:hide", () => setMode((m) => (m === "hit" ? m : "hidden"))),
    ];
    return () => {
      clearTimeout(labelTimer);
      offs.forEach((p) => p.then((off) => off()));
    };
  }, [x, y, tx, ty]);

  // After the success flash, fade out.
  useEffect(() => {
    if (mode !== "hit") return;
    const t = window.setTimeout(() => setMode("hidden"), 650);
    return () => clearTimeout(t);
  }, [mode]);

  if (!ptr) return null;

  const flipX = ptr.x > window.innerWidth - 240;
  const flipY = ptr.y > window.innerHeight - 60;
  const opacity = mode === "hidden" ? 0 : mode === "thinking" ? 0.35 : 1;
  const r = ptr.rect;

  return (
    <MotionConfig reducedMotion="user">
      {r && (
        <motion.div
          className={`ghost-box ghost-box--${mode}`}
          initial={false}
          animate={{
            x: r[0] - 5,
            y: r[1] - 5,
            width: r[2] + 10,
            height: r[3] + 10,
            opacity: mode === "shown" || mode === "hit" ? 1 : 0,
            scale: mode === "hit" ? 1.06 : 1,
          }}
          transition={{ type: "spring", ...MOVE }}
        />
      )}

      <motion.div className="ghost ghost--trail" style={{ x: tx, y: ty, opacity: mode === "shown" ? trailOpacity : 0, filter: trailFilter }}>
        <Arrow id="g-trail" />
      </motion.div>

      <motion.div className={`ghost ghost--${mode}`} style={{ x, y }} animate={{ opacity }} transition={{ duration: 0.2 }}>
        <motion.span
          className="ghost__halo"
          animate={mode === "hit" ? { scale: [0.8, 2.4], opacity: [1, 0] } : { scale: 1, opacity: mode === "shown" ? 1 : 0 }}
          transition={mode === "hit" ? { duration: 0.6, ease: [0.23, 1, 0.32, 1] } : { duration: 0.2 }}
        />
        <motion.div
          className="ghost__cursor"
          style={{ filter }}
          animate={mode === "hit" ? { scale: [1, 0.82, 1.12, 1] } : { scale: 1 }}
          transition={{ duration: 0.45, ease: [0.23, 1, 0.32, 1] }}
        >
          <Arrow id="g-main" />
        </motion.div>
        {ptr.label && (
          <motion.div
            className={`ghost__label ${flipX ? "is-left" : ""} ${flipY ? "is-up" : ""}`}
            initial={false}
            animate={
              showLabel && mode === "shown"
                ? { opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }
                : { opacity: 0, y: -4, scale: 0.96, filter: "blur(4px)" }
            }
            transition={{ duration: 0.25, ease: [0.23, 1, 0.32, 1] }}
          >
            {ptr.label}
          </motion.div>
        )}
      </motion.div>
    </MotionConfig>
  );
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <Overlay />
  </React.StrictMode>,
);
