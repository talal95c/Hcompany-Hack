import { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUpRight } from "lucide-react";
import geometry from "../public/computer/frames.json";

type Props = { onExit: () => void };
const SIZE = 640;
const COLUMNS = 19;
const ROWS = 3;
const CENTER = 28;

export default function ComputerEntrance({ onExit }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const stage = useRef<HTMLButtonElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const skip = useRef<HTMLButtonElement>(null);
  const target = useRef({ x: 12, y: 1 });
  const position = useRef({ x: 12, y: 1 });
  const frames = useRef(new Map<number, HTMLImageElement>());
  const entering = useRef(false);
  const animations = useRef<Animation[]>([]);
  const timeout = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [phase, setPhase] = useState("idle");
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    root.current?.focus({ preventScroll: true });
    const context = canvas.current?.getContext("2d");
    let disposed = false;
    let request = 0;
    let lastX = -1,
      lastY = -1,
      lastCount = -1;
    const pending = new Set<HTMLImageElement>();
    const activeAnimations = animations.current;
    const load = (index: number) =>
      new Promise<void>((resolve) => {
        const img = new Image();
        pending.add(img);
        img.onload = () => {
          if (!disposed) frames.current.set(index, img);
          pending.delete(img);
          resolve();
        };
        img.onerror = () => {
          pending.delete(img);
          resolve();
        };
        img.src = `/computer/frame-${Math.floor(index / COLUMNS)}-${index % COLUMNS}.webp`;
      });
    const loadAll = async () => {
      await load(CENTER);
      if (disposed) return;
      if (!frames.current.has(CENTER)) setFailed(true);
      else if (context) setReady(true);
      if (
        window.matchMedia("(pointer: coarse)").matches ||
        window.matchMedia("(prefers-reduced-motion: reduce)").matches
      )
        return;
      const queue = Array.from({ length: COLUMNS * ROWS }, (_, i) => i).filter(
        (i) => i !== CENTER,
      );
      await Promise.all(
        Array.from({ length: 4 }, async () => {
          while (queue.length && !disposed) await load(queue.shift()!);
        }),
      );
    };
    void loadAll();

    function draw() {
      if (disposed || !context) return;
      const p = position.current;
      const t = target.current;
      p.x += (t.x - p.x) * 0.095;
      p.y += (t.y - p.y) * 0.095;
      if (
        Math.abs(p.x - lastX) < 0.001 &&
        Math.abs(p.y - lastY) < 0.001 &&
        frames.current.size === lastCount
      ) {
        request = requestAnimationFrame(draw);
        return;
      }
      lastX = p.x;
      lastY = p.y;
      lastCount = frames.current.size;
      const x = Math.floor(p.x),
        y = Math.floor(p.y);
      const dx = p.x - x,
        dy = p.y - y;
      const samples = [
        [y * COLUMNS + x, (1 - dx) * (1 - dy)],
        [y * COLUMNS + Math.min(x + 1, COLUMNS - 1), dx * (1 - dy)],
        [Math.min(y + 1, ROWS - 1) * COLUMNS + x, (1 - dx) * dy],
        [
          Math.min(y + 1, ROWS - 1) * COLUMNS + Math.min(x + 1, COLUMNS - 1),
          dx * dy,
        ],
      ];
      context.clearRect(0, 0, SIZE, SIZE);
      if (
        samples.some(
          ([index, weight]) => weight > 0.001 && !frames.current.has(index),
        )
      ) {
        const nearest =
          frames.current.get(Math.round(p.y) * COLUMNS + Math.round(p.x)) ??
          frames.current.get(CENTER);
        context.globalCompositeOperation = "source-over";
        context.globalAlpha = 1;
        if (nearest) context.drawImage(nearest, 0, 0, SIZE, SIZE);
        request = requestAnimationFrame(draw);
        return;
      }
      context.globalCompositeOperation = "lighter";
      for (const [index, weight] of samples) {
        const img = frames.current.get(index) ?? frames.current.get(CENTER);
        if (img && weight > 0.001) {
          context.globalAlpha = weight;
          context.drawImage(img, 0, 0, SIZE, SIZE);
        }
      }
      context.globalAlpha = 1;
      request = requestAnimationFrame(draw);
    }
    function visibility() {
      cancelAnimationFrame(request);
      if (!document.hidden) request = requestAnimationFrame(draw);
    }
    request = requestAnimationFrame(draw);
    document.addEventListener("visibilitychange", visibility);
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const motionChanged = () => {
      if (media.matches) onExit();
    };
    media.addEventListener("change", motionChanged);
    return () => {
      disposed = true;
      cancelAnimationFrame(request);
      document.removeEventListener("visibilitychange", visibility);
      media.removeEventListener("change", motionChanged);
      for (const img of pending) {
        img.onload = null;
        img.onerror = null;
        img.src = "";
      }
      clearTimeout(timeout.current);
      for (const animation of activeAnimations) animation.cancel();
    };
  }, [onExit]);

  function enter() {
    if (entering.current) return;
    if (
      failed ||
      !frames.current.has(CENTER) ||
      !stage.current?.animate ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      onExit();
      return;
    }
    entering.current = true;
    target.current = { x: 9, y: 1 };
    setPhase("zooming");
    timeout.current = setTimeout(() => {
      if (!stage.current || !root.current) return;
      const rect = stage.current.getBoundingClientRect();
      const [topLeft, , bottomRight] = geometry.frames[CENTER].screen;
      const screen = {
        x: (topLeft[0] + bottomRight[0]) / 2,
        y: (topLeft[1] + bottomRight[1]) / 2,
        width: bottomRight[0] - topLeft[0],
        height: bottomRight[1] - topLeft[1],
      };
      const scale =
        Math.max(
          innerWidth / (rect.width * screen.width),
          innerHeight / (rect.height * screen.height),
        ) * 1.12;
      const tx = innerWidth / 2 - (rect.left + rect.width * screen.x);
      const ty = innerHeight / 2 - (rect.top + rect.height * screen.y);
      stage.current.style.transformOrigin = `${screen.x * 100}% ${screen.y * 100}%`;
      const zoom = stage.current.animate(
        [
          { transform: "translate(0, 0) scale(1)" },
          { transform: `translate(${tx}px, ${ty}px) scale(${scale})` },
        ],
        {
          duration: 1150,
          easing: "cubic-bezier(.65, 0, .16, 1)",
          fill: "forwards",
        },
      );
      const fade = root.current.animate([{ opacity: 1 }, { opacity: 0 }], {
        duration: 350,
        delay: 800,
        easing: "ease-out",
        fill: "forwards",
      });
      animations.current.push(zoom, fade);
      timeout.current = setTimeout(onExit, 1150);
    }, 200);
  }

  return (
    <div
      ref={root}
      className={`entrance entrance--${phase}`}
      role="dialog"
      tabIndex={-1}
      aria-modal="true"
      aria-labelledby="entrance-title"
      onPointerMove={(event) => {
        if (
          entering.current ||
          event.pointerType !== "mouse" ||
          window.matchMedia("(prefers-reduced-motion: reduce)").matches
        )
          return;
        target.current = {
          x: Math.max(
            0,
            Math.min(18, 9 + ((event.clientX / innerWidth) * 2 - 1) * 9),
          ),
          y: Math.max(
            0,
            Math.min(2, 1 + ((event.clientY / innerHeight) * 2 - 1)),
          ),
        };
      }}
      onKeyDown={(event) => {
        if (
          event.target === root.current &&
          (event.key === "Enter" || event.key === " ")
        ) {
          event.preventDefault();
          enter();
        }
        if (event.key === "Escape") onExit();
        if (event.key === "Tab") {
          event.preventDefault();
          (document.activeElement === stage.current
            ? skip.current
            : stage.current
          )?.focus();
        }
      }}
    >
      <header className="entrance-header entrance-meta">
        <span className="brand">
          <span className="brand-mark" aria-hidden="true">
            h
          </span>
          holo tutor<span className="brand-dot">β</span>
        </span>
        <button ref={skip} onClick={onExit} className="text-button">
          Passer l’intro <ArrowUpRight size={15} />
        </button>
      </header>
      <p className="entrance-kicker entrance-meta">
        UN NOUVEAU SAVOIR-FAIRE VOUS ATTEND
      </p>
      <button
        ref={stage}
        onClick={enter}
        className="computer-stage"
        aria-label="Entrer dans Holo Tutor"
      >
        <span className="computer-shadow" />
        {!failed && !ready && (
          <img
            src="/computer/frame-1-9.webp"
            className="computer-fallback"
            alt=""
            onError={() => setFailed(true)}
          />
        )}
        <canvas ref={canvas} width={SIZE} height={SIZE} aria-hidden="true" />
        {failed && (
          <span className="computer-error">
            Le décor n’a pas chargé.
            <br />
            Entrer dans Holo Tutor <ArrowUpRight size={22} />
          </span>
        )}
      </button>
      <div className="entrance-caption entrance-meta">
        <h1 id="entrance-title">Le prochain clic, c’est le vôtre.</h1>
        <p>
          Cliquez sur l’ordinateur pour commencer <ArrowDown size={13} />
        </p>
      </div>
      <footer className="entrance-footer entrance-meta">
        <span>APPRENDRE. ESSAYER. RECOMMENCER.</span>
        <span>Vous gardez la main.</span>
      </footer>
    </div>
  );
}
