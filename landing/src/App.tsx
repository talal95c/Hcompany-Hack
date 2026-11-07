import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  Box,
  Check,
  ChevronDown,
  Command,
  Github,
  Menu,
  Mic,
  MousePointer2,
  RotateCcw,
  ScanLine,
  Sparkles,
  X,
} from "lucide-react";
import ComputerEntrance from "./ComputerEntrance";
import { rememberIntro, shouldShowIntro } from "./intro";

const REPO = "https://github.com/talal95c/Hcompany-Hack";
const INSTALL = `${REPO}/tree/main/h-tutor#run`;
const STEPS = [
  {
    title: "Dites ce que vous voulez apprendre.",
    body: "« Aide-moi à créer mon premier objet dans Blender. » Partez d’un objectif ou choisissez un tutoriel. Holo le découpe en étapes.",
    label: "Votre objectif",
    instruction: "Créer mon premier objet dans Blender",
    icon: Sparkles,
  },
  {
    title: "Repérez le prochain geste.",
    body: "Holo observe votre écran et indique où cliquer avec un curseur fantôme. Plus besoin de jongler entre la vidéo et le logiciel.",
    label: "Une indication à l’écran",
    instruction: "Ouvrez le menu « Ajouter » dans la vue 3D.",
    icon: MousePointer2,
  },
  {
    title: "Faites-le vous-même. Et retenez.",
    body: "Vous faites l’action, le guide vous accompagne. Une hésitation ? Posez votre question à la voix et reprenez à votre rythme.",
    label: "Vous êtes aux commandes",
    instruction: "Une question ? Demandez à Holo de réexpliquer.",
    icon: AudioLines,
  },
];
const FAQ = [
  {
    question: "Est-ce une application ou un site web ?",
    answer:
      "Cette page présente Holo Tutor. Le guide, lui, est une application de bureau native : il a besoin d’accéder à votre écran pour vous accompagner. Il ne contrôle pas votre ordinateur depuis ce site.",
  },
  {
    question: "Comment l’installer aujourd’hui ?",
    answer: (
      <>
        Holo Tutor est un prototype à lancer depuis le code source. Le parcours
        natif actuel cible macOS et nécessite Node.js, Rust, les outils Tauri et
        vos clés de services. Il n’y a pas encore d’installateur publié.{" "}
        <a href={INSTALL} target="_blank" rel="noreferrer">
          Lire les instructions d’installation <ArrowUpRight size={13} />
        </a>
      </>
    ),
  },
  {
    question: "Est-ce uniquement pour Blender ?",
    answer:
      "Blender est l’un de nos premiers terrains d’apprentissage. Le guide travaille à partir de ce qu’il voit à l’écran, pas d’une intégration propre à un seul logiciel. La compatibilité et la qualité du guidage restent à vérifier pour chaque logiciel et chaque tutoriel.",
  },
  {
    question: "Quelles autorisations sont nécessaires ?",
    answer:
      "Sur macOS, la capture d’écran permet au guide de voir votre logiciel. Le microphone est utilisé si vous activez les questions vocales. L’analyse d’écran et la transcription font appel à des services cloud avec vos propres clés : consultez leur politique de rétention avant d’utiliser des données sensibles. Ce site ne demande ni capture d’écran ni microphone.",
  },
  {
    question: "Holo fait-il les actions à ma place ?",
    answer:
      "Le parcours présenté ici vous apprend à faire : le curseur fantôme indique la cible, vous cliquez. L’automatisation n’est pas présentée comme une fonction disponible sur cette page. Vous restez aux commandes.",
  },
];

function Brand({ footer = false }: { footer?: boolean }) {
  return (
    <a
      href="#accueil"
      className={`brand${footer ? " brand--footer" : ""}`}
      aria-label="Holo Tutor, accueil"
    >
      <span className="brand-mark" aria-hidden="true">
        h
      </span>
      holo tutor<span className="brand-dot">β</span>
    </a>
  );
}

