import { invoke } from "@tauri-apps/api/core";

export type MilestoneView = {
  id: string;
  goal: string;
  status: "todo" | "current" | "done" | "skipped";
  optional: boolean;
  /** The source video at the moment showing this milestone (YouTube imports). */
  video_url: string | null;
};
/** The front door's result: an answer, or a decision to guide. */
export type QaAnswer = {
  /** Holo's choice: answer the question, or guide the learner through it. */
  kind: "answer" | "guide";
  goal: string;
  answer: string;
  details: string[];
  app_name: string;
  target: string;
  searches: { app_name: string; query: string; backend: string }[];
  sources: { title: string; url: string }[];
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
export type SkillApp = { name: string; bundle_id?: string; min_version?: string };
export type Skill = {
  tutorial_id: string;
  title: string;
  goal: string;
  app: SkillApp;
  graph: { milestones: unknown[]; [key: string]: unknown };
  runs: { date: number; mode: "learner" | "rio" | "script"; outcome: string; duration_s: number; session_id: string }[];
  compiled: unknown[];
  muted_until: number | null;
  declines: number;
};
export type AutopilotView = {
  done: number;
  matched: string[];
  phase: "hidden" | "expanded" | "compact";
  skill_id: string;
  title: string;
  goal: string;
  index: number;
  total: number;
  label: string;
  outcome: "completed" | "failed" | "stopped" | null;
  message: string | null;
  mode: "script" | "rio";
};

/** One action for the learner, decided by Holo from the live screen. */
export type Step = {
  kind: "click" | "write" | "scroll" | "press_key" | "ask_learner" | "done" | "pending";
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
  /** The learner finds the element alone: no pointer until they ask. */
  hint_only: boolean;
  /** Answer choices when Holo asks the learner a question. */
  options: string[];
};
export type Answer = {
  answer: string;
  details: string[];
  action: "point" | "next" | "repeat" | "none";
  target: string;
  /** The pointer is already on the target. */
  pointed: boolean;
};
export type Status = {
  has_key: boolean;
  has_gladia: boolean;
  fast_model: string;
  smart_model: string;
  tts: string;
};

export const api = {
  skillsList: () => invoke<Skill[]>("skills_list"),
  skillDecline: (skillId: string) => invoke("skill_decline", { skillId }),
  skillProposeNow: (skillId: string) => invoke("skill_propose_now", { skillId }),
  autopilotAccept: (skillId: string) => invoke("autopilot_accept", { skillId }),
  autopilotStop: () => invoke("autopilot_stop"),
  autopilotDecline: () => invoke("autopilot_decline"),
  autopilotView: () => invoke<AutopilotView>("autopilot_view"),
  notchSurface: (surface: { x: number; y: number; width: number; height: number; radius: number }) => invoke("notch_surface", { surface }),
  status: () => invoke<Status>("status"),
  /** Starts a saved tutorial (`tutorialId`) or plans one from a free-form goal. */
  tutorStart: (goal: string | null, tutorialId: string | null, lang: string | null) =>
    invoke<Step>("tutor_start", { goal, tutorialId, lang }),
  tutorSkipMilestone: (lang: string | null) => invoke<Step>("tutor_skip_milestone", { lang }),
  /** Learner language of something said (Gladia's detection) or typed (text detection). */
  resolveLang: (text: string, spoken: string | null, fallback: string | null) =>
    invoke<string>("resolve_lang", { text, spoken, fallback }),
  listTutorials: () => invoke<TutorialSummary[]>("list_tutorials"),
  answerQuestion: (question: string, lang: string | null) => invoke<QaAnswer>("answer_question", { question, lang }),
  /** YouTube video → tutorial in the library (progress on "import:progress"). */
  importYoutube: (url: string) => invoke<Imported>("import_youtube", { url }),
  /** Real icons of installed apps, keyed by app name. */
  /** Saves the run as a tutorial in the library; returns its title. */
  saveTutorial: () => invoke<string>("save_tutorial"),
  tutorNext: (event: string, lang: string | null, onlyIfChanged = false) =>
    invoke<Step>("tutor_next", { event, onlyIfChanged, lang }),
  tutorRepoint: () => invoke("tutor_repoint"),
  /** Shows the element of a step the learner was meant to find alone. */
  tutorReveal: () => invoke("tutor_reveal"),
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
  /** `lang`: the language the learner chose to speak, or null to detect it. */
  listenStart: (lang: string | null) => invoke("listen_start", { lang }),
  listenStop: () => invoke("listen_stop"),
};

export function errorText(e: unknown): string {
  return typeof e === "string" ? e : e instanceof Error ? e.message : JSON.stringify(e);
}

// ---------- Voice output: Phonon (local), played natively; system voice as a fallback ----------

/** `lang` (ISO code) hints Phonon's language; the text's own language wins. */
export async function speak(text: string, lang: string | null = null) {
  window.speechSynthesis?.cancel();
  try {
    await invoke("speak", { text, lang });
  } catch (e) {
    console.warn("Phonon unavailable, using system voice:", e);
    const synth = window.speechSynthesis;
    if (!synth) return;
    const u = new SpeechSynthesisUtterance(text);
    if (lang) u.lang = lang;
    synth.speak(u);
  }
}

export function stopSpeaking() {
  window.speechSynthesis?.cancel();
  invoke("stop_speaking").catch(() => {});
}
