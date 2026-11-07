import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import Palette from "./Palette";
import { sfx, useSoundEnabled, setSoundEnabled } from "../sound";
import { Feedback } from "../feedback";
import { AnimatePresence, motion } from "motion/react";
import { Transcript, Wave, tail } from "./Dictaphone";
import { openUrl } from "@tauri-apps/plugin-opener";
import { listen } from "@tauri-apps/api/event";
import { api, errorText, speak, stopSpeaking, type Imported, type QaAnswer, type MilestoneView, type Status, type Step, type TutorialSummary } from "./api";
import {
  IconCheck,
  IconClose,
  IconGrid,
  IconKeyboard,
  IconMic,
  IconReplay,
  IconSkip,
  IconVolume,
  IconVolumeOff,
  IconSound,
  IconSoundOff,
} from "./icons";

type Phase = "home" | "planning" | "importing" | "imported" | "running" | "done";

const isYoutube = (s: string) => /^(https?:\/\/)?(www\.|m\.)?(youtube\.com\/|youtu\.be\/)/i.test(s.trim());
/** thinking: waiting for Holo · waiting: the learner's turn · success: brief "nice" */
type StepState = "thinking" | "waiting" | "success" | "error";
/** A question asked mid-tutorial; the tutorial is paused while it is open. */
type Explain = { question: string; answer?: string; details: string[]; target: string; error?: string };

const BAR_WIDTH = 560;
const PALETTE_WIDTH = 760;

