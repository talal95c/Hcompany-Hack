import { invoke } from "@tauri-apps/api/core";

export type MilestoneView = {
  id: string;
  goal: string;
  status: "todo" | "current" | "done" | "skipped";
  optional: boolean;
  /** The source video at the moment showing this milestone (YouTube imports). */
  video_url: string | null;
};
export type Imported = { id: string; title: string; app: string; milestones: number; language: string | null };
export type TutorialSummary = {
  id: string;
  title: string;
  app: string;
  bundle_id: string | null;
  goal: string;
  milestones: number;
  source: string;
};
export type AppIcon = { data_uri: string; color: string };

/** One action for the learner, decided by Holo from the live screen. */
export type Step = {
  kind: "click" | "write" | "scroll" | "press_key" | "done";
  instruction: string;
  element: string;
  point: [number, number] | null;
  text: string;
  keys: string;
  unchanged: boolean;
  /** Current milestone and the whole graph's state. */
  milestone: MilestoneView | null;
  progress: MilestoneView[];
  /** Milestones closed while computing this step. */
  completed: string[];
  teach: string | null;
};
export type Answer = {
  answer: string;
  details: string[];
  action: "point" | "next" | "repeat" | "none";
  target: string;
};
export type Status = {
  has_key: boolean;
  has_gladia: boolean;
  fast_model: string;
  smart_model: string;
  tts: string;
};

export const api = {
  status: () => invoke<Status>("status"),
  /** Starts a saved tutorial (`tutorialId`) or plans one from a free-form goal. */
  tutorStart: (goal: string | null, tutorialId: string | null, lang: string | null) =>
    invoke<Step>("tutor_start", { goal, tutorialId, lang }),
  tutorSkipMilestone: (lang: string | null) => invoke<Step>("tutor_skip_milestone", { lang }),
  /** Learner language of something said (Gladia's detection) or typed (text detection). */
  resolveLang: (text: string, spoken: string | null, fallback: string | null) =>
    invoke<string>("resolve_lang", { text, spoken, fallback }),
  listTutorials: () => invoke<TutorialSummary[]>("list_tutorials"),
  /** YouTube video → tutorial in the library (progress on "import:progress"). */
  importYoutube: (url: string) => invoke<Imported>("import_youtube", { url }),
  /** Real icons of installed apps, keyed by app name. */
  appIcons: (apps: [string, string | null][]) => invoke<Record<string, AppIcon>>("app_icons", { apps }),
  /** Saves the run as a tutorial in the library; returns its title. */
  saveTutorial: () => invoke<string>("save_tutorial"),
  tutorNext: (event: string, lang: string | null, onlyIfChanged = false) =>
    invoke<Step>("tutor_next", { event, onlyIfChanged, lang }),
  tutorRepoint: () => invoke("tutor_repoint"),
  /** Ends a question pause: shows the step again and watches the screen. */
  tutorResume: () => invoke("tutor_resume"),
  tutorStop: () => invoke("tutor_stop"),
  locate: (target: string, label: string) => invoke("locate", { target, label }),
  ask: (question: string, step: Step | null, lang: string | null) =>
    invoke<Answer>("ask", { question, instruction: step?.instruction, target: step?.element, lang }),
  hidePointer: () => invoke("hide_pointer"),
  /** Text next to the menu bar icon; null clears it. */
  setTray: (text: string | null) => invoke("set_tray_status", { text }),
  hideBar: () => invoke("hide_bar"),
  resizeBar: (height: number, width: number) => invoke("resize_bar", { height, width }),
  setSticky: (sticky: boolean) => invoke("set_bar_sticky", { sticky }),
  listenStart: () => invoke("listen_start"),
  listenStop: () => invoke("listen_stop"),
};

export function errorText(e: unknown): string {
  return typeof e === "string" ? e : e instanceof Error ? e.message : JSON.stringify(e);
}

// ---------- Voice output: Phonon (local), WebKit speech as a fallback ----------

let ctx: AudioContext | null = null;
let current: AudioBufferSourceNode | null = null;
let seq = 0;

/** `lang` (ISO code) picks Phonon's language and voice; detected from the text when null. */
export async function speak(text: string, lang: string | null = null) {
  const id = ++seq;
  stopAudio();
  try {
    const raw = await invoke<ArrayBuffer>("say", { text, lang });
    if (id !== seq) return; // superseded while synthesizing
    const rate = new DataView(raw).getUint32(0, true);
    const samples = new Float32Array(raw.slice(4));
    ctx ??= new AudioContext();
    if (ctx.state === "suspended") await ctx.resume();
    const buffer = ctx.createBuffer(1, samples.length, rate);
    buffer.copyToChannel(samples, 0);
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(ctx.destination);
    src.start();
    current = src;
  } catch (e) {
    if (id !== seq) return;
    console.warn("Phonon unavailable, using system voice:", e);
    const synth = window.speechSynthesis;
    if (!synth) return;
    const u = new SpeechSynthesisUtterance(text);
    if (lang) u.lang = lang;
    synth.speak(u);
  }
}

function stopAudio() {
  try {
    current?.stop();
  } catch {
    /* already stopped */
  }
  current = null;
  window.speechSynthesis?.cancel();
}

export function stopSpeaking() {
  seq++;
  stopAudio();
}
