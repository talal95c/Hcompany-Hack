import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  asset,
  Asterisk,
  BigMarquee,
  Btn,
  CountUp,
  EASE,
  Icon,
  Label,
  Marquee,
  PillLogo,
  Reveal,
  ScrollRevealText,
  Ticker,
} from "./ui";

const LOGOS = [
  "FIkeNB0CMpKHgxqL0a3aPHKlAyQ.png",
  "nJbNnh8E8FlHfzjwzNY6HTfjGnE.png",
  "3EwtMm1CTn3V13Xu2ufZVUnW4.png",
  "C7otSLQhZagCjkAC4M6MX1Ns.png",
  "PNxA5d1umCQiNSezotkgCnArwqU.png",
];

/* ---------------- Nav ---------------- */

export function Nav() {
  const links = ["Works", "Services", "Insights", "Pricing", "Company"];
  const ids = ["works", "services", "insights", "pricing", "company"];
  return (
    <motion.header
      className="nav"
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.8, ease: EASE, delay: 0.1 }}
    >
      <nav className="nav-pill">
        <a href="#top" className="nav-logo" aria-label="Home">
          <PillLogo size="md" />
        </a>
        {links.map((l, i) => (
          <a key={l} href={`#${ids[i]}`} className="nav-link">
            <span data-label={l}>{l}</span>
          </a>
        ))}
      </nav>
      <Btn label="Hire Team" variant="light" size="sm" href="#contact" className="nav-cta" />
    </motion.header>
  );
}

/* ---------------- Hero ---------------- */

export function Hero() {
  const up = (d: number) => ({
    initial: { opacity: 0, y: 40, filter: "blur(10px)" },
    animate: { opacity: 1, y: 0, filter: "blur(0px)" },
    transition: { duration: 1, ease: EASE, delay: d },
  });
  return (
    <section className="hero" id="top">
      <div className="hero-card">
        <motion.img
          className="hero-bg"
          src={asset("PXNhr4LbXoJRWLAHfzNTYjvdR5Y.png")}
          alt=""
          initial={{ scale: 1.08, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 1.6, ease: EASE }}
        />
        <div className="hero-shade" />
        <div className="hero-content">
          <h1 className="h-hero">
            <motion.span className="hero-l1" {...up(0.2)}>
              Scale your ideas.
            </motion.span>
            <motion.span className="hero-l2" {...up(0.32)}>
              Build with AI.
            </motion.span>
          </h1>
          <motion.p className="p-16 hero-sub" {...up(0.44)}>
            Deploy custom neural agents, LLMs, and automation in one seamless flow.
          </motion.p>
          <motion.div {...up(0.56)}>
            <Btn label="Start Build" href="#contact" />
          </motion.div>
        </div>
        <motion.a href="#services" className="brain-card" {...up(0.7)}>
          <img className="brain-glow" src={asset("i8M81i0PeB8FDxgPt1GPDik2kA.jpg")} alt="" />
          <div className="brain-img">
            <video src={asset("digital-brain.mp4")} poster={asset("i8M81i0PeB8FDxgPt1GPDik2kA.jpg")} autoPlay muted loop playsInline />
          </div>
          <div className="brain-meta">
            <div>
              <p className="brain-title">Digital Brain</p>
              <p className="p-12 brain-sub">// Model v4.0.2</p>
            </div>
            <Icon name="arrowRightLight" size={26} className="brain-arrow" />
          </div>
        </motion.a>
        <motion.div className="hero-bottom" {...up(0.85)}>
          <p className="p-14 hero-trust">
            +2,400 active deployments and 8,200 brands trust our high-performance architecture.
          </p>
          <Marquee duration={28} className="hero-logos">
            {LOGOS.map((l) => (
              <img key={l} src={asset(l)} alt="" />
            ))}
          </Marquee>
        </motion.div>
      </div>
    </section>
  );
}

/* ---------------- About / bento ---------------- */

function Ticks() {
  const n = 40;
  return (
    <svg className="ticks" viewBox="0 0 200 200" aria-hidden>
      {Array.from({ length: n }, (_, i) => {
        const a = (i / n) * Math.PI * 2 - Math.PI / 2;
        const x1 = 100 + Math.cos(a) * 74;
        const y1 = 100 + Math.sin(a) * 74;
        const x2 = 100 + Math.cos(a) * 100;
        const y2 = 100 + Math.sin(a) * 100;
        return (
          <line
            key={i}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            strokeWidth={1.5}
            strokeLinecap="round"
            style={{ animationDelay: `${(i / n) * 2.4}s` }}
          />
        );
      })}
    </svg>
  );
}

