import { FaqInsights, Footer, Hero, Nav, Pricing } from "./sections";

export default function App() {
  return (
    <>
      <Nav />
      <main className="page">
        <Hero />
        <Pricing />
        <FaqInsights />
      </main>
      <Footer />
    </>
  );
}
