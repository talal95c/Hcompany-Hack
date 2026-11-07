import { AppWindow, Camera, GhostCursor, StepPill, ease, useSceneFrame } from './primitives';

export function Voice() {
  const f = useSceneFrame();
  return <AppWindow name="Design studio">
    <Camera frame={f} x={493} y={124}>
      <div style={{ position: 'absolute', top: 43, bottom: 0, width: 116, background: '#fafafa', borderRight: '1px solid #eee', padding: 18, fontSize: 11, lineHeight: '30px', color: '#777' }}>LAYERS<br />◇ Cover<br />　 Title<br />　 Image<br />　 Caption</div>
      <div style={{ position: 'absolute', left: 147, top: 105, width: 248, height: 229, border: '1px solid #ddd', background: '#eeeae2', padding: 23 }}><div style={{ fontSize: 10, letterSpacing: 3 }}>FIELD NOTES / 001</div><div style={{ fontSize: 36, letterSpacing: -2, lineHeight: 1.1, marginTop: 25 }}>A little<br />perspective.</div><div style={{ width: 88, height: 47, background: '#b4c7a6', borderRadius: '60px 60px 0 0', marginTop: 26 }} /></div>
      <div style={{ position: 'absolute', right: 13, top: 77, width: 123, fontSize: 11, color: '#888', lineHeight: '24px' }}>DESIGN<br />W　 1440<br />H　 1080<br /><div style={{ marginTop: 14, padding: '6px 14px', background: f > 110 ? '#b4c7a6' : '#1a1a1a', color: f > 110 ? '#1a1a1a' : 'white', borderRadius: 6, fontSize: 13 }}>{f > 130 ? '✓ Exported' : 'Export　↗'}</div></div>
      <GhostCursor frame={f} to={[498, 189]} />
    </Camera>
    <div style={{ position: 'absolute', top: 65, left: 50, background: '#ffffffec', backdropFilter: 'blur(12px)', border: '1px solid #eee', borderRadius: 30, padding: '13px 18px', display: 'flex', alignItems: 'center', gap: 12, fontSize: 16, opacity: 1 - ease(f, 150, 175), boxShadow: '0 5px 20px #0001' }}>
      <div style={{ display: 'flex', gap: 3, alignItems: 'center', height: 22 }}>{[9, 18, 13, 22, 10].map((h, i) => <span key={i} style={{ width: 3, height: h * (.7 + .3 * Math.sin(f / 5 + i)), background: '#e98548', borderRadius: 3 }} />)}</div>Where is the export button?
    </div><StepPill frame={f} task="Find export" />
  </AppWindow>;
}
