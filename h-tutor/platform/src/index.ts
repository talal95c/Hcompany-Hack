// Rio platform (Cloudflare Worker).
//   /api/auth/*  better-auth (accounts, organizations, members, invitations)
//   /api/app/*   the console's API, for a signed-in member of the active organization
//   /v1/*        the Rio app's API, with `Authorization: Bearer <api token>`
//   everything else: the console (React, static assets)
//
// Knowledge: the global base lives in the rio-knowledge Worker (ReStep's graphs in D1,
// ReStep's core ported), reached through the KNOWLEDGE service binding; the
// organization's own tutorials live here, in D1.

import { Hono, type Context } from "hono";
import { createAuth, googleEnabled } from "./auth.ts";
import { type TutorialRow, advance, advancePending, kindOf, youtubeThumbnail } from "./ingest.ts";
import { type RioTutorial, type SearchHit, search, summaryOf, tutorialsAsKb } from "./kb.ts";

export interface Env {
  DB: D1Database;
  KNOWLEDGE: Fetcher;
  ASSETS: Fetcher;
  BETTER_AUTH_SECRET?: string;
  BETTER_AUTH_URL?: string;
  GOOGLE_CLIENT_ID?: string;
  GOOGLE_CLIENT_SECRET?: string;
  HAI_API_KEY?: string;
  GLADIA_API_KEY?: string;
  LINKUP_API_KEY?: string;
  HOLO_MODEL?: string;
  HOLO_DESIGN_MODEL?: string;
}

type Vars = { org: string; user: string; role: string };
type C = Context<{ Bindings: Env; Variables: Vars }>;

const app = new Hono<{ Bindings: Env; Variables: Vars }>();

