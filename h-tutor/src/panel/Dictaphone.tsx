import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "motion/react";

const BARS = 23;
/** Voice-memo silhouette: tall in the middle, low on the edges. */
const SHAPE = Array.from({ length: BARS }, (_, i) => {
  const t = (i / (BARS - 1)) * 2 - 1;
  return 0.3 + 0.7 * Math.exp(-t * t * 2.4);
});
const noise = (i: number, tick: number) => {
  const x = Math.sin(i * 12.9898 + tick * 78.233) * 43758.5453;
  return x - Math.floor(x);
};

/** Live waveform. `level` is the mic loudness (0..1); `done` flattens it once the sentence is sent. */
export function Wave({ level, done, size }: { level: number; done: boolean; size: "sm" | "lg" }) {
  const still = useReducedMotion();
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (still || done) return;
    const id = setInterval(() => setTick((t) => t + 1), 110);
    return () => clearInterval(id);
  }, [still, done]);
  const max = size === "lg" ? 38 : 20;
  const energy = 0.22 + Math.min(1, level) * 0.78;
  return (
    <div className={`wave wave--${size}`} style={{ height: max }} aria-hidden>
      {SHAPE.map((s, i) => {
        const jitter = still ? 0.6 : 0.35 + 0.65 * noise(i, tick);
        const h = done ? 0.1 : Math.max(0.12, s * jitter * energy);
        return (
          <motion.span
            key={i}
            className="wave__bar"
            style={{ opacity: 0.35 + 0.65 * s }}
            animate={{ height: Math.round(h * max) }}
            transition={{ type: "spring", stiffness: 380, damping: 20, mass: 0.6 }}
          />
        );
      })}
    </div>
  );
}

/** Keeps the end of a long sentence on a word boundary. */
export const tail = (s: string, n: number) => (s.length <= n ? s : "… " + s.slice(-n).replace(/^\S*\s/, ""));

/** Words appear one by one as Gladia refines the partial transcript. */
export function Transcript({ text, className }: { text: string; className: string }) {
  return (
    <p className={className}>
      {text
        .split(/\s+/)
        .filter(Boolean)
        .map((w, i) => (
          <motion.span
            key={`${i}-${w}`}
            initial={{ opacity: 0, y: 4, filter: "blur(4px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            transition={{ duration: 0.28, ease: [0.23, 1, 0.32, 1] }}
          >
            {w}
          </motion.span>
        ))}
    </p>
  );
}
