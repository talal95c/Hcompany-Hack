import type { CSSProperties, ReactNode } from "react";
import { AbsoluteFill, Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadMono } from "@remotion/google-fonts/GeistMono";

const { fontFamily: SANS } = loadInter("normal", { weights: ["300", "400", "500"], subsets: ["latin"] });
const { fontFamily: MONO } = loadMono("normal", { weights: ["300", "400", "500"], subsets: ["latin"] });

export const W = 1200;
export const H = 900;
export const FPS = 30;
export const DURATION = 600;

const INK = "#1a1a1a";
const MIST = "#f0f0f0";
const EASE = Easing.bezier(0.22, 1, 0.36, 1);
const ORANGE = ["#ffc078", "#ff7a1a", "#d9420b"];

const SCENES = [
  { from: 0, t: "Install the tools" },
  { from: 110, t: "Get the code" },
  { from: 210, t: "Add your keys" },
  { from: 310, t: "Launch Rio" },
  { from: 400, t: "Allow screen recording" },
  { from: 490, t: "Start a lesson" },
];

const ramp = (f: number, a: number, b: number, from = 0, to = 1) =>
  interpolate(f, [a, b], [from, to], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE });

const typed = (f: number, start: number, text: string, cps = 1.4) =>
  text.slice(0, Math.max(0, Math.floor((f - start) * cps)));

/* camera keyframes: frame → zoom + focus point (stage coords) */
const CAM: [number, number, number, number][] = [
  [0, 1, 600, 450],
  [20, 1.15, 600, 410],
  [100, 1.15, 600, 410],
  [125, 1.2, 600, 420],
  [200, 1.2, 600, 420],
  [225, 1.7, 520, 330],
  [300, 1.7, 520, 330],
  [325, 1.2, 600, 420],
  [350, 1.2, 600, 420],
  [368, 1, 600, 450],
  [378, 2.6, 1080, 40],
  [398, 2.6, 1080, 40],
  [415, 1, 600, 450],
  [440, 1.45, 600, 420],
  [482, 1.45, 600, 420],
  [500, 1, 600, 450],
  [560, 1.35, 760, 330],
  [590, 1, 600, 450],
];

function camera(f: number) {
  let i = 0;
  while (i < CAM.length - 2 && f > CAM[i + 1][0]) i++;
  const [f0, s0, x0, y0] = CAM[i];
  const [f1, s1, x1, y1] = CAM[i + 1];
  const k = ramp(f, f0, f1);
  const s = s0 + (s1 - s0) * k;
  const x = x0 + (x1 - x0) * k;
  const y = y0 + (y1 - y0) * k;
  return `translate(${W / 2}px, ${H / 2}px) scale(${s}) translate(${-x}px, ${-y}px)`;
}

const Caret = ({ f }: { f: number }) => (
  <span style={{ opacity: Math.floor(f / 8) % 2 ? 0 : 1, marginLeft: 2 }}>▍</span>
);

function Line({ f, start, cmd, out, outAt }: { f: number; start: number; cmd: string; out?: string; outAt?: number }) {
  if (f < start) return null;
  const t = typed(f, start, cmd);
  const done = t.length === cmd.length;
  return (
    <div style={{ marginBottom: 14 }}>
      <div>
        <span style={{ color: "rgba(255,255,255,.45)" }}>~ % </span>
        {t}
        {!done && <Caret f={f} />}
      </div>
      {out && outAt !== undefined && f > outAt && (
        <div style={{ color: "rgba(255,255,255,.55)", opacity: ramp(f, outAt, outAt + 8) }}>{out}</div>
      )}
    </div>
  );
}

function Window({ title, children, style }: { title: string; children: ReactNode; style?: CSSProperties }) {
  return (
    <div
      style={{
        position: "absolute",
        background: INK,
        color: "#fff",
        borderRadius: 16,
        border: "1px solid rgba(255,255,255,.1)",
        boxShadow: "0 30px 80px rgba(0,0,0,.25)",
        overflow: "hidden",
        ...style,
      }}
    >
      <div style={{ height: 38, display: "flex", alignItems: "center", gap: 8, padding: "0 16px", borderBottom: "1px solid rgba(255,255,255,.08)" }}>
        {[0, 1, 2].map((i) => (
          <span key={i} style={{ width: 11, height: 11, borderRadius: 6, background: "rgba(255,255,255,.22)" }} />
        ))}
        <span style={{ flex: 1, textAlign: "center", fontFamily: MONO, fontSize: 13, color: "rgba(255,255,255,.5)", marginRight: 50 }}>{title}</span>
      </div>
      {children}
    </div>
  );
}