export function About() {
  return (
    <section className="about">
      <div className="about-card">
        <ScrollRevealText
          className="h-reveal about-title"
          text="Automate the manual, accelerate the future. Our custom AI solutions deliver measurable growth and operational excellence."
        />
        <Reveal as="p" className="p-16 about-sub">
          Empowering teams with intelligent tools that turn complex data into actionable business outcomes daily.
        </Reveal>
        <div className="bento">
          <Reveal className="bento-dark" delay={0}>
            <span className="bento-icon">
              <Icon name="trendUp" size={30} />
            </span>
            <p className="stat-num">
              <CountUp to={45} prefix="$" suffix="M" />
            </p>
            <p className="p-14 bento-foot">Revenue generated for our clients through AI-led optimizations.</p>
          </Reveal>
          <div className="bento-col">
            <Reveal className="bento-dashed" delay={0.08}>
              <div className="avatars">
                {["D3gag0wTRQzvb6CCfJkTShmXTPI.jpg", "9AvPLCB2PkQCEoFgNdwvDaIaGGI.jpg", "pktP7O1JHzk75RWizEsb0jRSjk.jpg", "2418vQBGZ7CPVHaaIlQ5wuUyr4.jpg"].map((a) => (
                  <img key={a} src={asset(a)} alt="" />
                ))}
              </div>
              <p className="p-14 agents">
                <strong>15,400</strong> active agents
              </p>
            </Reveal>
            <Reveal className="bento-small" delay={0.16}>
              <p className="stat-num stat-dark">
                <CountUp to={5} suffix="x" />
              </p>
              <p className="p-14 muted-6">Faster speed to market.</p>
            </Reveal>
          </div>
          <Reveal className="bento-grey" delay={0.24}>
            <div className="ticks-wrap">
              <Ticks />
              <span className="ticks-core">
                <Icon name="rocket" size={24} />
              </span>
            </div>
            <div>
              <h4 className="h4-20">Inference speed</h4>
              <p className="p-14 muted-6">Real-time processing for enterprise-grade deployments.</p>
            </div>
          </Reveal>
          <Reveal className="bento-white" delay={0.32}>
            <div className="bento-quote-top">
              <Icon name="quotes" size={40} />
              <img src={asset("C7otSLQhZagCjkAC4M6MX1Ns.png")} alt="Cigna" className="bento-logo" />
            </div>
            <div>
              <p className="bento-quote">
                The custom LLM they built for us reduced our support tickets by 80% while increasing user satisfaction.
              </p>
              <p className="p-14 muted-6 bento-cite">CTO, Cigna</p>
            </div>
          </Reveal>
        </div>
        <Ticker />
      </div>
    </section>
  );
}

/* ---------------- Works ---------------- */

const WORKS = [
  { tag: "Healthcare AI", logo: "yV2zGDqTwUzGafOnvA53MLQkM.png", img: "sZxYLpvH56E3RznKPcnAPYlPvo.jpg", s: ["$45M+", "700%", "41x", "84"] },
  { tag: "Healthcare", logo: "CLpXi6HupcG6YYxVylXG8rj7eo4.png", img: "4GMiBYbu9SI4dXo9ENcqlNA.jpg", s: ["$62M+", "450%", "32x", "91"] },
  { tag: "Healthcare", logo: "RlGLod5QkyznR4SBy9PQw3raa80.png", img: "0g3E5eja3ueYAXkITtsy9quyYo.jpg", s: ["$82M+", "340%", "19x", "56"] },
  { tag: "Retail & Logistics", logo: "3ICxPpL7nA6WiDyreZSZlU70E8.png", img: "ZK0k9kMGgE21P7r3puSMYZ8548.jpg", s: ["$59M+", "215%", "73x", "28"] },
  { tag: "Cybersecurity", logo: "qA80rXn5OyEhaPlYKJ8gIEE6Ds.png", img: "LYQLqywSoqlHG7KLRJM70MIk.png", s: ["$94M+", "120%", "66x", "12"] },
];
const STAT_LABELS = ["Funds raised", "Social growth", "ATH ROI", "Partnerships"];

export function Works() {
  return (
    <div className="works-wrap" id="works">
      <section className="works">
        <BigMarquee word="Our Works" />
        <div className="works-grid">
          {WORKS.map((w, i) => (
            <div className="work-cell" key={i}>
              <Reveal className="work-card" delay={(i % 3) * 0.08}>
                <div className="work-top">
                  <span className="tag">{w.tag}</span>
                  <img className="work-logo" src={asset(w.logo)} alt="" />
                  <img className="work-img" src={asset(w.img)} alt="" />
                </div>
                <div className="work-stats">
                  {w.s.map((v, k) => (
                    <div className="work-stat" key={k}>
                      <p className="mono-16">{v}</p>
                      <p className="p-12 muted-7">{STAT_LABELS[k]}</p>
                    </div>
                  ))}
                </div>
              </Reveal>
            </div>
          ))}
          <div className="work-cell work-cell-empty" />
        </div>
      </section>
    </div>
  );
}

/* ---------------- Capabilities ---------------- */

const CAPS = [
  {
    n: "001",
    title: "Autonomous Agent Architecture Labs",
    body: "Architecting robust server environments and local LLM integrations to ensure data remains secure and local.",
    img: "WTuFQeqWgOcQVCks16yKxgDaefI.png",
  },
  {
    n: "002",
    title: "Autonomous Agentic Workflows",
    body: "Multi-step agents that plan, call your tools and hand off to humans only when judgement is required.",
    img: "liXydHdt7Kdt6VKUzzjSZwFJ4FA.png",
  },
  {
    n: "003",
    title: "Data Pipelines & RAG Systems",
    body: "Retrieval pipelines that keep every answer grounded in your own documents, versioned and auditable.",
    img: "WTuFQeqWgOcQVCks16yKxgDaefI.png",
  },
];

