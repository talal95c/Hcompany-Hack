import { navigate } from "../lib";
import { CopyButton, Head } from "../ui";

const REPO = "https://github.com/Jacqkues/rio";

type Step = { t: string; p: React.ReactNode; c?: string };

/** Install the Rio Mac app and connect it to this workspace. */
export function GetRioPage() {
  const url = window.location.origin;
  const steps: Step[] = [
    { t: "Install the tools", p: "Rio runs on macOS. You need Node.js 20+ and Rust.", c: "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh" },
    { t: "Get the code", p: "Clone the repository and open the app folder.", c: `git clone ${REPO}.git && cd rio` },
    {
      t: "Add your keys",
      p: (
        <>
          Copy the example file, then set <span className="mono">HAI_API_KEY</span> (H Company). <span className="mono">GLADIA_API_KEY</span> is optional and turns on voice.
        </>
      ),
      c: "cp .env.example .env",
    },
    {
      t: "Connect it to this workspace",
      p: (
        <>
          Add these two lines to <span className="mono">.env</span>. Create the token in{" "}
          <a
            href="/settings"
            onClick={(e) => {
              e.preventDefault();
              navigate("/settings");
            }}
          >
            Settings
          </a>
          : Rio then finds your team's tutorials and knowledge in ⌘K.
        </>
      ),
      c: `RIO_API_URL=${url}\nRIO_API_TOKEN=rio_…`,
    },
    { t: "Launch Rio", p: "Rio opens in your menu bar.", c: "npm install && npm run tauri dev" },
    { t: "Allow screen recording", p: "On first launch, macOS asks for Screen Recording. Grant it to your terminal, then restart Rio." },
    { t: "Start a lesson", p: "Press ⌥ ⇧ Space, paste a tutorial link or type what you want to do, and follow the orange cursor." },
  ];
  return (
    <>
      <Head title="Get Rio" sub="A one-click installer is on the way. Until then, Rio runs from source on your Mac in a few minutes.">
        <a className="btn btn--light" href={REPO} target="_blank" rel="noreferrer">
          View on GitHub
        </a>
      </Head>
      <div className="install__video">
        <video src="/get-rio.mp4" poster="/get-rio-poster.jpg" aria-label="How to install Rio, step by step" controls muted playsInline preload="metadata" />
      </div>
      <ol className="install">
        {steps.map((s, i) => (
          <li key={s.t} className="install__step">
            <span className="install__n mono">{String(i + 1).padStart(2, "0")}</span>
            <div className="install__body">
              <h3>{s.t}</h3>
              <p>{s.p}</p>
              {s.c && (
                <div className="install__code">
                  <div className="code">{s.c}</div>
                  <CopyButton text={s.c} />
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>
    </>
  );
}