async function sha256(s: string): Promise<string> {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// ------------------------------------------------------------------ knowledge

/**
 * The knowledge Worker (service binding), always scoped to the caller's organization: JSON, or null when it is
 * unreachable (Rio keeps working on the team's tutorials).
 */
async function kn<T>(c: C, path: string, params: Record<string, string | null | undefined> = {}, init?: RequestInit): Promise<T | null> {
  const q = new URLSearchParams(Object.entries({ ...params, workspace: c.get("org") }).filter((e): e is [string, string] => !!e[1]));
  try {
    const r = await c.env.KNOWLEDGE.fetch(`https://knowledge${path}?${q}`, init);
    // A failed read is treated as unreachable, so pages show an empty state instead of an error body.
    // Writes keep the body: its error message is shown to the user.
    if (!r.ok && !init) {
      console.error(`knowledge ${path}: ${r.status} ${await r.text()}`);
      return null;
    }
    return (await r.json()) as T;
  } catch {
    return null;
  }
}

type GlobalHit = Omit<SearchHit, "version"> & { version: SearchHit["version"] };

/**
 * Everything Rio knows for a question: the team's own tutorials first (their way), then the global base.
 * A weak match (often another language) is retried with English keywords from Holo.
 */
async function searchAll(c: C, q: string, o: { app?: string | null; version?: string | null; limit: number }) {
  const own = tutorialsAsKb(await readyTutorials(c.env, c.get("org")));
  let semanticOk = false;
  let topCos = 0;
  let unknownApp: string[] | null = null; // the `app` asked for is none of the apps this organization sees: their names

  const run = async (alt: string) => {
    // With English keywords for a foreign question, the keywords lead (the question's own words would mismatch).
    const foreign = !!alt && looksForeign(q);
    const [team, global] = await Promise.all([
      Promise.resolve(search(own, foreign ? [alt] : alt ? [q, alt] : [q], { app: o.app, version: o.version, limit: 3 }).filter((r) => r.score >= 2)),
      kn<{ results: GlobalHit[]; semantic?: boolean; top_cos?: number | null; unknown_app?: string; apps?: string[] }>(c, "/search", { q: foreign ? alt : q, alt: foreign ? "" : alt, app: o.app, version: o.version, limit: String(o.limit) }),
    ]);
    if (global?.semantic) semanticOk = true;
    if (global?.unknown_app) unknownApp = global.apps ?? [];
    if (global?.top_cos != null) topCos = Math.max(topCos, global.top_cos);
    return [...team.slice(0, 2), ...(global?.results ?? [])].slice(0, o.limit);
  };
  // The knowledge Worker understands any language (Qwen3 embeddings). Without them, ReStep's rule applies: a question
  // clearly not in English is searched with English keywords (French "commande" would find "Command").
  // A foreign question whose meaning match is not clear (idioms: "arrondir les bords" is Bevel) also gets Holo's
  // English keywords, started in parallel so a clear answer does not wait for them.
  const kw = looksForeign(q) ? englishKeywords(c.env, q) : null;
  let results = await run("");
  if (kw && (!semanticOk || topCos < 0.5)) {
    const keywords = await kw;
    if (keywords) {
      const more = await run(keywords);
      // keep both: the keywords' answers first, then what the question itself found
      const seen = new Set(more.map((r) => r.id));
      return { results: [...more, ...results.filter((r) => !seen.has(r.id))].slice(0, o.limit), keywords, unknownApp };
    }
  }
  let keywords = "";
  if (results.length < 2) {
    keywords = await englishKeywords(c.env, q);
    if (keywords) {
      const more = await run(keywords);
      if (more.length > results.length) results = more;
    }
  }
  return { results, keywords, unknownApp };
}

type GlobalTutorial = { id: string; title: string; app: string; bundle_id: string | null; skills: number; recorded_on: string | null; source_url: string | null; kind: string | null; author: string | null };

const globalSummary = (t: GlobalTutorial) => ({
  id: t.id,
  title: t.title,
  app: t.app,
  bundle_id: t.bundle_id,
  goal: t.title,
  milestones: t.skills,
  source: "company",
  source_url: t.source_url,
  author_kind: t.kind,
  recorded_on: t.recorded_on,
});

async function readyTutorials(env: Env, org: string): Promise<RioTutorial[]> {
  const { results } = await env.DB.prepare(
    `select "data" from "tutorial" where "organizationId" = ? and "status" = 'ready' and "visibility" != 'draft' order by "createdAt" desc`,
  )
    .bind(org)
    .all<{ data: string }>();
  return results.map((r) => JSON.parse(r.data) as RioTutorial);
}

function logUsage(c: C, e: { kind: string; tutorialId?: string | null; tutorialTitle?: string | null; milestone?: string | null; query?: string | null; app?: string | null; results?: number | null }) {
  c.executionCtx.waitUntil(
    c.env.DB.prepare(
      `insert into "usage_event" ("organizationId","kind","tutorialId","tutorialTitle","milestone","query","app","results","createdAt") values (?,?,?,?,?,?,?,?,?)`,
    )
      .bind(c.get("org"), e.kind, e.tutorialId ?? null, e.tutorialTitle ?? null, e.milestone ?? null, e.query?.slice(0, 300) ?? null, e.app ?? null, e.results ?? null, Date.now())
      .run()
      .catch(() => {}),
  );
}

// ------------------------------------------------------------------ auth

app.get("/v1/health", (c) => c.json({ ok: true }));
// Which sign-in methods the console shows (public, no secrets).
app.get("/api/providers", (c) => c.json({ google: googleEnabled(c.env) }));
app.on(["GET", "POST"], "/api/auth/*", (c) => createAuth(c.env).handler(c.req.raw));

// ------------------------------------------------------------------ Rio app API (/v1, bearer token)

app.use("/v1/*", async (c, next) => {
  const token = c.req.header("authorization")?.match(/^Bearer\s+(\S+)$/i)?.[1];
  if (!token) return c.json({ error: "missing token" }, 401);
  const row = await c.env.DB.prepare(`select "id", "organizationId", "lastUsedAt" from "api_token" where "hash" = ? and "revokedAt" is null`)
    .bind(await sha256(token))
    .first<{ id: string; organizationId: string; lastUsedAt: number | null }>();
  if (!row) return c.json({ error: "invalid or revoked token" }, 401);
  if (!row.lastUsedAt || Date.now() - row.lastUsedAt > 60_000) {
    c.executionCtx.waitUntil(c.env.DB.prepare(`update "api_token" set "lastUsedAt" = ? where "id" = ?`).bind(Date.now(), row.id).run());
  }
  c.set("org", row.organizationId);
  await next();
});

/** ReStep's hint words (kg/api.py FR_HINTS) and non-ASCII text: a question asked in another language. */
const FOREIGN = new Set(["comment", "pour", "les", "des", "une", "mon", "mes", "dans", "faire", "veux", "est", "que", "sur", "avec", "supprimer",
  "ajouter", "couper", "mettre", "trouve", "trouver", "quoi", "pourquoi", "cómo", "como", "wie", "créer", "creer", "marquer", "commande", "commandes"]);
const looksForeign = (q: string) => /[^\x00-\x7F]/.test(q) || q.toLowerCase().split(/[^a-zà-ÿ]+/).some((w) => FOREIGN.has(w));

const keywordCache = new Map<string, string>();

/** A question in any language as English keywords in the software's vocabulary (one Holo call, cached). */
async function englishKeywords(env: Env, q: string): Promise<string> {
  if (!env.HAI_API_KEY) return "";
  const k = q.trim().toLowerCase();
  if (keywordCache.has(k)) return keywordCache.get(k)!;
  try {
    const r = await fetch("https://api.hcompany.ai/v1/chat/completions", {
      method: "POST",
      headers: { authorization: `Bearer ${env.HAI_API_KEY}`, "content-type": "application/json" },
      body: JSON.stringify({
        model: env.HOLO_MODEL || "holo4-35b-a3b",
        messages: [
          {
            role: "user",
            content:
              "Rewrite this software how-to question as 3 to 8 English keywords, using the software's usual UI " +
              `terms (e.g. vertices, merge, collection, render). Answer the keywords only.\n\n${q}`,
          },
        ],
        max_tokens: 40,
        temperature: 0,
        reasoning_effort: "none",
      }),
      signal: AbortSignal.timeout(8000),
    });
    if (!r.ok) return "";
    const v = (await r.json()) as { choices?: { message?: { content?: string } }[] };
    const out = (v.choices?.[0]?.message?.content ?? "").trim();
    if (keywordCache.size > 500) keywordCache.clear();
    keywordCache.set(k, out);
    return out;
  } catch {
    return "";
  }
}

app.get("/v1/search", async (c) => {
  const q = (c.req.query("q") ?? "").trim();
  if (!q) return c.json({ error: "missing q" }, 400);
  const app = c.req.query("app");
  const { results, keywords, unknownApp } = await searchAll(c, q, { app, version: c.req.query("version"), limit: Math.min(Number(c.req.query("limit")) || 5, 10) });
  logUsage(c, { kind: "search", query: q, app, results: results.length });
  if (unknownApp && !results.length) return c.json({ error: `unknown app: ${app}`, apps: unknownApp }, 404);
  return c.json({ query: q, keywords: keywords || null, results });
});

/** The apps this organization can search (`/v1/search?app=<name or id>`): the shared ones and its own tools. */
app.get("/v1/apps", async (c) => {
  const r = await kn<{ apps: KnowledgeApp[] }>(c, "/apps");
  if (!r) return c.json({ error: "The knowledge base is unreachable" }, 502);
  return c.json({
    apps: r.apps.map((a) => ({ id: a.id, name: a.name, shared: !a.internal, current_version: a.current_version, versions: a.versions.map((v) => v.id), skills: a.skills })),
  });
});

app.get("/v1/tutorials", async (c) => {
  const [own, global] = await Promise.all([readyTutorials(c.env, c.get("org")), kn<{ tutorials: GlobalTutorial[] }>(c, "/tutorials", { app: c.req.query("app") })]);
  return c.json({ tutorials: [...own.map(summaryOf), ...(global?.tutorials ?? []).map(globalSummary)] });
});

app.get("/v1/tutorials/:id", async (c) => {
  const id = c.req.param("id");
  let t: unknown = null;
  if (id.startsWith("rio:org:")) {
    const row = await c.env.DB.prepare(`select "data" from "tutorial" where "id" = ? and "organizationId" = ? and "status" = 'ready' and "visibility" != 'draft'`)
      .bind(id.slice("rio:org:".length), c.get("org"))
      .first<{ data: string }>();
    t = row && JSON.parse(row.data);
  } else {
    const r = await kn<{ error?: string }>(c, `/tutorials/${encodeURIComponent(id)}`, { format: "rio", version: c.req.query("version") });
    t = r && !r.error ? r : null;
  }
  return t ? c.json(t) : c.json({ error: "unknown tutorial" }, 404);
});

const EVENTS = new Set(["tutorial_started", "milestone_done", "milestone_skipped", "tutorial_finished", "tutorial_abandoned"]);

/** What happens in Rio, for the usage page. */
app.post("/v1/events", async (c) => {
  const e = await c.req.json<{ kind?: string; tutorial_id?: string; tutorial_title?: string; milestone?: string; goal?: string; app?: string }>();
  if (!e.kind || !EVENTS.has(e.kind)) return c.json({ error: "unknown event" }, 400);
  logUsage(c, { kind: e.kind, tutorialId: e.tutorial_id, tutorialTitle: e.tutorial_title, milestone: e.milestone, query: e.goal, app: e.app });
  return c.json({ ok: true });
});

// ------------------------------------------------------------------ console API (/api/app, session)

app.use("/api/app/*", async (c, next) => {
  const session = await createAuth(c.env).api.getSession({ headers: c.req.raw.headers });
  if (!session) return c.json({ error: "not signed in" }, 401);
  const org = (session.session as { activeOrganizationId?: string | null }).activeOrganizationId;
  if (!org) return c.json({ error: "no active organization" }, 409);
  const m = await c.env.DB.prepare(`select "role" from "member" where "organizationId" = ? and "userId" = ?`)
    .bind(org, session.user.id)
    .first<{ role: string }>();
  if (!m) return c.json({ error: "not a member of this organization" }, 403);
  c.set("org", org);
  c.set("user", session.user.id);
  c.set("role", m.role);
  await next();
});

const canManage = (c: C) => /\b(owner|admin)\b/.test(c.get("role"));
const forbidden = (c: C) => c.json({ error: "only owners and admins can do this" }, 403);

app.get("/api/app/me", (c) => c.json({ role: c.get("role"), canManage: canManage(c) }));

// Tokens
app.get("/api/app/tokens", async (c) => {
  const { results } = await c.env.DB.prepare(
    `select t."id", t."name", t."prefix", t."createdAt", t."lastUsedAt", u."name" as "createdBy"
     from "api_token" t left join "user" u on u."id" = t."createdBy"
     where t."organizationId" = ? and t."revokedAt" is null order by t."createdAt" desc`,
  )
    .bind(c.get("org"))
    .all();
  return c.json({ tokens: results });
});

app.post("/api/app/tokens", async (c) => {
  if (!canManage(c)) return forbidden(c);
  const { name } = await c.req.json<{ name?: string }>();
  const bytes = crypto.getRandomValues(new Uint8Array(24));
  const token = `rio_${btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")}`;
  const id = crypto.randomUUID();
  await c.env.DB.prepare(`insert into "api_token" ("id","organizationId","name","hash","prefix","createdBy","createdAt") values (?,?,?,?,?,?,?)`)
    .bind(id, c.get("org"), (name || "Rio").slice(0, 60), await sha256(token), token.slice(0, 10), c.get("user"), Date.now())
    .run();
  return c.json({ id, token });
});

app.delete("/api/app/tokens/:id", async (c) => {
  if (!canManage(c)) return forbidden(c);
  await c.env.DB.prepare(`update "api_token" set "revokedAt" = ? where "id" = ? and "organizationId" = ?`)
    .bind(Date.now(), c.req.param("id"), c.get("org"))
    .run();
  return c.json({ ok: true });
});

// Tutorials (collaborative: any member creates; the author or an admin edits and publishes)
type RichRow = TutorialRow & { authorName: string | null; orgName: string | null; likes: number; liked: number; learners: number; remixes: number };

const RICH = `select t.*, u."name" as "authorName", o."name" as "orgName",
  (select count(*) from "tutorial_like" l where l."tutorialId" = t."id") as "likes",
  (select count(*) from "tutorial_like" l where l."tutorialId" = t."id" and l."userId" = ?) as "liked",
  (select count(*) from "usage_event" e where e."tutorialId" = 'rio:org:' || t."id" and e."kind" = 'tutorial_started') as "learners",
  (select count(*) from "tutorial" r where r."remixOf" = t."id") as "remixes"
  from "tutorial" t left join "user" u on u."id" = t."createdBy" left join "organization" o on o."id" = t."organizationId"`;

const publicRow = (r: RichRow, c?: C) => ({
  id: r.id,
  kind: r.kind,
  input: r.input,
  title: r.title,
  app: r.app,
  status: r.status,
  error: r.error,
  visibility: r.visibility,
  publishedAt: r.publishedAt,
  remixOf: r.remixOf,
  // A video's thumbnail, else the og:image of the first source page that has one.
  thumbnail:
    r.kind === "youtube"
      ? (youtubeThumbnail(r.input) ?? null)
      : ((r.sources ? (JSON.parse(r.sources) as { image?: string }[]) : []).find((s) => s.image)?.image ?? null),
  // While H's web agent reads the docs: its live view.
  agentViewUrl: r.status === "browsing" && r.job ? ((JSON.parse(r.job) as { agentViewUrl?: string }).agentViewUrl ?? null) : null,
  sources: r.sources ? JSON.parse(r.sources) : [],
  tutorial: r.data ? JSON.parse(r.data) : null,
  author: { id: r.createdBy, name: r.authorName },
  org: r.orgName,
  likes: r.likes,
  liked: !!r.liked,
  learners: r.learners,
  remixes: r.remixes,
  canEdit: c ? c.get("org") === r.organizationId && (canManage(c) || r.createdBy === c.get("user")) : false,
  createdAt: r.createdAt,
  updatedAt: r.updatedAt,
});

async function rich(c: C, where: string, ...binds: unknown[]): Promise<RichRow[]> {
  const { results } = await c.env.DB.prepare(`${RICH} where ${where}`).bind(c.get("user"), ...binds).all<RichRow>();
  return results;
}

async function ownRow(c: C, id: string): Promise<RichRow | null> {
  return (await rich(c, `t."id" = ? and t."organizationId" = ?`, id, c.get("org")))[0] ?? null;
}

const canEdit = (c: C, r: TutorialRow) => canManage(c) || r.createdBy === c.get("user");

app.get("/api/app/tutorials", async (c) => {
  const rows = await rich(c, `t."organizationId" = ? order by t."createdAt" desc`, c.get("org"));
  // The console polls this while jobs run: move them along.
  if (rows.some((r) => !["ready", "failed"].includes(r.status))) c.executionCtx.waitUntil(advancePending(c.env, c.get("org")));
  return c.json({ tutorials: rows.map((r) => publicRow(r, c)) });
});

app.get("/api/app/tutorials/:id", async (c) => {
  const id = c.req.param("id");
  // Your team's tutorial, or one published to the community.
  const r = (await rich(c, `t."id" = ? and (t."organizationId" = ? or t."visibility" = 'community')`, id, c.get("org")))[0];
  if (!r) return c.json({ error: "not found" }, 404);
  if (!["ready", "failed"].includes(r.status)) c.executionCtx.waitUntil(advancePending(c.env, c.get("org")));
  let remixOf: { id: string; title: string | null; org: string | null } | null = null;
  if (r.remixOf) {
    const o = (await rich(c, `t."id" = ?`, r.remixOf))[0];
    if (o) remixOf = { id: o.id, title: o.title, org: o.orgName };
  }
  return c.json({ ...publicRow(r, c), remixOfTutorial: remixOf });
});

app.post("/api/app/tutorials", async (c) => {
  const { input } = await c.req.json<{ input?: string }>();
  const text = (input ?? "").trim();
  if (text.length < 4) return c.json({ error: "Paste a YouTube link, a documentation link, or describe a goal" }, 400);
  const id = crypto.randomUUID();
  const now = Date.now();
  const kind = kindOf(text);
  await c.env.DB.prepare(
    `insert into "tutorial" ("id","organizationId","kind","input","title","status","createdBy","createdAt","updatedAt") values (?,?,?,?,?,?,?,?,?)`,
  )
    .bind(id, c.get("org"), kind, text.slice(0, 2000), kind === "goal" ? text.slice(0, 120) : null, "queued", c.get("user"), now, now)
    .run();
  const row = (await ownRow(c, id))!;
  c.executionCtx.waitUntil(advance(c.env, row));
  return c.json(publicRow(row, c));
});

/** Edit (title, goal, milestones) and publish (visibility). */
app.patch("/api/app/tutorials/:id", async (c) => {
  const r = await ownRow(c, c.req.param("id"));
  if (!r) return c.json({ error: "not found" }, 404);
  if (!canEdit(c, r)) return c.json({ error: "only the author or an admin can change this tutorial" }, 403);
  const body = await c.req.json<{ title?: string; goal?: string; milestones?: RioTutorial["milestones"]; visibility?: string }>();
  const now = Date.now();
  if (body.visibility) {
    if (!["draft", "team", "community"].includes(body.visibility)) return c.json({ error: "unknown visibility" }, 400);
    if (body.visibility !== "draft" && r.status !== "ready") return c.json({ error: "Only a ready tutorial can be published" }, 400);
    await c.env.DB.prepare(`update "tutorial" set "visibility" = ?, "publishedAt" = ?, "updatedAt" = ? where "id" = ?`)
      .bind(body.visibility, body.visibility === "draft" ? null : (r.publishedAt ?? now), now, r.id)
      .run();
  }
  if (r.data && (body.title || body.goal || body.milestones)) {
    const t = JSON.parse(r.data) as RioTutorial;
    if (body.title?.trim()) t.title = body.title.trim().slice(0, 120);
    if (body.goal?.trim()) t.goal = body.goal.trim().slice(0, 500);
    if (body.milestones?.length) {
      t.milestones = body.milestones.slice(0, 20).map((m, i) => ({
        id: `m${i + 1}`,
        goal: String(m.goal ?? "").slice(0, 200),
        done_when: String(m.done_when ?? "").slice(0, 300),
        hints: (m.hints ?? []).map((h) => String(h).slice(0, 200)).filter(Boolean).slice(0, 6),
        teach: m.teach ? String(m.teach).slice(0, 300) : undefined,
        video_at: typeof m.video_at === "number" ? m.video_at : undefined,
      })).filter((m) => m.goal && m.done_when);
      if (!t.milestones.length) return c.json({ error: "A tutorial needs at least one milestone with a goal and a check" }, 400);
    }
    await c.env.DB.prepare(`update "tutorial" set "data" = ?, "title" = ?, "updatedAt" = ? where "id" = ?`).bind(JSON.stringify(t), t.title, now, r.id).run();
  }
  return c.json(publicRow((await ownRow(c, r.id))!, c));
});

app.post("/api/app/tutorials/:id/like", async (c) => {
  const id = c.req.param("id");
  const r = (await rich(c, `t."id" = ? and (t."organizationId" = ? or t."visibility" = 'community')`, id, c.get("org")))[0];
  if (!r) return c.json({ error: "not found" }, 404);
  if (r.liked) await c.env.DB.prepare(`delete from "tutorial_like" where "tutorialId" = ? and "userId" = ?`).bind(id, c.get("user")).run();
  else await c.env.DB.prepare(`insert into "tutorial_like" ("tutorialId","userId","createdAt") values (?,?,?)`).bind(id, c.get("user"), Date.now()).run();
  return c.json({ liked: !r.liked, likes: r.likes + (r.liked ? -1 : 1) });
});

/** Copies a community tutorial into your team, as a draft you can adapt. */
app.post("/api/app/tutorials/:id/remix", async (c) => {
  const src = (await rich(c, `t."id" = ? and t."status" = 'ready' and (t."visibility" = 'community' or t."organizationId" = ?)`, c.req.param("id"), c.get("org")))[0];
  if (!src?.data) return c.json({ error: "not found" }, 404);
  const id = crypto.randomUUID();
  const now = Date.now();
  const t = { ...(JSON.parse(src.data) as RioTutorial), id: `rio:org:${id}` };
  await c.env.DB.prepare(
    `insert into "tutorial" ("id","organizationId","kind","input","title","app","status","data","sources","createdBy","createdAt","updatedAt","visibility","remixOf")
     values (?,?,?,?,?,?,'ready',?,?,?,?,?,'draft',?)`,
  )
    .bind(id, c.get("org"), src.kind, src.input, src.title, src.app, JSON.stringify(t), src.sources, c.get("user"), now, now, src.id)
    .run();
  return c.json({ id });
});

app.post("/api/app/tutorials/:id/retry", async (c) => {
  const r = await ownRow(c, c.req.param("id"));
  if (!r || !canEdit(c, r)) return c.json({ error: "not found" }, 404);
  await c.env.DB.prepare(`update "tutorial" set "status" = 'queued', "error" = null, "job" = null, "leaseUntil" = 0, "updatedAt" = ? where "id" = ? and "status" = 'failed'`)
    .bind(Date.now(), r.id)
    .run();
  return c.json({ ok: true });
});

app.delete("/api/app/tutorials/:id", async (c) => {
  const r = await ownRow(c, c.req.param("id"));
  if (!r || !canEdit(c, r)) return c.json({ error: "only the author or an admin can delete this tutorial" }, 403);
  await c.env.DB.prepare(`delete from "tutorial" where "id" = ?`).bind(r.id).run();
  return c.json({ ok: true });
});

// Community: tutorials every organization published to everyone
app.get("/api/app/community", async (c) => {
  const rows = await rich(c, `t."visibility" = 'community' and t."status" = 'ready' order by t."publishedAt" desc limit 200`);
  return c.json({ tutorials: rows.map((r) => publicRow(r, c)) });
});

// Knowledge: the global base (ReStep, versioned, in the knowledge Worker) and what the team created
type KnowledgeApp = { id: string; name: string; internal?: boolean; mine?: boolean; bundle_id: string | null; current_version: string; versions: { id: string; label: string | null }[]; skills: number; sources: number; proven: number; atoms: number; tutorials: number };

app.get("/api/app/knowledge", async (c) => {
  const [overview, tuts, own] = await Promise.all([
    kn<{ apps: KnowledgeApp[] }>(c, "/apps"),
    kn<{ tutorials: GlobalTutorial[] }>(c, "/tutorials"),
    teamTutorials(c),
  ]);
  return c.json({
    available: !!overview,
    global: (overview?.apps ?? []).map((a) => ({
      internal: !!a.internal,
      mine: !!a.mine,
      app: { id: a.id, name: a.name, versions: a.versions, current_version: a.current_version },
      skills: a.skills,
      sources: a.sources,
      proven: a.proven,
      atoms: a.atoms,
      tutorials: (tuts?.tutorials ?? []).filter((t) => t.app === a.name).map(globalSummary),
    })),
    created: tutorialsAsKb(own).map((d) => ({ app: d.app.name, skills: Object.keys(d.skills).length })),
  });
});

async function teamTutorials(c: C): Promise<RioTutorial[]> {
  return readyTutorials(c.env, c.get("org"));
}

/** Skills of one global app (all, or matching `q`), each re-targeted to every version. */
app.get("/api/app/knowledge/skills", async (c) => {
  const r = await kn(c, "/skills", { app: c.req.query("app"), q: c.req.query("q") });
  return c.json(r ?? { app: null, skills: [] });
});

/** The organization's own documents (internal tools, private guides), ingested into the knowledge base. */
app.get("/api/app/knowledge/docs", async (c) => c.json((await kn(c, "/sources")) ?? { sources: [] }));

app.post("/api/app/knowledge/docs", async (c) => {
  const b = await c.req.json<{ app?: string; version?: string; title?: string; text?: string; url?: string }>();
  if (!b.app?.trim() || !b.text?.trim()) return c.json({ error: "Name the tool and add the document's text" }, 400);
  const r = await kn<{ error?: string }>(c, "/ingest", {}, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ workspace: c.get("org"), app: b.app, version: b.version, title: b.title, text: b.text, url: b.url }),
  });
  if (!r) return c.json({ error: "The knowledge base is unreachable" }, 502);
  return r.error ? c.json(r, 422) : c.json(r);
});

