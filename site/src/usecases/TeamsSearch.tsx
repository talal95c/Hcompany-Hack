import { AbsoluteFill, spring, useCurrentFrame } from 'remotion';
import { ease, FPS } from './primitives';

export const TEAMS_SEARCH_DURATION = 330;
export const TEAMS_SEARCH_RESULTS = [
  { title: 'Refund an order', src: 'Team docs · Comptoir guide', steps: 'Orders › Order › Refund' },
  { title: 'Create a promo code', src: 'Team docs · Comptoir guide', steps: 'Marketing › Discounts › New' },
  { title: 'Render the final video', src: 'Team library · DaVinci Resolve', steps: 'Deliver › Add to Render Queue' },
];
const QUERIES = ['how do I refund a customer?', 'create a promo code', 'render the final video'];

export function TeamsSearchScene({ frame = 85, width }: { frame?: number; width?: number }) {
  const cycle = Math.floor(frame / 110) % 3;
  const f = frame % 110;
  const query = QUERIES[cycle];
  const typed = Math.min(query.length, Math.max(0, Math.floor((f - 6) / 1.4)));
  const exit = 1 - ease(f, 102, 109);
  const press = ease(f, 0, 4) * (1 - ease(f, 5, 10));
  const accent = ease(f, 65, 75) * exit;
  return <div className="teams-demo" style={{ width }}>
    <div className="teams-demo-bar">
      <span className="teams-demo-q" style={{ opacity: exit }}>{query.slice(0, typed)}{f < 53 && <span style={{ display: 'inline-block', height: 16, width: 1, background: '#fff', verticalAlign: '-3px', marginLeft: 2, opacity: Math.floor(f / 10) % 2 ? 0 : 1 }} />}</span>
      <span className="teams-demo-k" style={{ transform: press ? `scale(${1 - press * .08}) translateY(${press}px)` : undefined, background: press ? `rgba(255,255,255,${31 / 255 + press * .15})` : undefined }}>⌘K</span>
    </div>
    <ul className="teams-demo-list">
      {TEAMS_SEARCH_RESULTS.map((r, i) => {
        const enter = f >= 85 ? 1 : spring({ frame: f - 45 - i * 4, fps: FPS, config: { damping: 22, stiffness: 170 } });
        const highlight = i === cycle ? accent : 0;
        return <li key={r.title} style={{ boxShadow: `inset ${3 * highlight}px 0 0 #e98548`, opacity: Math.min(1, enter) * exit, transform: enter === 1 ? undefined : `translateY(${(1 - enter) * 8}px)`, background: `rgb(255, ${255 - Math.round(highlight * (1 - ease(f, 75, 85)) * 5)}, ${255 - Math.round(highlight * (1 - ease(f, 75, 85)) * 9)})` }}>
          <p className="teams-demo-title">{r.title}</p>
          <p className="teams-demo-meta"><span>{r.src}</span><span>{r.steps}</span></p>
        </li>;
      })}
    </ul>
    <p className="teams-demo-note mono-12">Illustrated example</p>
  </div>;
}

export function TeamsSearch({ width }: { width?: number }) {
  return <AbsoluteFill style={{ background: '#fff' }}><TeamsSearchScene frame={useCurrentFrame()} width={width} /></AbsoluteFill>;
}
