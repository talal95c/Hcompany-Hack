import { useEffect, useRef, useState } from "react";
import { mountComputer, type Computer } from "./computer";

export const DESTINATION = "https://www.google.com/";

export default function App() {
  const canvas = useRef<HTMLCanvasElement>(null);
  const computer = useRef<Computer | null>(null);
  const mounted = useRef(false);
  const [ready, setReady] = useState(false);
  const [zooming, setZooming] = useState(false);

  useEffect(() => {
    mounted.current = true;
    computer.current = mountComputer(canvas.current!, setReady);
    const move = (event: PointerEvent) => {
      if (event.pointerType === "mouse")
        computer.current?.point(event.clientX, event.clientY);
    };
    const reset = () => computer.current?.reset();
    const restore = (event: PageTransitionEvent) => {
      if (event.persisted) {
        computer.current?.cancel();
        setZooming(false);
      }
    };
    window.addEventListener("pointermove", move);
    document.documentElement.addEventListener("pointerleave", reset);
    window.addEventListener("pageshow", restore);
    return () => {
      mounted.current = false;
      computer.current?.dispose();
      computer.current = null;
      window.removeEventListener("pointermove", move);
      document.documentElement.removeEventListener("pointerleave", reset);
      window.removeEventListener("pageshow", restore);
    };
  }, []);

  function enter(event: React.MouseEvent<HTMLAnchorElement>) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
      return;
    if (zooming) {
      event.preventDefault();
      return;
    }
    if (
      computer.current?.enter(() => {
        if (mounted.current) window.location.assign(DESTINATION);
      })
    ) {
      event.preventDefault();
      setZooming(true);
    }
  }

  return (
    <main className={zooming ? "crt crt--zooming" : "crt"}>
      <canvas ref={canvas} aria-hidden="true" />
      <a
        className="computer-link"
        href={DESTINATION}
        aria-label="Cliquer sur l’ordinateur pour ouvrir Google"
        aria-busy={zooming}
        onClick={enter}
        onPointerEnter={() => computer.current?.hover(true)}
        onPointerLeave={() => computer.current?.hover(false)}
        onFocus={() => computer.current?.hover(true)}
        onBlur={() => computer.current?.hover(false)}
        onKeyDown={(event) => {
          if (event.key === " " && !event.repeat) {
            event.preventDefault();
            event.currentTarget.click();
          }
          if (event.key === "Escape") {
            computer.current?.cancel();
            setZooming(false);
          }
        }}
      >
        {!ready && (
          <>
            <img src="/crt/poster.png" alt="" draggable="false" />
            <span className="fallback-cue">Click</span>
          </>
        )}
      </a>
    </main>
  );
}
