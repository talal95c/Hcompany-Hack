import { AppWindow, Camera, GhostCursor, StepPill, ease, useSceneFrame } from './primitives';

export function Spreadsheet() {
  const f = useSceneFrame();
  const chart = ease(f, 117, 148);
  const rows = [['Category', 'Budget'], ['Rent', '$1,200'], ['Food', '$420'], ['Travel', '$180'], ['Other', '$260']];
  return <AppWindow name="LibreOffice Calc">
    <Camera frame={f} x={260} y={160}>
      <div style={{ position: 'absolute', top: 43, width: '100%', padding: '12px 18px', fontSize: 13, borderBottom: '1px solid #eee' }}>File　 Edit　 View　 <span style={{ background: '#e9eee6', padding: 6, borderRadius: 4 }}>Insert</span>　 Format</div>
      <div style={{ position: 'absolute', top: 84, width: '100%', padding: '8px 18px', background: '#fafafa', fontSize: 12, color: '#888' }}>B2　 |　 ƒx　 Monthly budget</div>
      <div style={{ position: 'absolute', top: 140, left: 26, width: 270, border: f > 30 ? '2px solid #8a9f7d' : '2px solid transparent', borderRadius: 3, overflow: 'hidden' }}>
        {rows.map((row, i) => <div key={i} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', background: i === 0 ? '#edf1e9' : '#fff', fontSize: 14 }}>{row.map(v => <span key={v} style={{ padding: '11px 13px', border: '1px solid #ededed' }}>{v}</span>)}</div>)}
      </div>
      <div style={{ position: 'absolute', top: 91, left: 182, background: '#fff', border: '1px solid #ddd', borderRadius: 6, padding: '10px 18px', fontSize: 14, opacity: 1 - chart, boxShadow: '0 6px 20px #0001' }}>Chart　 ↗</div>
      <div style={{ position: 'absolute', left: 321, top: 142, width: 224, height: 192, background: '#fff', border: '1px solid #ddd', borderRadius: 10, padding: 18, opacity: chart, transform: `translateY(${(1 - chart) * 16}px)` }}>
        <div style={{ fontSize: 13, marginBottom: 22 }}>Monthly budget</div><div style={{ height: 100, display: 'flex', alignItems: 'end', gap: 14, borderBottom: '1px solid #ddd' }}>{[85, 46, 25, 34].map((h, i) => <div key={i} style={{ height: h * chart, width: 30, background: i === 0 ? '#8b9f7e' : '#cbd6c3', borderRadius: '4px 4px 0 0' }} />)}</div><div style={{ fontSize: 9, marginTop: 8, color: '#888' }}>Rent　 Food　 Travel　 Other</div>
      </div>
      <GhostCursor frame={f} to={[224, 110]} from={[135, 270]} />
    </Camera><StepPill frame={f} task="Insert a chart" />
  </AppWindow>;
}
