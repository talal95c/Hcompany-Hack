import { useEffect, useRef, useState } from "react";
import { mountComputer, type Computer } from "./computer";

/** Opening screen: a CRT computer; clicking it zooms into the screen and reveals the site. */
export function Intro({ onEnter, onGone }: { onEnter: () => void; onGone: () => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const computer = useRef<Computer | null>(null);
  const [ready, setReady] = useState(false);
  const [zooming, setZooming] = useState(false);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    computer.current = mountComputer(canvas.current!, setReady);
    const move = (e: PointerEvent) => {
      if (e.pointerType === "mouse") computer.current?.point(e.clientX, e.clientY);
    };
    const reset = () => computer.current?.reset();
    window.addEventListener("pointermove", move);
    document.documentElement.addEventListener("pointerleave", reset);
    document.documentElement.classList.add("intro-lock");
    return () => {
      computer.current?.dispose();
      computer.current = null;
      window.removeEventListener("pointermove", move);
      document.documentElement.removeEventListener("pointerleave", reset);
      document.documentElement.classList.remove("intro-lock");
    };
  }, []);

  const finish = () => {
    setLeaving(true);
    onEnter();
    window.setTimeout(onGone, 900);
  };

  function enter(e: React.MouseEvent<HTMLButtonElement>) {
    e.preventDefault();
    if (zooming) return;
    setZooming(true);
    if (!computer.current?.enter(finish)) finish();
  }

  return (
    <div className={`crt${zooming ? " crt--zooming" : ""}${leaving ? " crt--leaving" : ""}`}>
      <canvas ref={canvas} aria-hidden="true" />
      <button
        type="button"
        className="computer-link"
        aria-label="Enter Rio"
        aria-busy={zooming}
        onClick={enter}
        onPointerEnter={() => computer.current?.hover(true)}
        onPointerLeave={() => computer.current?.hover(false)}
        onFocus={() => computer.current?.hover(true)}
        onBlur={() => computer.current?.hover(false)}
      >
        {!ready && <img src="/crt/poster.png" alt="" draggable="false" />}
      </button>
      <div className="crt-flash" aria-hidden />
      <p className="crt-hint">Click the computer to enter Rio</p>
    </div>
  );
}
