import { useEffect } from "react";
import { FaqInsights, Footer, Hero, Nav, Pricing } from "./sections";
import { Teams } from "./Teams";
import { UseCases } from "./usecases/UseCases";

export default function App() {
  useEffect(() => {
    // The install guide moved to the app; old links land on the page.
    if (location.hash === "#/get-rio") location.replace(`${location.pathname}#top`);
  }, []);
  return (
    <>
      <Nav />
      <main className="page">
        <Hero />
        <UseCases />
        <Teams />
        <Pricing />
        <FaqInsights />
      </main>
      <Footer />
    </>
  );
}
