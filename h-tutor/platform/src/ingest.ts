// Turns what a member adds into a Rio tutorial, as a resumable job:
//   youtube: Gladia transcribes the video from its link (timestamps)            -> Holo designs
//   page:    the page's text; if it is empty (JavaScript) or unreadable, H's
//            web agent (h/web-surfer-pro, Agents API) reads the guide in a browser -> Holo designs
//   goal:    H's web agent finds and reads the official docs (Linkup as fallback) -> Holo designs
// The application's name (and macOS bundle id) is extracted as soon as there is text.

import { HaiAgentsClient } from "hai-agents";
// Each call to `advance` does one step and saves it, so a job survives the
// Worker stopping between steps; a lease keeps two runs off the same job.

export interface IngestEnv {
  DB: D1Database;
  HAI_API_KEY?: string;
  GLADIA_API_KEY?: string;
  LINKUP_API_KEY?: string;
  HOLO_DESIGN_MODEL?: string;
  HOLO_MODEL?: string;
}

export type Kind = "youtube" | "page" | "goal";

export interface TutorialRow {
  id: string;
  organizationId: string;
  kind: Kind;
  input: string;
  title: string | null;
  app: string | null;
  status: string;
  error: string | null;
  job: string | null;
  data: string | null;
  sources: string | null;
  createdAt: number;
  updatedAt: number;
  leaseUntil: number;
  createdBy: string | null;
  visibility: "draft" | "team" | "community";
  publishedAt: number | null;
  remixOf: string | null;
}

interface Job {
  gladiaUrl?: string;
  author?: string;
  material?: string; // what Holo designs from
  language?: string;
  polls?: number;
  pageText?: string; // what a plain fetch got, kept as a fallback for the agent
  agentSession?: string; // H Agents API session reading the docs
  agentViewUrl?: string; // live view and replay of that session
  bundleId?: string;
}

const LEASE_MS = 3 * 60_000;
const PENDING = ["queued", "transcribing", "browsing", "designing"];
const AGENT = "h/web-surfer-pro";

export const youtubeId = (url: string) =>
  url.match(/(?:youtube\.com\/(?:watch\?(?:.*&)?v=|shorts\/|embed\/)|youtu\.be\/)([\w-]{11})/)?.[1] ?? null;

