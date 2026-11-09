import { useEffect, useRef } from "react";

// Floating particles in the white of the page: soft ink dots drifting up, with
// depth (far ones are smaller, fainter, slower and scroll less) and a gentle
// push away from the cursor. The canvas is sticky to the viewport inside
// `.page`, so it never covers the footer, and opaque cards hide it.

type Dot = { x: number; y: number; r: number; z: number; vx: number; vy: number; phase: number; accent: boolean };

const DENSITY = 1 / 9000; // dots per px² of viewport
const MAX_DOTS = 180;
const INK = "26, 26, 26";
const ACCENT = "255, 107, 53"; // Rio orange, a few dots only
const CURSOR_RADIUS = 140;

export function Particles() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    let dots: Dot[] = [];
    let width = 0;
    let height = 0;
    let frame = 0;
    let last = performance.now();
    let lastScroll = window.scrollY;
    const cursor = { x: -1e4, y: -1e4 };

    const spawn = (y?: number): Dot => {
      const z = Math.random(); // 0 far, 1 near
      return {
        x: Math.random() * width,
        y: y ?? Math.random() * height,
        r: 0.8 + z * 1.9,
        z,
        vx: 0,
        vy: -(4 + z * 10), // px/s upward
        phase: Math.random() * Math.PI * 2,
        accent: Math.random() < 0.06,
      };
    };

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = canvas.clientWidth;
      height = canvas.clientHeight;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const count = Math.min(MAX_DOTS, Math.round(width * height * DENSITY));
      dots = dots.filter((d) => d.x <= width && d.y <= height).slice(0, count);
      while (dots.length < count) dots.push(spawn());
    };

    const draw = (t: number) => {
      ctx.clearRect(0, 0, width, height);
      for (const d of dots) {
        const twinkle = 0.75 + 0.25 * Math.sin(t / 1400 + d.phase);
        const alpha = (0.08 + d.z * 0.2) * twinkle * (d.accent ? 1.6 : 1);
        ctx.beginPath();
        ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${d.accent ? ACCENT : INK}, ${alpha})`;
        ctx.fill();
      }
    };

    const step = (t: number) => {
      const dt = Math.min((t - last) / 1000, 0.05);
      last = t;
      const scroll = window.scrollY - lastScroll; // parallax: near dots move more with the page
      lastScroll = window.scrollY;
      for (const d of dots) {
        const sway = Math.sin(t / 2600 + d.phase) * (4 + d.z * 6);
        const dx = d.x - cursor.x;
        const dy = d.y - cursor.y;
        const dist = Math.hypot(dx, dy);
        if (dist < CURSOR_RADIUS && dist > 0.1) {
          const push = (1 - dist / CURSOR_RADIUS) ** 2 * 120 * (0.4 + d.z);
          d.vx += (dx / dist) * push * dt;
          d.y += (dy / dist) * push * dt;
        }
        d.vx *= 0.94;
        d.x += (sway * 0.15 + d.vx) * dt * 4;
        d.y += d.vy * dt - scroll * d.z * 0.25;
        if (d.y < -10) Object.assign(d, spawn(height + 10));
        else if (d.y > height + 10) Object.assign(d, spawn(-10));
        if (d.x < -10) d.x = width + 10;
        else if (d.x > width + 10) d.x = -10;
      }
      draw(t);
      frame = requestAnimationFrame(step);
    };

    const start = () => {
      cancelAnimationFrame(frame);
      if (reduced.matches) {
        draw(0); // still dots, no motion
        return;
      }
      last = performance.now();
      lastScroll = window.scrollY;
      frame = requestAnimationFrame(step);
    };

    const onMove = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      cursor.x = e.clientX - rect.left;
      cursor.y = e.clientY - rect.top;
    };
    const onLeave = () => {
      cursor.x = cursor.y = -1e4;
    };
    const observer = new ResizeObserver(() => {
      resize();
      if (reduced.matches) draw(0);
    });

    resize();
    start();
    observer.observe(canvas);
    window.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("pointerleave", onLeave);
    reduced.addEventListener("change", start);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
      reduced.removeEventListener("change", start);
    };
  }, []);

  return (
    <div className="particles" aria-hidden="true">
      <canvas ref={canvasRef} />
    </div>
  );
}
