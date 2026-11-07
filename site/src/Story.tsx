import { useEffect, useRef, useState } from "react";
import { Btn } from "./ui";
import { FEATURES, FeatIcon, PLANS } from "./sections";
import { RioArrow } from "./cursor";

const N = 120;
const SCROLL_VH = 500;
const frameSrc = (i: number) => `${import.meta.env.BASE_URL}story/f${String(i + 1).padStart(3, "0")}.webp`;
const MARKS = [
  { id: "top", at: 0 },
  { id: "features", at: 0.29 },
  { id: "pricing", at: 0.57 },
  { id: "try", at: 0.88 },
];
const STEP_MS = 1300;
const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
// [fade-in start, fully in, fully in until, faded out]
const WINDOWS: [number, number, number, number][] = [
  [-1, 0, 0.07, 0.15],
  [0.17, 0.24, 0.34, 0.41],
  [0.45, 0.52, 0.62, 0.69],
  [0.75, 0.82, 2, 3],
];

const ease = (t: number) => t * t * (3 - 2 * t);
function weight(p: number, [a, b, c, d]: [number, number, number, number]) {
  if (p <= a || p >= d) return 0;
  if (p < b) return ease((p - a) / (b - a));
  if (p > c) return ease(1 - (p - c) / (d - c));
  return 1;
}