export function kindOf(input: string): Kind {
  const s = input.trim();
  if (youtubeId(s)) return "youtube";
  if (/^https?:\/\//i.test(s)) return "page";
  return "goal";
}

async function save(env: IngestEnv, id: string, fields: Partial<TutorialRow> & { job?: string | null }) {
  const keys = Object.keys(fields) as (keyof TutorialRow)[];
  const set = [...keys.map((k) => `"${k}" = ?`), `"updatedAt" = ?`].join(", ");
  await env.DB.prepare(`update "tutorial" set ${set} where "id" = ?`)
    .bind(...keys.map((k) => fields[k] ?? null), Date.now(), id)
    .run();
}

/** Takes the job for LEASE_MS if nobody holds it; false when another run has it. */
async function claim(env: IngestEnv, id: string): Promise<boolean> {
  const now = Date.now();
  const r = await env.DB.prepare(`update "tutorial" set "leaseUntil" = ? where "id" = ? and "leaseUntil" < ?`)
    .bind(now + LEASE_MS, id, now)
    .run();
  return r.meta.changes === 1;
}

/** Advances every pending job of an organization (or all of them), one step each. */
export async function advancePending(env: IngestEnv, organizationId?: string) {
  const q = organizationId
    ? env.DB.prepare(
        `select * from "tutorial" where "organizationId" = ? and "status" in (${PENDING.map(() => "?").join(",")}) and "leaseUntil" < ?`,
      ).bind(organizationId, ...PENDING, Date.now())
    : env.DB.prepare(`select * from "tutorial" where "status" in (${PENDING.map(() => "?").join(",")}) and "leaseUntil" < ?`).bind(
        ...PENDING,
        Date.now(),
      );
  const { results } = await q.all<TutorialRow>();
  await Promise.all(results.map((row) => advance(env, row)));
}

export async function advance(env: IngestEnv, row: TutorialRow) {
  if (!(await claim(env, row.id))) return;
  const job: Job = row.job ? JSON.parse(row.job) : {};
  try {
    // One step, then release the lease so the next poll or cron continues.
    const next = await step(env, row, job);
    await save(env, row.id, { ...next, job: JSON.stringify(job), leaseUntil: 0 });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    await save(env, row.id, { status: "failed", error: msg.slice(0, 500), job: JSON.stringify(job), leaseUntil: 0 });
  }
}

async function step(env: IngestEnv, row: TutorialRow, job: Job): Promise<Partial<TutorialRow>> {
  switch (row.status) {
    case "queued":
      if (row.kind === "youtube") return startTranscription(env, row, job);
      if (row.kind === "page") return readPage(env, row, job);
      return searchGoal(env, row, job);
    case "transcribing":
      return pollTranscription(env, job);
    case "browsing":
      return pollAgent(env, row, job);
    case "designing":
      return design(env, row, job);
    default:
      return {};
  }
}

// ---------------------------------------------------------------- YouTube

async function startTranscription(env: IngestEnv, row: TutorialRow, job: Job): Promise<Partial<TutorialRow>> {
  if (!env.GLADIA_API_KEY) throw new Error("GLADIA_API_KEY is not set on the platform");
  const meta = await fetch(`https://www.youtube.com/oembed?format=json&url=${encodeURIComponent(row.input)}`)
    .then((r) => (r.ok ? (r.json() as Promise<{ title?: string; author_name?: string }>) : {}))
    .catch(() => ({}) as { title?: string; author_name?: string });
  const r = await fetch("https://api.gladia.io/v2/pre-recorded", {
    method: "POST",
    headers: { "x-gladia-key": env.GLADIA_API_KEY, "content-type": "application/json" },
    // Gladia fetches the video itself from its YouTube link.
    body: JSON.stringify({ audio_url: row.input }),
  });
  const v = (await r.json()) as { result_url?: string; message?: string };
  if (!r.ok || !v.result_url) throw new Error(`Gladia could not take this video: ${v.message ?? r.status}`);
  job.gladiaUrl = v.result_url;
  job.author = "author_name" in meta ? meta.author_name : undefined;
  const title = ("title" in meta && meta.title) || row.title;
  const app = await detectApp(env, job, `YouTube video "${title ?? ""}" by ${job.author ?? "?"}`);
  return { status: "transcribing", title, app, sources: JSON.stringify([{ title: `${title ?? "Video"}${job.author ? ` · ${job.author}` : ""}`, url: row.input }]) };
}

async function pollTranscription(env: IngestEnv, job: Job): Promise<Partial<TutorialRow>> {
  const r = await fetch(job.gladiaUrl!, { headers: { "x-gladia-key": env.GLADIA_API_KEY! } });
  const v = (await r.json()) as {
    status?: string;
    error_code?: number;
    result?: { transcription?: { languages?: string[]; utterances?: { start: number; text: string }[] } };
  };
  job.polls = (job.polls ?? 0) + 1;
  if (v.status === "error") throw new Error(`Gladia failed to transcribe the video (${v.error_code ?? "error"})`);
  if (v.status !== "done") {
    if (job.polls > 120) throw new Error("Transcription took too long");
    return {};
  }
  const t = v.result?.transcription;
  const lines = (t?.utterances ?? []).map((u) => `[${Math.floor(u.start)}s] ${u.text.trim()}`);
  if (!lines.length) throw new Error("The video has no speech to learn from");
  job.material = clip(lines.join("\n"));
  job.language = t?.languages?.[0];
  return { status: "designing" };
}

// ---------------------------------------------------------------- Page

async function readPage(env: IngestEnv, row: TutorialRow, job: Job): Promise<Partial<TutorialRow>> {
  let title = "";
  let text = "";
  try {
    const r = await fetch(row.input, { headers: { "user-agent": "RioPlatform/1.0 (+tutorial import)" }, redirect: "follow" });
    if (r.ok) {
      const html = await r.text();
      title = decode(html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1] ?? "").trim();
      text = decode(
        html
          .replace(/<(script|style|noscript|svg|nav|footer|header)[\s\S]*?<\/\1>/gi, " ")
          .replace(/<(br|\/p|\/li|\/h\d|\/tr|\/div)[^>]*>/gi, "\n")
          .replace(/<[^>]+>/g, " "),
      )
        .replace(/[ \t]+/g, " ")
        .replace(/\n\s*\n+/g, "\n")
        .trim();
    }
  } catch {
    // unreachable from here: the agent's browser may still get it
  }
  const app = await detectApp(env, job, `${title}\n${row.input}\n${text.slice(0, 1500)}`);
  // A JavaScript page, a blocked fetch or a thin page: let H's web agent read it in a real browser.
  if (text.length < 1500 && env.HAI_API_KEY) {
    job.pageText = text ? clip(text) : undefined;
    return { ...(await startAgent(env, job, pageTask(row.input))), title: title || row.title, app };
  }
  if (text.length < 200) throw new Error("The page has too little text to learn from");
  job.material = clip(text);
  return { status: "designing", title: title || row.title, app, sources: JSON.stringify([{ title: title || row.input, url: row.input }]) };
}