function Terminal({ f }: { f: number }) {
  const editing = f >= 210 && f < 310;
  return (
    <Window title={editing ? "nano .env" : "Terminal — zsh"} style={{ left: 170, top: 150, width: 860, height: 520 }}>
      <div style={{ padding: "26px 28px", fontFamily: MONO, fontSize: 19, lineHeight: 1.55, fontWeight: 300 }}>
        {editing ? (
          <>
            <div style={{ color: "rgba(255,255,255,.4)" }}>{"# H Company key"}</div>
            <div>
              {"HAI_API_KEY="}
              <span style={{ background: f > 226 ? "rgba(255,255,255,.12)" : "transparent", borderRadius: 4, padding: "0 4px" }}>
                {typed(f, 226, "hk-••••••••••••", 0.9)}
              </span>
              {f < 262 && <Caret f={f} />}
            </div>
            <div style={{ color: "rgba(255,255,255,.4)", marginTop: 22 }}>{"# Optional: voice"}</div>
            <div>{"GLADIA_API_KEY="}</div>
            {f > 272 && (
              <div style={{ marginTop: 40, color: "rgba(255,255,255,.55)", opacity: ramp(f, 272, 282) }}>✓ Saved .env</div>
            )}
          </>
        ) : (
          <>
            <Line f={f} start={12} cmd="curl https://sh.rustup.rs -sSf | sh" out="✓ Rust installed" outAt={72} />
            <Line f={f} start={116} cmd="git clone …/Hcompany-Hack && cd h-tutor" out="✓ Cloned into 'Hcompany-Hack'" outAt={176} />
            <Line f={f} start={312} cmd="npm install && npm run tauri dev" out="✓ Rio is running" outAt={352} />
          </>
        )}
      </div>
    </Window>
  );
}

function MenuBar({ f }: { f: number }) {
  const pop = spring({ frame: f - 360, fps: FPS, config: { damping: 12 } });
  return (
    <div
      style={{
        position: "absolute",
        inset: "0 0 auto 0",
        height: 34,
        background: "rgba(255,255,255,.7)",
        borderBottom: "1px solid rgba(0,0,0,.06)",
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
        gap: 18,
        padding: "0 22px",
        fontFamily: SANS,
        fontSize: 14,
        color: INK,
      }}
    >
      <span style={{ marginRight: "auto", fontWeight: 500 }}>Terminal</span>
      {f > 356 && (
        <span style={{ transform: `scale(${pop})`, display: "grid", placeItems: "center", width: 26, height: 22, borderRadius: 6, background: INK }}>
          <Img src={staticFile("rio-mark-white.svg")} style={{ width: 14 }} />
        </span>
      )}
      <span style={{ width: 22, height: 11, border: `1.5px solid ${INK}`, borderRadius: 3 }} />
      <span style={{ fontFamily: MONO, fontSize: 13 }}>9:41</span>
    </div>
  );
}

function Toggle({ on }: { on: number }) {
  return (
    <span style={{ position: "relative", display: "block", width: 46, height: 28, borderRadius: 14, background: `rgba(26,26,26,${0.15 + on * 0.85})` }}>
      <span style={{ position: "absolute", top: 3, left: 3 + on * 18, width: 22, height: 22, borderRadius: 11, background: "#fff", boxShadow: "0 1px 3px rgba(0,0,0,.3)" }} />
    </span>
  );
}

function Pointer({ x, y, color = INK }: { x: number; y: number; color?: string }) {
  return (
    <svg width={26} height={30} viewBox="0 0 26 30" style={{ position: "absolute", left: x, top: y, filter: "drop-shadow(0 2px 3px rgba(0,0,0,.25))" }}>
      <path d="M2 2 L2 24 L8 18.5 L12.5 28 L16.5 26 L12 17 L20 17 Z" fill={color} stroke="#fff" strokeWidth={1.6} strokeLinejoin="round" />
    </svg>
  );
}