app.delete("/api/app/knowledge/docs/:id", async (c) => {
  if (!canManage(c)) return forbidden(c);
  const r = await kn<{ ok?: boolean; error?: string }>(c, `/sources/${encodeURIComponent(c.req.param("id"))}`, {}, { method: "DELETE" });
  return r?.ok ? c.json({ ok: true }) : c.json({ error: r?.error ?? "Could not remove it" }, 404);
});

/** Shares one of the team's own tools with every organization, like Blender, or makes it private again (owners and admins). */
app.post("/api/app/knowledge/apps/:id/share", async (c) => {
  if (!canManage(c)) return forbidden(c);
  const { shared } = await c.req.json<{ shared?: boolean }>().catch(() => ({ shared: undefined }));
  const r = await kn<{ id?: string; shared?: boolean; error?: string }>(c, `/apps/${encodeURIComponent(c.req.param("id"))}/share`, { private: shared === false ? "1" : null }, { method: "POST" });
  if (!r) return c.json({ error: "The knowledge base is unreachable" }, 502);
  return r.error ? c.json({ error: r.error }, 409) : c.json(r);
});

/** ReStep's graph view for one app: sources -> skills -> UI atoms. */
app.get("/api/app/knowledge/graph", async (c) => {
  const r = await kn(c, "/graph", { app: c.req.query("app") });
  return c.json(r ?? { app: null, sources: [], skills: [], atoms: [] });
});