function ProductPreview({
  active,
  compact = false,
}: {
  active: number;
  compact?: boolean;
}) {
  const Icon = STEPS[active].icon;
  return (
    <div
      className={`product-preview${compact ? " product-preview--compact" : ""}`}
    >
      <div className="preview-topbar">
        <span className="window-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span>
          <Box size={12} /> Blender · votre espace de pratique
        </span>
        <span className="preview-topbar-note">LE GUIDE, À VOS CÔTÉS</span>
      </div>
      <div className="preview-screen">
        <img
          src="/blender.webp"
          width="1600"
          height="900"
          alt="Capture de Blender : un cube sélectionné dans la vue 3D."
          loading="lazy"
        />
        <div
          className={`ghost-pointer ghost-pointer--${active}`}
          aria-hidden="true"
        >
          <MousePointer2 size={27} fill="currentColor" />
          <span>Holo vous guide ici</span>
        </div>
        <div className="tutor-bar">
          <span className="tutor-symbol" aria-hidden="true">
            <Icon size={20} />
          </span>
          <div className="tutor-instruction">
            <span>{STEPS[active].label}</span>
            <p>{STEPS[active].instruction}</p>
          </div>
          <span className="tutor-mic" aria-hidden="true">
            <Mic size={16} />
          </span>
          <span className="tutor-shortcut" aria-hidden="true">
            <Command size={12} /> ⇧ espace
          </span>
        </div>
      </div>
      <div className="preview-caption">
        <span className="status-dot" /> Aperçu illustré du guide sur une capture
        réelle de Blender.<span>Pas une session en direct.</span>
      </div>
    </div>
  );
}

