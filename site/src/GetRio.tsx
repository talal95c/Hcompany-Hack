import { useEffect, useState } from "react";
import { Btn, Label, Reveal } from "./ui";

const REPO = "https://github.com/talal95c/Hcompany-Hack";

type Step = { t: string; p: string; c?: string };

const STEPS: Step[] = [
  {
    t: "Install the tools",
    p: "Rio runs on macOS. You need Node.js 20+ and Rust.",
    c: "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh",
  },
  { t: "Get the code", p: "Clone the repository and open the app folder.", c: `git clone ${REPO} && cd Hcompany-Hack/h-tutor` },
  {
    t: "Add your keys",
    p: "Set HAI_API_KEY (H Company). GLADIA_API_KEY is optional and turns on voice.",
    c: "cp .env.example .env",
  },
  { t: "Launch Rio", p: "Rio opens in your menu bar.", c: "npm install && npm run tauri dev" },
  {
    t: "Allow screen recording",
    p: "On first launch, macOS asks for Screen Recording. Grant it to your terminal, then restart Rio.",
  },
  {
    t: "Start a lesson",
    p: "Press ⌥ ⇧ Space, type what you want to learn and follow the orange cursor.",
  },
];

function Copy({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className="gr-copy mono-12"
      onClick={() =>
        navigator.clipboard?.writeText(text).then(() => {
          setDone(true);
          setTimeout(() => setDone(false), 1400);
        })
      }
    >
      {done ? "Copied" : "Copy"}
    </button>
  );
}

export function GetRio() {
  useEffect(() => {
    scrollTo(0, 0);
  }, []);
  return (
    <section className="faq-wrap getrio" id="get-rio">
      <div className="faq-card">
        <div className="faq">
          <div className="faq-left">
            <div>
              <Label text="GET RIO" pillFirst light={false} className="w-500" />
              <Reveal as="p" className="p-16 faq-sub">
                A one-click installer is on the way. Until then, Rio runs from source in a few minutes.
              </Reveal>
            </div>
            <div>
              <Reveal as="h2" className="h2-54 faq-title">
                Get Rio on your Mac.
              </Reveal>
              <Reveal delay={0.1}>
                <Btn label="View on GitHub" href={REPO} />
              </Reveal>
            </div>
          </div>
          <ol className="faq-list gr-steps">
            {STEPS.map((s, i) => (
              <Reveal as="li" key={s.t} delay={i * 0.05} y={20} className="faq-item gr-step">
                <div className="faq-q">
                  <h4 className="h4-20 faq-h">{s.t}</h4>
                  <span className="mono-12 gr-n">{String(i + 1).padStart(2, "0")}</span>
                </div>
                <p className="p-16 faq-a">{s.p}</p>
                {s.c && (
                  <div className="gr-code">
                    <code className="mono-12">{s.c}</code>
                    <Copy text={s.c} />
                  </div>
                )}
              </Reveal>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
