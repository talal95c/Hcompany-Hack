import { useEffect, useState } from "react";
import { Footer, Nav } from "./sections";
import { GhostCursor } from "./cursor";
import { Tour } from "./Tour";
import { SideRail } from "./SideRail";
import { Story } from "./Story";
import { Launch } from "./Launch";

export default function App() {
  const [hash, setHash] = useState(location.hash);
  useEffect(() => {
    const f = () => setHash(location.hash);
    addEventListener("hashchange", f);
    return () => removeEventListener("hashchange", f);
  }, []);
  if (hash === "#/launch")
    return (
      <>
        <GhostCursor />
        <Launch />
      </>
    );
  return (
    <>
      <GhostCursor />
      <div className="site">
        <Nav />
        <main className="page">
          <Story />
        </main>
        <Footer />
        <Tour />
        <SideRail />
        <div className="bottom-blur" aria-hidden />
      </div>
    </>
  );
}
