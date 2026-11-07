// Knowledge base logic, independent of Cloudflare so it runs under `node --test`.
// Data comes from scripts/export_restep.py: per skill, its steps already
// re-targeted to every version of the app by ReStep.

export interface Step {
  do: string;
  label?: string | null;
  paths: string[];
  keys: string[];
  was?: { version: string; label: string | null; paths: string[]; via_keys: string[] } | null;
  changed: boolean;
  missing: boolean;
  replaced?: string | null;
  routine: boolean;
  t?: number | null;
  source?: string | null;
}

export interface Source {
  id: string;
  title: string | null;
  kind: string | null;
  url: string | null;
  version: string | null;
  language: string | null;
  t?: number | null;
  end?: number | null;
}

export interface Skill {
  intent: string;
  words: string[];
  intent_words: string[];
  sources: Source[];
  proofs: Record<string, string>;
  steps: Record<string, Step[]>;
}

export interface AppData {
  format: number;
  app: {
    id: string;
    name: string;
    bundle_id: string | null;
    versions: { id: string; label: string | null; covers_from: string }[];
    current_version: string;
  };
  skills: Record<string, Skill>;
  tutorials: Record<string, { title: string; recorded_on: string | null; source: Source; paths: string[] }>;
}

/** Same as ReStep's `inventory.norm`, plus accents folded so "créer" stays one word. */
export function norm(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

/** Words that say nothing about a task: on a small base they would match anything. */
const STOP = new Set(
  ("the and for with from into onto that this then than your you are was were has have how what when where which who why " +
    "can could should would will just only also all any each its it's not but use using make get set via per over under " +
    "les des une pour avec dans sur par que qui quoi comment est sont mon mes ton tes son ses nos vos leur aux faire veux " +
    "peux dois je tu il elle nous vous ils elles pas plus").split(" "),
);

export function tokens(q: string): string[] {
  return norm(q)
    .split(" ")
    .filter((t) => t.length > 2 && !STOP.has(t));
}

interface Index {
  docs: Map<string, { words: Set<string>; intent: Set<string> }>;
  idf: Map<string, number>;
}

const indexes = new WeakMap<AppData, Index>();

function index(data: AppData): Index {
  let ix = indexes.get(data);
  if (ix) return ix;
  const docs = new Map<string, { words: Set<string>; intent: Set<string> }>();
  const df = new Map<string, number>();
  for (const [id, s] of Object.entries(data.skills)) {
    const words = new Set(s.words);
    docs.set(id, { words, intent: new Set(s.intent_words) });
    for (const w of words) df.set(w, (df.get(w) ?? 0) + 1);
  }
  const n = Math.max(docs.size, 1);
  const idf = new Map<string, number>();
  for (const [w, c] of df) idf.set(w, Math.log(1 + n / c));
  ix = { docs, idf };
  indexes.set(data, ix);
  return ix;
}

/** ReStep's scoring: rare words weigh more, words of the skill's name count double, a plural matches its singular. */
function score(toks: string[], words: Set<string>, intent: Set<string>, idf: Map<string, number>): number {
  let s = 0;
  let hits = 0;
  for (const t of toks) {
    const hit = words.has(t) ? t : t.length > 4 && words.has(t.slice(0, -1)) ? t.slice(0, -1) : null;
    if (hit) {
      s += (idf.get(hit) ?? 1) * (intent.has(hit) ? 2 : 1);
      hits++;
    }
  }
  // At least half of the query's words must match: one generic word ("settings") is not an answer.
  return hits * 2 >= toks.length ? s : 0;
}

function versionParts(v: string): number[] {
  return (v.match(/\d+/g) ?? []).map(Number);
}

function cmp(a: number[], b: number[]): number {
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const d = (a[i] ?? 0) - (b[i] ?? 0);
    if (d) return d;
  }
  return 0;
}

export interface ResolvedVersion {
  /** The version whose steps are served. */
  id: string;
  /** What the client asked for, if it named a version. */
  requested: string | null;
  /** True when the served version is the one asked for (same leading numbers). */
  exact: boolean;
}

