import { Btn, Label, Reveal } from "./ui";
import { useEffect, useRef, useState } from 'react';
import { Player } from '@remotion/player';
import { TeamsSearch, TeamsSearchScene, TEAMS_SEARCH_DURATION } from './usecases/TeamsSearch';
import { FPS } from './usecases/primitives';

/** The web console for companies: where a team's tutorials and internal knowledge live. */
// VITE_APP_URL="" when the console serves this page itself (same origin).
const APP_ORIGIN: string = import.meta.env.VITE_APP_URL ?? "https://rio.vignemale.com";
export const APP_URL = `${APP_ORIGIN}/home`;
/** "Download for Mac": the install guide in the README (no installer yet; no login needed). */
export const INSTALL_URL = "https://github.com/Jacqkues/rio#how-to-install";
export const SIGNUP_URL = `${APP_ORIGIN}/sign-up`;
export const SIGNIN_URL = `${APP_ORIGIN}/sign-in`;

const POINTS = [
  {
    n: "01",
    title: "One library for the team",
    text: "Make a tutorial from a YouTube video, a doc page or a plain goal. Keep it as a draft, publish it to your team or share it with the community.",
  },
  {
    n: "02",
    title: "Your internal tools, too",
    text: "Add the Markdown guides of your back-office and in-house apps. Rio searches them and guides people through tools no YouTube video covers.",
  },
  {
    n: "03",
    title: "See what people learn",
    text: "Members join from an invite link. Insights show which tutorials your team runs, and API tokens connect each Rio app to your workspace.",
  },
];

function Search() {
  const container = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 548, height: 366 });
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const change = () => setReduced(media.matches);
    media.addEventListener('change', change);
    const observer = new ResizeObserver(([entry]) => setSize({ width: entry.contentRect.width, height: entry.contentRect.height }));
    if (container.current) observer.observe(container.current);
    return () => { media.removeEventListener('change', change); observer.disconnect(); };
  }, []);
  // Hidden on phones (display: none), the container measures 0x0, and Remotion throws on
  // a zero composition size, which would unmount the whole page: render the player only once it has a size.
  const width = Math.ceil(size.width), height = Math.ceil(size.height);
  return (
    <div ref={container} style={{ position: 'relative' }} aria-label="Illustration: Rio searching a team's tutorials and internal docs">
      <div style={{ opacity: reduced ? 1 : 0 }}><TeamsSearchScene /></div>
      {!reduced && width > 0 && height > 0 && <div aria-hidden="true" style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
        <Player component={TeamsSearch} inputProps={{ width: size.width }} compositionWidth={width} compositionHeight={height} durationInFrames={TEAMS_SEARCH_DURATION} fps={FPS} autoPlay loop initiallyMuted controls={false} clickToPlay={false} doubleClickToFullscreen={false} spaceKeyToPlayOrPause={false} acknowledgeRemotionLicense style={{ width, height }} />
      </div>}
    </div>
  );
}

export function Teams() {
  return (
    <section className="teams" id="teams">
      <Label text="FOR TEAMS" light={false} />
      <div className="teams-grid">
        <div className="teams-copy">
          <Reveal as="h2" className="h2-54">
            Teach your team the tools you actually use.
          </Reveal>
          <Reveal as="p" className="p-16 teams-sub">
            Rio's console gives your company a shared space for tutorials and internal knowledge. Everyone gets the same guidance, on their own screen.
          </Reveal>
          <ul className="teams-points">
            {POINTS.map((p, i) => (
              <Reveal as="li" key={p.n} delay={i * 0.08}>
                <span className="mono-12 teams-n">{p.n}</span>
                <div>
                  <h3>{p.title}</h3>
                  <p className="p-14l">{p.text}</p>
                </div>
              </Reveal>
            ))}
          </ul>
          <Reveal className="teams-cta" delay={0.2}>
            <Btn label="Open the console" href={APP_URL} />
          </Reveal>
        </div>
        <Reveal delay={0.1}>
          <Search />
        </Reveal>
      </div>
    </section>
  );
}