export function Capabilities() {
  const [open, setOpen] = useState(0);
  return (
    <section className="caps" id="services">
      <div className="caps-left">
        <div>
          <Label text="CAPABILITIES" pillFirst className="w-500" />
          <Reveal as="p" className="p-16 caps-sub">
            We bridge the gap between abstract machine learning and practical business utility through bespoke engineering.
          </Reveal>
        </div>
        <div>
          <Reveal as="h2" className="h2-54 caps-title">
            Tailored Intelligence for Modern Enterprises.
          </Reveal>
          <Reveal delay={0.1}>
            <Btn label="Start Build" variant="ghost" href="#contact" />
          </Reveal>
        </div>
      </div>
      <div className="caps-acc">
        {CAPS.map((c, i) => {
          const active = i === open;
          return (
            <motion.div
              key={c.n}
              className={`cap ${active ? "cap-open" : ""}`}
              layout
              transition={{ layout: { duration: 0.7, ease: EASE } }}
              onMouseEnter={() => setOpen(i)}
              onClick={() => setOpen(i)}
            >
              <img className="cap-grid" src={asset(active ? "qWpzthqQ4FGQWP39IeKgah1OP8.png" : "pEct5trUmjDYAblzuKYq2MpHaA.png")} alt="" />
              <span className="cap-num">{c.n}</span>
              <AnimatePresence initial={false}>
                {active ? (
                  <motion.div
                    key="open"
                    className="cap-body"
                    initial={{ opacity: 0, filter: "blur(8px)" }}
                    animate={{ opacity: 1, filter: "blur(0px)", transition: { delay: 0.25, duration: 0.6 } }}
                    exit={{ opacity: 0, transition: { duration: 0.15 } }}
                  >
                    <h3 className="h3-28">{c.title}</h3>
                    <p className="p-14l cap-text">{c.body}</p>
                    <img className="cap-iso" src={asset(c.img)} alt="" />
                  </motion.div>
                ) : (
                  <motion.span
                    key="closed"
                    className="cap-vertical"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1, transition: { delay: 0.3 } }}
                    exit={{ opacity: 0, transition: { duration: 0.1 } }}
                  >
                    {c.title}
                  </motion.span>
                )}
              </AnimatePresence>
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}

/* ---------------- Vision ---------------- */

function Corner({ className }: { className: string }) {
  return <span className={`corner ${className}`} aria-hidden />;
}

export function Vision() {
  const models = ["SMyO8DDP1JPIhoq2Ak1dNFDpGIo.png", "ss2Osfd5P1AGF1NpgQhGgyGabA.png", "fQ71Xa5nLv0lmW62RjPI68rMDcU.png", "Yhx5rRmY8EDv8iMIG0L554Xx3k.png"];
  return (
    <>
      <div className="vision-stack">
        <section className="vision" id="company">
          <Reveal className="vision-left">
            <div className="portrait">
              <img src={asset("jnIpVvHAXWiAGa8gLEmWtRuDwQ.png")} alt="Alexander Vacca" />
              <Corner className="c-tl" />
              <Corner className="c-tr" />
              <Corner className="c-br" />
              <Corner className="c-bl" />
            </div>
            <p className="mono-12 portrait-name">ALEXANDER VACCA</p>
            <p className="p-12 muted-w7">Founder &amp; Lead Engineer</p>
          </Reveal>
          <div className="vision-right">
            <Label text="OUR VISION" className="w-500" />
            <ScrollRevealText
              className="h-reveal h-reveal-tight vision-title"
              text="We believe that AI should not just automate tasks, but amplify the creative and strategic potential of every human."
            />
            <Reveal as="p" className="p-16 vision-sub">
              By merging technical rigor with intuitive design, we build systems that don't just solve problems—they create entirely new opportunities for growth.
            </Reveal>
          </div>
        </section>
        <div className="vision-strip" />
      </div>
      <section className="engineering">
        <div className="eng-row">
          <Reveal as="p" className="mono-12l eng-text">
            ENGINEERING SYSTEMS THAT SCALE WITH YOUR AMBITION. WE LEVERAGE INDUSTRY-LEADING MODELS TO DEPLOY CUSTOM NEURAL SOLUTIONS TAILORED TO YOUR STACK.
          </Reveal>
          <Reveal className="models" delay={0.1}>
            {models.map((m) => (
              <span key={m} className="model">
                <img src={asset(m)} alt="" />
              </span>
            ))}
          </Reveal>
          <Reveal delay={0.2}>
            <Btn label="Digital Brain v4.0.2" variant="ghost" href="#top" />
          </Reveal>
        </div>
        <div className="features">
          <Reveal className="feature" delay={0}>
            <div className="feat-icon feat-search">
              <svg viewBox="0 0 30.956 44.192" width={36} height={52}>
                <path
                  fill="#fff"
                  d="M 5.587 1.427 C 10.875 -1.564 17.587 0.299 20.577 5.587 C 23.402 10.582 21.894 16.844 17.262 20.044 L 21.222 27.048 L 22.096 26.555 L 30.956 42.223 L 27.475 44.192 L 18.613 28.524 L 19.481 28.033 L 15.521 21.028 C 10.392 23.346 4.251 21.41 1.427 16.417 C -1.563 11.129 0.299 4.417 5.587 1.427 Z M 18.836 6.571 C 16.389 2.245 10.898 0.721 6.571 3.168 C 2.245 5.615 0.721 11.106 3.168 15.432 C 5.615 19.759 11.106 21.283 15.432 18.836 C 19.759 16.389 21.283 10.898 18.836 6.571 Z"
                  transform="rotate(-30 15 22)"
                />
              </svg>
              <span className="sparkle s1" />
              <span className="sparkle s2" />
            </div>
            <p className="p-15 feat-text">Semantic vector search for hyper-accurate retrieval</p>
          </Reveal>
          <Reveal className="feature" delay={0.08}>
            <div className="feat-icon feat-orbit">
              <span className="orbit-ring" />
              <span className="orbit-ring r2" />
              <span className="orbit-dot" />
            </div>
            <p className="p-15 feat-text">Unified data lakes for expansive model context.</p>
          </Reveal>
          <Reveal className="feature" delay={0.16}>
            <div className="feat-icon feat-bars">
              {[0, 1, 2, 3].map((k) => (
                <span key={k} className="bar" style={{ animationDelay: `${k * 0.25}s` }}>
                  <i />
                </span>
              ))}
            </div>
            <p className="p-15 feat-text">Token-optimized flows for high speed processing</p>
          </Reveal>
          <Reveal className="feature" delay={0.24}>
            <div className="feat-icon feat-langs">
              <span className="lang-caret" />
              <Marquee duration={8} className="lang-marquee">
                {["ZH", "HI", "ES", "FR", "AR", "BN", "PT", "RU", "EN", "DE"].map((l) => (
                  <span key={l}>{l}</span>
                ))}
              </Marquee>
            </div>
            <p className="p-15 feat-text">Global LLM deployment. Support for 95+ languages.</p>
          </Reveal>
        </div>
      </section>
    </>
  );
}

/* ---------------- Experiences (testimonials) ---------------- */

const TESTI = [
  { name: "MARCUS CHENG", role: "Head of AI, Aetna", avatar: "w2hyXovpoCcfHZkjR4Hmr53RA5o.jpg", logo: "3EwtMm1CTn3V13Xu2ufZVUnW4.png", q: "The custom agentic workflows they built reduced our manual data entry by 90%, saving us hundreds of hours weekly." },
  { name: "DAVID ROSSI", role: "Lead Dev, Cigna", avatar: "rLkyXpp1TSaADDj0EYjy9c8uw.jpg", logo: "yV2zGDqTwUzGafOnvA53MLQkM.png", q: "Their team didn't just provide tools; they provided a roadmap for AI integration that actually makes sense for ROI." },
  { name: "SARAH JENKINS", role: "CTO, Anthem Group", avatar: "IIK9uqdpvVqpPgAHuhf8s9r4Ee4.jpg", logo: "RlGLod5QkyznR4SBy9PQw3raa80.png", q: "A game-changer for our R&D. The neural infrastructure is robust, secure, and perfectly tailored to our niche stack." },
  { name: "ELENA VANCE", role: "VP Eng, UnitedHealth", avatar: "QHChEEbpWFuUCrhS6zqN5BK4Rr0.jpg", logo: "qA80rXn5OyEhaPlYKJ8gIEE6Ds.png", q: "Incredible technical depth. They handled our complex RAG implementation with ease and delivered ahead of schedule." },
];
const STEP = 301;

export function Experiences() {
  const n = TESTI.length;
  const [idx, setIdx] = useState(n);
  const [instant, setInstant] = useState(false);
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    if (paused) return;
    const t = setInterval(() => setIdx((i) => i + 1), 3500);
    return () => clearInterval(t);
  }, [paused]);
  const settle = () => {
    if (idx >= 2 * n || idx < n) {
      setInstant(true);
      setIdx((i) => ((i % n) + n) % n + n);
      requestAnimationFrame(() => requestAnimationFrame(() => setInstant(false)));
    }
  };
  const cards = [...TESTI, ...TESTI, ...TESTI, ...TESTI];
  return (
    <section className="exp">
      <BigMarquee word="Experiences" />
      <div className="exp-head">
        <Reveal as="p" className="p-16 exp-sub">
          Empowering global enterprises through bespoke neural architectures and autonomous agentic workflows.
        </Reveal>
        <Reveal className="exp-ctrl" delay={0.1}>
          <button type="button" aria-label="Previous" onClick={() => setIdx((i) => i - 1)}>
            <img src={asset("6tTbkXggWgQCAJ4DO2QEdXXmgM.svg")} alt="" />
          </button>
          <button type="button" aria-label="Next" onClick={() => setIdx((i) => i + 1)}>
            <img src={asset("11KSGbIZoRSg4pjdnUoif6MKHI.svg")} alt="" />
          </button>
        </Reveal>
      </div>
      <div className="exp-viewport" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
        <motion.ul
          className="exp-track"
          animate={{ x: -idx * STEP }}
          transition={instant ? { duration: 0 } : { duration: 0.8, ease: EASE }}
          onAnimationComplete={settle}
        >
          {cards.map((t, i) => (
            <li key={i} className="t-card">
              <div className="t-overlay" />
              <div className="t-pill">
                <img className="t-avatar" src={asset(t.avatar)} alt="" />
                <img className="t-logo" src={asset(t.logo)} alt="" />
              </div>
              <div className="t-quote">
                <svg viewBox="0 0 24 24" width={24} height={24} className="t-mark" aria-hidden>
                  {[14, 2].map((x) => (
                    <path
                      key={x}
                      transform={`translate(${x} 3)`}
                      fill="none"
                      strokeWidth={1.5}
                      stroke="currentColor"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M 1 0 L 7 0 C 7.552 0 8 0.448 8 1 L 8 9.5 C 8 10.052 7.552 10.5 7 10.5 L 4.5 10.5 C 4.224 10.5 4 10.724 4 11 L 4 12 C 4 13.105 4.895 14 6 14 L 7 14 C 7.552 14 8 14.448 8 15 L 8 17 C 8 17.552 7.552 18 7 18 L 6 18 C 2.686 18 0 15.314 0 12 L 0 1 C 0 0.448 0.448 0 1 0 Z"
                    />
                  ))}
                </svg>
                <p className="t-text">{t.q}</p>
              </div>
              <div className="person">
                <span className="person-bar" />
                <div>
                  <h5 className="plex-13">{t.name}</h5>
                  <p className="p-12 muted-7">{t.role}</p>
                </div>
              </div>
            </li>
          ))}
        </motion.ul>
      </div>
      <Ticker />
    </section>
  );
}

/* ---------------- Video ---------------- */

export function Video() {
  const [playing, setPlaying] = useState(false);
  return (
    <section className="video">
      <motion.img
        className="video-bg"
        src={asset("Y43VBCJU98vH9ESfLTOmhYvVKjY.jpg")}
        alt=""
        initial={{ scale: 1.12 }}
        whileInView={{ scale: 1 }}
        viewport={{ once: true }}
        transition={{ duration: 1.6, ease: EASE }}
      />
      <div className="video-top">
        <Reveal as="p" className="p-16 video-sub">
          Exploring the intersection of human creativity and machine logic to redefine what's possible in the digital age.
        </Reveal>
        <Reveal className="watch-pill" delay={0.1}>
          <Icon name="timer" size={24} />
          <span className="p-14">2mins watch</span>
        </Reveal>
      </div>
      <button type="button" className={`play ${playing ? "is-playing" : ""}`} aria-label="Play video" onClick={() => setPlaying((p) => !p)}>
        <span className="play-ring" />
        <svg viewBox="0 0 38 32" width={32} height={38} aria-hidden style={{ transform: "rotate(90deg)" }}>
          <path d="M 19 4 L 35.454 28 L 2.546 28 Z" fill="#fff" />
        </svg>
      </button>
      <div className="video-bottom">
        <Reveal as="h2" className="h2-54 video-title">
          Intelligence by Design.
        </Reveal>
        <PillLogo size="lg" light />
      </div>
    </section>
  );
}

/* ---------------- Process + Team ---------------- */

const STEPS = [
  { t: "Comprehensive Strategic Audit", tag: "Audit", d: "We perform a deep-layer analysis of your current technical stack and fragmented data silos to identify high-impact AI opportunities that align with your core business objectives and ROI targets." },
  { t: "Custom Architecture Design", tag: "Design", d: "We blueprint the models, retrieval layers and integrations your use case needs, choosing every component for accuracy, latency and total cost of ownership." },
  { t: "Rapid Prototype Development", tag: "Build", d: "Working prototypes ship in weeks, not quarters, tested against your real data so stakeholders can judge impact before the full rollout." },
  { t: "Enterprise Scale Deployment", tag: "Scale", d: "We harden, monitor and scale the system across your organisation, with observability, access control and continuous evaluation built in." },
];

const TEAM = [
  { name: "SARAH JENKINS", role: "Head of Machine Learning", img: "OrsgMbvM0AZiEvhgHFZUJM2g.png", bio: "Our focus remains on the ethical deployment of large-scale models. We don't just optimize for performance; we ensure every neural architecture we build is interpretable, secure, and ready for enterprise-grade scrutiny." },
  { name: "MARCUS CHENG", role: "Principal Design Director", img: "BbqpJjnldDFDulJFBarqs7wJpFk.png", bio: "AI shouldn't feel like a black box. My goal is to design intuitive interfaces that make complex data actionable, ensuring that the human-machine collaboration is seamless, visually stunning, and highly efficient for users." },
  { name: "ELENA VANCE", role: "Lead Cognitive Scientist", img: "8k7FcfFSjgocOslFu94p0ih1UY.png", bio: "We study the cognitive friction between AI output and human decision-making. By applying behavioral science to our agentic workflows, we create tools that naturally align with how your best employees actually think and work." },
  { name: "DAVID ROSSI", role: "Infrastructure Architect", img: "FnCj7jgTvcpKSt0CUVIqbyiS9o.png", bio: "Latency is the enemy of adoption. I architect the backbone of our solutions to ensure that even the most complex RAG systems deliver sub-second responses, maintaining 99.9% uptime across distributed global compute clusters." },
];

export function Process() {
  const [open, setOpen] = useState(0);
  return (
    <div className="process-wrap">
      <section className="process">
        <Label text="OUR PROCESS" />
        <Reveal as="h2" className="h2-54 process-title">
          From raw data to refined intelligence. Our iterative deployment cycle.
        </Reveal>
        <div className="process-grid">
          <Reveal className="process-art">
            <img className="process-grid-bg" src={asset("QRyW2z7jtn8Iu8Ohz7dYmwxFJo.png")} alt="" />
            <motion.img
              key={open}
              className="process-iso"
              src={asset("liXydHdt7Kdt6VKUzzjSZwFJ4FA.png")}
              alt=""
              initial={{ opacity: 0, scale: 0.92, rotate: -4 }}
              animate={{ opacity: 1, scale: 1, rotate: 0 }}
              transition={{ duration: 0.8, ease: EASE }}
            />
          </Reveal>
          <div className="steps">
            {STEPS.map((s, i) => {
              const active = open === i;
              return (
                <motion.div
                  layout
                  key={s.t}
                  className={`step ${active ? "step-open" : ""}`}
                  onClick={() => setOpen(i)}
                  onMouseEnter={() => setOpen(i)}
                  transition={{ layout: { duration: 0.6, ease: EASE } }}
                >
                  <motion.p layout="position" className="p-14l step-n">
                    // 0{i + 1}
                  </motion.p>
                  <div className="step-main">
                    <motion.div layout="position" className="step-head">
                      <p className="step-t">{s.t}</p>
                      <AnimatePresence>
                        {active && (
                          <motion.span className="tag tag-sm" initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}>
                            {s.tag}
                          </motion.span>
                        )}
                      </AnimatePresence>
                    </motion.div>
                    <AnimatePresence initial={false}>
                      {active && (
                        <motion.p
                          className="p-15 step-d"
                          initial={{ opacity: 0, filter: "blur(6px)" }}
                          animate={{ opacity: 1, filter: "blur(0px)", transition: { delay: 0.2, duration: 0.5 } }}
                          exit={{ opacity: 0, transition: { duration: 0.1 } }}
                        >
                          {s.d}
                        </motion.p>
                      )}
                    </AnimatePresence>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
        <div className="process-foot">
          <Reveal as="p" className="mono-12l process-note">
            WE DON'T JUST SHIP CODE; WE SHIP COMPETITIVE ADVANTAGES. EVERY STEP IS DESIGNED TO ENSURE YOUR AI INFRASTRUCTURE IS FUTURE-PROOF AND SCALABLE.
          </Reveal>
          <Reveal delay={0.1}>
            <Btn label="Build Now" variant="ghost" href="#contact" />
          </Reveal>
        </div>

        <Reveal as="h2" className="h-collective">
          We are a collective of engineers, designers, and researchers dedicated to the frontier of AI.
        </Reveal>
        <div className="story">
          <Reveal as="p" className="p-16">
            Bridging the gap between academic research and commercial deployment with precision engineering.
          </Reveal>
          <Reveal delay={0.1}>
            <Btn label="Our Story" variant="ghost" href="#company" />
          </Reveal>
        </div>
        <div className="team">
          {TEAM.map((m, i) => (
            <Reveal className="member" key={m.name} delay={i * 0.08}>
              <div className="member-photo">
                <img src={asset(m.img)} alt={m.name} />
                <PillLogo size="sm" light />
              </div>
              <div className="person on-dark">
                <span className="person-bar" />
                <div>
                  <h5 className="plex-13">{m.name}</h5>
                  <p className="p-12 muted-w5">{m.role}</p>
                </div>
              </div>
              <div className="member-bio">
                <div className="bio-social">
                  <a href="https://x.com" aria-label="X">
                    <Icon name="xFill" size={15} />
                  </a>
                  <a href="https://github.com" aria-label="GitHub">
                    <Icon name="github" size={15} />
                  </a>
                </div>
                <p className="bio-text">{m.bio}</p>
                <div className="person">
                  <span className="person-bar" />
                  <div>
                    <p className="plex-13">{m.name}</p>
                    <p className="plex-11">{m.role}</p>
                  </div>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>
    </div>
  );
}

/* ---------------- Pricing ---------------- */

const PLANS = [
  { name: "Core", price: 495, tagline: "Automate your repetitive tasks.", f: ["3 Automation Flows", "Standard RAG Support", "1 Admin Seat", "Discord Support"] },
  { name: "Growth", price: 1250, tagline: "Advanced agentic workflows.", f: ["10 Automation Flows", "Vector DB Hosting", "5 Admin Seats", "Priority Email"] },
  { name: "Pro", price: 2900, tagline: "Custom neural architecture.", f: ["Unlimited Flows", "Custom Fine-Tuning", "15 Admin Seats", "24/7 Slack Connect"], dark: true },
  { name: "Scale", price: 7500, tagline: "Enterprise infrastructure.", f: ["Full Neural Stack", "On-Premise LLMs", "Unlimited Seats", "Dedicated Engineer"] },
];

function Price({ value }: { value: number }) {
  return (
    <AnimatePresence mode="popLayout" initial={false}>
      <motion.span
        key={value}
        initial={{ opacity: 0, y: 20, filter: "blur(6px)" }}
        animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
        exit={{ opacity: 0, y: -20, filter: "blur(6px)" }}
        transition={{ duration: 0.45, ease: EASE }}
        className="price-val"
      >
        ${value.toLocaleString("en-US")}
      </motion.span>
    </AnimatePresence>
  );
}

export function Pricing() {
  const [annual, setAnnual] = useState(true);
  return (
    <section className="pricing" id="pricing">
      <BigMarquee word="Pricing" />
      <div className="pricing-head">
        <Reveal className="toggle-row">
          <button type="button" className="p-14l toggle-label" onClick={() => setAnnual(false)}>
            Monthly
          </button>
          <button type="button" className={`toggle ${annual ? "on" : ""}`} aria-label="Toggle annual billing" onClick={() => setAnnual((a) => !a)}>
            <motion.span className="knob" layout transition={{ type: "spring", stiffness: 500, damping: 32 }}>
              <Icon name="check" size={16} />
            </motion.span>
          </button>
          <button type="button" className="p-14l toggle-label" onClick={() => setAnnual(true)}>
            Annually <span className="p-12 muted-6">(Save 20%)</span>
          </button>
        </Reveal>
        <Reveal as="p" className="p-16 pricing-sub">
          Flexible intelligence tiers designed to scale alongside your business. No hidden costs, just high-performance results.
        </Reveal>
      </div>
      <Reveal className="plans">
        {PLANS.map((p) => (
          <div key={p.name} className={`plan ${p.dark ? "plan-dark" : ""}`}>
            <img className="plan-wave" src={asset("lu9xdgbj7zB5GkewV6UCW9Y68.jpg")} alt="" />
            <div className="plan-top">
              <h6 className="plan-name">{p.name}</h6>
              <p className="plan-price">
                <Price value={annual ? p.price : Math.round(p.price / 0.8 / 5) * 5} />
                <span className="p-14l plan-mo">/mo</span>
              </p>
              <p className="p-14l">USD Billed {annual ? "Annually" : "Monthly"}</p>
            </div>
            <div className="plan-band">
              <p className="plan-tag">{p.tagline}</p>
              <Btn label="Get started" size="sm" variant={p.dark ? "light" : "ghost"} href="#contact" />
            </div>
            <ul className="plan-feats">
              {p.f.map((f) => (
                <li key={f} className="p-14l">
                  {f}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </Reveal>
      <Ticker />
    </section>
  );
}

/* ---------------- FAQ + Insights ---------------- */

const FAQ = [
  { q: "How do you ensure our data remains secure?", a: "We utilize SOC2-compliant local vector databases and on-premise LLM hosting to ensure your proprietary data never leaves your infrastructure." },
  { q: "What is the typical deployment timeline?", a: "A focused pilot ships in four to six weeks; enterprise-wide rollouts typically take one to three months depending on integrations." },
  { q: "Can we integrate with our existing CRM?", a: "Yes. We connect to Salesforce, HubSpot, Dynamics and custom CRMs through their APIs, so agents read and write where your teams already work." },
  { q: "Do you provide model fine-tuning?", a: "We fine-tune open and commercial models on your domain data, with evaluation suites that prove the gain before anything reaches production." },
  { q: "How do you calculate ROI for automation?", a: "We baseline hours, error rates and cycle times before launch, then track the same metrics live so every dollar saved is measured, not estimated." },
  { q: "Do we own the custom code you build?", a: "Yes. All code, prompts, pipelines and fine-tuned weights built for you are transferred to your organisation at handover." },
  { q: "What models do you specialize in?", a: "GPT, Claude, Gemini, Llama and Mistral families, plus smaller task-specific models when latency or cost matters most." },
];

const ARTICLES = [
  { cat: "Transformation", title: "The Sovereign Cloud: Why On-Premise AI is the Future of Data Privacy", body: "Explore how federated learning and private hosting are allowing firms to innovate without risking security.", author: "Frank Joel", img: "862JbA3xEJjbdSDVyKEwOZ0f2g.jpeg" },
  { cat: "Architecture", title: "The Architecture of Autonomy: Scaling AI Within Legacy Frameworks", body: "A comprehensive guide on integrating custom machine learning models into complex enterprise environments.", author: "Damilola Manuel", img: "YKAEpvQFebP2OETEJDVNip8UTg.jpeg", flip: true },
  { cat: "Privacy", title: "Human-Centric Automation: Designing AI That Empowers Your Workforce", body: "Why the most successful AI implementations focus on augmenting human talent rather than simply replacing it.", author: "Deborah Reachie", img: "egDVD5dc2AvUIZKG0seuGXtH0.jpeg" },
];

export function FaqInsights() {
  const [open, setOpen] = useState(0);
  return (
    <section className="faq-wrap" id="insights">
      <div className="faq-card">
        <div className="faq">
          <div className="faq-left">
            <div>
              <Label text="COMMON QUERIES" pillFirst light={false} className="w-500" />
              <Reveal as="p" className="p-16 faq-sub">
                Find answers to technical specifications, deployment timelines, and our data security protocols.
              </Reveal>
            </div>
            <div>
              <Reveal as="h2" className="h2-54 faq-title">
                Everything you need to know about our AI.
              </Reveal>
              <Reveal delay={0.1}>
                <Btn label="Contact Support" href="#contact" />
              </Reveal>
            </div>
          </div>
          <div className="faq-list">
            {FAQ.map((f, i) => {
              const active = open === i;
              return (
                <Reveal key={f.q} delay={i * 0.05} y={20}>
                  <motion.div layout className="faq-item" onClick={() => setOpen(active ? -1 : i)} transition={{ layout: { duration: 0.5, ease: EASE } }}>
                    <motion.div layout="position" className="faq-q">
                      <h4 className="h4-20 faq-h">{f.q}</h4>
                      <motion.span className="faq-ico" animate={{ rotate: active ? 0 : 45 }} transition={{ duration: 0.4, ease: EASE }}>
                        <svg viewBox="0 0 256 256" width={16} height={16} fill="currentColor" aria-hidden>
                          <path d="M208.49,191.51a12,12,0,0,1-17,17L128,145,64.49,208.49a12,12,0,0,1-17-17L111,128,47.51,64.49a12,12,0,0,1,17-17L128,111l63.51-63.52a12,12,0,0,1,17,17L145,128Z" />
                        </svg>
                      </motion.span>
                    </motion.div>
                    <AnimatePresence initial={false}>
                      {active && (
                        <motion.p
                          className="p-16 faq-a"
                          initial={{ opacity: 0, filter: "blur(6px)" }}
                          animate={{ opacity: 1, filter: "blur(0px)", transition: { delay: 0.15, duration: 0.4 } }}
                          exit={{ opacity: 0, transition: { duration: 0.1 } }}
                        >
                          {f.a}
                        </motion.p>
                      )}
                    </AnimatePresence>
                  </motion.div>
                </Reveal>
              );
            })}
          </div>
        </div>

        <BigMarquee word="Insights" star="#ffffff" />
        <div className="insights-head">
          <Reveal as="p" className="p-16">
            A curated repository of technical frameworks, model benchmarks, and strategic guides for leaders navigating the integration of custom neural architectures.
          </Reveal>
          <Reveal delay={0.1}>
            <Btn label="All articles" href="#insights" />
          </Reveal>
        </div>
        <div className="articles">
          {ARTICLES.map((a, i) => (
            <Reveal key={a.title} className={`article ${a.flip ? "flip" : ""}`} delay={i * 0.08}>
              <a href="#insights" className="article-link">
                <div className="article-img">
                  <img src={asset(a.img)} alt="" />
                </div>
                <div className="article-body">
                  <div>
                    <p className="mono-12">{a.cat}</p>
                    <h4 className="h4-20 article-title">{a.title}</h4>
                    <p className="p-14l">{a.body}</p>
                  </div>
                  <div className="article-foot">
                    <div>
                      <p className="p-14">Written by</p>
                      <p className="p-12">{a.author}</p>
                    </div>
                    <span className="article-go">
                      <Icon name="arrowRight" size={25} />
                    </span>
                  </div>
                </div>
              </a>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------------- Footer ---------------- */

export function Footer() {
  const cols = [
    { h: "Quick Links", l: ["Home", "Digital Brain", "Projects", "Articles"] },
    { h: "Company", l: ["About Us", "Contact Us", "Book A Call", "More Templates"] },
    { h: "Policies", l: ["Terms & Conditions", "Privacy Policy"] },
  ];
  const socials = [
    { n: "xLogo" as const, href: "https://x.com" },
    { n: "linkedin" as const, href: "https://www.linkedin.com" },
    { n: "youtube" as const, href: "https://youtube.com" },
    { n: "instagram" as const, href: "https://instagram.com" },
  ];
  return (
    <footer className="footer" id="contact">
      <img className="footer-bg" src={asset("v2cZIMtgjEII7EpDnUDGGgCyuiQ.png")} alt="" />
      <div className="footer-inner">
        <div className="footer-left">
          <PillLogo size="md" light />
          <img className="footer-logo" src={asset("8AjRJ3fmfVsGAO1xyzDT2NbfkE8.png")} alt="Spartan" />
          <p className="p-15 footer-text">
            Lorem ipsum dolor sit amet, consectetur adipiscing elit. Etiam ac ultrices massa. Vivamus faucibus egestas nulla
          </p>
          <form className="subscribe" onSubmit={(e) => e.preventDefault()}>
            <input type="email" name="Email" placeholder="jane@framer.com" aria-label="Email" />
            <button type="submit" className="btn btn-light btn-sm">
              <span className="btn-box">
                <svg viewBox="0 0 30 15" width={30} height={15} className="px-arrow" aria-hidden>
                  {[1, 4].map((dx) =>
                    [[0, 0], [1, 1], [2, 2], [1, 3], [0, 4]].map(([x, y]) => (
                      <rect key={`${dx}${x}${y}`} x={(x + dx) * 3} y={y * 3} width={3} height={3} fill="currentColor" />
                    )),
                  )}
                </svg>
              </span>
              <span className="btn-label">
                <span className="btn-label-inner" data-label="Subscribe">
                  Subscribe
                </span>
              </span>
            </button>
          </form>
          <p className="mono-12">Follow Us:</p>
          <div className="socials">
            {socials.map((s) => (
              <a key={s.n} href={s.href} aria-label={s.n}>
                <Icon name={s.n} size={20} />
              </a>
            ))}
          </div>
        </div>
        <div className="footer-cols">
          {cols.map((c) => (
            <div key={c.h} className="footer-col">
              <p className="mono-16w">{c.h}</p>
              {c.l.map((l) => (
                <a key={l} href="#top" className="p-14l footer-link">
                  {l}
                </a>
              ))}
            </div>
          ))}
        </div>
      </div>
      <img className="footer-word" src={asset("8AjRJ3fmfVsGAO1xyzDT2NbfkE8.png")} alt="" />
    </footer>
  );
}

export { Asterisk };
