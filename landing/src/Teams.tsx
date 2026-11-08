import { Btn, Label, Reveal } from "./ui";

/** The web console for companies: where a team's tutorials and internal knowledge live. */
// VITE_APP_URL="" when the console serves this page itself (same origin).
const APP_ORIGIN: string = import.meta.env.VITE_APP_URL ?? "https://rio.vignemale.com";
export const APP_URL = `${APP_ORIGIN}/home`;
export const INSTALL_URL = `${APP_ORIGIN}/get-rio`;
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

const RESULTS = [
  { title: "Refund an order", src: "Team docs · Comptoir guide", steps: "Orders › Order › Refund" },
  { title: "Create a promo code", src: "Team docs · Comptoir guide", steps: "Marketing › Discounts › New" },
  { title: "Render the final video", src: "Team library · DaVinci Resolve", steps: "Deliver › Add to Render Queue" },
];

function Search() {
  return (
    <div className="teams-demo" aria-label="Illustration: Rio searching a team's tutorials and internal docs">
      <div className="teams-demo-bar">
        <span className="teams-demo-q">how do I refund a customer?</span>
        <span className="teams-demo-k">⌘K</span>
      </div>
      <ul className="teams-demo-list">
        {RESULTS.map((r, i) => (
          <li key={r.title} className={i === 0 ? "on" : ""}>
            <p className="teams-demo-title">{r.title}</p>
            <p className="teams-demo-meta">
              <span>{r.src}</span>
              <span>{r.steps}</span>
            </p>
          </li>
        ))}
      </ul>
      <p className="teams-demo-note mono-12">Illustrated example</p>
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
