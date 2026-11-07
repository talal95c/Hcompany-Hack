import { Features, Footer, Hero, Nav, Pricing } from "./sections";
import { GhostCursor } from "./cursor";
import { Tour } from "./Tour";
import { SideRail } from "./SideRail";

export default function App() {
  return (
    <>
      <GhostCursor />
      <div className="site">
        <Nav />
        <main className="page">
          <Hero />
          <Pricing />
          <Features />
        </main>
        <Footer />
        <Tour />
        <SideRail />
        <div className="bottom-blur" aria-hidden />
      </div>
    </>
  );
}