export function Story() {
  const wrap = useRef<HTMLElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const layers = useRef<(HTMLDivElement | null)[]>([]);
  const [loaded, setLoaded] = useState(0);

  useEffect(() => {
    const cv = canvas.current!;
    const ctx = cv.getContext("2d")!;
    const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const imgs: HTMLImageElement[] = [];
    let cur = 0;
    let target = 0;
    let shown = -1;
    let raf = 0;
    let count = 0;

    let blur = 0;
    let drawnBlur = 0;
    // Zoom blur: the frame is re-stamped slightly enlarged around the centre,
    // which reads as forward camera motion.
    const draw = () => {
      let i = Math.round(cur);
      while (i > 0 && !imgs[i]?.naturalWidth) i--;
      const im = imgs[i];
      if (!im?.naturalWidth) return;
      const s = Math.max(cv.width / im.naturalWidth, cv.height / im.naturalHeight);
      const stamp = (z: number) => {
        const w = im.naturalWidth * s * z;
        const h = im.naturalHeight * s * z;
        ctx.drawImage(im, (cv.width - w) / 2, (cv.height - h) / 2, w, h);
      };
      ctx.globalAlpha = 1;
      stamp(1);
      if (blur > 0.02) {
        for (let k = 1; k <= 4; k++) {
          ctx.globalAlpha = 0.3 * blur;
          stamp(1 + blur * 0.022 * k);
        }
        ctx.globalAlpha = 1;
      }
      drawnBlur = blur;
    };
    for (let i = 0; i < N; i++) {
      const im = new Image();
      im.decoding = "async";
      im.onload = () => {
        setLoaded(++count);
        if (i <= Math.round(cur)) draw();
      };
      im.src = frameSrc(i);
      imgs.push(im);
    }
    const paintLayers = (p: number) => {
      layers.current.forEach((el, k) => {
        if (!el) return;
        const w = weight(p, WINDOWS[k]);
        const dir = p < WINDOWS[k][1] ? 1 : -1;
        el.style.opacity = String(w);
        el.style.transform = `translate3d(0, ${(1 - w) * 28 * dir}px, 0)`;
        el.style.filter = w > 0.98 ? "none" : `blur(${(1 - w) * 8}px)`;
        el.style.visibility = w < 0.02 ? "hidden" : "visible";
        el.classList.toggle("on", w > 0.6);
      });
    };
    const size = () => {
      const d = Math.min(devicePixelRatio || 1, 2);
      cv.width = innerWidth * d;
      cv.height = innerHeight * d;
      shown = -1;
      draw();
    };
    const tick = () => {
      const prev = cur;
      cur = calm ? target : cur + (target - cur) * 0.22;
      if (Math.abs(target - cur) < 0.05) cur = target;
      const speed = calm ? 0 : Math.min(Math.abs(cur - prev) / 0.6, 1);
      blur += (speed - blur) * 0.25;
      if (cur === target && blur < 0.03) blur = 0;
      if (Math.round(cur) !== shown || Math.abs(blur - drawnBlur) > 0.04 || (blur === 0 && drawnBlur)) {
        shown = Math.round(cur);
        draw();
      }
      raf = cur === target && blur === 0 && !drawnBlur ? 0 : requestAnimationFrame(tick);
    };
    const onScroll = () => {
      const r = wrap.current!.getBoundingClientRect();
      const p = Math.min(Math.max(-r.top / (r.height - innerHeight), 0), 1);
      target = p * (N - 1);
      paintLayers(p);
      if (!raf) raf = requestAnimationFrame(tick);
    };
    // One gesture = one step: the video plays to the next stop, then rests.
    let tween = 0;
    let busyUntil = 0;
    let acc = 0;
    let touchY = 0;
    const bounds = () => {
      const el = wrap.current!;
      const top = el.getBoundingClientRect().top + scrollY;
      return { top, span: el.offsetHeight - innerHeight };
    };
    const inside = () => {
      const { top, span } = bounds();
      return scrollY >= top - 2 && scrollY <= top + span + 2;
    };
    const step = (dir: 1 | -1) => {
      const { top, span } = bounds();
      const p = (scrollY - top) / span;
      const stops = MARKS.map((m) => m.at);
      const next = dir > 0 ? stops.find((s) => s > p + 0.01) : [...stops].reverse().find((s) => s < p - 0.01);
      if (next === undefined) return false;
      const from = scrollY;
      const to = top + next * span;
      const t0 = performance.now();
      const dur = calm ? 0 : STEP_MS;
      cancelAnimationFrame(tween);
      busyUntil = t0 + dur + 350;
      const run = (now: number) => {
        const k = dur ? Math.min((now - t0) / dur, 1) : 1;
        scrollTo({ top: from + (to - from) * easeInOut(k), behavior: "instant" });
        if (k < 1) tween = requestAnimationFrame(run);
      };
      tween = requestAnimationFrame(run);
      return true;
    };
    const tryStep = (dir: 1 | -1, e: Event) => {
      if (!inside()) return;
      if (performance.now() < busyUntil) return e.preventDefault();
      if (step(dir)) e.preventDefault();
    };
    // A new step needs a fresh gesture: trackpad inertia keeps firing wheel
    // events, so wait for a quiet gap (after the step ends) before re-arming.
    let lastWheel = 0;
    let armed = true;
    const onWheel = (e: WheelEvent) => {
      if (!inside() || e.ctrlKey) return;
      const now = performance.now();
      if (now - Math.max(lastWheel, busyUntil) > 400) armed = true;
      lastWheel = now;
      if (!armed || now < busyUntil) {
        acc = 0;
        return e.preventDefault();
      }
      acc += e.deltaY;
      if (Math.abs(acc) < 24) return e.preventDefault();
      const dir = acc > 0 ? 1 : -1;
      acc = 0;
      armed = false;
      tryStep(dir, e);
    };
    const onTouchStart = (e: TouchEvent) => {
      touchY = e.touches[0].clientY;
    };
    const onTouchMove = (e: TouchEvent) => {
      const dy = touchY - e.touches[0].clientY;
      if (Math.abs(dy) < 30) {
        if (inside() && performance.now() < busyUntil) e.preventDefault();
        return;
      }
      touchY = e.touches[0].clientY;
      tryStep(dy > 0 ? 1 : -1, e);
    };
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest?.("input, textarea")) return;
      const down = ["ArrowDown", "PageDown", " "].includes(e.key);
      const up = ["ArrowUp", "PageUp"].includes(e.key);
      if (down || up) tryStep(down ? 1 : -1, e);
    };

    size();
    onScroll();
    cur = target;
    addEventListener("resize", size);
    addEventListener("scroll", onScroll, { passive: true });
    addEventListener("wheel", onWheel, { passive: false });
    addEventListener("touchstart", onTouchStart, { passive: true });
    addEventListener("touchmove", onTouchMove, { passive: false });
    addEventListener("keydown", onKey);
    return () => {
      cancelAnimationFrame(raf);
      cancelAnimationFrame(tween);
      removeEventListener("resize", size);
      removeEventListener("scroll", onScroll);
      removeEventListener("wheel", onWheel);
      removeEventListener("touchstart", onTouchStart);
      removeEventListener("touchmove", onTouchMove);
      removeEventListener("keydown", onKey);
    };
  }, []);

  const layer = (k: number) => (el: HTMLDivElement | null) => {
    layers.current[k] = el;
  };
  return (
    <section className="flythru" ref={wrap} style={{ height: `${SCROLL_VH + 100}vh` }}>
      {MARKS.map((m) => (
        <div key={m.id} id={m.id} className="story-mark" style={{ top: `${m.at * SCROLL_VH}vh` }} />
      ))}
      <div className="story-stage">
        <canvas ref={canvas} className="story-canvas" />
        <div className="story-shade" />
        <span className={`story-load${loaded >= N ? " done" : ""}`}>
          {String(Math.round((loaded / N) * 100)).padStart(3, "0")}
        </span>

        <div ref={layer(0)} className="story-layer story-hero">
          <h1 className="h-hero">
            <span className="hero-l1">Learn any software.</span>
            <span className="hero-l2">Live, on your screen.</span>
          </h1>
          <Btn label="Try it now" href="#try" />
        </div>

        <div ref={layer(1)} className="story-layer story-feat">
          <span className="story-k">Features</span>
          <ul className="sf-list">
            {FEATURES.map((f) => (
              <li key={f.k} className="sf">
                <FeatIcon k={f.k} />
                <span>{f.t}</span>
              </li>
            ))}
          </ul>
        </div>

        <div ref={layer(2)} className="story-layer story-plans">
          <span className="story-k">Pricing</span>
          <ul className="sp-list">
            {PLANS.slice(0, 3).map((p) => (
              <li key={p.name} className={`sp${p.dark ? " sp-hot" : ""}`}>
                <span className="sp-name">{p.name}</span>
                <span className="sp-tag">{p.tagline}</span>
                <span className="sp-price">${p.price}</span>
              </li>
            ))}
          </ul>
        </div>

        <div ref={layer(3)} className="story-layer story-try">
          <a className="try-btn" href="#/launch">
            <RioArrow size={18} />
            Try it now
          </a>
        </div>
      </div>
    </section>
  );
}