const pageTask = (url: string) =>
  `Open ${url}. It explains how to do something in a piece of software. Read the whole guide: scroll to the end, and ` +
  `if the guide continues on other pages or tabs of the same site, open them too (at most 5 pages). Then answer with: ` +
  `the software's name and the version the guide is for if stated, and every step in order with the exact menu paths, ` +
  `button labels, keyboard shortcuts and settings it gives. Do not invent steps. End with "Sources:" and the URLs you read.`;

const goalTask = (goal: string) =>
  `Find out how to do this in the software's official documentation (prefer the vendor's own docs, then reputable ` +
  `tutorials): "${goal}". Read the relevant pages (at most 5). Then answer with: the software's name and the version ` +
  `the docs are for, and every step in order with the exact menu paths, button labels, keyboard shortcuts and settings. ` +
  `Do not invent steps. End with "Sources:" and the URLs you read.`;

// ---------------------------------------------------------------- H web agent (Agents API)

const agents = (env: IngestEnv) => new HaiAgentsClient({ apiKey: env.HAI_API_KEY });

async function startAgent(env: IngestEnv, job: Job, task: string): Promise<Partial<TutorialRow>> {
  const session = await agents(env).startSession({ agent: AGENT, messages: task, maxTimeS: 300, queue: true });
  job.agentSession = session.id;
  job.polls = 0;
  try {
    const s = (await session.get()) as { agentViewUrl?: string | null };
    job.agentViewUrl = s.agentViewUrl ?? undefined;
  } catch {
    // the live view is a nice-to-have
  }
  return { status: "browsing" };
}

async function pollAgent(env: IngestEnv, row: TutorialRow, job: Job): Promise<Partial<TutorialRow>> {
  const session = agents(env).session(job.agentSession!);
  const st = await session.status();
  job.polls = (job.polls ?? 0) + 1;
  if (["pending", "queued", "running", "awaiting_tool_results", "paused"].includes(st.status)) {
    // About 10 minutes of polls: make it answer with what it has.
    if (job.polls === 150) await session.forceAnswer().catch(() => {});
    if (job.polls > 220) throw new Error("The web agent took too long to read the docs");
    return {};
  }
  const s = (await session.get()) as { latestAnswer?: unknown; answer?: unknown; agentViewUrl?: string | null };
  const raw = s.latestAnswer ?? s.answer;
  const answer = typeof raw === "string" ? raw : raw ? JSON.stringify(raw) : "";
  if (!["completed", "idle"].includes(st.status) || answer.trim().length < 80) {
    // The agent could not read it: fall back on what we have.
    if (row.kind === "page" && job.pageText && job.pageText.length >= 200) {
      job.material = job.pageText;
      return { status: "designing", sources: JSON.stringify([{ title: row.title ?? row.input, url: row.input }]) };
    }
    if (row.kind === "goal") return searchLinkup(env, row, job);
    throw new Error(`The web agent could not read the page (${st.error ?? st.status})`);
  }
  job.material = clip(answer);
  job.pageText = undefined;
  const urls = [...new Set(answer.match(/https?:\/\/[^\s)\]>"']+/g) ?? [])].slice(0, 6);
  const sources = urls.map((u) => ({ title: u.replace(/^https?:\/\/(www\.)?/, "").slice(0, 80), url: u }));
  if (row.kind === "page" && !urls.includes(row.input)) sources.unshift({ title: row.title ?? row.input, url: row.input });
  const view = job.agentViewUrl ?? s.agentViewUrl ?? undefined;
  if (view) sources.push({ title: "How H's web agent read it (replay)", url: view });
  const app = row.app ?? (await detectApp(env, job, answer.slice(0, 1500)));
  return { status: "designing", sources: JSON.stringify(sources), app };
}

function decode(s: string): string {
  return s
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)));
}