/** Where a UI element is now, under any name it has had ("Remove Doubles" -> Merge by Distance). */
app.get("/api/app/knowledge/locate", async (c) => {
  const r = await kn(c, "/locate", { app: c.req.query("app"), q: c.req.query("q"), version: c.req.query("version") });
  return c.json(r ?? { results: [] });
});

/** One question across everything Rio knows for this team (what Holo gets when it searches). */
app.get("/api/app/knowledge/search", async (c) => {
  const q = (c.req.query("q") ?? "").trim();
  if (!q) return c.json({ results: [] });
  const { results } = await searchAll(c, q, { app: c.req.query("app"), limit: 8 });
  return c.json({ results });
});

// Usage
app.get("/api/app/usage", async (c) => {
  const days = Math.min(Math.max(Number(c.req.query("days")) || 30, 1), 365);
  const since = Date.now() - days * 86_400_000;
  const org = c.get("org");
  const q = (sql: string) => c.env.DB.prepare(sql).bind(org, since);
  const [totals, daily, queries, gaps, tutorials, skipped] = await c.env.DB.batch([
    q(`select "kind", count(*) as "n", sum(case when "kind" = 'search' and "results" = 0 then 1 else 0 end) as "empty"
       from "usage_event" where "organizationId" = ? and "createdAt" >= ? group by "kind"`),
    q(`select ("createdAt" / 86400000) as "day", "kind", count(*) as "n" from "usage_event"
       where "organizationId" = ? and "createdAt" >= ? and "kind" in ('search', 'tutorial_started') group by "day", "kind" order by "day"`),
    q(`select "query", count(*) as "n" from "usage_event" where "organizationId" = ? and "createdAt" >= ? and "kind" = 'search'
       group by lower("query") order by "n" desc limit 8`),
    q(`select "query", max("app") as "app", count(*) as "n", max("createdAt") as "last" from "usage_event" where "organizationId" = ? and "createdAt" >= ?
       and "kind" = 'search' and "results" = 0 group by lower("query") order by "n" desc, "last" desc limit 8`),
    q(`select "tutorialId" as "id", max("tutorialTitle") as "title",
         sum(case when "kind" = 'tutorial_started' then 1 else 0 end) as "started",
         sum(case when "kind" = 'tutorial_finished' then 1 else 0 end) as "finished",
         sum(case when "kind" = 'milestone_skipped' then 1 else 0 end) as "skipped"
       from "usage_event" where "organizationId" = ? and "createdAt" >= ? and "tutorialId" is not null
       group by "tutorialId" order by "started" desc limit 10`),
    q(`select max("tutorialTitle") as "title", "milestone", count(*) as "n" from "usage_event"
       where "organizationId" = ? and "createdAt" >= ? and "kind" = 'milestone_skipped'
       group by "tutorialId", "milestone" order by "n" desc limit 6`),
  ]);
  return c.json({
    days,
    totals: totals.results,
    daily: daily.results,
    queries: queries.results,
    gaps: gaps.results,
    tutorials: tutorials.results,
    skipped: skipped.results,
  });
});

// ------------------------------------------------------------------ console (static)

// The landing (../landing, built into web/dist/landing) is the domain's front page; the console lives on its own paths.
app.get("/", (c) => c.env.ASSETS.fetch(new URL("/landing/index.html", c.req.url)));

app.notFound((c) => (c.req.path.startsWith("/api/") || c.req.path.startsWith("/v1/") ? c.json({ error: "not found" }, 404) : c.env.ASSETS.fetch(c.req.raw)));

export default {
  fetch: app.fetch,
  // Every minute: move the tutorial jobs along, even when nobody has the console open.
  async scheduled(_e, env, ctx) {
    ctx.waitUntil(advancePending(env));
  },
} satisfies ExportedHandler<Env>;
