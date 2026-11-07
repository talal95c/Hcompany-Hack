import type { ReactNode } from 'react';
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame } from 'remotion';

export const DURATION = 270;
export const FPS = 30;
export const FINAL_FRAME = 218;
export const ease = (f: number, start: number, end: number) => interpolate(f, [start, end], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic) });
// Return to the exact opening scene before the loop boundary.
export function useSceneFrame() {
  const f = useCurrentFrame();
  return f > 238 ? 218 * (1 - ease(f, 238, 269)) : f;
}

export function Camera({ frame, x, y, amount = .55, children }: { frame: number; x: number; y: number; amount?: number; children: ReactNode }) {
  const zoom = spring({ frame: Math.max(0, frame - 35), fps: FPS, config: { damping: 24, stiffness: 65 } }) * (1 - ease(frame, 145, 192));
  return <AbsoluteFill style={{ transformOrigin: `${x}px ${y}px`, transform: `scale(${1 + zoom * amount})` }}>{children}</AbsoluteFill>;
}

export function AppWindow({ name, children, dark = false }: { name: string; children: ReactNode; dark?: boolean }) {
  return <AbsoluteFill style={{ background: '#f0f0f0', fontFamily: 'Inter Variable, Inter, sans-serif', color: '#1a1a1a', padding: 28 }}>
    <div style={{ height: '100%', borderRadius: 18, overflow: 'hidden', background: dark ? '#303335' : '#fff', boxShadow: '0 16px 35px #00000012', border: '1px solid #00000015', position: 'relative' }}>
      <div style={{ height: 43, background: dark ? '#242729' : '#fafafa', display: 'flex', alignItems: 'center', gap: 7, padding: '0 18px', borderBottom: '1px solid #88888820', color: dark ? '#ccc' : '#777' }}>
        {[0, 1, 2].map(i => <span key={i} style={{ width: 7, height: 7, background: '#99999966', borderRadius: 20 }} />)}
        <span style={{ marginLeft: 14, fontSize: 13 }}>{name}</span><span style={{ marginLeft: 'auto', fontSize: 11 }}>Untitled</span>
      </div>{children}
    </div>
  </AbsoluteFill>;
}

export function GhostCursor({ frame, to, from = [430, 235], click = 110 }: { frame: number; to: number[]; from?: number[]; click?: number }) {
  const t = ease(frame, 25, 90);
  const x = from[0] + (to[0] - from[0]) * t;
  const y = from[1] + (to[1] - from[1]) * t;
  const pulse = ease(frame, click, click + 16);
  return <div style={{ position: 'absolute', left: x, top: y, opacity: 1 - ease(frame, 165, 185), pointerEvents: 'none' }}>
    <div style={{ position: 'absolute', width: 58, height: 58, left: -29, top: -29, border: '2px solid #e98548', borderRadius: '50%', transform: `scale(${.3 + pulse})`, opacity: frame >= click ? 1 - pulse : 0 }} />
    <svg width="31" height="38" viewBox="0 0 31 38" style={{ filter: 'drop-shadow(0 3px 4px #0003)' }}><path d="M3 3Q2 1 5 3L27 22Q29 25 25 25L16 25L11 33Q9 36 8 32Z" fill="#e98548" stroke="white" strokeWidth="2" strokeLinejoin="round" /></svg>
    <span style={{ position: 'absolute', top: 33, left: 17, background: '#e98548', color: '#fff', borderRadius: 20, padding: '4px 10px', fontSize: 12 }}>Rio</span>
  </div>;
}

export function StepPill({ frame, task }: { frame: number; task: string }) {
  const done = frame >= 176;
  return <div style={{ position: 'absolute', bottom: 14, left: '50%', transform: 'translateX(-50%)', display: 'flex', alignItems: 'center', gap: 12, whiteSpace: 'nowrap', padding: '11px 18px', borderRadius: 40, background: done ? '#b4c7a6ed' : '#ffffffda', backdropFilter: 'blur(16px)', border: '1px solid #ffffffaa', boxShadow: '0 8px 28px #0002', fontSize: 16 }}>
    <span style={{ fontSize: 18 }}>{done ? '✓' : '◌'}</span><span>{done ? 'Step verified' : `Step 2/3 · ${task}`}</span><span style={{ opacity: .4, fontSize: 12 }}>RIO</span>
  </div>;
}
