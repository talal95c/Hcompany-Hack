import { spring } from 'remotion';
import { ease, FPS } from './primitives';

export function TutorialPlayer({ frame: f }: { frame: number }) {
  const expand = ease(f, 51, 72);
  const dock = spring({ frame: Math.max(0, f - 120), fps: FPS, config: { damping: 24, stiffness: 65 } });
  const progress = .12 + ease(f, 67, 116) * .38 + ease(f, 291, 330) * .4;
  const press = ease(f, 40, 46) * (1 - ease(f, 46, 53));
  const pasted = f >= 17;
  const flash = ease(f, 17, 20) * (1 - ease(f, 24, 34));
  const added = ease(f, 93, 105);
  return <div style={{ position: 'absolute', left: 66 + dock * 336, top: 135 - expand * 80 - dock * 10, width: 508, height: 76 + expand * 224, transform: `scale(${1 - dock * .63})`, transformOrigin: 'top left', borderRadius: 18, overflow: 'hidden', background: '#ffffffdc', border: '1px solid #ffffff', backdropFilter: 'blur(20px)', boxShadow: '0 12px 40px #0002' }}>
    <div style={{ position: 'absolute', inset: 12, display: 'flex', alignItems: 'center', gap: 12, opacity: 1 - expand }}>
      <div style={{ flex: 1, height: 49, border: '1px solid #ddd', borderRadius: 10, display: 'flex', alignItems: 'center', padding: '0 13px', fontSize: 17, color: pasted ? '#1a1a1a' : '#999', background: `rgba(180,199,166,${flash * .4})` }}>{pasted ? 'youtube.com/watch?v=first-donut' : 'Paste a YouTube link'}</div>
      <div style={{ padding: '16px 18px', borderRadius: 10, background: '#1a1a1a', color: '#fff', fontSize: 17, transform: `scale(${1 - press * .1})` }}>Start</div>
    </div>
    <div style={{ position: 'absolute', inset: 0, opacity: expand }}>
      <div style={{ height: 53, display: 'flex', alignItems: 'center', gap: 10, padding: '0 17px', fontSize: 17, whiteSpace: 'nowrap' }}><span style={{ width: 27, height: 21, display: 'grid', placeItems: 'center', background: '#b84f46', color: '#fff', borderRadius: 5, fontSize: 12 }}>▶</span>Blender for beginners: your first donut</div>
      <svg viewBox="0 0 508 202" width="508" height="202" style={{ display: 'block', background: '#e2e4e2' }}>
        <path d="M0 146L508 84M0 185L508 123M120 0L230 202M220 0L330 202M320 0L430 202" stroke="#c8cdca" fill="none" />
        <rect width="508" height="29" fill="#cdd2ce" /><text x="18" y="20" fontSize="14" fill="#515954">View　 Select　 Add　 Object</text>
        <g opacity={1 - added}><rect x="145" y="36" width="102" height="111" rx="7" fill="#f9faf8" /><text x="159" y="59" fontSize="14" fill="#606762">Mesh　 ›</text><text x="159" y="88" fontSize="14" fill="#9a9e9b">Cube</text><rect x="152" y="101" width="87" height="31" rx="4" fill="#bac6b3" /><text x="160" y="122" fontSize="15" fill="#515954">Torus</text></g>
        <g opacity={added}><ellipse cx="322" cy="134" rx="72" ry="24" fill="#0001" /><ellipse cx="322" cy="111" rx="60" ry="32" fill="none" stroke="#949e97" strokeWidth="23" /><ellipse cx="322" cy="106" rx="60" ry="32" fill="none" stroke="#bcc5bf" strokeWidth="23" /></g>
        <g transform={`translate(${320 - ease(f, 70, 93) * 115} ${150 - ease(f, 70, 93) * 35})`} opacity={1 - ease(f, 108, 116)}><path d="M0 0V-16Q0-20 4-20Q8-20 8-16V-7L17-3Q21-1 20 4L17 15H3L-5 4Q-7 0-3-1Z" fill="white" stroke="#6b736e" strokeWidth="2" /></g>
      </svg>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '13px 17px', fontSize: 13, color: '#6e766f' }}><span>{f >= 120 && f < 291 ? 'Ⅱ' : '▶'}</span><div style={{ height: 5, flex: 1, background: '#dce0d9', borderRadius: 4, overflow: 'hidden' }}><div style={{ height: '100%', width: `${progress * 100}%`, background: '#b84f46' }} /></div><span>{f >= 120 && f < 291 ? 'Waiting for you' : 'Tutorial'}</span></div>
    </div>
  </div>;
}
