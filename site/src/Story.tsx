import { useEffect, useRef, useState } from "react";
import { Btn, Marquee } from "./ui";
import { FEATURES, FeatIcon, PLANS } from "./sections";
import { APP_ICONS } from "./appIcons";
import { RioArrow } from "./cursor";

const N = 120;
const SCROLL_VH = 500;
const frameSrc = (i: number) => `${import.meta.env.BASE_URL}story/f${String(i + 1).padStart(3, "0")}.webp`;
const MARKS = [
  { id: "top", at: 0 },
  { id: "features", at: 0.26 },
  { id: "pricing", at: 0.55 },
  { id: "try", at: 0.86 },
];

function stageOf(p: number) {
  if (p < 0.1) return 0;
  if (p < 0.17) return -1;
  if (p < 0.4) return 1;
  if (p < 0.46) return -1;
  if (p < 0.68) return 2;
  if (p < 0.78) return -1;
  return 3;
}

export function Story() {
  const wrap = useRef<HTMLElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [stage, setStage] = useState(0);
  const [loaded, setLoaded] = useState(0);

  useEffect(() => {
    const cv = canvas.current!;
    const ctx = cv.getContext("2d")!;
    let cur = 0;
    let target = 0;
    let shown = -1;
    let raf = 0;
    let count = 0;
    const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const imgs: HTMLImageElement[] = [];
    const draw = () => {
      let i = Math.round(cur);
      while (i > 0 && !imgs[i]?.naturalWidth) i--;
      const im = imgs[i];
      if (!im?.naturalWidth) return;
      const s = Math.max(cv.width / im.naturalWidth, cv.height / im.naturalHeight);
      const w = im.naturalWidth * s;
      const h = im.naturalHeight * s;
      ctx.drawImage(im, (cv.width - w) / 2, (cv.height - h) / 2, w, h);
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
    const size = () => {
      const d = Math.min(devicePixelRatio || 1, 2);
      cv.width = innerWidth * d;
      cv.height = innerHeight * d;
      shown = -1;
      draw();
    };
    const tick = () => {
      cur = calm ? target : cur + (target - cur) * 0.16;
      if (Math.abs(target - cur) < 0.05) cur = target;
      if (Math.round(cur) !== shown) {
        shown = Math.round(cur);
        draw();
      }
      raf = cur === target ? 0 : requestAnimationFrame(tick);
    };
    const onScroll = () => {
      const r = wrap.current!.getBoundingClientRect();
      const p = Math.min(Math.max(-r.top / (r.height - innerHeight), 0), 1);
      target = p * (N - 1);
      setStage(stageOf(p));
      if (!raf) raf = requestAnimationFrame(tick);
    };
    size();
    onScroll();
    cur = target;
    addEventListener("resize", size);
    addEventListener("scroll", onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      removeEventListener("resize", size);
      removeEventListener("scroll", onScroll);
    };
  }, []);

  const on = (s: number) => (stage === s ? " on" : "");
  return (
    <section className="flythru" ref={wrap} style={{ height: `${SCROLL_VH + 100}vh` }}>
      {MARKS.map((m) => (
        <div key={m.id} id={m.id} className="story-mark" style={{ top: `${m.at * SCROLL_VH}vh` }} />
      ))}
      <div className="story-stage">
        <canvas ref={canvas} className="story-canvas" />
        <div className="story-shade" />
        <span className={`story-load${loaded >= N ? " done" : ""}`}>
          Loading scene {String(Math.round((loaded / N) * 100)).padStart(3, "0")}
        </span>

        <div className={`story-hero${on(0)}`}>
          <h1 className="h-hero">
            <span className="hero-l1">Learn any software.</span>
            <span className="hero-l2">Live, on your screen.</span>
          </h1>
          <p className="p-16 hero-sub">
            Rio watches your screen, breaks any task into steps and shows you exactly where to click. You do it, Rio checks it.
          </p>
          <Btn label="Try it now" href="#try" />
          <span className="story-hint">Scroll to fly in</span>
        </div>
        <div className={`story-logos${on(0)}`}>
          <Marquee duration={28} className="hero-logos">
            {APP_ICONS.map((a, i) => (
              <span key={a.name} className="app-logo" style={{ animationDelay: `${-i * 0.9}s` }}>
                <svg viewBox="0 0 24 24" aria-hidden>
                  <path d={a.path} />
                </svg>
                {a.name}
              </span>
            ))}
          </Marquee>
        </div>

        <div className={`story-panel story-feat${on(1)}`}>
          <span className="story-k">Features</span>
          <h2 className="story-h">A tutor that sees your screen.</h2>
          <div className="sf-grid">
            {FEATURES.map((f) => (
              <div key={f.k} className="sf">
                <FeatIcon k={f.k} />
                <h3>{f.t}</h3>
                <p>{f.d}</p>
              </div>
            ))}
          </div>
        </div>

        <div className={`story-panel story-plans${on(2)}`}>
          <span className="story-k">Pricing</span>
          <h2 className="story-h">Start free. Upgrade when Rio clicks.</h2>
          <div className="sp-grid">
            {PLANS.slice(0, 3).map((p) => (
              <div key={p.name} className={`sp${p.dark ? " sp-hot" : ""}`}>
                <span className="sp-name">{p.name}</span>
                <span className="sp-price">${p.price}<em>/mo</em></span>
                <span className="sp-tag">{p.tagline}</span>
                <ul>
                  {p.f.slice(0, 3).map((x) => <li key={x}>{x}</li>)}
                </ul>
              </div>
            ))}
          </div>
          <span className="sp-note">Indicative pricing, early access.</span>
        </div>

        <div className={`story-try${on(3)}`}>
          <span className="story-k">Rio · ready</span>
          <a className="try-btn" href="#/launch">
            <RioArrow size={22} />
            Try it now
          </a>
          <span className="story-hint">Click the screen to launch the app</span>
        </div>
        <a className={`story-screen-hit${on(3)}`} href="#/launch" aria-label="Launch Rio" />
      </div>
    </section>
  );
}
