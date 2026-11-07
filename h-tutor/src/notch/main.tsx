import React, { useEffect, useRef, useState } from "react";
import ReactDOM from "react-dom/client";
import { listen } from "@tauri-apps/api/event";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { api, errorText, type AutopilotView } from "../panel/api";
import "@fontsource-variable/geist";
import "../panel/styles.css";
import "./styles.css";

const shapes = {
  closed: { width: 136, height: 32, borderRadius: 100 },
  expanded: { width: 480, height: 180, borderRadius: 20 },
  compact: { width: 400, height: 112, borderRadius: 16 },
  final: { width: 320, height: 124, borderRadius: 16 },
};

function Notch() {
  const [view, setView] = useState<AutopilotView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const surface = useRef<HTMLElement>(null);
  const reduced = useReducedMotion();
  const phase = !view || view.phase === "hidden" ? "closed" : view.outcome ? "final" : view.phase;

  function reportSurface() {
    const element = surface.current;
    if (!element) return;
    const { x, y, width, height } = element.getBoundingClientRect();
    const radius = parseFloat(getComputedStyle(element).borderRadius);
    if (!Number.isFinite(radius) || x < 0 || y < 0 || width <= 0 || height <= 0 || x + width > window.innerWidth || y + height > window.innerHeight) return;
    api.notchSurface({ x, y, width, height, radius }).catch(console.error);
  }

  useEffect(() => {
    let disposed = false;
    let received = false;
    const subscription = listen<AutopilotView>("autopilot:view", ({ payload }) => {
      received = true;
      if (!disposed) { setView(payload); setError(null); }
    });
    subscription.then(() => api.autopilotView()).then((snapshot) => {
      if (!disposed && !received) setView(snapshot);
    }).catch((e) => { if (!disposed) setError(errorText(e)); });
    return () => { disposed = true; subscription.then((off) => off()); };
  }, []);

  useEffect(() => { reportSurface(); }, [phase, reduced]);

  async function act(command: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try { await command(); } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  }

  return (
    <motion.section ref={surface} className={`notch notch--${phase}`} aria-live="polite" aria-label="Rio does it for you" aria-hidden={phase === "closed"}
      initial={shapes.closed}
      animate={{ ...shapes[phase], opacity: phase === "closed" ? 0 : 1 }}
      transition={reduced ? { duration: 0 } : { type: "spring", stiffness: 380, damping: 36, mass: 0.8, opacity: { duration: 0.14, delay: phase === "closed" ? 0.42 : 0 } }}
      onUpdate={reportSurface}>
      <div className="notch__brand" aria-hidden="true">
        <svg width="16" height="14" viewBox="0 0 96 84" fill="currentColor">
          <path d="M24 0H84V40L64 60V20H24V60L0 84V24Z M24 60H64L96 84H48Z" />
        </svg>
        <span>{phase === "closed" ? "RIO" : "RIO DOES IT FOR YOU"}</span>
      </div>
      <AnimatePresence initial={false}>
        {phase !== "closed" && <motion.div key={phase} className="notch__content" style={{ width: shapes[phase].width - 40 }}
          initial={{ opacity: 0, y: reduced ? 0 : 6, filter: reduced ? "none" : "blur(4px)" }}
          animate={{ opacity: 1, y: 0, filter: reduced ? "none" : "blur(0px)" }}
          exit={{ opacity: 0, y: reduced ? 0 : -4, filter: reduced ? "none" : "blur(4px)" }}
          transition={{ duration: reduced ? 0 : 0.2, ease: [0.22, 1, 0.36, 1] }}>
          {phase === "expanded" ? (
            <>
              <h1>Want me to do <span>{view?.title}</span>?</h1>
              <p className="notch__goal" title={view?.goal}>{view?.goal}</p>
              <div className="notch__actions">
                <button className="notch__secondary" disabled={busy} onClick={() => act(api.autopilotDecline)}>Not now <kbd>esc</kbd></button>
                <button className="notch__primary" disabled={busy} onClick={() => act(() => api.autopilotAccept(view!.skill_id))}>Yes</button>
              </div>
            </>
          ) : phase === "final" ? (
            <>
              <h1 className="notch__result" title={view?.message ?? undefined}>{view?.message}</h1>
              <p className="notch__status" title={view?.title}>{view?.title}</p>
            </>
          ) : (
            <>
              <div className="notch__task">
                <h1>{view?.title}</h1>
                <button className="notch__stop" disabled={busy} onClick={() => act(api.autopilotStop)}>Stop</button>
              </div>
              <p className="notch__status">Step {view?.index ?? 0}/{view?.total ?? 0} · {view?.label ?? ""}</p>
              <div className="notch__progress" role="progressbar" aria-label="Task progress" aria-valuemin={0} aria-valuemax={view?.total || 1} aria-valuenow={view?.index ?? 0}>
                <motion.span animate={{ width: `${100 * (view?.index ?? 0) / (view?.total || 1)}%` }} transition={{ duration: reduced ? 0 : 0.4, ease: [0.22, 1, 0.36, 1] }} />
              </div>
            </>
          )}
          {view?.mode === "script" && <span className="notch__badge">Script tested by Devin</span>}
          {error && <p className="notch__error" role="alert">{error}</p>}
        </motion.div>}
      </AnimatePresence>
    </motion.section>
  );
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(<React.StrictMode><Notch /></React.StrictMode>);
