import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { RioArrow } from "./cursor";

const STEPS: { sel: string; text: string }[] = [
  { sel: ".nav-logo", text: "This is Rio's logo" },
  { sel: ".h-hero", text: "The title: what Rio does" },
  { sel: ".hero .btn", text: "Start a live lesson here" },
  { sel: ".tv-screen", text: "Rio points, you click" },
  { sel: ".hero-logos", text: "Works on top of your apps" },
  { sel: ".toggle-row", text: "Switch monthly or annual billing" },
  { sel: ".plan-dark", text: "Team plan, for a whole team" },
  { sel: ".plan", text: "Free plan to get started" },
  { sel: ".rf", text: "What Rio does for you" },
  { sel: ".footer form, .footer input", text: "Get Rio news by email" },
  { sel: ".footer-cols", text: "All the links live here" },
];

type Spot = { x: number; y: number; text: string; key: number };

function visible(el: Element) {
  const r = el.getBoundingClientRect();
  const cx = Math.min(Math.max(r.left + r.width / 2, 1), innerWidth - 1);
  const cy = Math.min(Math.max(r.top + r.height / 2, 1), innerHeight - 1);
  if (r.bottom < 80 || r.top > innerHeight - 80 || r.width === 0) return false;
  const hit = document.elementFromPoint(cx, cy);
  return !!hit && (el === hit || el.contains(hit) || hit.contains(el));
}

function spotFor(i: number): Spot | null {
  const el = document.querySelector(STEPS[i].sel);
  if (!el || !visible(el)) return null;
  const r = el.getBoundingClientRect();
  const x = Math.min(r.left + Math.min(r.width * 0.75, r.width - 12), innerWidth - 240);
  const y = Math.min(Math.max(r.top + Math.min(r.height * 0.6, r.height - 8), 90), innerHeight - 60);
  return { x, y, text: STEPS[i].text, key: i };
}

/** Rio guide cursor: tours the visible parts of the page as you scroll, like the app's ghost cursor. */
export function Tour() {
  const idx = useRef(0);
  const [spot, setSpot] = useState<Spot | null>(null);

  useEffect(() => {
    const pick = (advance: boolean) => {
      const n = STEPS.length;
      for (let k = advance ? 1 : 0; k <= n; k++) {
        const i = (idx.current + k) % n;
        const s = spotFor(i);
        if (s) {
          idx.current = i;
          setSpot(s);
          return;
        }
      }
      setSpot(null);
    };
    pick(false);
    const timer = window.setInterval(() => pick(true), 2600);
    let raf = 0;
    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => pick(false));
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      clearInterval(timer);
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  return (
    <AnimatePresence>
      {spot && (
        <motion.div
          className="tour"
          initial={{ opacity: 0, x: spot.x, y: spot.y, scale: 0.6 }}
          animate={{ opacity: 1, x: spot.x, y: spot.y, scale: 1 }}
          exit={{ opacity: 0, scale: 0.6 }}
          transition={{ type: "spring", stiffness: 120, damping: 18, mass: 0.9 }}
          aria-hidden
        >
          <RioArrow size={28} />
          <AnimatePresence mode="wait">
            <motion.span
              key={spot.key}
              className="tour-bubble"
              initial={{ opacity: 0, y: 6, filter: "blur(4px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              exit={{ opacity: 0, y: -4, filter: "blur(4px)" }}
              transition={{ duration: 0.35, delay: 0.25 }}
            >
              {spot.text}
            </motion.span>
          </AnimatePresence>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
