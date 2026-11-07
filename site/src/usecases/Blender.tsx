import { Camera, AppWindow, GhostCursor, StepPill, ease, useSceneFrame } from './primitives';

export function Blender() {
  const f = useSceneFrame();
  const added = ease(f, 115, 140);
  const scale = 1 + ease(f, 155, 180) * .18;
  return <AppWindow name="Blender" dark>
    <Camera frame={f} x={235} y={245}>
      <div style={{ position: 'absolute', top: 43, left: 0, right: 0, height: 31, background: '#3c3f41', color: '#ddd', fontSize: 13, padding: '8px 16px' }}>Object Mode　 View　 Select　 <span style={{ color: '#e98548' }}>Add</span>　 Object</div>
      <svg viewBox="0 0 584 300" style={{ position: 'absolute', top: 88, width: '100%', height: 300 }}>
        {Array.from({ length: 15 }, (_, i) => <g key={i} stroke="#ffffff0d"><path d={`M${i * 55 - 130} 0L${i * 55 + 50} 300`} /><path d={`M0 ${i * 28}L584 ${i * 28 - 100}`} /></g>)}
        <path d="M0 230L584 130" stroke="#a5686155" /><path d="M120 0L300 300" stroke="#82a08855" />
        <g opacity={added} transform={`translate(345 130) scale(${scale})`}>
          <ellipse cy="30" rx="95" ry="28" fill="#0003" />
          <ellipse rx="82" ry="47" fill="none" stroke="#aeb3b5" strokeWidth="32" />
          <ellipse rx="82" ry="47" fill="none" stroke="#e98548" strokeWidth="1.6" />
          {Array.from({ length: 16 }, (_, i) => { const a = i * Math.PI / 8; return <path key={i} d={`M${Math.cos(a) * 66} ${Math.sin(a) * 31}L${Math.cos(a) * 98} ${Math.sin(a) * 63}`} stroke="#d3d6d7" strokeWidth="1" />; })}
        </g>
      </svg>
      <div style={{ position: 'absolute', top: 82, left: 155, width: 140, padding: 12, borderRadius: 8, background: '#484b4e', color: '#eee', fontSize: 14, lineHeight: '29px', opacity: 1 - added, boxShadow: '0 8px 24px #0003' }}>Mesh　 ›<br /><span style={{ color: '#aaa' }}>Plane<br />Cube<br />Circle</span><br /><span style={{ display: 'block', background: '#65716b', borderRadius: 4, paddingLeft: 8 }}>Torus</span></div>
      <GhostCursor frame={f} to={[210, 218]} />
      <div style={{ position: 'absolute', right: 15, top: 92, fontSize: 11, color: '#aaa' }}>SCENE<br /><br />{f > 130 ? '◇ Torus' : '◇ Collection'}</div>
    </Camera>
    <StepPill frame={f} task="Add a torus" />
  </AppWindow>;
}