/** The app version that covers what the learner has: the one with the highest `covers_from` not above it. */
export function resolveVersion(app: AppData["app"], hint: string | null | undefined): ResolvedVersion {
  // Tutorials made on the platform are not tied to a version.
  if (app.versions.length === 1 && app.versions[0].id === ANY) return { id: ANY, requested: null, exact: true };
  const m = (hint ?? "").match(/\d+(?:\.\d+)*[a-z]?/);
  if (!m) return { id: app.current_version, requested: null, exact: false };
  const req = versionParts(m[0]);
  const sorted = [...app.versions].sort((a, b) => cmp(versionParts(a.covers_from), versionParts(b.covers_from)));
  let pick = sorted[0];
  for (const v of sorted) if (cmp(versionParts(v.covers_from), req) <= 0) pick = v;
  const have = versionParts(pick.id);
  const exact = req.every((x, i) => have[i] === x);
  return { id: pick.id, requested: m[0], exact };
}

/** Which apps of the organization a free-text app name ("Blender 4.2", "blender") refers to. */
export function resolveApps(all: AppData[], appText: string | null | undefined): AppData[] {
  const t = norm(appText ?? "");
  if (!t) return all;
  return all.filter((d) => {
    const name = norm(d.app.name);
    return t.includes(name) || t.includes(d.app.id) || (t.length > 2 && name.includes(t));
  });
}

export interface SearchHit {
  app: string;
  app_name: string;
  id: string;
  intent: string;
  score: number;
  version: ResolvedVersion;
  /** "PASS" | "FAIL" when ReStep's engine ran this path on that version, else null. */
  proof: string | null;
  steps: Step[];
  sources: Source[];
}

/**
 * Skills for a goal or a question. `queries` holds the learner's words and,
 * optionally, English keywords for them; each skill keeps its best score.
 */
export function search(
  all: AppData[],
  queries: string[],
  opts: { app?: string | null; version?: string | null; limit?: number } = {},
): SearchHit[] {
  const sets = queries.map(tokens).filter((t) => t.length);
  const out: SearchHit[] = [];
  for (const data of resolveApps(all, opts.app)) {
    const { docs, idf } = index(data);
    const version = resolveVersion(data.app, opts.version || opts.app);
    for (const [id, d] of docs) {
      const s = Math.max(0, ...sets.map((t) => score(t, d.words, d.intent, idf)));
      if (!s) continue;
      const skill = data.skills[id];
      const steps = skill.steps[version.id] ?? Object.values(skill.steps)[0] ?? [];
      out.push({
        app: data.app.id,
        app_name: data.app.name,
        id,
        intent: skill.intent,
        score: Math.round(s * 100) / 100,
        version,
        proof: skill.proofs[version.id] ?? null,
        steps,
        sources: skill.sources.slice(0, 4),
      });
    }
  }
  out.sort((a, b) => b.score - a.score || b.sources.length - a.sources.length);
  return out.slice(0, opts.limit ?? 5);
}

export interface TutorialSummary {
  id: string;
  title: string;
  app: string;
  bundle_id: string | null;
  goal: string;
  milestones: number;
  source: "company";
  source_url: string | null;
  author_kind: string | null;
  recorded_on: string | null;
}

/** Rio's tutorial id for a platform tutorial: `rio:<app>:<tutorial>`. */
export function rioId(app: string, tid: string): string {
  return `rio:${app}:${tid}`;
}

function goalOf(data: AppData, tid: string): string {
  const t = data.tutorials[tid];
  const intents = t.paths.map((p) => data.skills[p].intent);
  const head = intents.slice(0, 4).join("; ");
  return `${t.title} (${data.app.name}): ${head}${intents.length > 4 ? "; …" : ""}`;
}

export function listTutorials(all: AppData[], appText?: string | null): TutorialSummary[] {
  const out: TutorialSummary[] = [];
  for (const data of resolveApps(all, appText)) {
    for (const [tid, t] of Object.entries(data.tutorials)) {
      out.push({
        id: rioId(data.app.id, tid),
        title: t.title,
        app: data.app.name,
        bundle_id: data.app.bundle_id,
        goal: goalOf(data, tid),
        milestones: t.paths.length,
        source: "company",
        source_url: t.source.url,
        author_kind: t.source.kind,
        recorded_on: t.recorded_on,
      });
    }
  }
  return out.sort((a, b) => a.title.localeCompare(b.title));
}

