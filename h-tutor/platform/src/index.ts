// Rio platform (Cloudflare Worker).
//   /api/auth/*  better-auth (accounts, organizations, members, invitations)
//   /api/app/*   the console's API, for a signed-in member of the active organization
//   /v1/*        the Rio app's API, with `Authorization: Bearer <api token>`
//   everything else: the console (React, static assets)
//
// Knowledge: ReStep exports in KV (`kb:shared:<app>` for every organization,
// `kb:<orgId>:<app>` for one), plus the organization's own tutorials in D1.

import { Hono, type Context } from "hono";
import { createAuth } from "./auth.ts";
import { type TutorialRow, advance, advancePending, kindOf } from "./ingest.ts";
import { type AppData, type RioTutorial, listTutorials, rioTutorial, search, summaryOf, tutorialsAsKb } from "./kb.ts";

export interface Env {
  DB: D1Database;
  KB: KVNamespace;
  ASSETS: Fetcher;
  BETTER_AUTH_SECRET?: string;
  BETTER_AUTH_URL?: string;
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

const kvCache = new Map<string, { at: number; data: AppData[] }>();

/** ReStep knowledge for an organization: the shared bases and its own (KV, cached a minute per isolate). */
async function kvKnowledge(env: Env, org: string): Promise<AppData[]> {
  const hit = kvCache.get(org);
  if (hit && Date.now() - hit.at < 60_000) return hit.data;
  const load = async (scope: string) => {
    const apps = (await env.KB.get<string[]>(`kb:${scope}:apps`, "json")) ?? [];
    return Promise.all(apps.map((a) => env.KB.get<AppData>(`kb:${scope}:${a}`, "json")));
  };
  const data = [...(await load("shared")), ...(await load(org))].filter((d): d is AppData => !!d);
  kvCache.set(org, { at: Date.now(), data });
  return data;
}

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

/** Every base the organization searches: ReStep's (KV) and its own tutorials (D1). */
async function knowledge(c: C) {
  const [kv, own] = await Promise.all([kvKnowledge(c.env, c.get("org")), readyTutorials(c.env, c.get("org"))]);
  return { kv, own, all: [...kv, ...tutorialsAsKb(own)] };
}

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
  const { all } = await knowledge(c);
  const opts = { app: c.req.query("app"), version: c.req.query("version"), limit: Math.min(Number(c.req.query("limit")) || 5, 10) };
  let results = search(all, [q], opts);
  let keywords = "";
  // Weak or no match (often a question in another language): retry with English keywords.
  if (!results.length || results[0].score < 2) {
    keywords = await englishKeywords(c.env, q);
    if (keywords) results = search(all, [q, keywords], opts);
  }
  logUsage(c, { kind: "search", query: q, app: opts.app, results: results.filter((r) => r.score >= 2).length });
  return c.json({ query: q, keywords: keywords || null, results });
});

app.get("/v1/tutorials", async (c) => {
  const { kv, own } = await knowledge(c);
  const list = [...own.map(summaryOf), ...listTutorials(kv, c.req.query("app"))];
  return c.json({ tutorials: list });
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
    t = rioTutorial(await kvKnowledge(c.env, c.get("org")), id, c.req.query("version"));
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

// Knowledge: the global base (ReStep, versioned) and what the team created
app.get("/api/app/knowledge", async (c) => {
  const kv = await kvKnowledge(c.env, c.get("org"));
  const own = await teamTutorials(c);
  return c.json({
    global: kv.map((d) => ({
      app: d.app,
      skills: Object.keys(d.skills).length,
      sources: new Set(Object.values(d.skills).flatMap((s) => s.sources.map((x) => x.id))).size,
      proven: Object.values(d.skills).filter((s) => Object.values(s.proofs).includes("PASS")).length,
      tutorials: listTutorials([d]),
    })),
    created: tutorialsAsKb(own).map((d) => ({ app: d.app.name, skills: Object.keys(d.skills).length })),
  });
});

async function teamTutorials(c: C): Promise<RioTutorial[]> {
  const { results } = await c.env.DB.prepare(
    `select "data" from "tutorial" where "organizationId" = ? and "status" = 'ready' and "visibility" != 'draft'`,
  )
    .bind(c.get("org"))
    .all<{ data: string }>();
  return results.map((r) => JSON.parse(r.data) as RioTutorial);
}

/** Skills of one global app (all, or matching `q`), with their versions, proofs and sources. */
app.get("/api/app/knowledge/skills", async (c) => {
  const kv = await kvKnowledge(c.env, c.get("org"));
  const data = kv.find((d) => d.app.id === c.req.query("app")) ?? kv[0];
  if (!data) return c.json({ app: null, skills: [] });
  const q = (c.req.query("q") ?? "").trim();
  const ids = q ? search([data], [q], { limit: 50 }).map((h) => h.id) : Object.keys(data.skills).sort((a, b) => data.skills[b].sources.length - data.skills[a].sources.length);
  const skills = ids.map((id) => {
    const s = data.skills[id];
    return {
      id,
      intent: s.intent,
      sources: s.sources,
      proofs: s.proofs,
      changed: Object.values(s.steps).some((st) => st.some((x) => x.changed)),
      steps: s.steps,
    };
  });
  return c.json({ app: data.app, skills });
});

/** One question across everything Rio knows for this team (what Holo gets when it searches). */
app.get("/api/app/knowledge/search", async (c) => {
  const q = (c.req.query("q") ?? "").trim();
  if (!q) return c.json({ results: [] });
  const kv = await kvKnowledge(c.env, c.get("org"));
  const all = [...kv, ...tutorialsAsKb(await teamTutorials(c))];
  let results = search(all, [q], { app: c.req.query("app"), limit: 8 });
  if (!results.length || results[0].score < 2) {
    const kw = await englishKeywords(c.env, q);
    if (kw) results = search(all, [q, kw], { app: c.req.query("app"), limit: 8 });
  }
  return c.json({ results: results.filter((r) => r.score >= 2) });
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

app.notFound((c) => (c.req.path.startsWith("/api/") || c.req.path.startsWith("/v1/") ? c.json({ error: "not found" }, 404) : c.env.ASSETS.fetch(c.req.raw)));

export default {
  fetch: app.fetch,
  // Every minute: move the tutorial jobs along, even when nobody has the console open.
  async scheduled(_e, env, ctx) {
    ctx.waitUntil(advancePending(env));
  },
} satisfies ExportedHandler<Env>;
