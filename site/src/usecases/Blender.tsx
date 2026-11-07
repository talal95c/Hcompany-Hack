import { AbsoluteFill, useCurrentFrame } from 'remotion';
import { Camera, AppWindow, GhostCursor, StepPill, ease } from './primitives';

export const BLENDER_DURATION = 360;
export const BLENDER_FINAL_FRAME = 330;

function TutorialIntake({ frame }: { frame: number }) {
  const url = 'youtube.com/watch?v=your-first-donut';
  const typed = Math.floor(ease(frame, 8, 35) * url.length);
  return <AppWindow name="Rio · New lesson">
    <Camera frame={frame * .6} x={290} y={170} amount={.14}>
      <div style={{ position: 'absolute', top: 61, left: 40, right: 40 }}>
        <p style={{ fontSize: 23, letterSpacing: -.7, margin: '0 0 14px' }}>A tutorial. Your next skill.</p>
        <div style={{ display: 'flex', alignItems: 'center', height: 39, padding: '0 12px', borderRadius: 9, background: '#f0f0f0', border: '1px solid #ddd', fontSize: 13, color: '#666' }}><span>{url.slice(0, typed)}<span style={{ color: '#e98548' }}>│</span></span><span style={{ marginLeft: 'auto', color: '#1a1a1a', fontSize: 12 }}>Start ↗</span></div>
        <div style={{ display: 'flex', gap: 15, marginTop: 10, alignItems: 'center' }}>
          <svg width="104" height="63" viewBox="0 0 104 63"><rect width="104" height="63" rx="8" fill="#e7e9e4" /><ellipse cx="52" cy="33" rx="26" ry="15" fill="none" stroke="#adb6a6" strokeWidth="12" /><rect x="37" y="20" width="30" height="23" rx="6" fill="#bd5149" /><path d="M49 26L58 31.5L49 37Z" fill="white" /></svg>
          <div><p style={{ fontSize: 15, lineHeight: 1.4, maxWidth: 260, margin: 0 }}>Blender for beginners:<br />your first donut</p><p style={{ fontSize: 11, margin: '5px 0 0', color: '#888' }}>VIDEO TUTORIAL → YOUR LESSON</p></div>
        </div>
        <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 5 }}>
          {['Add a torus', 'Scale your object', 'Check the result'].map((step, i) => { const show = ease(frame, 45 + i * 11, 56 + i * 11); return <div key={step} style={{ opacity: show, transform: `translateY(${(1 - show) * 8}px)`, display: 'flex', gap: 10, alignItems: 'center', fontSize: 13 }}><span style={{ background: '#edf1e9', color: '#607250', borderRadius: 20, width: 21, height: 21, display: 'grid', placeItems: 'center', fontSize: 11 }}>{i + 1}</span>{step}</div>; })}
        </div>
      </div>
    </Camera>
  </AppWindow>;
}

export function Blender() {
  const frame = useCurrentFrame();
  const f = Math.max(0, frame - 110);
  const transition = ease(frame, 104, 120) * (1 - ease(frame, 342, 359));
  return <AbsoluteFill>
    <TutorialIntake frame={frame > 335 ? 0 : Math.min(frame, 100)} />
    <AbsoluteFill style={{ opacity: transition, transform: `translateY(${(1 - transition) * 14}px)` }}><BlenderScene frame={f} /></AbsoluteFill>
  </AbsoluteFill>;
}

function BlenderScene({ frame: f }: { frame: number }) {
  const added = ease(f, 115, 140);
  const scale = 1 + ease(f, 155, 180) * .18;
  return <AppWindow name="Blender" dark>
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
      <div style={{ position: 'absolute', top: 82, left: 155, width: 140, padding: 12, borderRadius: 8, background: '#484b4e', color: '#eee', fontSize: 14, lineHeight: '29px', opacity: 1 - added, boxShadow: '0 8px 24px #0003' }}>Mesh　 ›<br /><span style={{ color: '#aaa' }}>Plane<br />Cube<br />Circle</span><br /><span style={{ display: 'block', background: '#65716b', borderRadius: 4, paddingLeft: 8 }}>Torus</span></div>
      <GhostCursor frame={f} to={[210, 218]} />
      <div style={{ position: 'absolute', right: 15, top: 92, fontSize: 11, color: '#aaa' }}>SCENE<br /><br />{f > 130 ? '◇ Torus' : '◇ Collection'}</div>
    </Camera>
    <StepPill frame={f} task="Add a torus" />
  </AppWindow>;
}
