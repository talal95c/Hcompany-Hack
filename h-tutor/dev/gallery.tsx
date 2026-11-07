import ReactDOM from "react-dom/client";
import { MotionConfig } from "motion/react";
import { mockIPC, mockWindows } from "@tauri-apps/api/mocks";
import { emit } from "@tauri-apps/api/event";
import App from "../src/panel/App";
import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";
import "../src/panel/styles.css";
import "./gallery.css";

const states = ["home-empty", "home-typed", "listening", "importing", "planning", "thinking", "running", "explain", "qa", "done", "error", "palette", "palette-empty"];
const backgrounds = ["pioneer", "terracotta", "grey", "busy"];
const params = new URLSearchParams(location.search);
const state = states.includes(params.get("state") ?? "") ? params.get("state")! : "home-typed";
const background = backgrounds.includes(params.get("bg") ?? "") ? params.get("bg")! : "pioneer";
document.documentElement.dataset.material = params.get("material") === "css" ? "css" : "native";
document.documentElement.dataset.background = background;
document.documentElement.dataset.state = state;

const tutorials = [
  { id: "01", title: "Créer une scène et son premier objet", goal: "Créer une scène", app: "Blender", bundle_id: null, milestones: 6, source: "youtube" },
  { id: "02", title: "Éclairer une scène avec une lumière douce", goal: "Éclairer une scène", app: "Blender", bundle_id: null, milestones: 4, source: "generated" },
  { id: "03", title: "Organiser un tableau de suivi", goal: "Créer un tableau", app: "Excel", bundle_id: null, milestones: 5, source: "recorded" },
];
const progress = Array.from({ length: 6 }, (_, i) => ({ id: String(i), goal: i === 2 ? "Ajouter un objet" : "Préparer la scène", status: i < 2 ? "done" : i === 2 ? "current" : "todo", optional: false, video_url: null }));
const step = { kind: "click", instruction: "Ouvre le menu Ajouter, puis choisis Mesh → Cube.", element: "Ajouter", point: null, text: "", keys: "", unchanged: false, milestone: progress[2], progress, completed: [], teach: "Le cube sera placé au centre de la scène." };
const pending = () => new Promise<never>(() => {});
let mounted!: () => void;
const mountReady = new Promise<void>(resolve => { mounted = resolve; });
mockWindows("main");
mockIPC(async (cmd) => {
  if (cmd === "status") { mounted(); return { has_key: true, has_gladia: true }; }
  if (cmd === "list_tutorials") return state === "palette-empty" ? [] : tutorials;
  if (cmd === "app_icons") return {};
  if (cmd === "resolve_lang") return "fr";
  if (cmd === "import_youtube") return pending();
  if (cmd === "answer_question") {
    if (state === "thinking") return pending();
    if (state === "error") throw "La connexion a été interrompue. Réessaie dans un instant.";
    if (state === "qa") return { kind: "answer", answer: "Le mode Objet permet de déplacer un objet entier. Le mode Édition permet de modifier ses sommets, arêtes et faces.", details: ["Appuie sur Tab pour passer d’un mode à l’autre."], target: "Mode Objet", searches: [], sources: [{ title: "Blender · Modes d’édition", url: "https://docs.blender.org/manual/fr/latest/modeling/meshes/introduction.html" }] };
    return { kind: "guide" };
  }
  if (cmd === "tutor_start") {
    if (state === "planning") { void emit("tutor:planning"); return pending(); }
    return state === "done" ? { ...step, kind: "done" } : step;
  }
  if (cmd === "ask") {
    await frame();
    return { answer: "Le menu Ajouter rassemble les objets que tu peux insérer dans ta scène.", details: ["Mesh contient les formes de base : cube, sphère et plan."], action: "point", target: "Ajouter" };
  }
  if (cmd === "listen_start") { await emit("stt:state", true); await emit("stt:level", .16); await emit("stt:transcript", { text: "Comment ajouter un cube dans ma scène", is_final: false, language: "fr" }); }
  if (cmd === "listen_stop") await emit("stt:state", false);
  return null;
}, { shouldMockEvents: true });

function changeParam(key: string, value: string) {
  params.set(key, value);
  location.search = params.toString();
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <MotionConfig reducedMotion="user">
    <div className="study-background" aria-hidden="true" />
    {background === "busy" && <div className="busy-app" aria-hidden="true"><div className="busy-app__menu">File　 Edit　 View　 Insert　 Format　 Data　 Tools　 Window　 Help</div><div className="busy-app__toolbar">↶　↷　　Arial　 11　　 B　 I　 U　　 Σ　　Sort & Filter</div><div className="busy-app__formula">A1　　 fx　　Quarterly forecast · Operations</div><div className="busy-app__grid">{Array.from({ length: 252 }, (_, i) => <span key={i}>{i < 12 ? String.fromCharCode(65 + i) : i % 12 === 0 ? Math.floor(i / 12) : i % 9 === 0 ? "Forecast" : (i * 173.42).toLocaleString("fr-FR", { maximumFractionDigits: 2 })}</span>)}</div></div>}
    <header className="study-controls"><svg className="r-mark" viewBox="0 0 96 84" aria-label="R"><path fill="currentColor" d="M24 0H84V40L64 60V20H24V60L0 84V24ZM24 60H64L96 84H48Z" /></svg><span>Material study</span><label>État<select aria-label="État" value={state} onChange={e => changeParam("state", e.target.value)}>{states.map(s => <option key={s}>{s}</option>)}</select></label><label>Fond<select aria-label="Fond" value={background} onChange={e => changeParam("bg", e.target.value)}>{backgrounds.map(s => <option key={s}>{s}</option>)}</select></label><label>Matériau<select aria-label="Matériau" value={document.documentElement.dataset.material} onChange={e => changeParam("material", e.target.value)}><option>native</option><option>css</option></select></label></header>
    <main className={`study-stage ${state.startsWith("palette") ? "study-stage--wide" : ""}`}><App /></main>
    <footer className="study-caption">{state} <span>·</span> {background} <span>·</span> données de démonstration · aucun service connecté</footer>
  </MotionConfig>,
);

const frame = () => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
async function input(selector: string, value: string) {
  const el = document.querySelector<HTMLInputElement>(selector)!;
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  await frame();
}
async function arrange() {
  await mountReady;
  await frame();
  if (state.startsWith("palette")) {
    document.querySelector<HTMLButtonElement>('[title="Tutos (⌘K)"]')!.click();
  } else if (state === "listening") {
    document.querySelector<HTMLButtonElement>('[title="Parler"]')!.click();
  } else if (state !== "home-empty") {
    await input(".composer input", state === "importing" ? "https://www.youtube.com/watch?v=demo" : state === "qa" || state === "thinking" || state === "error" ? "Quelle différence entre le mode Objet et le mode Édition ?" : "Créer ma première scène dans Blender");
    if (state !== "home-typed") document.querySelector<HTMLFormElement>(".composer")!.requestSubmit();
    await frame();
    await frame();
    if (state === "explain") {
      document.querySelector<HTMLButtonElement>('[title="Écrire une question"]')!.click();
      await frame();
      await input(".ask input", "À quoi sert ce menu ?");
      document.querySelector<HTMLFormElement>(".ask")!.requestSubmit();
      await frame();
      await frame();
    }
  }
  await frame();
  document.documentElement.dataset.ready = "true";
}
void arrange();
