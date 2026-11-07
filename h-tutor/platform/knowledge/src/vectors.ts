// Semantic search with Qwen3-Embedding-0.6B (Workers AI): one vector per search row, compared by
// cosine in the Worker. At this size (hundreds of skills) a scan beats any index; Vectorize can take
// over at tens of thousands.

export const MODEL = "@cf/qwen/qwen3-embedding-0.6b";
const BATCH = 32; // the model's limit per call
const MAX_CHARS = 1_500; // the skill and what its sources say first: a long tail of labels dilutes the meaning

export interface VecEnv {
  DB: D1Database;
  AI?: Ai;
}

async function sha(s: string) {
  const d = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 16);
}

function unit(v: number[]): Float32Array {
  const f = Float32Array.from(v);
  const n = Math.hypot(...f) || 1;
  for (let i = 0; i < f.length; i++) f[i] /= n;
  return f;
}

async function embed(env: VecEnv, input: { documents: string[] } | { queries: string[] }): Promise<Float32Array[]> {
  if (!env.AI) throw new Error("Workers AI is not bound");
  const r = (await env.AI.run(MODEL as Parameters<Ai["run"]>[0], input as never)) as { data?: number[][] };
  if (!r.data) throw new Error("no embeddings returned");
  return r.data.map(unit);
}

/** Embeds the search rows that are new or changed (all, one app, one workspace, or some skills). */
export async function syncVectors(env: VecEnv, f: { app?: string; workspace?: string | null; skills?: string[] } = {}) {
  if (!env.AI) return { embedded: 0, removed: 0, skipped: "no AI binding" };
  const where: string[] = [];
  const binds: unknown[] = [];
  if (f.app) where.push("app = ?"), binds.push(f.app);
  if (f.workspace !== undefined) where.push(f.workspace === null ? "workspace is null" : "workspace = ?"), f.workspace !== null && binds.push(f.workspace);
  if (f.skills?.length) where.push(`skill_id in (${f.skills.map(() => "?").join(",")})`), binds.push(...f.skills);
  const cond = where.length ? `where ${where.join(" and ")}` : "";
  const { results: rows } = await env.DB.prepare(`select skill_id, app, workspace, intent, body from skill_search ${cond}`)
    .bind(...binds)
    .all<{ skill_id: string; app: string; workspace: string | null; intent: string; body: string }>();
  const { results: have } = await env.DB.prepare(`select skill_id, workspace, text_hash, model from skill_vector ${cond.replace(/workspace is null/, "workspace = ''")}`)
    .bind(...binds.map((b) => b))
    .all<{ skill_id: string; workspace: string; text_hash: string; model: string }>();
  const known = new Map(have.map((h) => [`${h.skill_id}|${h.workspace}`, h]));
  const todo: { key: string; skill: string; ws: string; app: string; text: string; hash: string }[] = [];
  const live = new Set<string>();
  for (const r of rows) {
    const ws = r.workspace ?? "";
    const text = `${r.intent}\n${r.body}`.slice(0, MAX_CHARS);
    const hash = await sha(text);
    const key = `${r.skill_id}|${ws}`;
    live.add(key);
    const k = known.get(key);
    if (!k || k.text_hash !== hash || k.model !== MODEL) todo.push({ key, skill: r.skill_id, ws, app: r.app, text, hash });
  }
  for (let i = 0; i < todo.length; i += BATCH) {
    const batch = todo.slice(i, i + BATCH);
    const vecs = await embed(env, { documents: batch.map((b) => b.text) });
    await env.DB.batch(
      batch.map((b, j) =>
        env.DB.prepare(`insert or replace into skill_vector (skill_id, workspace, app, model, text_hash, vec) values (?,?,?,?,?,?)`).bind(
          b.skill,
          b.ws,
          b.app,
          MODEL,
          b.hash,
          vecs[j].buffer,
        ),
      ),
    );
  }
  // Vectors whose search row is gone (a removed document, a deleted skill).
  const stale = have.filter((h) => !live.has(`${h.skill_id}|${h.workspace}`));
  for (const s of stale) await env.DB.prepare(`delete from skill_vector where skill_id = ? and workspace = ?`).bind(s.skill_id, s.workspace).run();
  cache.clear();
  return { embedded: todo.length, removed: stale.length };
}

// Per isolate: the vectors of what an organization sees, for a minute.
const cache = new Map<string, { at: number; ids: string[]; apps: string[]; mat: Float32Array[] }>();

async function matrix(env: VecEnv, apps: string[], ws: string | null) {
  const key = `${ws ?? ""}|${apps.sort().join(",")}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < 60_000) return hit;
  const { results } = await env.DB.prepare(
    `select skill_id, app, vec from skill_vector where app in (${apps.map(() => "?").join(",")}) and (workspace = '' or workspace = ?)`,
  )
    .bind(...apps, ws ?? "")
    .all<{ skill_id: string; app: string; vec: ArrayBuffer | number[] }>();
  // D1 hands BLOBs back as an array of bytes: rebuild the floats from them.
  const floats = (b: ArrayBuffer | number[]) => new Float32Array(b instanceof ArrayBuffer ? b : new Uint8Array(b).buffer);
  const m = { at: Date.now(), ids: results.map((r) => r.skill_id), apps: results.map((r) => r.app), mat: results.map((r) => floats(r.vec)) };
  cache.set(key, m);
  return m;
}

/** Skills by meaning: the best cosine per skill (its shared row or the organization's), highest first. */
export async function semantic(env: VecEnv, apps: string[], ws: string | null, query: string, k = 20) {
  if (!env.AI || !apps.length) return Object.assign([] as { id: string; app: string; cos: number }[], { cosOf: new Map<string, number>() });
  const [m, [q]] = await Promise.all([matrix(env, apps, ws), embed(env, { queries: [query] })]);
  const best = new Map<string, { id: string; app: string; cos: number }>();
  for (let i = 0; i < m.ids.length; i++) {
    const v = m.mat[i];
    let dot = 0;
    for (let d = 0; d < v.length; d++) dot += v[d] * q[d];
    const cur = best.get(m.ids[i]);
    if (!cur || dot > cur.cos) best.set(m.ids[i], { id: m.ids[i], app: m.apps[i], cos: dot });
  }
  const all = [...best.values()].sort((a, b) => b.cos - a.cos);
  return Object.assign(all.slice(0, k), { cosOf: new Map(all.map((x) => [x.id, x.cos])) });
}
