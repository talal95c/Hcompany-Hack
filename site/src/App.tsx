import { useState } from "react";
import { Footer, Hero, Nav, Pricing } from "./sections";
import { GhostCursor } from "./cursor";
import { Intro } from "./Intro";
import { Tour } from "./Tour";

export default function App() {
  const [phase, setPhase] = useState<"intro" | "enter" | "done">("intro");
  return (
    <>
      <GhostCursor />
      {phase !== "done" && <Intro onEnter={() => setPhase("enter")} onGone={() => setPhase("done")} />}
      {phase !== "intro" && (
        <div className="site site-enter">
          <Nav />
          <main className="page">
            <Hero />
            <Pricing />
          </main>
          <Footer />
          {phase === "done" && <Tour />}
        </div>
      )}
    </>
  );
}