// ---------------------------------------------------------------- Goal (Linkup)

async function searchGoal(env: IngestEnv, row: TutorialRow, job: Job): Promise<Partial<TutorialRow>> {
  const app = await detectApp(env, job, row.input);
  if (env.HAI_API_KEY) {
    try {
      return { ...(await startAgent(env, job, goalTask(row.input))), app };
    } catch {
      // Agents API unavailable (quota, outage): search the web another way
    }
  }
  return { ...(await searchLinkup(env, row, job)), app };
}

async function searchLinkup(env: IngestEnv, row: TutorialRow, job: Job): Promise<Partial<TutorialRow>> {
  if (!env.LINKUP_API_KEY) {
    // No web search configured: Holo designs from its own knowledge, and says so.
    job.material = `No web search available. Design from your own knowledge of the software; only include menu paths and shortcuts you are sure of.`;
    return { status: "designing", sources: JSON.stringify([{ title: "Holo's knowledge (no web search)", url: "" }]) };
  }
  const r = await fetch("https://api.linkup.so/v1/search", {
    method: "POST",
    headers: { authorization: `Bearer ${env.LINKUP_API_KEY}`, "content-type": "application/json" },
    body: JSON.stringify({ q: `How to: ${row.input}. Step by step, with exact menu paths and shortcuts.`, depth: "standard", outputType: "sourcedAnswer" }),
  });
  if (!r.ok) throw new Error(`Linkup search failed (${r.status})`);
  const v = (await r.json()) as { answer?: string; sources?: { name?: string; url?: string; snippet?: string }[] };
  const sources = (v.sources ?? []).slice(0, 6).map((s) => ({ title: s.name ?? s.url ?? "", url: s.url ?? "" }));
  job.material = clip(
    `Web search answer:\n${v.answer ?? ""}\n\nSources:\n` +
      (v.sources ?? [])
        .slice(0, 6)
        .map((s) => `- ${s.name} (${s.url}): ${s.snippet ?? ""}`)
        .join("\n"),
  );
  return { status: "designing", sources: JSON.stringify(sources) };
}

// ---------------------------------------------------------------- Design

function clip(s: string, max = 40_000): string {
  return s.length > max ? `${s.slice(0, max)}\n[…truncated]` : s;
}

const SCHEMA = {
  type: "object",
  properties: {
    title: { type: "string" },
    app: { type: "string" },
    bundle_id: { type: "string" },
    goal: { type: "string" },
    milestones: {
      type: "array",
      minItems: 1,
      maxItems: 10,
      items: {
        type: "object",
        properties: {
          goal: { type: "string" },
          done_when: { type: "string" },
          hints: { type: "array", items: { type: "string" }, maxItems: 4 },
          teach: { type: "string" },
          video_at: { type: "integer" },
        },
        required: ["goal", "done_when", "hints", "teach", "video_at"],
      },
    },
  },
  required: ["title", "app", "bundle_id", "goal", "milestones"],
};

interface Plan {
  title: string;
  app: string;
  bundle_id: string;
  goal: string;
  milestones: { goal: string; done_when: string; hints: string[]; teach: string; video_at: number }[];
}

const MATERIAL: Record<Kind, string> = {
  youtube: "the video's timestamped transcript",
  page: "the documentation page",
  goal: "a web search about the goal",
};