function hint(s: Step): string {
  let h = s.do;
  if (s.changed && s.was?.label) h += ` (changed: it was "${s.was.label}" in ${s.was.version})`;
  return h;
}

/**
 * A platform tutorial in Rio's milestone format: one milestone per skill, the
 * steps re-targeted to the learner's version as hints (guidance, not a script).
 */
export function rioTutorial(all: AppData[], id: string, versionHint?: string | null) {
  const [, appId, tid] = id.match(/^rio:([^:]+):(.+)$/) ?? [];
  const data = all.find((d) => d.app.id === appId);
  const t = data?.tutorials[tid];
  if (!data || !t) return null;
  const version = resolveVersion(data.app, versionHint);
  return {
    id,
    version: 1,
    title: t.title,
    app: { name: data.app.name, bundle_id: data.app.bundle_id ?? undefined, min_version: undefined },
    goal: goalOf(data, tid),
    source: "company",
    source_url: t.source.url ?? undefined,
    platform_version: version,
    milestones: t.paths.map((pid, i) => {
      const s = data.skills[pid];
      const steps = (s.steps[version.id] ?? []).filter((x) => !x.routine && !x.missing);
      const own = s.sources.find((x) => x.id === t.source.id);
      return {
        id: `m${i + 1}`,
        goal: s.intent,
        done_when: `The result of "${s.intent}" is visible on screen`,
        hints: steps.slice(0, 4).map(hint),
        video_at: own?.t != null && t.source.kind === "video" ? Math.floor(own.t) : undefined,
      };
    }),
  };
}

export const ANY = "any";

/** A tutorial made on the platform, in Rio's format (stored in D1). */
export interface RioTutorial {
  id: string;
  title: string;
  app: { name: string; bundle_id?: string };
  goal: string;
  source_url?: string;
  credit?: { kind: string; title?: string; author?: string; url: string; thumbnail?: string };
  milestones: { id: string; goal: string; done_when: string; hints?: string[]; teach?: string; video_at?: number }[];
}

const appSlug = (name: string) => norm(name).replace(/ /g, "-") || "app";

/**
 * The organization's own tutorials as searchable knowledge: each milestone is a
 * skill (its goal, hints and lesson), one knowledge base per application.
 */
export function tutorialsAsKb(tutorials: RioTutorial[]): AppData[] {
  const byApp = new Map<string, AppData>();
  for (const t of tutorials) {
    const id = appSlug(t.app.name);
    let data = byApp.get(id);
    if (!data) {
      data = {
        format: 1,
        app: { id, name: t.app.name, bundle_id: t.app.bundle_id ?? null, versions: [{ id: ANY, label: null, covers_from: "0" }], current_version: ANY },
        skills: {},
        tutorials: {},
      };
      byApp.set(id, data);
    }
    const source: Source = { id: t.id, title: t.title, kind: "tutorial", url: t.source_url ?? null, version: null, language: null };
    for (const m of t.milestones) {
      const hints = m.hints ?? [];
      data.skills[`${t.id}#${m.id}`] = {
        intent: m.goal,
        words: [...new Set(tokens([t.title, m.goal, ...hints, m.teach ?? ""].join(" ")))],
        intent_words: [...new Set(tokens(m.goal))],
        sources: [{ ...source, t: m.video_at ?? null }],
        proofs: {},
        steps: { [ANY]: hints.map((h) => ({ do: h, paths: [], keys: [], changed: false, missing: false, routine: false })) },
      };
    }
  }
  return [...byApp.values()];
}

export function summaryOf(t: RioTutorial): TutorialSummary {
  return {
    id: t.id,
    title: t.title,
    app: t.app.name,
    bundle_id: t.app.bundle_id ?? null,
    goal: t.goal,
    milestones: t.milestones.length,
    source: "company",
    source_url: t.source_url ?? null,
    author_kind: "platform",
    recorded_on: null,
  };
}