export default function App() {
  const sound = useSoundEnabled();
  const [status, setStatus] = useState<Status | null>(null);
  const [phase, setPhase] = useState<Phase>("home");
  const [goal, setGoal] = useState("");
  const [title, setTitle] = useState("");
  const [homeError, setHomeError] = useState("");
  const [step, setStep] = useState<Step | null>(null);
  const [progress, setProgress] = useState<MilestoneView[]>([]);
  const [library, setLibrary] = useState<TutorialSummary[]>([]);
  const [planning, setPlanning] = useState(false); // Holo is designing the milestones
  const [saved, setSaved] = useState<string | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [importStage, setImportStage] = useState("");
  const [qa, setQa] = useState<{ question: string; result?: QaAnswer; error?: string } | null>(null);
  const [imported, setImported] = useState<Imported | null>(null);
  const paletteRef = useRef(paletteOpen);
  paletteRef.current = paletteOpen;
  const [stepState, setStepState] = useState<StepState>("thinking");
  const [message, setMessage] = useState("");
  const [voice, setVoice] = useState(true);
  const [listening, setListening] = useState(false);
  /** What the learner is saying (live), kept briefly once final. */
  const [voiceText, setVoiceText] = useState<{ text: string; final: boolean } | null>(null);
  const [level, setLevel] = useState(0);
  const [asking, setAsking] = useState(false);
  const [explain, setExplain] = useState<Explain | null>(null);
  const [question, setQuestion] = useState("");
  /** Holo's reasoning, streamed live while it decides the next step. */
  const [thinking, setThinking] = useState("");

  /** Learner's language: updated by everything they say (Gladia) or type
   *  (text detection), sent to Holo with every step. Never taken from the screen. */
  const langRef = useRef<string | null>(null);
  const voiceRef = useRef(voice);
  voiceRef.current = voice;
  const liveRef = useRef({ phase, stepState, step, explain });
  liveRef.current = { phase, stepState, step, explain };
  const barRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const previous = useRef({ phase, paletteOpen, listening, homeError, error: "" });
  const visibleError = qa?.error || explain?.error || (stepState === "error" ? message : "");
  useEffect(() => {
    const prev = previous.current;
    if (phase === "done" && prev.phase !== phase) sfx.success();
    if (paletteOpen && !prev.paletteOpen) sfx.open();
    if (listening !== prev.listening) (listening ? sfx.micOn : sfx.micOff)();
    if ((homeError && homeError !== prev.homeError) || (visibleError && visibleError !== prev.error)) sfx.error();
    previous.current = { phase, paletteOpen, listening, homeError, error: visibleError };
  }, [phase, paletteOpen, listening, homeError, visibleError]);
  useEffect(() => {
    const tap = (event: MouseEvent) => {
      const button = event.target instanceof Element ? event.target.closest<HTMLButtonElement>("button.tool, button.pill, button.key") : null;
      if (button && !button.disabled) sfx.tap();
    };
    document.addEventListener("click", tap);
    return () => document.removeEventListener("click", tap);
  }, []);

  useEffect(() => {
    api.status().then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    if (phase === "home" || paletteOpen) api.listTutorials().then(setLibrary).catch(() => setLibrary([]));
  }, [phase, paletteOpen]);

  useEffect(() => {
    const offs = [
      listen("tutor:planning", () => setPlanning(true)),
      listen<string>("holo:thinking", (e) => setThinking(e.payload)),
      listen<{ stage: string; detail: string }>("import:progress", (e) => setImportStage(e.payload.detail)),
      listen<MilestoneView[]>("tutor:plan", (e) => {
        setPlanning(false);
        setProgress(e.payload);
      }),
    ];
    return () => offs.forEach((p) => p.then((off) => off()));
  }, []);

  // The native window is exactly the size of what is shown (bar, plus the
  // palette above it when open): follow it.
  useLayoutEffect(() => {
    const el = barRef.current;
    if (!el) return;
    const fit = () =>
      api.resizeBar(Math.ceil(el.getBoundingClientRect().height), paletteRef.current ? PALETTE_WIDTH : BAR_WIDTH);
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    fit();
    return () => ro.disconnect();
  }, [paletteOpen]);

  useEffect(() => {
    api.setSticky(phase === "running" || phase === "planning" || phase === "importing" || phase === "imported" || !!qa);
  }, [phase, qa]);

  useEffect(() => {
    const onFocus = () => inputRef.current?.focus();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey) && liveRef.current.phase === "home") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      } else if (e.key === "Escape" && liveRef.current.phase !== "running" && !paletteRef.current) {
        api.hideBar();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // ---------- Tutorial loop (Holo decides each step from the live screen) ----------

  const showStep = useCallback((s: Step) => {
    if (s.progress.length) setProgress(s.progress);
    if (s.kind === "done") {
      setStep(s);
      setPhase("done");
      api.hidePointer();
      if (voiceRef.current) speak(doneLine(langRef.current), langRef.current);
      return;
    }
    setStep(s);
    setThinking("");
    if (liveRef.current.step) (s.completed.length ? sfx.success : sfx.step)();
    // A milestone just closed: say so briefly.
    const closed = s.completed.length ? liveRef.current.step?.milestone?.goal : null;
    setMessage(closed ? `✓ ${closed}` : "");
    setStepState("waiting");
    if (voiceRef.current) speak(s.instruction, langRef.current);
  }, []);

  /** Tells Holo what the learner did and moves to the step it picks next. */
  const report = useCallback(
    async (event: string) => {
      const { phase, stepState, explain } = liveRef.current;
      if (phase !== "running" || stepState === "thinking" || explain) return;
      setStepState("thinking");
      setThinking("");
      api.hidePointer();
      try {
        const next = await api.tutorNext(event, langRef.current);
        if (liveRef.current.phase !== "running") return;
        showStep(next);
      } catch (e) {
        if (liveRef.current.phase !== "running") return;
        setStepState("error");
        setMessage(errorText(e));
      }
    },
    [showStep],
  );

  // The screen changed and settled (or the target was clicked with no visible
  // effect): let Holo look and decide.
  useEffect(() => {
    const off = listen<{ event: string }>("watch:changed", (e) => report(e.payload.event));
    return () => {
      off.then((f) => f());
    };
  }, [report]);

  // Mirror progress in the menu bar.
  useEffect(() => {
    if (phase === "running" && step) {
      const total = progress.length;
      const n = progress.filter((m) => m.status === "done" || m.status === "skipped").length + 1;
      const prefix = stepState === "thinking" ? "…" : `${Math.min(n, total)}/${total}`;
      api.setTray(`${prefix} · ${step.instruction}`);
    } else if (phase === "done") {
      api.setTray("✓ Terminé");
      const t = setTimeout(() => api.setTray(null), 6000);
      return () => clearTimeout(t);
    } else {
      api.setTray(null);
    }
  }, [phase, step, stepState, progress]);

  async function importVideo(url: string) {
    setHomeError("");
    setImported(null);
    setImportStage("Lecture de la vidéo…");
    setPhase("importing");
    try {
      const t = await api.importYoutube(url.trim());
      setImported(t);
      setGoal("");
      setPhase("imported");
      if (voiceRef.current) speak(readyLine(t.title, t.milestones, langRef.current), langRef.current);
    } catch (e) {
      setHomeError(errorText(e));
      setPhase("home");
    }
  }

  // ---------- The front door: Holo decides between answering and guiding ----------

  async function askOnly(text: string, spoken: string | null = null) {
    const q = text.trim();
    if (!q) return;
    stopSpeaking();
    api.hidePointer();
    setHomeError("");
    setThinking("");
    setQa({ question: q });
    setGoal("");
    langRef.current = await api.resolveLang(q, spoken, langRef.current);
    try {
      const result = await api.answerQuestion(q, langRef.current);
      if (result.kind === "guide") {
        // They want to do it: walk them through it.
        setQa(null);
        startTutorial(q, langRef.current, null, true);
        return;
      }
      setQa((cur) => (cur?.question === q ? { question: q, result } : cur));
      if (voiceRef.current && result.answer) speak(result.answer, langRef.current);
    } catch (e) {
      setQa((cur) => (cur?.question === q ? { question: q, error: errorText(e) } : cur));
    }
  }

  function closeQa() {
    stopSpeaking();
    api.hidePointer();
    setQa(null);
    inputRef.current?.focus();
  }

  /** `direct`: skip the front door (Holo already chose to guide, or "Guide me"). */
  async function startTutorial(
    text = goal,
    lang: string | null = null,
    tutorialId: string | null = null,
    direct = false,
  ) {
    const g = text.trim();
    if (!g && !tutorialId) return;
    if (!tutorialId && isYoutube(g)) return importVideo(g);
    if (!tutorialId && !direct) return askOnly(g, lang);
    setQa(null);
    setHomeError("");
    setSaved(null);
    setProgress([]);
    setPlanning(false);
    setTitle(g);
    // A typed or spoken goal sets the language; a library pick keeps the current one.
    langRef.current = tutorialId ? lang ?? langRef.current : await api.resolveLang(g, lang, langRef.current);
    liveRef.current.step = null;
    setStep(null);
    setPhase("planning");
    try {
      const first = await api.tutorStart(tutorialId ? null : g, tutorialId, langRef.current);
      setPhase("running");
      showStep(first);
    } catch (e) {
      setHomeError(errorText(e));
      setPhase("home");
    }
  }
  const startRef = useRef(startTutorial);
  startRef.current = startTutorial;

  async function skipMilestone() {
    if (liveRef.current.stepState === "thinking") return;
    setStepState("thinking");
    api.hidePointer();
    try {
      showStep(await api.tutorSkipMilestone(langRef.current));
    } catch (e) {
      setStepState("error");
      setMessage(errorText(e));
    }
  }

  function iDidIt() {
    const s = liveRef.current.step;
    const event =
      s?.kind === "write"
        ? `The learner typed “${s.text}”.`
        : s?.kind === "press_key"
          ? `The learner pressed ${s.keys}.`
          : s?.kind === "scroll"
            ? "The learner scrolled."
            : "The learner says they did it.";
    report(event);
  }

  function quit() {
    setExplain(null);
    api.tutorStop();
    stopSpeaking();
    setPhase("home");
  }

  function toggleVoice() {
    if (voice) stopSpeaking();
    setVoice(!voice);
  }

  // ---------- Questions (pause, explain, continue) ----------

  async function askQuestion(text: string, spoken: string | null = null) {
    const q = text.trim();
    if (!q || phase !== "running") return;
    langRef.current = await api.resolveLang(q, spoken, langRef.current);
    stopSpeaking();
    api.hidePointer();
    setQuestion("");
    setAsking(false);
    setExplain({ question: q, details: [], target: "" });
    try {
      const a = await api.ask(q, liveRef.current.step, langRef.current);
      if (!liveRef.current.explain) return; // closed meanwhile
      if (voiceRef.current) speak(a.answer, langRef.current);
      if (a.action === "next") {
        setExplain(null);
        report(`The learner said: “${q}”.`);
        return;
      }
      if (a.action === "repeat") {
        setExplain(null);
        api.tutorResume();
        return;
      }
      const target = a.action === "point" ? a.target : "";
      setExplain({ question: q, answer: a.answer, details: a.details ?? [], target });
      if (target) api.locate(target, a.answer).catch(() => {});
    } catch (e) {
      setExplain({ question: q, details: [], target: "", error: errorText(e) });
    }
  }
  /** A spoken sentence: a question during a tutorial, else a request for the front door. */
  const askRef = useRef((text: string, spoken: string | null) =>
    liveRef.current.phase === "running" ? askQuestion(text, spoken) : askOnly(text, spoken),
  );
  askRef.current = (text: string, spoken: string | null) =>
    liveRef.current.phase === "running" ? askQuestion(text, spoken) : askOnly(text, spoken);

  function continueTutorial() {
    stopSpeaking();
    setExplain(null);
    api.tutorResume();
  }

  // ---------- Voice input (Gladia) ----------

  async function toggleMic() {
    if (listening) {
      api.listenStop();
      return;
    }
    stopSpeaking();
    try {
      await api.listenStart();
    } catch (e) {
      const m = errorText(e);
      if (liveRef.current.phase === "running") setMessage(m);
      else setHomeError(m);
    }
  }

  // A full spoken sentence: a goal on the home screen, a question during a tutorial.
  const onUtterance = useCallback(
    async (text: string, lang: string | null) => {
      const { phase } = liveRef.current;
      if (phase === "home") {
        askRef.current(text, lang);
        return;
      }
      if (phase === "running") askRef.current(text, lang);
    },
    [],
  );

  useEffect(() => {
    const offs = [
      listen<boolean>("stt:state", (e) => {
        setListening(e.payload);
        if (e.payload) {
          setVoiceText({ text: "", final: false });
          return;
        }
        setLevel(0);
        // A sent sentence stays on screen a moment before the dictaphone folds.
        setVoiceText((v) => (v?.final ? v : null));
        setTimeout(() => setVoiceText((v) => (v?.final ? null : v)), 700);
      }),
      listen<number>("stt:level", (e) => setLevel(Math.min(1, Math.sqrt(e.payload) * 2.2))),
      listen<{ text: string; is_final: boolean; language: string | null }>("stt:transcript", (e) => {
        setVoiceText({ text: e.payload.text, final: e.payload.is_final });
        if (e.payload.is_final) onUtterance(e.payload.text, e.payload.language);
      }),
    ];
    return () => offs.forEach((p) => p.then((off) => off()));
  }, [onUtterance]);

  const busy = stepState === "thinking";

  return (
    <div className={`shell ${paletteOpen && phase === "home" ? "shell--library" : ""}`} ref={barRef}>
      {paletteOpen && phase === "home" && (
        <Palette
          tutorials={library}
          onClose={() => {
            setPaletteOpen(false);
            inputRef.current?.focus();
          }}
          onStart={(t) => {
            setPaletteOpen(false);
            startTutorial(t.title, null, t.id);
          }}
        />
      )}
    <div className="bar">
      {phase === "home" && qa && (qa.result || qa.error) && (
        <div className="explain qa">
          <div className="explain__q">
            “{qa.question}”
            <button className="tool qa__close" onClick={closeQa} title="Fermer">
              <IconClose />
            </button>
          </div>
          {qa.error ? (
            <p className="status status--error">{qa.error}</p>
          ) : qa.result ? (
            <>
              <p className="explain__a">{qa.result.answer}</p>
              {qa.result.details.length > 0 && (
                <ul className="explain__list">
                  {qa.result.details.map((d, i) => (
                    <li key={i}>{d}</li>
                  ))}
                </ul>
              )}
              {(qa.result.sources.length > 0 || qa.result.searches.length > 0) && (
                <div className="qa__sources">
                  {qa.result.sources.length > 0
                    ? qa.result.sources.map((s) => (
                        <button key={s.url} className="video-link" onClick={() => openUrl(s.url)} title={s.url}>
                          {s.title}
                        </button>
                      ))
                    : qa.result.searches.map((s, i) => (
                        <span key={i} className="qa__searched">
                          Recherche : « {s.query} »{s.backend === "simulated" ? " · documentation simulée" : ""}
                        </span>
                      ))}
                </div>
              )}
              <div className="explain__actions">
                {qa.result.target && (
                  <button className="pill" onClick={() => api.locate(qa.result!.target, qa.result!.answer).catch(() => {})}>
                    Montre-moi
                  </button>
                )}
                <button
                  className="pill pill--light"
                  onClick={() => {
                    const q = qa.question;
                    closeQa();
                    startTutorial(q, langRef.current, null, true);
                  }}
                >
                  Guide-moi
                </button>
              </div>
            </>
          ) : (
            <p className="explain__a thinking-line">
              <span className="pulse" />
              <span className="thinking-text">{thinking || "Holo lit ta demande…"}</span>
            </p>
          )}
        </div>
      )}
      {(phase === "home" || phase === "planning" || phase === "importing") && (
        <>
          <form
            className="row row--input composer"
            onSubmit={(e) => {
              e.preventDefault();
              if (goal.trim()) sfx.confirm();
              startTutorial();
            }}
          >
            {(phase === "planning" || phase === "importing") && (
              <span className="lead">
                <span className="spinner" />
              </span>
            )}
            {voiceText ? (
              <motion.div
                className="dicta-inline"
                initial={{ opacity: 0, filter: "blur(6px)" }}
                animate={{ opacity: 1, filter: "blur(0px)" }}
                transition={{ duration: 0.24, ease: [0.23, 1, 0.32, 1] }}
              >
                <Wave level={level} done={voiceText.final} size="sm" />
                <Transcript text={tail(voiceText.text, 44)} placeholder="Je t'écoute…" className="dicta-inline__text" />
              </motion.div>
            ) : (
              <input
                ref={inputRef}
                autoFocus
                value={goal}
                disabled={phase === "planning" || phase === "importing"}
                onChange={(e) => setGoal(e.target.value)}
                placeholder="Que veux-tu apprendre ? Ou colle un lien YouTube"
                spellCheck={false}
              />
            )}
            <div className="composer__foot">
            <span className="agent-label">Agent · Holo</span>
            {phase === "importing" ? (
              <span className="hint shimmer">{importStage}</span>
            ) : phase === "planning" ? (
              <span className="hint shimmer">{planning ? "Holo prépare les étapes…" : "Démarrage…"}</span>
            ) : (
              <>
                <button
                  type="button"
                  className={`tool ${paletteOpen ? "tool--on" : ""}`}
                  onClick={() => setPaletteOpen((o) => !o)}
                  title="Tutos (⌘K)"
                >
                  <IconGrid />
                </button>
                <button
                  type="button"
                  className={`tool ${listening ? "tool--rec" : ""}`}
                  style={{ "--mic-ring": 1 + level * 0.25 } as CSSProperties}
                  onClick={toggleMic}
                  title={listening ? "Arrêter l'écoute" : "Parler"}
                >
                  <IconMic />
                </button>
                <button className="key" type="submit" disabled={!goal.trim()} title="Lancer">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19V5m-6 6 6-6 6 6" /></svg>
                </button>
              </>
            )}
            </div>
          </form>
          {phase === "home" && qa && !qa.result && !qa.error && (
            <div className="job-card">
              <div><p className="thinking-line"><span className="pulse" />Holo réfléchit…</p><span className="job-card__detail">{thinking || "Holo lit ta demande…"}</span></div>
              <span className="job-card__tag">holo</span>
            </div>
          )}
          {(phase === "importing" || phase === "planning") && (
            <div className="job-card">
              <div><p>{phase === "importing" ? "Import du tutoriel" : "Création du plan"}</p><span className="job-card__detail">{phase === "importing" ? importStage : planning ? "Holo prépare les étapes…" : "Démarrage…"}</span></div>
              <span className="job-card__tag">{phase === "importing" ? "youtube" : "plan"}</span>
            </div>
          )}
          {homeError && <div className="note note--error">{homeError}</div>}
          {status && !status.has_key && !homeError && (
            <div className="note note--error">HAI_API_KEY manque dans .env</div>
          )}
        </>
      )}

      {phase === "running" && step && (
        <motion.div
          className="run"
          initial={{ opacity: 0, y: 8, filter: "blur(6px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ duration: 0.24, ease: [0.23, 1, 0.32, 1] }}
        >
          <div className="row row--meta">
            <div className="segments" aria-label="Étapes">
              {progress.map((m) => (
                <span
                  key={m.id}
                  title={m.goal}
                  className={`seg ${m.status === "done" ? "seg--done" : m.status === "current" ? "seg--now" : m.status === "skipped" ? "seg--skip" : ""}`}
                />
              ))}
            </div>
            <span className="count milestone" title={step.milestone?.goal}>
              {step.milestone?.goal ?? ""}
            </span>
            <div className="tools">
              <button
                className={`tool ${listening ? "tool--rec" : ""}`}
                style={{ "--mic-ring": 1 + level * 0.25 } as CSSProperties}
                onClick={toggleMic}
                title={listening ? "Arrêter l'écoute" : "Poser une question à voix haute"}
              >
                <IconMic />
              </button>
              <button
                className={`tool ${asking ? "tool--on" : ""}`}
                onClick={() => setAsking((a) => !a)}
                title="Écrire une question"
              >
                <IconKeyboard />
              </button>
              <button className="tool" onClick={() => api.tutorRepoint()} disabled={busy} title="Remontre-moi">
                <IconReplay />
              </button>
              <button className="tool" onClick={iDidIt} disabled={busy} title="C'est fait">
                <IconCheck />
              </button>
              <button
                className="tool"
                onClick={skipMilestone}
                disabled={busy}
                title="Passer cette étape"
              >
                <IconSkip />
              </button>
              <button className="tool" onClick={toggleVoice} title={voice ? "Couper la voix" : "Réactiver la voix"}>
                {voice ? <IconVolume /> : <IconVolumeOff />}
              </button>
              <button className="tool" aria-pressed={sound} onClick={() => setSoundEnabled(!sound)} title={sound ? "Couper les sons" : "Réactiver les sons"}>
                {sound ? <IconSound /> : <IconSoundOff />}
              </button>
              <button className="tool" onClick={quit} title="Arrêter">
                <IconClose />
              </button>
            </div>
          </div>

          {explain && (
            <div className="explain">
              <div className="explain__q">“{explain.question}”</div>
              {explain.error ? (
                <p className="status status--error">{explain.error}</p>
              ) : explain.answer ? (
                <>
                  <p className="explain__a">{explain.answer}</p>
                  {explain.details.length > 0 && (
                    <ul className="explain__list">
                      {explain.details.map((d, i) => (
                        <li key={i}>{d}</li>
                      ))}
                    </ul>
                  )}
                </>
              ) : (
                <p className="explain__a shimmer">Holo réfléchit…</p>
              )}
              <div className="explain__actions">
                {explain.target && (
                  <button className="pill" onClick={() => api.locate(explain.target, explain.answer ?? "")}>
                    Montre-moi
                  </button>
                )}
                <button className="pill pill--light" onClick={continueTutorial}>
                  Continuer
                </button>
              </div>
            </div>
          )}

          <motion.p
            key={step.instruction}
            className={`instruction ${busy || explain ? "instruction--dim" : ""}`}
            initial={{ opacity: 0, y: 6, filter: "blur(6px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            transition={{ duration: 0.24, ease: [0.23, 1, 0.32, 1] }}
          >
            {step.instruction}
          </motion.p>
          {step.teach && !busy && !explain && <div className="teach">{step.teach}</div>}
          {step.milestone?.video_url && !explain && (
            <button className="video-link" onClick={() => openUrl(step.milestone!.video_url!)} title="Ouvrir la vidéo à ce moment">
              <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor" aria-hidden="true"><path d="m2 1 7 4-7 4Z" /></svg> Voir ce passage dans la vidéo
            </button>
          )}
          {step.kind === "write" && step.text && !busy && (
            <div className="chip">
              Tape <code>{step.text}</code>
            </div>
          )}
          {step.kind === "press_key" && step.keys && !busy && (
            <div className="chip">
              Appuie sur <kbd>{step.keys}</kbd>
            </div>
          )}

          {voiceText ? null : explain ? (
            <div className="status">En pause pendant qu'on parle.</div>
          ) : busy ? (
            thinking ? (
              <div className="status status--thinking" title={thinking}>
                <span className="pulse" />
                <span className="thinking-text">{thinking}</span>
              </div>
            ) : (
              <div className="status shimmer">Holo regarde ton écran…</div>
            )
          ) : stepState === "error" ? (
            <div className="status status--error">{message}</div>
          ) : stepState === "success" || message.startsWith("✓ ") ? (
            <div className="status status--ok"><Feedback />{message.replace(/^✓ /, "")}</div>
          ) : (
            <div className="status">
              {message ||
                (step.kind === "click"
                  ? "Va là où je pointe. Je regarde ton écran."
                  : step.kind === "write"
                    ? "Tape-le dans le champ que je pointe."
                    : "Vas-y, je regarde ton écran.")}
            </div>
          )}
          <AnimatePresence initial={false}>
            {voiceText ? (
              <motion.div
                key="dicta"
                className="dicta"
                initial={{ opacity: 0, height: 0, filter: "blur(6px)" }}
                animate={{ opacity: 1, height: "auto", filter: "blur(0px)" }}
                exit={{ opacity: 0, height: 0, filter: "blur(6px)", transition: { duration: 0.2, ease: [0.23, 1, 0.32, 1] } }}
                transition={{ duration: 0.28, ease: [0.23, 1, 0.32, 1] }}
              >
                <Wave level={level} done={voiceText.final} size="lg" />
                <Transcript text={tail(voiceText.text, 140)} placeholder="Je t'écoute…" className="dicta__text" />
              </motion.div>
            ) : (
              asking && (
                <motion.form
                  key="ask"
                  className="ask"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0, transition: { duration: 0.16, ease: [0.23, 1, 0.32, 1] } }}
                  transition={{ duration: 0.22, ease: [0.23, 1, 0.32, 1] }}
                  onSubmit={(e) => {
                    e.preventDefault();
                    askQuestion(question);
                  }}
                >
                  <input
                    autoFocus
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => e.key === "Escape" && setAsking(false)}
                    placeholder="Pose une question à Holo…"
                    spellCheck={false}
                  />
                </motion.form>
              )
            )}
          </AnimatePresence>
        </motion.div>
      )}

      {phase === "imported" && imported && (
        <div className="row row--done">
          <span className="done-text">
            {imported.title} <span className="dim">· {imported.app} · {imported.milestones} étapes</span>
          </span>
          <button className="pill" onClick={() => setPhase("home")}>
            Plus tard
          </button>
          <button className="pill pill--light" onClick={() => startTutorial(imported.title, null, imported.id)}>
            Lancer
          </button>
        </div>
      )}

      {phase === "done" && (
        <div className="row row--done">
          <span className="lead lead--ok">
            <Feedback />
          </span>
          <span className="done-text">
            {saved ? "Ajouté à ta bibliothèque" : "Terminé"} <span className="dim">· {saved ?? title}</span>
          </span>
          {!saved && (
            <button
              className="pill"
              onClick={() => api.saveTutorial().then(setSaved).catch((e) => setHomeError(errorText(e)))}
              title="Garder ce parcours comme tuto réutilisable, avec le chemin que tu as pris comme indices"
            >
              Garder comme tuto
            </button>
          )}
          <button
            className="pill pill--light"
            onClick={() => {
              setGoal("");
              setPhase("home");
            }}
          >
            Nouveau
          </button>
        </div>
      )}
    </div>
    </div>
  );
}

function doneLine(lang: string | null): string {
  return lang === "en" ? "Well done, you finished the tutorial!" : "Bravo, tu as terminé le tuto !";
}

function readyLine(title: string, milestones: number, lang: string | null): string {
  return lang === "en" ? `${title}: ${milestones} milestones, ready.` : `${title} : ${milestones} étapes, c'est prêt.`;
}
