import { useCallback, useState } from "react";
import { Features, Footer, Hero, Nav, Pricing } from "./sections";
import { GhostCursor } from "./cursor";
import { Intro } from "./Intro";
import { Tour } from "./Tour";
import { Preloader } from "./Preloader";
import { SideRail } from "./SideRail";

export default function App() {
  const [loading, setLoading] = useState(true);
  const done = useCallback(() => setLoading(false), []);
  const [phase, setPhase] = useState<"intro" | "enter" | "done">("intro");
  return (
    <>
      <GhostCursor />
      {loading && <Preloader onDone={done} />}
      {phase !== "done" && <Intro onEnter={() => setPhase("enter")} onGone={() => setPhase("done")} />}
      {phase !== "intro" && (
        <div className="site site-enter">
          <Nav />
          <main className="page">
            <Hero />
            <Pricing />
            <Features />
          </main>
          <Footer />
          {phase === "done" && <Tour />}
          <SideRail />
          <div className="bottom-blur" aria-hidden />
          <div className="vhs-in" aria-hidden>
            <span className="vhs-band" />
            <span className="vhs-band vhs-band--2" />
            <span className="vhs-osd">PLAY ►<em>SP 0:00:01</em></span>
          </div>
        </div>
      )}
    </>
  );
}