export default function App() {
  const [intro, setIntro] = useState(shouldShowIntro);
  const [menu, setMenu] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [activeStep, setActiveStep] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const exitIntro = useCallback(() => {
    rememberIntro();
    setIntro(false);
    requestAnimationFrame(() =>
      heading.current?.focus({ preventScroll: true }),
    );
  }, []);

  useEffect(() => {
    const previous = document.body.style.overflow;
    if (intro || menu) document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [intro, menu]);

  useEffect(() => {
    const scroll = () => setScrolled(window.scrollY > 64);
    scroll();
    window.addEventListener("scroll", scroll, { passive: true });
    return () => window.removeEventListener("scroll", scroll);
  }, []);

  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 761px)");
    const resize = () => {
      if (desktop.matches) setMenu(false);
    };
    desktop.addEventListener("change", resize);
    return () => desktop.removeEventListener("change", resize);
  }, []);

  return (
    <>
      <div className="site" inert={intro}>
        <a className="skip-link" href="#contenu">
          Aller au contenu
        </a>
        <header
          className={`navigation${scrolled ? " navigation--floating" : ""}${menu ? " navigation--open" : ""}`}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setMenu(false);
              menuButton.current?.focus();
            }
          }}
        >
          <div className="nav-inner">
            <Brand />
            <nav
              aria-label="Navigation principale"
              className={menu ? "nav-links nav-links--open" : "nav-links"}
              id="main-navigation"
            >
              <a href="#le-guide" onClick={() => setMenu(false)}>
                Le guide
              </a>
              <a href="#comment-ca-marche" onClick={() => setMenu(false)}>
                Comment ça marche
              </a>
              <a href="#questions" onClick={() => setMenu(false)}>
                Questions
              </a>
              <a
                href={INSTALL}
                target="_blank"
                rel="noreferrer"
                className="nav-install"
              >
                Installer le prototype <ArrowUpRight size={14} />
              </a>
            </nav>
            <button
              ref={menuButton}
              className="menu-toggle"
              aria-expanded={menu}
              aria-controls="main-navigation"
              aria-label={menu ? "Fermer le menu" : "Ouvrir le menu"}
              onClick={() => setMenu(!menu)}
            >
              {menu ? <X size={22} /> : <Menu size={22} />}
            </button>
          </div>
        </header>

        <main id="contenu">
          <section id="accueil" className="hero" aria-labelledby="hero-title">
            <div className="hero-landscape" aria-hidden="true" />
            <div className="hero-content">
              <p className="eyebrow">
                <span className="status-dot" /> UN TUTEUR. VOTRE ÉCRAN. VOTRE
                DÉCLIC.
              </p>
              <h1 ref={heading} tabIndex={-1} id="hero-title">
                Moins de pause.
                <br />
                <em>Plus de pratique.</em>
              </h1>
              <p className="hero-description">
                Ne regardez plus seulement les tutos. Faites-les.
                <br />
                Holo vous montre où cliquer, directement dans votre logiciel.
                <br className="desktop-break" /> Vous apprenez en faisant, un
                geste à la fois.
              </p>
              <div className="hero-actions">
                <a href="#le-guide" className="button button--light">
                  Découvrir le guide <ArrowUpRight size={16} />
                </a>
                <a
                  href={INSTALL}
                  target="_blank"
                  rel="noreferrer"
                  className="hero-secondary"
                >
                  Installer Holo Tutor <ArrowUpRight size={14} />
                </a>
              </div>
              <p className="hero-note">
                Prototype natif pour macOS · installation depuis le code source
              </p>
            </div>
            <div className="hero-bottom">
              <span>POUR CEUX QUI PRÉFÈRENT FAIRE.</span>
              <a href="#le-guide" aria-label="Descendre vers le guide">
                <ArrowDown size={17} />
              </a>
              <span>PAS BESOIN DE TOUT SAVOIR POUR COMMENCER.</span>
            </div>
          </section>

          <section
            id="le-guide"
            className="guide section-shell"
            aria-labelledby="guide-title"
          >
            <div className="section-heading">
              <p className="eyebrow">L’APPRENTISSAGE, DANS LA VRAIE VIE</p>
              <h2 id="guide-title">
                Un guide à vos côtés.
                <br />
                <em>Pas à votre place.</em>
              </h2>
              <p>
                Votre logiciel reste votre terrain de jeu.
                <br />
                Holo apporte juste le coup de pouce au bon moment.
              </p>
            </div>
            <ProductPreview active={activeStep} />
            <div
              className="preview-selector"
              role="group"
              aria-label="Explorer l’aperçu du guide"
            >
              {STEPS.map((step, index) => (
                <button
                  key={step.label}
                  className={activeStep === index ? "active" : ""}
                  aria-pressed={activeStep === index}
                  onClick={() => setActiveStep(index)}
                >
                  <span>0{index + 1}</span>
                  {step.label}
                  <ArrowUpRight size={13} />
                </button>
              ))}
            </div>
          </section>

          <section
            className="manifesto section-shell"
            aria-label="Notre approche"
          >
            <span className="small-star" aria-hidden="true">
              ✳
            </span>
            <p>
              Un tutoriel vous montre <em>comment.</em>
              <br />
              La pratique vous apprend <em>vraiment.</em>
            </p>
            <span className="manifesto-note">
              Moins d’allers-retours. Plus de déclics.
            </span>
          </section>

          <section
            id="comment-ca-marche"
            className="how section-shell"
            aria-labelledby="how-title"
          >
            <div className="how-intro">
              <p className="eyebrow">DU « COMMENT ? » AU « J’AI COMPRIS. »</p>
              <h2 id="how-title">
                Le bon geste.
                <br />
                <em>Au bon endroit.</em>
              </h2>
              <p>
                Pas de vidéo à mettre en pause.
                <br />
                Juste vous, votre objectif, et un guide qui suit.
              </p>
              <a
                className="inline-link"
                href={INSTALL}
                target="_blank"
                rel="noreferrer"
              >
                Faire mes premiers pas <ArrowUpRight size={16} />
              </a>
            </div>
            <div className="steps">
              {STEPS.map((step, index) => (
                <article
                  className={`step${activeStep === index ? " step--active" : ""}`}
                  key={step.title}
                >
                  <h3>
                    <button
                      aria-expanded={activeStep === index}
                      aria-controls={`step-${index}`}
                      onClick={() => setActiveStep(index)}
                    >
                      <span className="step-number">0{index + 1}</span>
                      <span className="step-title">{step.title}</span>
                      <ChevronDown size={17} />
                    </button>
                  </h3>
                  <div id={`step-${index}`} hidden={activeStep !== index}>
                    <p>{step.body}</p>
                    <div className="step-detail">
                      <step.icon size={14} />
                      <span>
                        {index === 0
                          ? "Un objectif, exprimé avec vos mots"
                          : index === 1
                            ? "Un curseur fantôme, une cible claire"
                            : "Vos gestes, votre rythme"}
                      </span>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section
            className="benefits section-shell"
            aria-label="Ce qui change avec Holo Tutor"
          >
            <article>
              <span className="benefit-icon">
                <ScanLine size={24} strokeWidth={1.25} />
              </span>
              <h3>Dans votre contexte.</h3>
              <p>
                Le guide part de votre écran. Il vous accompagne là où vous
                travaillez, sans vous demander de changer vos habitudes.
              </p>
              <span className="benefit-tag">
                VOTRE LOGICIEL, PAS UNE SIMULATION
              </span>
            </article>
            <article>
              <span className="benefit-icon">
                <AudioLines size={24} strokeWidth={1.25} />
              </span>
              <h3>Une question ? Parlez.</h3>
              <p>
                « Où est le menu ? » « Tu peux répéter ? » Avec la voix activée,
                posez votre question sans quitter ce que vous faites.
              </p>
              <span className="benefit-tag">LE DIALOGUE RESTE OUVERT</span>
            </article>
            <article>
              <span className="benefit-icon">
                <MousePointer2 size={24} strokeWidth={1.25} />
              </span>
              <h3>C’est vous qui faites.</h3>
              <p>
                Holo montre le chemin. Vous réalisez les gestes. Parce qu’un
                savoir-faire s’apprend mieux quand il passe par vos mains.
              </p>
              <span className="benefit-tag">
                L’AUTONOMIE COMME POINT D’ARRIVÉE
              </span>
            </article>
          </section>

          <section
            className="control section-shell"
            aria-labelledby="control-title"
          >
            <div className="control-art" aria-hidden="true">
              <div className="control-orbit orbit-one" />
              <div className="control-orbit orbit-two" />
              <div className="control-orbit orbit-three" />
              <div className="control-key">
                <Command size={26} strokeWidth={1.2} />
                <span>⇧</span>
                <span>espace</span>
              </div>
              <span className="control-caption">
                UN RACCOURCI. UN COUP DE POUCE.
              </span>
            </div>
            <div className="control-copy">
              <p className="eyebrow">DISCRET PAR NATURE</p>
              <h2 id="control-title">
                Là quand il faut.
                <br />
                <em>À vous quand même.</em>
              </h2>
              <p>
                Un raccourci pour appeler Holo. Une barre de guidage pour garder
                le fil. Et tout l’espace pour essayer par vous-même.
              </p>
              <ul>
                <li>
                  <Check size={15} /> Le guide se superpose à votre logiciel
                </li>
                <li>
                  <Check size={15} /> L’écran et le micro nécessitent vos
                  autorisations
                </li>
                <li>
                  <Check size={15} /> Vos actions restent entre vos mains
                </li>
              </ul>
            </div>
          </section>

          <section
            id="questions"
            className="faq section-shell"
            aria-labelledby="faq-title"
          >
            <div>
              <p className="eyebrow">AVANT LE PREMIER CLIC</p>
              <h2 id="faq-title">
                C’est bien
                <br />
                <em>de se poser des questions.</em>
              </h2>
              <p>Le projet avance. On vous dit où il en est.</p>
              <a
                href={`${REPO}#readme`}
                target="_blank"
                rel="noreferrer"
                className="inline-link"
              >
                Explorer le projet <ArrowUpRight size={15} />
              </a>
            </div>
            <div className="faq-list">
              {FAQ.map((item) => (
                <details key={item.question}>
                  <summary>
                    {item.question}
                    <span className="faq-plus" aria-hidden="true" />
                  </summary>
                  <div className="faq-answer">{item.answer}</div>
                </details>
              ))}
            </div>
          </section>

          <section className="final-cta" aria-labelledby="cta-title">
            <div className="cta-glow" aria-hidden="true" />
            <p className="eyebrow">VOTRE PROCHAIN SAVOIR-FAIRE COMMENCE ICI.</p>
            <h2 id="cta-title">
              Et si vous
              <br />
              <em>essayiez, tout simplement ?</em>
            </h2>
            <a
              href={INSTALL}
              target="_blank"
              rel="noreferrer"
              className="button button--light"
            >
              Installer Holo Tutor <ArrowUpRight size={16} />
            </a>
            <p className="cta-note">
              Un prototype à explorer. Des gestes à apprendre.
              <br />
              Code source et instructions sur GitHub.
            </p>
          </section>
        </main>

        <footer className="footer section-shell">
          <div className="footer-main">
            <div>
              <Brand footer />
              <p>Le déclic, c’est de faire.</p>
            </div>
            <div className="footer-links">
              <a href="#le-guide">Le guide</a>
              <a href="#questions">Questions</a>
              <a href={REPO} target="_blank" rel="noreferrer">
                <Github size={14} /> Le code source <ArrowUpRight size={12} />
              </a>
            </div>
          </div>
          <div className="footer-bottom">
            <span>Holo Tutor · Apprendre en faisant.</span>
            <button
              className="text-button"
              onClick={() => {
                window.scrollTo({ top: 0, behavior: "instant" });
                setIntro(true);
              }}
            >
              <RotateCcw size={12} /> Rejouer l’intro
            </button>
            <a href="#accueil">
              Retour en haut <ArrowRight size={12} className="arrow-up" />
            </a>
          </div>
        </footer>
      </div>
      {intro && <ComputerEntrance onExit={exitIntro} />}
    </>
  );
}
