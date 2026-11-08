import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
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
import { INSTALL_URL, SIGNIN_URL, SIGNUP_URL } from "./Teams";

const APPS = ["Blender", "LibreOffice Calc", "Excel", "Photoshop", "Docker", "Finder", "Figma", "VS Code"];

/* ---------------- Nav ---------------- */


export function Nav() {
  const links = [
    ["Use cases", "#use-cases"],
    ["Teams", "#teams"],
    ["Pricing", "#pricing"],
    ["FAQ", "#faq"],
  ];
  const [open, setOpen] = useState(false);
  const [hover, setHover] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    addEventListener("hashchange", close);
    return () => removeEventListener("hashchange", close);
  }, [open]);
  return (
    <motion.header
      className={`nav ${open ? "nav-open" : ""}`}
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.8, ease: EASE, delay: 0.1 }}
    >
      <a href="#top" className="nav-brand" aria-label="Rio home">
        <PillLogo size="sm" />
        <span>Rio</span>
      </a>
      <nav className="nav-pill" aria-label="Main" onMouseLeave={() => setHover(null)}>
        {links.map(([l, href]) => (
          <a key={l} href={href} className="nav-link" onMouseEnter={() => setHover(l)} onFocus={() => setHover(l)} onBlur={() => setHover(null)}>
            <AnimatePresence>
              {hover === l && (
                <motion.span
                  layoutId="nav-hover"
                  className="nav-hover"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ type: "spring", stiffness: 520, damping: 38, opacity: { duration: 0.15 } }}
                />
              )}
            </AnimatePresence>
            <span className="nav-text">{l}</span>
          </a>
        ))}
      </nav>
      <div className="nav-right">
        <a href={SIGNIN_URL} className="nav-login">Sign in</a>
        <Btn label="Get started" size="sm" href={SIGNUP_URL} className="nav-cta" />
        <button type="button" className="nav-menu" aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          <span />
          <span />
        </button>
      </div>
      <AnimatePresence>
        {open && (
          <motion.div
            className="nav-sheet"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.25, ease: EASE }}
          >
            {links.map(([l, href]) => (
              <a key={l} href={href} onClick={() => setOpen(false)}>{l}</a>
            ))}
            <a href={SIGNIN_URL} className="nav-sheet-login" onClick={() => setOpen(false)}>Sign in</a>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.header>
  );
}

/* ---------------- Hero ---------------- */

/** What people paste or type in Rio, shown in turn in the hero. */
const SOURCES = [
  { word: "YouTube tutorial.", kind: "YouTube", input: "youtube.com/watch?v=your-first-donut" },
  { word: "blog post.", kind: "Article", input: "notes.design/how-to-export-for-web-in-figma" },
  { word: "help page.", kind: "Docs", input: "docs.blender.org/manual/modeling/bevel.html" },
];
const TYPE_MS = 38;
const HOLD_MS = 2200;

/** Cycles through SOURCES, typing each input like someone pasting or asking. */
function useSource() {
  const reduced = useReducedMotion();
  const [i, setI] = useState(0);
  const [n, setN] = useState(0);
  const full = SOURCES[i].input.length;
  useEffect(() => {
    if (reduced) {
      const t = setTimeout(() => setI((i + 1) % SOURCES.length), HOLD_MS + 1200);
      return () => clearTimeout(t);
    }
    if (n < full) {
      const t = setTimeout(() => setN(n + 1), TYPE_MS);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => {
      setN(0);
      setI((i + 1) % SOURCES.length);
    }, HOLD_MS);
    return () => clearTimeout(t);
  }, [i, n, full, reduced]);
  return { src: SOURCES[i], i, typed: reduced ? SOURCES[i].input : SOURCES[i].input.slice(0, n) };
}

function HeroLine({ text, k }: { text: string; k: number }) {
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.span
        key={k}
        className="hero-swap"
        initial={{ opacity: 0, y: 18, filter: "blur(8px)" }}
        animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
        exit={{ opacity: 0, y: -18, filter: "blur(8px)" }}
        transition={{ duration: 0.45, ease: EASE }}
      >
        {text}
      </motion.span>
    </AnimatePresence>
  );
}