async function design(env: IngestEnv, row: TutorialRow, job: Job): Promise<Partial<TutorialRow>> {
  if (!env.HAI_API_KEY) throw new Error("HAI_API_KEY is not set on the platform");
  const what = row.kind === "goal" ? `The goal: "${row.input}"` : `Source: ${row.title ?? row.input}${job.author ? ` by ${job.author}` : ""}`;
  const prompt =
    `You turn ${MATERIAL[row.kind]} into a hands-on interactive tutorial that a learner follows live in the ` +
    `application, guided by an AI tutor that sees their screen.\n\n${what}\n\n<material>\n${job.material}\n</material>\n\n` +
    `Design 2 to 10 milestones the learner performs inside the application, in order. Skip parts that only talk, or ` +
    `happen outside the app (downloading, installing).\nFor each milestone, in English:\n` +
    `- goal: an imperative sub-goal (e.g. "Add a torus").\n` +
    `- done_when: the intended state, checkable on a screenshot of the learner's screen; describe the state, not a ` +
    `specific object they may not have.\n` +
    `- hints: the GUI paths and shortcuts the material gives for it; do not invent any.\n` +
    `- teach: one sentence the material explains about the concept, or empty.\n` +
    `- video_at: ${row.kind === "youtube" ? "the second in the video where it is shown" : "0"}.\n` +
    `Also: a short title (max 6 words), the application's official product name${row.app ? ` (detected: "${row.app}")` : ""}, ` +
    `its macOS bundle identifier if you know it (e.g. "org.blenderfoundation.blender", "com.blackmagic-design.DaVinciResolve"; ` +
    `empty if unsure), and the overall goal as an imperative sentence.`;
  const r = await fetch("https://api.hcompany.ai/v1/chat/completions", {
    method: "POST",
    headers: { authorization: `Bearer ${env.HAI_API_KEY}`, "content-type": "application/json" },
    body: JSON.stringify({
      model: env.HOLO_DESIGN_MODEL || "holo4-27b",
      messages: [{ role: "user", content: prompt }],
      temperature: 0,
      max_tokens: 4096,
      reasoning_effort: "low",
      structured_outputs: { json: SCHEMA },
    }),
  });
  if (!r.ok) throw new Error(`Holo could not design the tutorial (${r.status}): ${(await r.text()).slice(0, 200)}`);
  const v = (await r.json()) as { choices?: { message?: { content?: string } }[] };
  const p = JSON.parse(v.choices?.[0]?.message?.content ?? "null") as Plan | null;
  if (!p?.milestones?.length) throw new Error("Holo returned no milestones");
  const id = `rio:org:${row.id}`;
  const tutorial = {
    id,
    version: 1,
    title: p.title,
    app: { name: p.app || row.app || "Application", bundle_id: (p.bundle_id || job.bundleId || "").trim() || undefined },
    goal: p.goal,
    language: job.language,
    source: "company",
    source_url: row.kind === "goal" ? undefined : row.input,
    milestones: p.milestones.map((m, i) => ({
      id: `m${i + 1}`,
      goal: m.goal,
      done_when: m.done_when,
      hints: m.hints,
      teach: m.teach?.trim() || undefined,
      video_at: row.kind === "youtube" ? m.video_at : undefined,
    })),
  };
  job.material = undefined; // the tutorial replaces it
  return { status: "ready", title: p.title, app: tutorial.app.name, data: JSON.stringify(tutorial), error: null };
}

// ---------------------------------------------------------------- application

/**
 * The application a tutorial is about, from whatever text there is (a goal, a
 * video title, the start of a page): its official name, and its macOS bundle id
 * so Rio shows the installed app's icon. One fast Holo call; null if unsure.
 */
async function detectApp(env: IngestEnv, job: Job, text: string): Promise<string | null> {
  if (!env.HAI_API_KEY || !text.trim()) return null;
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
              "Which software application is this tutorial about? Answer with its official product name (e.g. " +
              '"Blender", "DaVinci Resolve", "Microsoft Excel", "Figma") and its macOS bundle identifier if you know it ' +
              `(empty if unsure). If no application is clear, answer an empty name.\n\n${text.slice(0, 2000)}`,
          },
        ],
        temperature: 0,
        max_tokens: 80,
        reasoning_effort: "none",
        structured_outputs: { json: { type: "object", properties: { app: { type: "string" }, bundle_id: { type: "string" } }, required: ["app", "bundle_id"] } },
      }),
      signal: AbortSignal.timeout(15_000),
    });
    if (!r.ok) return null;
    const v = (await r.json()) as { choices?: { message?: { content?: string } }[] };
    const out = JSON.parse(v.choices?.[0]?.message?.content ?? "{}") as { app?: string; bundle_id?: string };
    if (out.bundle_id?.trim()) job.bundleId = out.bundle_id.trim();
    return out.app?.trim() || null;
  } catch {
    return null;
  }
}