function Permission({ f }: { f: number }) {
  const o = ramp(f, 402, 416) * (1 - ramp(f, 482, 494));
  const on = ramp(f, 452, 462);
  const px = interpolate(f, [418, 448], [930, 812], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE });
  const py = interpolate(f, [418, 448], [640, 428], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE });
  const press = f > 448 && f < 456 ? 0.92 : 1;
  return (
    <AbsoluteFill style={{ opacity: o }}>
      <AbsoluteFill style={{ background: "rgba(240,240,240,.55)", backdropFilter: "blur(6px)" }} />
      <div
        style={{
          position: "absolute",
          left: 330,
          top: 300,
          width: 540,
          background: "#fff",
          color: INK,
          borderRadius: 18,
          boxShadow: "0 30px 80px rgba(0,0,0,.18)",
          fontFamily: SANS,
          padding: 28,
          transform: `scale(${0.96 + 0.04 * ramp(f, 402, 420)})`,
        }}
      >
        <div style={{ fontFamily: MONO, fontSize: 12, letterSpacing: 1, color: "rgba(26,26,26,.5)" }}>PRIVACY &amp; SECURITY</div>
        <div style={{ fontSize: 24, fontWeight: 500, letterSpacing: -0.5, margin: "8px 0 22px" }}>Screen Recording</div>
        {["Terminal", "Rio"].map((n, i) => (
          <div key={n} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 0", borderTop: "1px solid rgba(0,0,0,.08)", fontSize: 18 }}>
            <span>{n}</span>
            <span style={{ transform: i === 0 ? `scale(${press})` : undefined }}>
              <Toggle on={i === 0 ? on : 0} />
            </span>
          </div>
        ))}
      </div>
      <Pointer x={px} y={py} />
    </AbsoluteFill>
  );
}

function Key({ k, f, at, wide }: { k: string; f: number; at: number; wide?: boolean }) {
  const s = spring({ frame: f - at, fps: FPS, config: { damping: 11, stiffness: 160 } });
  const down = f > at + 14 && f < at + 26 ? 4 : 0;
  return (
    <span
      style={{
        display: "grid",
        placeItems: "center",
        minWidth: wide ? 210 : 96,
        height: 96,
        padding: "0 24px",
        borderRadius: 20,
        background: "#fff",
        color: INK,
        fontFamily: SANS,
        fontSize: wide ? 30 : 40,
        boxShadow: `0 ${8 - down}px 0 rgba(0,0,0,.12), 0 20px 40px rgba(0,0,0,.08)`,
        transform: `translateY(${down + (1 - s) * 30}px) scale(${s})`,
        opacity: s,
      }}
    >
      {k}
    </span>
  );
}

function Lesson({ f }: { f: number }) {
  const keysOut = ramp(f, 528, 538);
  const bar = spring({ frame: f - 534, fps: FPS, config: { damping: 15 } });
  const winIn = ramp(f, 492, 510);
  const cx = interpolate(f, [556, 580], [560, 860], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE });
  const cy = interpolate(f, [556, 580], [480, 252], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: EASE });
  const ring = ramp(f, 582, 598);
  return (
    <AbsoluteFill>
      <Window title="Blender" style={{ left: 120, top: 120, width: 960, height: 640, opacity: winIn, background: "#232323" }}>
        <div style={{ display: "flex", height: 602 }}>
          <div style={{ flex: 1, display: "grid", placeItems: "center" }}>
            <div style={{ width: 170, height: 170, border: "2px solid rgba(255,255,255,.35)", transform: "rotate(45deg) skew(8deg,8deg)", borderRadius: 6 }} />
          </div>
          <div style={{ width: 300, borderLeft: "1px solid rgba(255,255,255,.08)", padding: 22, fontFamily: SANS, fontSize: 16, color: "rgba(255,255,255,.65)" }}>
            {["Object", "Modifiers", "Materials", "Physics"].map((t, i) => (
              <div
                key={t}
                style={{
                  padding: "12px 14px",
                  borderRadius: 10,
                  marginBottom: 6,
                  background: i === 1 && f > 580 ? "rgba(255,255,255,.12)" : "rgba(255,255,255,.04)",
                  color: i === 1 && f > 580 ? "#fff" : undefined,
                }}
              >
                {t}
              </div>
            ))}
          </div>
        </div>
      </Window>

      {f < 540 && (
        <AbsoluteFill style={{ display: "flex", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 18, opacity: 1 - keysOut, filter: `blur(${keysOut * 8}px)` }}>
          <Key k="⌥" f={f} at={498} />
          <Key k="⇧" f={f} at={504} />
          <Key k="Space" f={f} at={510} wide />
        </AbsoluteFill>
      )}

      {f >= 534 && (
        <div
          style={{
            position: "absolute",
            left: 300,
            top: 60,
            width: 600,
            height: 64,
            borderRadius: 32,
            background: "#0d0d0d",
            border: "1px solid rgba(255,255,255,.14)",
            display: "flex",
            alignItems: "center",
            gap: 14,
            padding: "0 22px",
            color: "#fff",
            fontFamily: SANS,
            fontSize: 20,
            fontWeight: 300,
            transform: `translateY(${(1 - bar) * -20}px) scale(${0.94 + bar * 0.06})`,
            opacity: bar,
          }}
        >
          <Img src={staticFile("rio-mark-white.svg")} style={{ width: 20 }} />
          <span>
            {typed(f, 538, "Add a bevel to this cube", 1.6)}
            {f < 556 && <Caret f={f} />}
          </span>
        </div>
      )}

      {f >= 552 && (
        <div style={{ position: "absolute", left: cx, top: cy, opacity: ramp(f, 552, 560) }}>
          {f > 580 && (
            <span
              style={{
                position: "absolute",
                left: -26 + 4,
                top: -26 + 4,
                width: 52,
                height: 52,
                borderRadius: 26,
                border: `2px solid ${ORANGE[1]}`,
                transform: `scale(${0.4 + ring * 1.2})`,
                opacity: 1 - ring,
              }}
            />
          )}
          <svg width={34} height={38} viewBox="0 0 26 30" style={{ filter: "drop-shadow(0 0 10px rgba(255,122,26,.55))" }}>
            <defs>
              <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stopColor={ORANGE[0]} />
                <stop offset=".55" stopColor={ORANGE[1]} />
                <stop offset="1" stopColor={ORANGE[2]} />
              </linearGradient>
            </defs>
            <path d="M2 2 L2 24 L8 18.5 L12.5 28 L16.5 26 L12 17 L20 17 Z" fill="url(#g)" stroke="#fff" strokeWidth={1.4} strokeLinejoin="round" />
          </svg>
          <span
            style={{
              position: "absolute",
              left: 34,
              top: 30,
              whiteSpace: "nowrap",
              background: "#fff",
              color: INK,
              fontFamily: MONO,
              fontSize: 14,
              padding: "6px 10px",
              borderRadius: 8,
            }}
          >
            Click Modifiers
          </span>
        </div>
      )}
    </AbsoluteFill>
  );
}

