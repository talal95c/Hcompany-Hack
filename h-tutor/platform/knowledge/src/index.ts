// Rio knowledge: a Worker that only searches. It holds ReStep's graphs in D1 (see
// migrations/0001_knowledge.sql) and runs ReStep's core, ported (src/core), to answer:
//   GET /apps                              apps, versions, sizes
//   GET /search?q=&alt=&app=&version=&workspace=&limit=
//                                          skills for a goal, each with its steps for the learner's version
//   GET /skills?app=&q=                    browse an app's skills
//   GET /skills/:id?version=&source=       one skill re-targeted to a version
//   GET /tutorials?app=                    sources read as whole tutorials
//   GET /tutorials/:id?version=&format=rio a tutorial re-targeted, optionally in Rio's milestone format
//   GET /locate?app=&q=&version=           where a UI element is now, under any name it has had
// No public route (workers_dev = false): the platform calls it through a service binding.

import { norm } from "./core/inventory.ts";
import type { Successor, Where } from "./core/inventory.ts";
import { type IngestBody, ingest, listSources, removeSource } from "./ingest.ts";
import { semantic, syncVectors } from "./vectors.ts";
import { type Claim, type Grounding, type Lookup, type PathStep, type Skill, path, resolve } from "./core/retarget.ts";

export interface Env {
  DB: D1Database;
  AI?: Ai;
  HAI_API_KEY?: string;
  HOLO_INGEST_MODEL?: string;
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json; charset=utf-8" } });

// ---------------------------------------------------------------- versions

interface AppRow {
  id: string;
  name: string;
  vendor: string | null;
  current_version: string;
  grounding: string;
}
interface VersionRow {
  version: string;
  label: string | null;
  covers_from: string;
  year: number | null;
}

const parts = (v: string) => (v.match(/\d+/g) ?? []).map(Number);
const cmp = (a: number[], b: number[]) => {
  for (let i = 0; i < Math.max(a.length, b.length); i++) if ((a[i] ?? 0) !== (b[i] ?? 0)) return (a[i] ?? 0) - (b[i] ?? 0);
  return 0;
};

/** The covered version standing for what the learner has: the highest `covers_from` not above it. */
function resolveVersion(app: AppRow, versions: VersionRow[], hint?: string | null) {
  const m = (hint ?? "").match(/\d+(?:\.\d+)*[a-z]?/);
  if (!m) return { id: app.current_version, requested: null as string | null, exact: false };
  const req = parts(m[0]);
  const sorted = [...versions].sort((a, b) => cmp(parts(a.covers_from), parts(b.covers_from)));
  let pick = sorted[0];
  for (const v of sorted) if (cmp(parts(v.covers_from), req) <= 0) pick = v;
  const have = parts(pick.version);
  return { id: pick.version, requested: m[0], exact: req.every((x, i) => have[i] === x) };
}

/** The apps an organization sees: the shared ones and its own internal tools. */
class Apps {
  constructor(private db: D1Database, readonly ws: string | null) {}
  private cache?: Promise<{ apps: AppRow[]; versions: Map<string, VersionRow[]> }>;
  all() {
    return (this.cache ??= (async () => {
      const [a, v] = await this.db.batch([
        this.db.prepare(`select * from app where workspace is null or workspace = ? order by name`).bind(this.ws),
        this.db.prepare(`select v.app, v.version, v.label, v.covers_from, v.year from app_version v join app a on a.id = v.app where a.workspace is null or a.workspace = ?`).bind(this.ws),
      ]);
      const versions = new Map<string, VersionRow[]>();
      for (const r of v.results as (VersionRow & { app: string })[]) (versions.get(r.app) ?? versions.set(r.app, []).get(r.app)!).push(r);
      return { apps: a.results as AppRow[], versions };
    })());
  }
  /** Apps a free-text name refers to ("Blender 4.2", "davinci"); all when empty. */
  async match(text?: string | null) {
    const { apps } = await this.all();
    const t = norm(text);
    if (!t) return apps;
    return apps.filter((a) => {
      const n = norm(a.name);
      return t.includes(n) || t.includes(a.id) || (t.length > 2 && n.includes(t)) || n.split(" ").some((w) => w.length > 3 && t.includes(w));
    });
  }
}

// ---------------------------------------------------------------- the graph, read from D1

const grounding = (a: AppRow): Grounding => ({ nav_ops: [], routine_ops: [], menu_openers: [], confirm_ops: [], ...JSON.parse(a.grounding) });

/** Everything needed to re-target some skills: their claims, and where their operators are in every version. */
async function load(db: D1Database, app: AppRow, skillIds: string[], ws: string | null = null) {
  if (!skillIds.length) return { skills: new Map<string, Skill & { name: string }>(), claims: new Map<string, Claim>(), L: lookup(new Map(), new Map()) };
  const q = skillIds.map(() => "?").join(",");
  const [sk, seg, pr] = await db.batch([
    db.prepare(`select * from skill where id in (${q}) and (workspace is null or workspace = ?)`).bind(...skillIds, ws),
    db.prepare(`select s.*, t.skill_id from segment s join teaches t on t.segment_id = s.id join source o on o.id = s.source_id where t.skill_id in (${q}) and (o.workspace is null or o.workspace = ?)`).bind(...skillIds, ws),
    db.prepare(`select * from proof where skill_id in (${q})`).bind(...skillIds),
  ]);
  const skills = new Map<string, Skill & { name: string; proofs: Record<string, string>; effect: string | null }>();
  for (const r of sk.results as { id: string; name: string; effect_atom: string | null; ops_json: string; steps_json: string }[]) {
    skills.set(r.id, { id: r.id, name: r.name, intent: r.name, ops: JSON.parse(r.ops_json), steps: JSON.parse(r.steps_json), sources: [], proofs: {}, effect: r.effect_atom });
  }
  for (const r of seg.results as { skill_id: string; source_id: string; t_start: number | null; t_end: number | null; version: string | null; steps_json: string }[]) {
    skills.get(r.skill_id)?.sources.push({ source: r.source_id, t: r.t_start, end: r.t_end, version: r.version, steps: JSON.parse(r.steps_json) });
  }
  for (const r of pr.results as { skill_id: string; version: string; status: string }[]) {
    const s = skills.get(r.skill_id);
    if (s) s.proofs[r.version] = r.status;
  }
  const claimIds = [...new Set([...skills.values()].flatMap((s) => [...s.steps, ...s.sources.flatMap((x) => x.steps)]))];
  const claims = new Map<string, Claim>();
  for (let i = 0; i < claimIds.length; i += 90) {
    const ids = claimIds.slice(i, i + 90);
    const { results } = await db
      .prepare(`select c.*, g.atom_id as op from claim c left join grounds g on g.claim_id = c.id where c.id in (${ids.map(() => "?").join(",")})`)
      .bind(...ids)
      .all<{ id: string; source_id: string; say: string | null; action: string | null; ui_json: string; keys: string | null; value: string | null; t: number | null; version: string; variant: string | null; op: string | null }>();
    for (const r of results)
      claims.set(r.id, { id: r.id, say: r.say, action: r.action, ui: JSON.parse(r.ui_json || "[]"), keys: r.keys, value: r.value, t: r.t, source: r.source_id, version: r.version, op: r.op, variant: r.variant });
  }
  const ops = new Set<string>([...claims.values()].map((c) => c.op).filter((o): o is string => !!o));
  for (const s of skills.values()) for (const o of s.ops) ops.add(o);
  const edges = await rows(db, `select * from atom_edge where app = ? and src in (__)`, app.id, [...ops]);
  for (const e of edges) ops.add(e.dst as string);
  const placements = await rows(db, `select * from placement where app = ? and atom_id in (__)`, app.id, [...ops]);
  const where = new Map<string, Where>();
  for (const p of placements)
    where.set(`${p.version}|${p.atom_id}`, {
      op: p.atom_id as string,
      label: p.label as string | null,
      paths: JSON.parse(p.paths_json as string),
      keys: JSON.parse(p.keys_json as string),
      via_keys: JSON.parse(p.via_keys_json as string),
      missing: false,
    });
  const succ = new Map<string, Successor>();
  for (const e of edges) succ.set(`${e.from_version}|${e.to_version}|${e.src}`, { op: e.dst as string, label: e.label as string, why: e.evidence as string, key: e.key as string | null });
  return { skills, claims, L: lookup(where, succ) };
}

function lookup(where: Map<string, Where>, succ: Map<string, Successor>): Lookup {
  return {
    where: (op, v) => where.get(`${v}|${op}`) ?? { op, label: null, paths: [], keys: [], via_keys: [], missing: true },
    successor: (op, from, to) => succ.get(`${from}|${to}|${op}`) ?? null,
  };
}

/** `in (__)` over any number of values, in chunks D1 accepts. */
async function rows(db: D1Database, sql: string, app: string, values: string[]): Promise<Record<string, unknown>[]> {
  const out: Record<string, unknown>[] = [];
  for (let i = 0; i < values.length; i += 90) {
    const chunk = values.slice(i, i + 90);
    const { results } = await db.prepare(sql.replace("__", chunk.map(() => "?").join(","))).bind(app, ...chunk).all();
    out.push(...results);
  }
  return out;
}

const compact = (s: PathStep) => ({
  do: s.do,
  say: s.say,
  label: s.label,
  paths: s.where?.paths.slice(0, 2) ?? [],
  keys: s.where?.keys.slice(0, 2) ?? [],
  was: s.was,
  changed: s.changed,
  missing: s.missing,
  replaced: s.replaced?.label ?? null,
  routine: s.routine,
  t: s.t,
  source: s.source,
});

async function sourcesOf(db: D1Database, ids: string[]) {
  if (!ids.length) return new Map<string, Record<string, unknown>>();
  const { results } = await db
    .prepare(`select id, title, kind, url, version, language from source where id in (${ids.map(() => "?").join(",")})`)
    .bind(...ids)
    .all();
  return new Map(results.map((x) => [x.id as string, x]));
}

// ---------------------------------------------------------------- search

const STOP = new Set(
  ("the and for with from into onto that this then than your you are was were has have how what when where which who why " +
    "can could should would will just only also all any each its not but use using make get set via per over under " +
    "les des une pour avec dans sur par que qui quoi comment est sont mon mes ton tes son ses nos vos leur aux faire veux " +
    "peux dois je tu il elle nous vous ils elles pas plus").split(" "),
);
const tokens = (q: string) =>
  norm(q.normalize("NFD").replace(/[̀-ͯ]/g, ""))
    .split(" ")
    .filter((t) => t.length > 2 && !STOP.has(t));
const stem = (t: string) => t.replace(/(ing|ed|es|s)$/, "").slice(0, Math.max(4, t.length - 3)) || t;

/** Below this cosine, Qwen3's nearest skill is only the least unrelated one (calibrated with scripts/eval.ts). */
const MIN_COS = 0.36; // unrelated questions top out near 0.35 (scripts/eval.ts)
/** A words match whose meaning is this far from the question is a false friend. */
const FALSE_FRIEND = 0.3;

async function search(env: Env, apps: Apps, url: URL) {
  const p = (k: string) => url.searchParams.get(k);
  const sets = [p("q") ?? "", p("alt") ?? ""].map(tokens).filter((t) => t.length);
  const q = (p("q") ?? "").trim();
  if (!q) return { results: [] };
  // fts: ReStep's words search · vec: Qwen3 embeddings · hybrid (default): both, fused by rank
  const mode = (p("mode") ?? (env.AI ? "hybrid" : "fts")) as "fts" | "vec" | "hybrid";
  const targets = await apps.match(p("app"));
  if (!targets.length) return { results: [] };
  const { versions } = await apps.all();
  const limit = Math.min(Number(p("limit")) || 5, 10);
  const all = [...new Set(sets.flat())];
  const fts = all.map((t) => `"${t.replace(/"/g, "")}"`).join(" OR ");
  const ws = p("workspace");
  const { results } = !sets.length || mode === "vec" ? { results: [] as { skill_id: string; app: string; intent: string; body: string; rank: number }[] } : await env.DB.prepare(
    `select skill_id, app, intent, body, bm25(skill_search, 0, 0, 0, 3.0, 1.0) as rank from skill_search
     where skill_search match ? and app in (${targets.map(() => "?").join(",")}) and (workspace is null or workspace = ?)
     order by rank limit 40`,
  )
    .bind(fts, ...targets.map((a) => a.id), ws)
    .all<{ skill_id: string; app: string; intent: string; body: string; rank: number }>();

  // ReStep's rule, kept: at least half of the query's words must be there (any phrasing of it).
  const scored = results
    .map((r) => {
      const text = norm(`${r.intent} ${r.body}`.normalize("NFD").replace(/[̀-ͯ]/g, ""));
      const cover = Math.max(...sets.map((s) => s.filter((t) => text.includes(stem(t))).length / s.length));
      return { ...r, cover, score: Math.round(-r.rank * 100) / 100 };
    })
    .filter((r) => r.cover >= 0.5)
    .filter((r, i, all) => all.findIndex((x) => x.skill_id === r.skill_id) === i);

  // Meaning: any language, any wording. Below MIN_COS a neighbour is just the closest of unrelated things.
  const minCos = Number(p("min_cos") ?? MIN_COS); // calibration (scripts/eval.ts)
  // If Workers AI fails, the words search still answers.
  const sem = mode === "fts" ? null : await semantic(env, targets.map((a) => a.id), ws, q, 20).catch(() => null);
  const near = (sem ?? []).filter((r) => r.cos >= minCos);
  // With meaning available, a words-only match must still mean something close ("commande" is not "Command").
  if (sem && sem.cosOf.size) {
    for (let i = scored.length - 1; i >= 0; i--) if ((sem.cosOf.get(scored[i].skill_id) ?? 0) < FALSE_FRIEND) scored.splice(i, 1);
  }
  // Reciprocal rank fusion: a skill both searches find rises; either one alone still counts.
  const fused = new Map<string, { skill_id: string; app: string; score: number; cos: number | null; words: boolean }>();
  const add = (id: string, app: string, rank: number, cos: number | null, words: boolean) => {
    const f = fused.get(id) ?? { skill_id: id, app, score: 0, cos: null, words: false };
    f.score += 1 / (60 + rank);
    if (cos != null) f.cos = cos;
    f.words ||= words;
    fused.set(id, f);
  };
  scored.forEach((r, i) => add(r.skill_id, r.app, i, null, true));
  near.forEach((r, i) => add(r.id, r.app, i, r.cos, false));
  const ranked = [...fused.values()]
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map((f) => ({ ...f, score: Math.round(f.score * 10000) / 100 }));

  const out = [];
  for (const app of targets) {
    const mine = ranked.filter((r) => r.app === app.id);
    if (!mine.length) continue;
    const version = resolveVersion(app, versions.get(app.id) ?? [], p("version") || p("app"));
    const { skills, claims, L } = await load(env.DB, app, [...new Set(mine.map((r) => r.skill_id))], apps.ws);
    const g = grounding(app);
    const srcs = await sourcesOf(env.DB, [...new Set([...skills.values()].flatMap((s) => s.sources.map((x) => x.source)))]);
    for (const r of mine) {
      const s = skills.get(r.skill_id) as (Skill & { name: string; proofs: Record<string, string> }) | undefined;
      if (!s) continue;
      out.push({
        app: app.id,
        app_name: app.name,
        id: s.id,
        intent: s.name,
        score: r.score,
        match: { words: r.words, cos: r.cos == null ? null : Math.round(r.cos * 1000) / 1000 },
        version,
        proof: s.proofs[version.id] ?? null,
        steps: path(L, g, s, claims, version.id).map(compact),
        sources: s.sources.slice(0, 4).map((x) => ({ ...(srcs.get(x.source) ?? { id: x.source }), t: x.t })),
        taught_by: s.sources.length,
      });
    }
  }
  // Ties go to the skill more sources teach (ReStep's order).
  out.sort((a, b) => b.score - a.score || b.taught_by - a.taught_by);
  return { results: out, semantic: near.length > 0, top_cos: near[0]?.cos ?? null };
}

// ---------------------------------------------------------------- skills, tutorials, atoms

async function oneSkill(env: Env, apps: Apps, id: string, url: URL) {
  const row = await env.DB.prepare(`select app from skill where id = ? and (workspace is null or workspace = ?)`).bind(id, apps.ws).first<{ app: string }>();
  if (!row) return null;
  const { apps: all, versions } = await apps.all();
  const app = all.find((a) => a.id === row.app);
  if (!app) return null;
  const version = resolveVersion(app, versions.get(app.id) ?? [], url.searchParams.get("version"));
  const { skills, claims, L } = await load(env.DB, app, [id], apps.ws);
  const s = skills.get(id)! as Skill & { name: string; proofs: Record<string, string> };
  const srcs = await sourcesOf(env.DB, s.sources.map((x) => x.source));
  const { results: notes } = await env.DB.prepare(
    `select n.source_id, n.kind, n.text, n.t from note n join source s on s.id = n.source_id where n.skill_id = ? and (s.workspace is null or s.workspace = ?)`,
  )
    .bind(id, apps.ws)
    .all();
  return {
    id,
    app: app.id,
    app_name: app.name,
    intent: s.name,
    version,
    proofs: s.proofs,
    steps: path(L, grounding(app), s, claims, version.id, url.searchParams.get("source")).map(compact),
    sources: s.sources.map((x) => ({ ...(srcs.get(x.source) ?? { id: x.source }), t: x.t, end: x.end })),
    notes,
  };
}

async function listSkills(env: Env, apps: Apps, url: URL) {
  const [app] = await apps.match(url.searchParams.get("app"));
  if (!app) return { app: null, skills: [] };
  const q = url.searchParams.get("q");
  let ids: string[];
  if (q?.trim()) {
    ids = (await search(env, apps, new URL(`http://x/search?q=${encodeURIComponent(q)}&app=${app.id}&limit=10`))).results.map((r) => r.id);
  } else {
    const { results } = await env.DB.prepare(
      `select s.id from skill s left join teaches t on t.skill_id = s.id where s.app = ? and (s.workspace is null or s.workspace = ?) group by s.id order by count(t.segment_id) desc, s.name limit 200`,
    )
      .bind(app.id, apps.ws)
      .all<{ id: string }>();
    ids = results.map((r) => r.id);
  }
  const { versions } = await apps.all();
  const vs = versions.get(app.id) ?? [];
  const { skills, claims, L } = await load(env.DB, app, ids, apps.ws);
  const g = grounding(app);
  const srcs = await sourcesOf(env.DB, [...new Set([...skills.values()].flatMap((s) => s.sources.map((x) => x.source)))]);
  return {
    app: { id: app.id, name: app.name, current_version: app.current_version, versions: vs.map((v) => ({ id: v.version, label: v.label })) },
    skills: ids
      .map((id) => skills.get(id) as (Skill & { name: string; proofs: Record<string, string> }) | undefined)
      .filter((s): s is Skill & { name: string; proofs: Record<string, string> } => !!s)
      .map((s) => {
        const steps = Object.fromEntries(vs.map((v) => [v.version, path(L, g, s, claims, v.version).map(compact)]));
        return {
          id: s.id,
          intent: s.name,
          sources: s.sources.map((x) => ({ ...(srcs.get(x.source) ?? { id: x.source }), t: x.t })),
          proofs: s.proofs,
          changed: Object.values(steps).some((st) => st.some((x) => x.changed)),
          steps,
        };
      }),
  };
}

async function tutorials(env: Env, apps: Apps, url: URL) {
  const targets = await apps.match(url.searchParams.get("app"));
  if (!targets.length) return { tutorials: [] };
  const { results } = await env.DB.prepare(
    `select t.*, s.url, s.kind, s.title as source_title, s.author, s.language, a.name as app_name from tutorial t
     join source s on s.id = t.source_id join app a on a.id = t.app
     where t.app in (${targets.map(() => "?").join(",")}) and (t.workspace is null or t.workspace = ?) order by t.title`,
  )
    .bind(...targets.map((a) => a.id), apps.ws)
    .all<{ id: string; app: string; app_name: string; title: string; version: string; skills_json: string; url: string; kind: string; author: string | null; language: string | null }>();
  return {
    tutorials: results.map((t) => ({
      id: `rio:${t.app}:${t.id}`,
      title: t.title,
      app: t.app_name,
      app_id: t.app,
      bundle_id: BUNDLES[t.app] ?? null,
      skills: JSON.parse(t.skills_json).length,
      recorded_on: t.version,
      source_url: t.url,
      kind: t.kind,
      author: t.author,
      language: t.language,
    })),
  };
}

const BUNDLES: Record<string, string> = { blender: "org.blenderfoundation.blender", resolve: "com.blackmagic-design.DaVinciResolve" };

async function oneTutorial(env: Env, apps: Apps, ref: string, url: URL) {
  const [, appId, tid] = ref.match(/^rio:([^:]+):(.+)$/) ?? [null, null, ref];
  const t = await env.DB.prepare(
    `select t.*, s.url, s.kind, s.title as source_title from tutorial t join source s on s.id = t.source_id where t.id = ? and (t.workspace is null or t.workspace = ?)${appId ? " and t.app = ?" : ""}`,
  )
    .bind(...(appId ? [tid, apps.ws, appId] : [tid, apps.ws]))
    .first<{ id: string; app: string; source_id: string; title: string; version: string; skills_json: string; url: string; kind: string }>();
  if (!t) return null;
  const { apps: all, versions } = await apps.all();
  const app = all.find((a) => a.id === t.app);
  if (!app) return null;
  const version = resolveVersion(app, versions.get(app.id) ?? [], url.searchParams.get("version"));
  const ids: string[] = JSON.parse(t.skills_json);
  const { skills, claims, L } = await load(env.DB, app, ids, apps.ws);
  const g = grounding(app);
  const parts = ids
    .map((id) => skills.get(id) as (Skill & { name: string; proofs: Record<string, string> }) | undefined)
    .filter((s): s is Skill & { name: string; proofs: Record<string, string> } => !!s)
    .map((s) => ({ skill: s, steps: path(L, g, s, claims, version.id, t.source_id).map(compact), at: s.sources.find((x) => x.source === t.source_id)?.t ?? null }));
  if (url.searchParams.get("format") !== "rio")
    return { id: `rio:${app.id}:${t.id}`, title: t.title, app: app.name, recorded_on: t.version, version, source: { url: t.url, kind: t.kind }, skills: parts.map((p) => ({ id: p.skill.id, intent: p.skill.name, t: p.at, steps: p.steps })) };
  // Rio's milestone format: one milestone per skill, the re-targeted steps as hints.
  return {
    id: `rio:${app.id}:${t.id}`,
    version: 1,
    title: t.title,
    app: { name: app.name, bundle_id: BUNDLES[app.id] },
    goal: `${t.title} (${app.name}): ${parts.slice(0, 4).map((p) => p.skill.name).join("; ")}${parts.length > 4 ? "; …" : ""}`,
    source: "company",
    source_url: t.url ?? undefined,
    platform_version: version,
    milestones: parts.map((p, i) => ({
      id: `m${i + 1}`,
      goal: p.skill.name,
      done_when: `The result of "${p.skill.name}" is visible on screen`,
      hints: p.steps
        .filter((s) => !s.routine && !s.missing)
        .slice(0, 4)
        .map((s) => s.do + (s.changed && s.was?.label ? ` (it was "${s.was.label}" in ${s.was.version})` : "")),
      video_at: p.at != null && t.kind === "video" ? Math.floor(p.at) : undefined,
    })),
  };
}

/** A UI element by any name it has had: where it is now (its successor if it was replaced), and its older names. */
async function locate(env: Env, apps: Apps, url: URL) {
  const targets = await apps.match(url.searchParams.get("app"));
  const q = norm(url.searchParams.get("q"));
  if (!q || !targets.length) return { results: [] };
  const { versions } = await apps.all();
  const out = [];
  for (const app of targets) {
    const { results } = await env.DB.prepare(`select distinct atom_id from atom_label where app = ? and label_norm = ? limit 8`).bind(app.id, q).all<{ atom_id: string }>();
    if (!results.length) continue;
    const vs = versions.get(app.id) ?? [];
    const version = resolveVersion(app, vs, url.searchParams.get("version"));
    const ops = results.map((r) => r.atom_id);
    const edges = await rows(env.DB, `select * from atom_edge where app = ? and src in (__)`, app.id, ops);
    const all = [...new Set([...ops, ...edges.map((e) => e.dst as string)])];
    const placements = await rows(env.DB, `select * from placement where app = ? and atom_id in (__)`, app.id, all);
    const where = new Map<string, Where>(
      placements.map((p) => [`${p.version}|${p.atom_id}`, { op: p.atom_id as string, label: p.label as string, paths: JSON.parse(p.paths_json as string), keys: JSON.parse(p.keys_json as string), via_keys: JSON.parse(p.via_keys_json as string), missing: false }]),
    );
    const succ = new Map<string, Successor>(edges.map((e) => [`${e.from_version}|${e.to_version}|${e.src}`, { op: e.dst as string, label: e.label as string, why: e.evidence as string, key: e.key as string | null }]));
    const L = lookup(where, succ);
    const seen = new Set<string>();
    for (const op of ops) {
      const from = vs.map((v) => v.version).find((v) => !L.where(op, v).missing) ?? version.id;
      const [cur, s] = resolve(L, op, from, version.id);
      if (!cur || seen.has(cur)) continue;
      seen.add(cur);
      const w = L.where(cur, version.id);
      const aka = [...new Set(vs.map((v) => L.where(op, v.version).label).filter((l): l is string => !!l && l.toLowerCase() !== (w.label ?? "").toLowerCase()))];
      out.push({ app: app.id, app_name: app.name, op: cur, label: w.label ?? op, where: w.missing ? null : w, aka, replaced: s ? { from: op, why: s.why } : null, version });
    }
  }
  return { results: out.slice(0, 6) };
}

async function overview(env: Env, apps: Apps) {
  const { apps: all, versions } = await apps.all();
  const counts = await env.DB.batch([
    env.DB.prepare(`select app, count(*) as n from skill where workspace is null or workspace = ? group by app`).bind(apps.ws),
    env.DB.prepare(`select app, count(*) as n from source where workspace is null or workspace = ? group by app`).bind(apps.ws),
    env.DB.prepare(`select s.app, count(distinct p.skill_id) as n from proof p join skill s on s.id = p.skill_id where p.status = 'PASS' group by s.app`),
    env.DB.prepare(`select app, count(*) as n from atom group by app`),
    env.DB.prepare(`select app, count(*) as n from tutorial where workspace is null or workspace = ? group by app`).bind(apps.ws),
  ]);
  const by = (i: number) => new Map((counts[i].results as { app: string; n: number }[]).map((r) => [r.app, r.n]));
  const [skills, sources, proven, atoms, tuts] = [0, 1, 2, 3, 4].map(by);
  return {
    apps: all.map((a) => ({
      id: a.id,
      name: a.name,
      internal: !!(a as AppRow & { workspace?: string | null }).workspace,
      vendor: a.vendor,
      bundle_id: BUNDLES[a.id] ?? null,
      current_version: a.current_version,
      versions: (versions.get(a.id) ?? []).map((v) => ({ id: v.version, label: v.label })),
      skills: skills.get(a.id) ?? 0,
      sources: sources.get(a.id) ?? 0,
      proven: proven.get(a.id) ?? 0,
      atoms: atoms.get(a.id) ?? 0,
      tutorials: tuts.get(a.id) ?? 0,
    })),
  };
}

/** A name for an atom no scan labelled: tool:builtin.move -> "Move tool", resolve:menu/edit/undo -> "Undo". */
function readable(op: string): string {
  const tool = op.match(/^tool:builtin\.(.+)$/);
  const words = (tool ? tool[1] : op.split(/[/.:]/).pop() ?? op).replace(/[_.]/g, " ");
  const name = words.charAt(0).toUpperCase() + words.slice(1);
  return tool ? `${name} tool` : name;
}

/** ReStep's graph view: sources -> skills -> UI atoms, each atom as the learner meets it now. */
async function graph(env: Env, apps: Apps, url: URL) {
  const [app] = await apps.match(url.searchParams.get("app"));
  if (!app) return { app: null, sources: [], skills: [], atoms: [] };
  const [sk, te, pr, so] = await env.DB.batch([
    env.DB.prepare(`select id, name, ops_json from skill where app = ? and (workspace is null or workspace = ?)`).bind(app.id, apps.ws),
    env.DB.prepare(`select t.skill_id, s.source_id from teaches t join segment s on s.id = t.segment_id join skill k on k.id = t.skill_id join source o on o.id = s.source_id where k.app = ? and (o.workspace is null or o.workspace = ?)`).bind(app.id, apps.ws),
    env.DB.prepare(`select p.skill_id from proof p join skill k on k.id = p.skill_id where k.app = ? and p.status = 'PASS'`).bind(app.id),
    env.DB.prepare(`select id, title, kind, url from source where app = ? and (workspace is null or workspace = ?)`).bind(app.id, apps.ws),
  ]);
  const taught = new Map<string, Set<string>>();
  for (const r of te.results as { skill_id: string; source_id: string }[]) (taught.get(r.skill_id) ?? taught.set(r.skill_id, new Set()).get(r.skill_id)!).add(r.source_id);
  const proven = new Set((pr.results as { skill_id: string }[]).map((r) => r.skill_id));
  const skills = (sk.results as { id: string; name: string; ops_json: string }[])
    .map((r) => ({ id: r.id, name: r.name, ops: [...new Set(JSON.parse(r.ops_json) as string[])], sources: [...(taught.get(r.id) ?? [])], proven: proven.has(r.id) }))
    .filter((r) => r.ops.length);
  const ops = [...new Set(skills.flatMap((s) => s.ops))];
  const placements = await rows(env.DB, `select atom_id, label from placement where app = ? and version = '${app.current_version.replace(/'/g, "")}' and atom_id in (__)`, app.id, ops);
  const label = new Map(placements.map((p) => [p.atom_id as string, p.label as string]));
  // An atom the current version dropped shows under the name it had.
  // Toolbar tools are not in the scans (ReStep reads them from Blender's sources): not missing, just unnamed.
  const missing = ops.filter((o) => !label.has(o) && !o.startsWith("tool:"));
  const older = await rows(env.DB, `select atom_id, label, version from placement where app = ? and atom_id in (__)`, app.id, missing);
  for (const o of older) if (!label.has(o.atom_id as string)) label.set(o.atom_id as string, `${o.label} (${o.version})`);
  return {
    app: { id: app.id, name: app.name, current_version: app.current_version },
    sources: (so.results as { id: string; title: string; kind: string; url: string }[]).filter((s) => skills.some((k) => k.sources.includes(s.id))),
    skills,
    atoms: ops.map((o) => ({ id: o, label: label.get(o) ?? readable(o), current: !missing.includes(o) })),
  };
}

// ---------------------------------------------------------------- routing

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const apps = new Apps(env.DB, url.searchParams.get("workspace"));
    if (req.method === "POST" && url.pathname === "/ingest") {
      const body = (await req.json()) as IngestBody;
      if (!body.workspace || !body.app?.trim() || !body.text) return json({ error: "workspace, app and text are required" }, 400);
      try {
        const r = await ingest(env, body);
        await syncVectors(env, { workspace: body.workspace }).catch(() => {}); // the new skills become searchable by meaning
        return json(r);
      } catch (e) {
        return json({ error: e instanceof Error ? e.message : String(e) }, 422);
      }
    }
    const del = url.pathname.match(/^\/sources\/(.+)$/);
    if (req.method === "DELETE" && del) {
      if (!apps.ws) return json({ error: "workspace required" }, 400);
      const ok = await removeSource(env.DB, apps.ws, decodeURIComponent(del[1]));
      if (ok) await syncVectors(env, { workspace: apps.ws }).catch(() => {});
      return ok ? json({ ok: true }) : json({ error: "unknown source" }, 404);
    }
    // Embeds what changed (after an import: `curl -X POST .../vectors/sync`).
    if (req.method === "POST" && url.pathname === "/vectors/sync") return json(await syncVectors(env, { app: url.searchParams.get("app") ?? undefined }));
    if (req.method !== "GET") return json({ error: "method not allowed" }, 405);
    try {
      if (url.pathname === "/health") return json({ ok: true });
      if (url.pathname === "/apps") return json(await overview(env, apps));
      if (url.pathname === "/sources") return json({ sources: apps.ws ? await listSources(env.DB, apps.ws) : [] });
      if (url.pathname === "/graph") return json(await graph(env, apps, url));
      if (url.pathname === "/search") return json(await search(env, apps, url));
      if (url.pathname === "/skills") return json(await listSkills(env, apps, url));
      if (url.pathname === "/locate") return json(await locate(env, apps, url));
      if (url.pathname === "/tutorials") return json(await tutorials(env, apps, url));
      let m = url.pathname.match(/^\/skills\/(.+)$/);
      if (m) {
        const s = await oneSkill(env, apps, decodeURIComponent(m[1]), url);
        return s ? json(s) : json({ error: "unknown skill" }, 404);
      }
      m = url.pathname.match(/^\/tutorials\/(.+)$/);
      if (m) {
        const t = await oneTutorial(env, apps, decodeURIComponent(m[1]), url);
        return t ? json(t) : json({ error: "unknown tutorial" }, 404);
      }
      return json({ error: "not found" }, 404);
    } catch (e) {
      return json({ error: e instanceof Error ? e.message : String(e) }, 500);
    }
  },
} satisfies ExportedHandler<Env>;
