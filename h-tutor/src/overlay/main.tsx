import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { listen } from "@tauri-apps/api/event";
import "./overlay.css";

/** `rect`: the real UI element under the point (accessibility), when known. */
type Pointer = { x: number; y: number; label: string; rect: [number, number, number, number] | null };
type Mode = "hidden" | "thinking" | "shown" | "hit";

/** The label is only a reminder: it fades out after a few seconds. */
const LABEL_MS = 4000;

function Overlay() {
  const [mode, setMode] = useState<Mode>("hidden");
  const [ptr, setPtr] = useState<Pointer | null>(null);
  const [showLabel, setShowLabel] = useState(false);

  useEffect(() => {
    let labelTimer: number | undefined;
    const offs = [
      listen<Pointer>("pointer:show", (e) => {
        setPtr(e.payload);
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
  }, []);

  // After the success flash, fade out.
  useEffect(() => {
    if (mode !== "hit") return;
    const t = window.setTimeout(() => setMode("hidden"), 450);
    return () => clearTimeout(t);
  }, [mode]);

  if (!ptr) return null;

  const flipX = ptr.x > window.innerWidth - 240;
  const flipY = ptr.y > window.innerHeight - 60;

  const r = ptr.rect;
  return (
    <>
    {r && (
      <div
        className={`ghost-box ghost-box--${mode}`}
        style={{ transform: `translate(${r[0] - 4}px, ${r[1] - 4}px)`, width: r[2] + 8, height: r[3] + 8 }}
      />
    )}
    <div className={`ghost ghost--${mode}`} style={{ transform: `translate(${ptr.x}px, ${ptr.y}px)` }}>
      <span className="ghost__halo" />
      <svg className="ghost__cursor" width="20" height="24" viewBox="0 0 15 18" aria-hidden>
        <path
          d="M1 1 L1 14.5 L4.6 11.2 L7.2 16.8 L9.6 15.7 L7.1 10.3 L12.2 10.3 Z"
          fill="var(--ghost)"
          stroke="white"
          strokeWidth="1.2"
          strokeLinejoin="round"
        />
      </svg>
      {ptr.label && (
        <div
          className={`ghost__label ${showLabel && mode === "shown" ? "is-on" : ""} ${flipX ? "is-left" : ""} ${flipY ? "is-up" : ""}`}
        >
          {ptr.label}
        </div>
      )}
    </div>
    </>
  );
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <Overlay />
  </React.StrictMode>,
);
