import { About, Capabilities, FaqInsights, Footer, Hero, Nav, Pricing, Process, Video, Vision, Works } from "./sections";

export default function App() {
  return (
    <>
      <Nav />
      <main className="page">
        <Hero />
        <About />
        <Works />
        <div className="dark-zone">
          <Capabilities />
          <Vision />
        </div>
        <div className="dark-zone">
          <Video />
          <Process />
        </div>
        <Pricing />
        <FaqInsights />
      </main>
      <Footer />
    </>
  );
}
