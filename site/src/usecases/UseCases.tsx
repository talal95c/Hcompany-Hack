import { useEffect, useRef, useState } from 'react';
import { Player, type PlayerRef } from '@remotion/player';
import { Label, Reveal } from '../ui';
import { Blender, BLENDER_DURATION, BLENDER_FINAL_FRAME } from './Blender';
import { Spreadsheet } from './Spreadsheet';
import { Voice } from './Voice';
import { DURATION, FINAL_FRAME, FPS } from './primitives';

const cases = [
  { app: 'Blender', title: 'Paste a tutorial, do it for real', benefit: 'Turn a YouTube tutorial into checked steps in your own Blender scene.', steps: ['Paste a link', 'Follow the steps', 'Rio checks'], component: Blender },
  { app: 'Spreadsheets', title: 'Turn a budget into a chart', benefit: 'Make sense of your numbers, with a little guidance at every click.', steps: ['Select a range', 'Insert chart', 'Rio checks'], component: Spreadsheet },
  { app: 'Any app, voice', title: 'Just ask out loud', benefit: 'Skip the menu hunt. Ask a question and see exactly where to go.', steps: ['Ask Rio', 'Follow the pointer', 'You click'], component: Voice },
];

function Preview({ item }: { item: typeof cases[number] }) {
  const duration = item.component === Blender ? BLENDER_DURATION : DURATION;
  const finalFrame = item.component === Blender ? BLENDER_FINAL_FRAME : FINAL_FRAME;
  const container = useRef<HTMLDivElement>(null);
  const player = useRef<PlayerRef>(null);
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const change = () => setReduced(query.matches);
    query.addEventListener('change', change);
    return () => query.removeEventListener('change', change);
  }, []);
  useEffect(() => {
    const p = player.current;
    if (!p || !container.current) return;
    p.pause();
    if (reduced) { p.seekTo(finalFrame); return; }
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && !document.hidden) p.play(); else p.pause();
    }, { threshold: .15 });
    const visibility = () => {
      const rect = container.current?.getBoundingClientRect();
      if (!document.hidden && rect && rect.bottom > 0 && rect.top < innerHeight) p.play(); else p.pause();
    };
    observer.observe(container.current);
    document.addEventListener('visibilitychange', visibility);
    return () => { observer.disconnect(); document.removeEventListener('visibilitychange', visibility); p.pause(); };
  }, [reduced, finalFrame]);
  return <div ref={container} className="usecase-video" role="img" aria-label={`${item.app}: ${item.title}. Illustrated Rio guidance demonstration.`}>
    <Player ref={player} component={item.component} compositionWidth={640} compositionHeight={400} durationInFrames={duration} fps={FPS} autoPlay={!reduced} loop initiallyMuted controls={false} clickToPlay={false} doubleClickToFullscreen={false} spaceKeyToPlayOrPause={false} acknowledgeRemotionLicense style={{ width: '100%', height: '100%' }} />
  </div>;
}

export function UseCases() {
  return <section className="usecases" id="use-cases">
    <Label text="USE CASES" light={false} />
    <div className="usecases-head"><Reveal as="h2" className="h2-54">From a YouTube tutorial<br />to your screen.</Reveal><Reveal as="p" className="p-16">Paste the link. Follow the steps in your own app.<br />Rio points the way and checks your progress.</Reveal></div>
    <div className="usecases-grid">{cases.map((item, i) => <Reveal key={item.app} delay={i * .1} className="usecase-card">
      <Preview item={item} /><div className="usecase-copy"><p className="mono-12 usecase-app">0{i + 1} / {item.app}</p><h3>{item.title}</h3><p className="p-14l">{item.benefit}</p><div className="usecase-chips">{item.steps.map(step => <span className="tag" key={step}>{step}</span>)}</div></div>
    </Reveal>)}</div><p className="usecases-note mono-12">ILLUSTRATED DEMOS · YOU CLICK. RIO GUIDES AND CHECKS.</p>
  </section>;
}
