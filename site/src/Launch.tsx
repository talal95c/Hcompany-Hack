import { useEffect, useState } from "react";
import { PillLogo } from "./ui";

const REPO = "https://github.com/talal95c/Hcompany-Hack";
const STEPS = [
  { t: "Get the code", c: `git clone ${REPO} && cd Hcompany-Hack/h-tutor` },
  { t: "Add your Holo key", c: "cp .env.example .env   # then set HAI_API_KEY" },
  { t: "Launch Rio", c: "npm install && npm run tauri dev" },
];

function Copy({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className="ln-copy"
      onClick={() => navigator.clipboard?.writeText(text).then(() => {
        setDone(true);
        setTimeout(() => setDone(false), 1400);
      })}
    >
      {done ? "Copied" : "Copy"}
    </button>
  );
}

export function Launch() {
  useEffect(() => {
    scrollTo(0, 0);
  }, []);
  return (
    <main className="launch">
      <a href="#top" className="ln-back">← Back to the site</a>
      <div className="ln-inner">
        <PillLogo size="md" />
        <h1 className="ln-title">Launch Rio</h1>
        <p className="ln-sub">Rio is a macOS menu-bar app. Run it on your Mac in three commands.</p>
        <ol className="ln-steps">
          {STEPS.map((s, i) => (
            <li key={s.t} className="ln-step">
              <span className="ln-n">{String(i + 1).padStart(2, "0")}</span>
              <div>
                <h3>{s.t}</h3>
                <div className="ln-code"><code>{s.c}</code><Copy text={s.c} /></div>
              </div>
            </li>
          ))}
          <li className="ln-step">
            <span className="ln-n">04</span>
            <div>
              <h3>Start a lesson</h3>
              <p>Press <kbd>⌥</kbd><kbd>⇧</kbd><kbd>Space</kbd>, type what you want to learn and follow the orange cursor.</p>
            </div>
          </li>
        </ol>
        <p className="ln-note">On first launch, macOS asks for Screen Recording permission. Grant it to your terminal, then restart.</p>
      </div>
    </main>
  );
}
