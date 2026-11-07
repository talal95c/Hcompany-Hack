import { useEffect, useState } from "react";
import { FaqInsights, Footer, GET_RIO, Hero, Nav, Pricing } from "./sections";
import { GetRio } from "./GetRio";

export default function App() {
  const [hash, setHash] = useState(location.hash);
  useEffect(() => {
    const f = () => setHash(location.hash);
    addEventListener("hashchange", f);
    return () => removeEventListener("hashchange", f);
  }, []);
  const getRio = hash === GET_RIO;
  useEffect(() => {
    if (!getRio && hash.length > 1) document.getElementById(hash.slice(1))?.scrollIntoView();
  }, [getRio, hash]);
  return (
    <>
      <Nav />
      <main className="page">
        {getRio ? (
          <GetRio />
        ) : (
          <>
            <Hero />
            <Pricing />
            <FaqInsights />
          </>
        )}
      </main>
      <Footer />
    </>
  );
}