function Caption({ f }: { f: number }) {
  const i = SCENES.reduce((acc, sc, j) => (f >= sc.from ? j : acc), 0);
  const s = SCENES[i];
  const k = ramp(f, s.from, s.from + 14);
  return (
    <div style={{ position: "absolute", left: 40, right: 40, bottom: 34, display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 14,
          background: INK,
          color: "#fff",
          borderRadius: 999,
          padding: "12px 22px 12px 14px",
          opacity: k,
          filter: `blur(${(1 - k) * 6}px)`,
          transform: `translateY(${(1 - k) * 10}px)`,
        }}
      >
        <span style={{ fontFamily: MONO, fontSize: 15, background: "#fff", color: INK, borderRadius: 999, padding: "3px 9px" }}>
          {String(i + 1).padStart(2, "0")}
        </span>
        <span style={{ fontFamily: SANS, fontSize: 22, fontWeight: 500, letterSpacing: -0.4 }}>{s.t}</span>
      </div>
      <div style={{ display: "flex", gap: 6, marginBottom: 18 }}>
        {SCENES.map((sc, j) => {
          const end = SCENES[j + 1]?.from ?? DURATION;
          const p = ramp(f, sc.from, end);
          return (
            <span key={sc.t} style={{ width: 34, height: 4, borderRadius: 2, background: "rgba(26,26,26,.15)", overflow: "hidden" }}>
              <span style={{ display: "block", height: "100%", width: `${p * 100}%`, background: INK }} />
            </span>
          );
        })}
      </div>
    </div>
  );
}

export function GetRio() {
  const f = useCurrentFrame();
  useVideoConfig();
  const termOut = ramp(f, 400, 412);
  const loop = ramp(f, 0, 8) * (1 - ramp(f, DURATION - 10, DURATION));
  return (
    <AbsoluteFill style={{ background: MIST, fontFamily: SANS, opacity: loop }}>
      <AbsoluteFill style={{ transform: camera(f), transformOrigin: "0 0" }}>
        <AbsoluteFill
          style={{
            backgroundImage: "radial-gradient(rgba(26,26,26,.13) 1px, transparent 1px)",
            backgroundSize: "22px 22px",
          }}
        />
        <MenuBar f={f} />
        {f < 412 && (
          <div style={{ opacity: 1 - termOut }}>
            <Terminal f={f} />
          </div>
        )}
        {f >= 400 && f < 496 && <Permission f={f} />}
        {f >= 490 && <Lesson f={f} />}
      </AbsoluteFill>
      <Caption f={f} />
    </AbsoluteFill>
  );
}