export function Hero() {
  const { src, i, typed } = useSource();
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
              <span className="sr-only">Paste a YouTube tutorial, a blog post or a help page.</span>
              <span aria-hidden>Paste a <HeroLine text={src.word} k={i} /></span>
            </motion.span>
            <motion.span className="hero-l2" {...up(0.32)}>
              Do it with Rio.
            </motion.span>
          </h1>
          <motion.p className="p-16 hero-sub" {...up(0.44)}>
            Rio turns it into steps, shows you where to click in your own app and checks each step. No link? Just type what you want to do.
          </motion.p>
          <motion.div className="hero-link-demo" {...up(0.5)} aria-label="Paste a tutorial link or type a goal to start a lesson">
            <span className="hero-demo-kind mono-12" aria-hidden>{src.kind}</span>
            <span className="hero-demo-url" aria-hidden>{typed}<span className="hero-caret" /></span>
            <span className="hero-demo-start" aria-hidden>↵</span>
          </motion.div>
          <motion.div className="hero-ctas" {...up(0.56)}>
            <Btn label="Get started free" href={SIGNUP_URL} />
            <a className="hero-alt" href={INSTALL_URL}>
              <svg width="15" height="18" viewBox="0 0 814 1000" aria-hidden><path fill="currentColor" d="M788 341c-6 4-108 62-108 190 0 148 130 200 134 202-1 3-21 72-69 142-43 62-88 124-156 124s-86-40-165-40c-77 0-104 41-166 41s-106-58-156-128C44 790 0 669 0 554 0 370 120 272 238 272c63 0 115 41 155 41 38 0 97-44 168-44 27 0 125 2 189 72zM554 160c29-35 50-83 50-131 0-7-1-13-2-19-47 2-104 32-138 72-27 31-52 79-52 128 0 7 1 15 2 17 3 1 8 1 13 1 42 0 96-28 127-68z"/></svg>
              Download for Mac
            </a>
          </motion.div>
        </div>
        <motion.div className="hero-bottom" {...up(0.85)}>
          <p className="p-14 hero-trust">
            Works on top of the apps you already use, from 3D to spreadsheets.
          </p>
          <Marquee duration={28} className="hero-logos">
            {APPS.map((l) => (
              <span key={l} className="app-logo">{l}</span>
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
          text="Stop watching tutorials. Start doing. Rio turns any goal into guided steps on your own screen."
        />
        <Reveal as="p" className="p-16 about-sub">
          Type or say what you want to learn. Rio plans the milestones from what it sees and coaches you through each one, in real time.
        </Reveal>
        <div className="bento">
          <Reveal className="bento-dark" delay={0}>
            <span className="bento-icon">
              <Icon name="trendUp" size={30} />
            </span>
            <p className="stat-num">
              <CountUp to={100} suffix="%" />
            </p>
            <p className="p-14 bento-foot">Hands-on: you make every click yourself, Rio only points the way.</p>
          </Reveal>
          <div className="bento-col">
            <Reveal className="bento-dashed" delay={0.08}>
              <div className="avatars">
                {["D3gag0wTRQzvb6CCfJkTShmXTPI.jpg", "9AvPLCB2PkQCEoFgNdwvDaIaGGI.jpg", "pktP7O1JHzk75RWizEsb0jRSjk.jpg", "2418vQBGZ7CPVHaaIlQ5wuUyr4.jpg"].map((a) => (
                  <img key={a} src={asset(a)} alt="" />
                ))}
              </div>
              <p className="p-14 agents">
                Ask out loud: <strong>“where is it?”</strong>
              </p>
            </Reveal>
            <Reveal className="bento-small" delay={0.16}>
              <p className="stat-num stat-dark">
                <CountUp to={4} />
              </p>
              <p className="p-14 muted-6">Steps: ask, plan, do, save.</p>
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
              <h4 className="h4-20">Click detection</h4>
              <p className="p-14 muted-6">Rio sees your real click and moves on. No “next” button.</p>
            </div>
          </Reveal>
          <Reveal className="bento-white" delay={0.32}>
            <div className="bento-quote-top">
              <Icon name="quotes" size={40} />
              <img src={asset("rio-mark-black.svg")} alt="Rio" className="bento-mark" />
            </div>
            <div>
              <p className="bento-quote">
                Holo looks at the screen, a ghost cursor shows the way, and the learner does the clicking.
              </p>
              <p className="p-14 muted-6 bento-cite">How Rio teaches</p>
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
  { tag: "3D", app: "Blender", img: "sZxYLpvH56E3RznKPcnAPYlPvo.jpg", s: ["First donut", "Beginner", "Voice on", "Ghost cursor"] },
  { tag: "3D", app: "Blender", img: "4GMiBYbu9SI4dXo9ENcqlNA.jpg", s: ["Basics & render", "Beginner", "Voice on", "Ghost cursor"] },
  { tag: "Spreadsheets", app: "LibreOffice Calc", img: "0g3E5eja3ueYAXkITtsy9quyYo.jpg", s: ["Budget chart", "Beginner", "Voice on", "Ghost cursor"] },
  { tag: "Developer tools", app: "Docker", img: "ZK0k9kMGgE21P7r3puSMYZ8548.jpg", s: ["Run a container", "Intermediate", "Voice on", "Ghost cursor"] },
  { tag: "Any desktop app", app: "Your app", img: "LYQLqywSoqlHG7KLRJM70MIk.png", s: ["Typed goal", "Any level", "Voice on", "Ghost cursor"] },
];
const STAT_LABELS = ["Lesson", "Level", "Questions", "Guidance"];

export function Works() {
  return (
    <div className="works-wrap" id="works">
      <section className="works">
        <BigMarquee word="Use cases" />
        <div className="works-grid">
          {WORKS.map((w, i) => (
            <div className="work-cell" key={i}>
              <Reveal className="work-card" delay={(i % 3) * 0.08}>
                <div className="work-top">
                  <span className="tag">{w.tag}</span>
                  <span className="work-logo work-app">{w.app}</span>
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
  { n: "001", title: "Sees your screen", body: "Holo by H Company reads the current screenshot and locates the exact button, menu or field for the next step.", img: "WTuFQeqWgOcQVCks16yKxgDaefI.png" },
  { n: "002", title: "Plans the milestones", body: "Type a goal or pick a tutorial: Rio breaks it into milestones, each with a success check it can verify on screen.", img: "liXydHdt7Kdt6VKUzzjSZwFJ4FA.png" },
  { n: "003", title: "Checks your work", body: "A step completes when Rio sees the result, so you only move on when it is really done.", img: "WTuFQeqWgOcQVCks16yKxgDaefI.png" },
];

export function Capabilities() {
  const [open, setOpen] = useState(0);
  return (
    <section className="caps" id="services">
      <div className="caps-left">
        <div>
          <Label text="HOW IT WORKS" pillFirst className="w-500" />
          <Reveal as="p" className="p-16 caps-sub">
            Rio pairs a vision model that reads your screen with a coach that never takes the mouse from you.
          </Reveal>
        </div>
        <div>
          <Reveal as="h2" className="h2-54 caps-title">
            A coach that sees what you see.
          </Reveal>
          <Reveal delay={0.1}>
            <Btn label="Try Rio" variant="ghost" href="#contact" />
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
              <img src={asset("jnIpVvHAXWiAGa8gLEmWtRuDwQ.png")} alt="The Rio team" />
              <Corner className="c-tl" />
              <Corner className="c-tr" />
              <Corner className="c-br" />
              <Corner className="c-bl" />
            </div>
            <p className="mono-12 portrait-name">THE RIO TEAM</p>
            <p className="p-12 muted-w7">Built at the H Company hackathon</p>
          </Reveal>
          <div className="vision-right">
            <Label text="OUR VISION" className="w-500" />
            <ScrollRevealText
              className="h-reveal h-reveal-tight vision-title"
              text="We believe software should teach itself: every app, every task, learned by doing instead of watching."
            />
            <Reveal as="p" className="p-16 vision-sub">
              Video tutorials go stale and never match your screen. Rio reads the real interface, adapts when menus move, and keeps you in control of every click.
            </Reveal>
          </div>
        </section>
        <div className="vision-strip" />
      </div>
      <section className="engineering">
        <div className="eng-row">
          <Reveal as="p" className="mono-12l eng-text">
            BUILT ON H COMPANY'S HOLO MODELS, GLADIA LIVE SPEECH-TO-TEXT AND A LOCAL GRADIUM VOICE. RIO'S OWN WINDOWS ARE NEVER CAPTURED.
          </Reveal>
          <Reveal className="models" delay={0.1}>
            {models.map((m) => (
              <span key={m} className="model">
                <img src={asset(m)} alt="" />
              </span>
            ))}
          </Reveal>
          <Reveal delay={0.2}>
            <Btn label="See it in action" variant="ghost" href="#top" />
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
            <p className="p-15 feat-text">A ghost cursor that points to your next click</p>
          </Reveal>
          <Reveal className="feature" delay={0.08}>
            <div className="feat-icon feat-orbit">
              <span className="orbit-ring" />
              <span className="orbit-ring r2" />
              <span className="orbit-dot" />
            </div>
            <p className="p-15 feat-text">Milestone graphs, not brittle click scripts.</p>
          </Reveal>
          <Reveal className="feature" delay={0.16}>
            <div className="feat-icon feat-bars">
              {[0, 1, 2, 3].map((k) => (
                <span key={k} className="bar" style={{ animationDelay: `${k * 0.25}s` }}>
                  <i />
                </span>
              ))}
            </div>
            <p className="p-15 feat-text">Ask “show me again” and Rio repeats the step</p>
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
            <p className="p-15 feat-text">A multilingual voice that runs on your machine.</p>
          </Reveal>
        </div>
      </section>
    </>
  );
}

/* ---------------- Experiences (testimonials) ---------------- */

const TESTI = [
  { name: "THE BEGINNER", role: "Blender, first donut", avatar: "w2hyXovpoCcfHZkjR4Hmr53RA5o.jpg", app: "Blender", q: "Rio pointed at the exact menu every time. I finished my first donut without pausing a single video." },
  { name: "THE ANALYST", role: "LibreOffice Calc, budget chart", avatar: "rLkyXpp1TSaADDj0EYjy9c8uw.jpg", app: "Calc", q: "I asked “where is it?” out loud and the cursor jumped to the chart wizard. That is how I want to learn." },
  { name: "THE DEVELOPER", role: "Docker, first container", avatar: "IIK9uqdpvVqpPgAHuhf8s9r4Ee4.jpg", app: "Docker", q: "No copy-pasting commands I don't understand. Each step was checked on my screen before moving on." },
  { name: "THE SWITCHER", role: "macOS, Finder basics", avatar: "QHChEEbpWFuUCrhS6zqN5BK4Rr0.jpg", app: "Finder", q: "New laptop, new system. Rio sat next to me for the basics and I never felt lost." },
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
      <BigMarquee word="Stories" />
      <div className="exp-head">
        <Reveal as="p" className="p-16 exp-sub">
          What learning feels like when the tutorial is your own screen.
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
                <span className="t-app">{t.app}</span>
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
          From goal to done in one flow: ask, follow the ghost cursor, click, repeat.
        </Reveal>
        <Reveal className="watch-pill" delay={0.1}>
          <Icon name="timer" size={24} />
          <span className="p-14">Live demo</span>
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
          Learning by Doing.
        </Reveal>
        <PillLogo size="lg" light />
      </div>
    </section>
  );
}

/* ---------------- Process + Team ---------------- */

const STEPS = [
  { t: "Say or type your goal", tag: "Ask", d: "Press ⌥⇧Space over any app and describe what you want to learn, or pick a ready-made tutorial from the library." },
  { t: "Rio plans the milestones", tag: "Plan", d: "Holo reads your screen and breaks the goal into milestones, each with a success check it can verify visually." },
  { t: "Follow the ghost cursor", tag: "Do", d: "A ghost cursor shows where to click. You make the click yourself; Rio sees it and moves to the next step." },
  { t: "Save it as a tutorial", tag: "Share", d: "At the end, the path you actually took is saved back to the library, so the next learner gets there faster." },
];

const TEAM = [
  { name: "HOLO VISION", role: "Sees and locates", img: "OrsgMbvM0AZiEvhgHFZUJM2g.png", bio: "Holo by H Company looks at each screenshot and returns the exact spot to click, so Rio points instead of guessing." },
  { name: "MILESTONE PLANNER", role: "Plans and checks", img: "BbqpJjnldDFDulJFBarqs7wJpFk.png", bio: "Every goal becomes a graph of milestones with a visual success check. Rio moves on only when the result is on screen." },
  { name: "GLADIA LIVE", role: "Listens", img: "8k7FcfFSjgocOslFu94p0ih1UY.png", bio: "Ask out loud during a lesson. Gladia transcribes you live, and Rio answers, points, skips or repeats the step." },
  { name: "GRADIUM VOICE", role: "Speaks", img: "FnCj7jgTvcpKSt0CUVIqbyiS9o.png", bio: "Rio answers out loud with a multilingual voice that runs locally on your machine, fast enough to keep up with you." },
];

export function Process() {
  const [open, setOpen] = useState(0);
  return (
    <div className="process-wrap">
      <section className="process">
        <Label text="THE FLOW" />
        <Reveal as="h2" className="h2-54 process-title">
          From a goal to real skills. Four steps, on your own screen.
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
            NO AUTOPILOT. YOU KEEP THE MOUSE, RIO KEEPS YOU ON TRACK. EVERY STEP IS CHECKED ON SCREEN BEFORE YOU MOVE ON.
          </Reveal>
          <Reveal delay={0.1}>
            <Btn label="Try Rio" variant="ghost" href="#contact" />
          </Reveal>
        </div>

        <Reveal as="h2" className="h-collective">
          We are building the coach that sits next to everyone who opens new software.
        </Reveal>
        <div className="story">
          <Reveal as="p" className="p-16">
            Born at the H Company hackathon, built on Holo computer-use models and real-time voice.
          </Reveal>
          <Reveal delay={0.1}>
            <Btn label="How it works" variant="ghost" href="#services" />
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
  { name: "Learner", price: 0, tagline: "One app at a time.", f: ["Tutorial library", "Typed goals", "Ghost cursor", "Community support"] },
  { name: "Pro", price: 12, tagline: "Unlimited live coaching.", f: ["Unlimited goals", "Voice questions", "Save as tutorial", "Priority support"] },
  { name: "Team", price: 29, tagline: "Onboard a whole team.", f: ["Team library", "Internal docs search", "Invites & admin", "Usage insights"], dark: true },
  { name: "Enterprise", price: -1, tagline: "Your apps, your rules.", f: ["Custom tutorials", "SSO & admin", "Data controls", "Dedicated success"] },
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
        {value < 0 ? "Custom" : `$${value.toLocaleString("en-US")}`}
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
          Simple plans for early access. Prices are indicative and will be confirmed at launch.
        </Reveal>
      </div>
      <Reveal className="plans">
        {PLANS.map((p) => (
          <div key={p.name} className={`plan ${p.dark ? "plan-dark" : ""}`}>
            <img className="plan-wave" src={asset("lu9xdgbj7zB5GkewV6UCW9Y68.jpg")} alt="" />
            <div className="plan-top">
              <h6 className="plan-name">{p.name}</h6>
              <p className="plan-price">
                <Price value={annual || p.price <= 0 ? p.price : Math.round(p.price / 0.8)} />
                {p.price >= 0 && <span className="p-14l plan-mo">/mo</span>}
              </p>
              <p className="p-14l">{p.price < 0 ? "Talk to us" : p.price === 0 ? "Free forever" : `USD per seat, billed ${annual ? "annually" : "monthly"}`}</p>
            </div>
            <div className="plan-band">
              <p className="plan-tag">{p.tagline}</p>
              <Btn label="Get started" size="sm" variant={p.dark ? "light" : "ghost"} href={SIGNUP_URL} />
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
  { q: "Can I use any YouTube tutorial?", a: "Paste a YouTube tutorial link and Rio turns it into a step-by-step lesson in your app. Blender is our starting point. A lesson needs to be checked against the app and version you use; not every video can become a verified lesson. You stay in control of the clicks." },
  { q: "Does Rio click for me?", a: "No. Rio points with a ghost cursor and you make every click. Learning sticks because you do it yourself." },
  { q: "Which apps does Rio work with?", a: "Any desktop app. Tutorials ship for Blender, LibreOffice Calc, Docker and Finder, and you can type a goal for anything else." },
  { q: "Can Rio learn our internal tools?", a: "Yes, on a team workspace. Add the Markdown guides of your in-house apps in the console: Rio turns them into procedures and finds them when someone asks. Your notes stay in your workspace." },
  { q: "What does Rio see on my screen?", a: "A screenshot of your main display when it plans or checks a step. Rio's own windows are excluded from captures." },
  { q: "Can I ask questions out loud?", a: "Yes. Click the mic and ask “where is it?”, “I'm done” or “show me again”: Rio answers out loud, points, skips or repeats." },
  { q: "What if the menus have changed?", a: "Tutorials are graphs of milestones, not click scripts. Rio finds the current path on screen, so outdated hints don't break the lesson." },
  { q: "Which AI models power Rio?", a: "Holo by H Company for vision and planning, Gladia for live speech-to-text and Gradium for the local voice." },
  { q: "Which platforms are supported?", a: "macOS first: Rio lives in the menu bar and floats over full-screen apps. More platforms are on the roadmap." },
];


export function FaqInsights() {
  const [open, setOpen] = useState(0);
  return (
    <section className="faq-wrap" id="faq">
      <div className="faq-card">
        <div className="faq">
          <div className="faq-left">
            <div>
              <Label text="FAQ" pillFirst light={false} className="w-500" />
              <Reveal as="p" className="p-16 faq-sub">
                How Rio sees, guides and respects your screen.
              </Reveal>
            </div>
            <div>
              <Reveal as="h2" className="h2-54 faq-title">
                Everything you need to know about Rio.
              </Reveal>
              <Reveal delay={0.1}>
                <Btn label="Contact us" href="#contact" />
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

      </div>
    </section>
  );
}

/* ---------------- Footer ---------------- */

export function Footer() {
  const cols = [
    { h: "Product", l: [["Use cases", "#use-cases"], ["For teams", "#teams"], ["Pricing", "#pricing"], ["FAQ", "#faq"]] },
    { h: "Get started", l: [["Create an account", SIGNUP_URL], ["Sign in", SIGNIN_URL], ["Download for Mac", INSTALL_URL]] },
    { h: "Built with", l: [["H Company", "https://www.hcompany.ai"], ["Gladia", "https://www.gladia.io"], ["Gradium", "https://gradium.ai"]] },
  ];
  return (
    <footer className="footer" id="contact">
      <img className="footer-bg" src={asset("v2cZIMtgjEII7EpDnUDGGgCyuiQ.png")} alt="" />
      <div className="footer-inner">
        <div className="footer-left">
          <PillLogo size="md" light />
          <p className="footer-wordmark">Rio</p>
          <p className="p-15 footer-text">
            Rio is your live software coach. Tell it what you want to learn and it shows you the way, on your own screen.
          </p>
          <div className="footer-ctas">
            <Btn label="Get started free" variant="light" size="sm" href={SIGNUP_URL} />
          </div>
        </div>
        <div className="footer-cols">
          {cols.map((c) => (
            <div key={c.h} className="footer-col">
              <p className="mono-16w">{c.h}</p>
              {c.l.map(([l, href]) => (
                <a key={l} href={href} className="p-14l footer-link" {...(href.startsWith("http") ? { target: "_blank", rel: "noreferrer" } : {})}>
                  {l}
                </a>
              ))}
            </div>
          ))}
        </div>
      </div>
      <p className="footer-word" aria-hidden>rio</p>
    </footer>
  );
}

export { Asterisk };
