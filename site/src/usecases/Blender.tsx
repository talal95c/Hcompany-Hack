import { AbsoluteFill, useCurrentFrame } from 'remotion';
import { Camera, AppWindow, GhostCursor, StepPill, ease } from './primitives';
import { TutorialPlayer } from './TutorialPlayer';

export const BLENDER_DURATION = 360;
export const BLENDER_FINAL_FRAME = 330;

export function Blender() {
  const frame = useCurrentFrame();
  const f = Math.max(0, (frame - 150) * 1.3);
  const transfer = ease(frame, 139, 171);
  const reset = ease(frame, 342, 359);
  return <AbsoluteFill style={{ background: '#f0f0f0', fontFamily: 'Inter Variable, Inter, sans-serif', color: '#1a1a1a' }}>
    <AbsoluteFill style={{ opacity: ease(frame, 120, 159) }}><BlenderScene frame={f} /></AbsoluteFill>
    <TutorialPlayer frame={frame} />
    {frame > 135 && frame < 180 && <svg width="640" height="400" style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}><path d="M470 144Q460 198 373 246" fill="none" stroke="#e98548" strokeWidth="2" strokeDasharray="4 7" opacity={Math.sin(transfer * Math.PI) * .6} /><ellipse cx={470 - transfer * 97} cy={144 + transfer * 102} rx="28" ry="16" fill="none" stroke="#e98548" strokeWidth="8" opacity={Math.sin(transfer * Math.PI) * .7} /></svg>}
    {frame < 65 && <div style={{ position: 'absolute', bottom: 25, left: 0, right: 0, textAlign: 'center', fontSize: 19, opacity: 1 - ease(frame, 50, 65) }}>Paste a tutorial</div>}
    {frame >= 180 && frame < 285 && <div style={{ position: 'absolute', right: 51, top: 163, fontSize: 14, background: '#ffffffdd', backdropFilter: 'blur(12px)', padding: '7px 12px', borderRadius: 20, opacity: ease(frame, 180, 193) }}>Tutorial paused for you</div>}
    <AbsoluteFill style={{ opacity: reset, pointerEvents: 'none', background: '#f0f0f0' }}><TutorialPlayer frame={0} /><div style={{ position: 'absolute', bottom: 25, width: '100%', textAlign: 'center', fontSize: 19 }}>Paste a tutorial</div></AbsoluteFill>
  </AbsoluteFill>;
}

function BlenderScene({ frame: f }: { frame: number }) {
  const added = ease(f, 115, 140);
  const scale = 1 + ease(f, 155, 180) * .18;
  return <AppWindow name="Your Blender" dark>
    <Camera frame={f} x={235} y={245}>
      <div style={{ position: 'absolute', top: 43, left: 0, right: 0, height: 31, background: '#3c3f41', color: '#ddd', fontSize: 13, padding: '8px 16px' }}>Object Mode　 View　 Select　 <span style={{ color: '#e98548' }}>Add</span>　 Object</div>
      <svg viewBox="0 0 584 300" style={{ position: 'absolute', top: 88, width: '100%', height: 300 }}>
        {Array.from({ length: 15 }, (_, i) => <g key={i} stroke="#ffffff0d"><path d={`M${i * 55 - 130} 0L${i * 55 + 50} 300`} /><path d={`M0 ${i * 28}L584 ${i * 28 - 100}`} /></g>)}
        <path d="M0 230L584 130" stroke="#a5686155" /><path d="M120 0L300 300" stroke="#82a08855" />
        <g opacity={added} transform={`translate(345 130) scale(${scale})`}>
          <defs><linearGradient id="torus-shade" x1="0" y1="0" x2=".35" y2="1"><stop stopColor="#e1e5e4" /><stop offset=".38" stopColor="#b9c0c0" /><stop offset=".7" stopColor="#7d898d" /><stop offset="1" stopColor="#c2c9c8" /></linearGradient></defs>
          <ellipse cy="37" rx="96" ry="28" fill="#0004" />
          <ellipse cy="9" rx="78" ry="43" fill="none" stroke="#657174" strokeWidth="34" />
          <ellipse rx="78" ry="43" fill="none" stroke="url(#torus-shade)" strokeWidth="34" />
          <ellipse cy="-3" rx="78" ry="43" fill="none" stroke="#e5e8e6" strokeWidth="2" opacity=".55" />
          <ellipse rx="96" ry="61" fill="none" stroke="#e98548" strokeWidth="1" opacity=".8" />
        </g>
      </svg>
      <div style={{ position: 'absolute', top: 82, left: 155, width: 140, padding: 12, borderRadius: 8, background: '#484b4e', color: '#eee', fontSize: 14, lineHeight: '29px', opacity: ease(f, 12, 27) * (1 - added), boxShadow: '0 8px 24px #0003' }}>Mesh　 ›<br /><span style={{ color: '#aaa' }}>Plane<br />Cube<br />Circle</span><br /><span style={{ display: 'block', background: '#65716b', borderRadius: 4, paddingLeft: 8 }}>Torus</span></div>
      <GhostCursor frame={f} to={[210, 218]} />
      {f >= 109 && f < 139 && <svg width="25" height="32" viewBox="0 0 31 38" style={{ position: 'absolute', left: 211, top: 219, opacity: 1 - ease(f, 124, 139) }}><path d="M3 3L27 22L16 24L10 34Z" fill="#1a1a1a" stroke="white" strokeWidth="2" strokeLinejoin="round" /></svg>}
    </Camera>
    <StepPill frame={f} task="Add a torus" />
  </AppWindow>;
}
