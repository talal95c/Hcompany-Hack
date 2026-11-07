// Ingesting an organization's written knowledge (markdown docs about any tool, internal or not),
// ported from restep/kg/ingest.py: structure (Holo) -> ground each step on the tool's inventory ->
// one skill per effect (merged with what is already known) -> store.
// A tool with no UI scan (an internal back-office) gets its inventory from the docs themselves,
// the way ReStep builds DaVinci Resolve's from its manual.
import { norm } from "./core/inventory.ts";
import { type Placed, type StructStep, STRUCT_SCHEMA, atomsFromSteps, chunkMarkdown, ground, structPrompt, view } from "./core/ground.ts";
import { type Grounding, effectOp } from "./core/retarget.ts";

export interface IngestEnv {
  DB: D1Database;
  HAI_API_KEY?: string;
  HOLO_INGEST_MODEL?: string;
}

export interface IngestBody {
  workspace: string;
  app: string; // the tool's name ("Comptoir", "Blender")
  version?: string | null;
  title?: string | null;
  text: string; // markdown
  url?: string | null;
}

interface StructPath {
  intent: string;
  steps: StructStep[];
  notes?: string[];
}

async function sha(s: string, n = 10) {
  const d = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, n);
}

const slug = (s: string) => norm(s).replace(/ /g, "-").slice(0, 40) || "tool";

async function structure(env: IngestEnv, app: string, text: string, title?: string | null) {
  if (!env.HAI_API_KEY) throw new Error("HAI_API_KEY is not set on the knowledge Worker");
  const out = { title: title ?? "", version: "", paths: [] as StructPath[] };
  for (const chunk of chunkMarkdown(text)) {
    // The H API sometimes stalls a request: give each attempt a deadline, and try twice.
    let r: Response | null = null;
    let last = "";
    for (let attempt = 0; attempt < 2 && !r?.ok; attempt++) {
      try {
        r = await fetch("https://api.hcompany.ai/v1/chat/completions", {
          method: "POST",
          signal: AbortSignal.timeout(60_000),
          headers: { authorization: `Bearer ${env.HAI_API_KEY}`, "content-type": "application/json" },
          body: JSON.stringify({
            model: env.HOLO_INGEST_MODEL || "holo4-27b",
            messages: [{ role: "user", content: structPrompt("documentation page", app, chunk) }],
            temperature: 0,
            max_tokens: 6000,
            reasoning_effort: "low",
            structured_outputs: { json: STRUCT_SCHEMA },
          }),
        });
        if (!r.ok) last = `${r.status}: ${(await r.clone().text()).slice(0, 200)}`;
      } catch (e) {
        last = e instanceof Error ? e.message : String(e);
        r = null;
      }
    }
    if (!r?.ok) throw new Error(`Holo could not read the document (${last})`);
    const v = (await r.json()) as { choices?: { message?: { content?: string } }[] };
    const d = JSON.parse(v.choices?.[0]?.message?.content ?? "{}") as { title?: string; version?: string; paths?: StructPath[] };
    out.title ||= d.title ?? "";
    out.version ||= d.version ?? "";
    out.paths.push(...(d.paths ?? []).filter((p) => p.steps?.length).map(clean));
  }
  return out;
}

/** What models write for "nothing" ("none", "n/a"), UI chains in one string ("Orders › All orders"),
 *  and UI words where a shortcut or a value belongs. */
const NOTHING = /^(none|null|n\/?a|-|no|empty)?$/i;
const SHORTCUT = /^((ctrl|control|cmd|command|shift|alt|option|opt|meta|super|⌘|⇧|⌥|⌃)\s*[+-]\s*)+\S+$|^(f\d{1,2}|esc|escape|enter|return|tab|space|delete|backspace|home|end|[a-z0-9])$/i;
function clean(p: StructPath): StructPath {
  return {
    ...p,
    steps: p.steps.map((s) => {
      const ui = (s.ui ?? []).flatMap((u) => String(u).split(/\s*[›❯>»⌤→]\s*/)).map((u) => u.trim()).filter(Boolean);
      const uiWords = new Set(ui.map(norm));
      const keys = String(s.keys ?? "")
        .split(/\s*(?:\||,|\bor\b)\s*/i)
        .map((k) => k.trim())
        .filter((k) => k && !NOTHING.test(k) && SHORTCUT.test(k));
      const value = s.value != null && !NOTHING.test(String(s.value).trim()) && !uiWords.has(norm(s.value)) ? s.value : null;
      return { ...s, ui, keys: keys.length ? keys.join(" or ") : null, value };
    }),
  };
}

/** A shortcut the document writes on the line that names the step's element ("Click Export › CSV, or press Ctrl+Shift+E"),
 *  when the model left it out. */
const SHORTCUT_IN_TEXT = /\b(?:(?:Ctrl|Control|Cmd|Command|Shift|Alt|Option|⌘|⇧|⌥)\s*\+\s*)+(?:[A-Z0-9]|F\d{1,2}|Enter|Delete|Tab|Space)\b/g;
function recoverShortcuts(paths: StructPath[], text: string) {
  const lines = text.split("\n").map((l) => ({ n: norm(l), keys: l.match(SHORTCUT_IN_TEXT) ?? [] })).filter((l) => l.keys.length);
  for (const p of paths)
    for (const s of p.steps) {
      if (s.keys || !s.ui?.length) continue;
      const label = norm(s.ui.at(-1));
      const line = label.length > 2 ? lines.find((l) => l.n.includes(label)) : undefined;
      if (line) s.keys = [...new Set(line.keys)].join(" or ");
    }
}

const blank = (s: unknown) => (s == null || String(s).trim() === "" ? null : String(s).trim());

export async function ingest(env: IngestEnv, body: IngestBody) {
  const t0 = Date.now();
  const db = env.DB;
  const ws = body.workspace;
  const text = body.text.slice(0, 60_000);
  if (text.trim().length < 80) throw new Error("The document is too short to learn from");
  const title = blank(body.title) ?? text.match(/^#\s*(.+)$/m)?.[1]?.trim() ?? "Untitled document";

  // 1. The tool: one of the shared apps, one of this organization's, or a new internal tool.
  const { results: apps } = await db
    .prepare(`select * from app where workspace is null or workspace = ?`)
    .bind(ws)
    .all<{ id: string; name: string; current_version: string; grounding: string; workspace: string | null }>();
  let app = apps.find((a) => norm(a.name) === norm(body.app) || a.id === body.app);
  const internal = !app || app.workspace === ws;
  if (!app) {
    const id = `w${await sha(ws, 6)}-${slug(body.app)}`;
    const version = blank(body.version) ?? "current";
    await db.batch([
      db.prepare(`insert into app (id, name, vendor, current_version, grounding, imported_at, workspace) values (?,?,?,?,?,?,?)`).bind(id, body.app.trim(), null, version, "{}", Date.now(), ws),
      db.prepare(`insert into app_version (app, version, label, covers_from, year) values (?,?,?,?,?)`).bind(id, version, `${body.app.trim()} ${version}`, "0", null),
    ]);
    app = { id, name: body.app.trim(), current_version: version, grounding: "{}", workspace: ws };
  }
  const version = app.workspace === ws ? app.current_version : app.current_version; // shared apps: the current interface
  const g: Grounding = { nav_ops: [], routine_ops: [], menu_openers: [], confirm_ops: [], ...JSON.parse(app.grounding) };

  // 2. Structure.
  const struct = await structure(env, app.name, text, title);
  if (!struct.paths.length) throw new Error("Holo found no procedure in this document");
  recoverShortcuts(struct.paths, text);
  const sid = `doc_${await sha(`${ws}|${title}|${text.slice(0, 4000)}`)}`;
  await removeSource(db, ws, sid); // re-ingesting the same document replaces it

  // 3. The inventory: the tool's scan, plus (for an internal tool) every UI chain the docs name.
  const allSteps = struct.paths.flatMap((p) => p.steps);
  if (internal) {
    const atoms = atomsFromSteps(app.id, allSteps);
    const existing = await placements(db, app.id, version);
    const known = new Map(existing.map((p) => [p.op, p]));
    const rows: D1PreparedStatement[] = [];
    for (const a of atoms) {
      const old = known.get(a.op);
      const keys = [...new Set([...(old?.keys ?? []), ...a.keys])];
      rows.push(db.prepare(`insert or ignore into atom (id, app, kind) values (?,?,?)`).bind(a.op, app.id, a.kind ?? "menu"));
      rows.push(
        db.prepare(`insert or replace into placement (atom_id, app, version, label, paths_json, keys_json, via_keys_json) values (?,?,?,?,?,?,?)`)
          .bind(a.op, app.id, version, a.label, JSON.stringify(a.paths), JSON.stringify(keys), "[]"),
      );
      for (const l of new Set([norm(a.label), norm(a.paths[0].split(" › ").slice(-2).join(" "))]))
        if (l) rows.push(db.prepare(`insert or ignore into atom_label (app, version, label_norm, atom_id) values (?,?,?,?)`).bind(app.id, version, l, a.op));
    }
    for (let i = 0; i < rows.length; i += 80) await db.batch(rows.slice(i, i + 80));
  }
  const inv = await placements(db, app.id, version);
  const { results: others } = await db
    .prepare(`select label_norm, atom_id from atom_label where app = ? and version != ?`)
    .bind(app.id, version)
    .all<{ label_norm: string; atom_id: string }>();
  const v = view(inv, others.map((o) => [o.label_norm, o.atom_id]));

  // 4. Ground, then one skill per effect.
  const { results: skillRows } = await db
    .prepare(`select id, name, effect_atom, ops_json from skill where app = ? and (workspace is null or workspace = ?)`)
    .bind(app.id, ws)
    .all<{ id: string; name: string; effect_atom: string | null; ops_json: string }>();
  const { results: edges } = await db
    .prepare(`select src, dst from atom_edge where app = ? and to_version = ? and type = 'successor'`)
    .bind(app.id, version)
    .all<{ src: string; dst: string }>();
  const succ = new Map(edges.map((e) => [e.src, e.dst]));
  const canonical = (op: string | null) => (op && !v.ops.has(op) ? succ.get(op) ?? op : op);

  const stmts: D1PreparedStatement[] = [
    db.prepare(`insert into source (id, workspace, app, url, kind, title, author, language, stated_version, version, added_at) values (?,?,?,?,?,?,?,?,?,?,?)`)
      .bind(sid, ws, app.id, blank(body.url), "doc", struct.title || title, null, null, blank(struct.version), version, Date.now() / 1000),
  ];
  const touched = new Set<string>();
  const tutorialSkills: string[] = [];
  let grounded = 0;
  let merged = 0;
  let created = 0;
  for (const [pi, p] of struct.paths.entries()) {
    const claimIds: string[] = [];
    const ops: string[] = [];
    for (const [si, s] of p.steps.entries()) {
      const [op, conf] = ground(v, s);
      const id = `s_${sid}_${pi}_${si}`;
      claimIds.push(id);
      stmts.push(
        db.prepare(`insert into claim (id, source_id, say, action, ui_json, keys, value, t, version, variant) values (?,?,?,?,?,?,?,?,?,?)`)
          .bind(id, sid, blank(s.say), blank(s.action), JSON.stringify(s.ui ?? []), blank(s.keys), blank(s.value), null, version, null),
      );
      if (op) {
        grounded++;
        if (!g.nav_ops.includes(op)) ops.push(op);
        stmts.push(db.prepare(`insert into grounds (claim_id, atom_id, confidence) values (?,?,?)`).bind(id, op, conf));
      }
    }
    // ReStep's rule: two sources ending on the same element (or its successor) teach the same skill; without one, the same intent.
    const eff = canonical(effectOp(ops, g));
    let skill = eff && !g.routine_ops.includes(eff) ? skillRows.find((k) => canonical(k.effect_atom) === eff) : undefined;
    skill ??= skillRows.find((k) => norm(k.name) === norm(p.intent) && (!eff || !k.effect_atom));
    let skillId: string;
    if (skill) {
      skillId = skill.id;
      merged++;
    } else {
      skillId = `p_${await sha(`${p.intent}|${ops.join(",")}|${sid}`)}`;
      created++;
      stmts.push(
        db.prepare(`insert into skill (id, app, name, effect_atom, ops_json, steps_json, workspace) values (?,?,?,?,?,?,?)`)
          .bind(skillId, app.id, p.intent, effectOp(ops, g), JSON.stringify(ops), JSON.stringify(claimIds), ws),
      );
      skillRows.push({ id: skillId, name: p.intent, effect_atom: effectOp(ops, g), ops_json: JSON.stringify(ops) });
    }
    const seg = `${sid}|${skillId}`;
    stmts.push(db.prepare(`insert or replace into segment (id, source_id, intent, t_start, t_end, version, steps_json) values (?,?,?,?,?,?,?)`).bind(seg, sid, p.intent, null, null, version, JSON.stringify(claimIds)));
    stmts.push(db.prepare(`insert or replace into teaches (segment_id, skill_id) values (?,?)`).bind(seg, skillId));
    for (const n of p.notes ?? []) if (n.trim()) stmts.push(db.prepare(`insert into note (skill_id, source_id, kind, text, t) values (?,?,?,?,?)`).bind(skillId, sid, "note", n.trim(), null));
    touched.add(skillId);
    tutorialSkills.push(skillId);
  }
  stmts.push(
    db.prepare(`insert or replace into tutorial (id, app, source_id, title, version, skills_json, workspace) values (?,?,?,?,?,?,?)`)
      .bind(`t_${sid}`, app.id, sid, struct.title || title, version, JSON.stringify([...new Set(tutorialSkills)]), ws),
  );
  for (let i = 0; i < stmts.length; i += 80) await db.batch(stmts.slice(i, i + 80));
  await reindex(db, ws, app.id, [...touched], v);

  return {
    source: sid,
    title: struct.title || title,
    app: { id: app.id, name: app.name, internal: app.workspace === ws },
    version,
    skills: struct.paths.length,
    new_skills: created,
    merged_into_known: merged,
    steps: allSteps.length,
    grounded,
    elapsed_s: Math.round((Date.now() - t0) / 100) / 10,
  };
}

async function placements(db: D1Database, app: string, version: string): Promise<Placed[]> {
  const { results } = await db
    .prepare(`select p.atom_id, p.label, p.paths_json, p.keys_json, a.kind from placement p left join atom a on a.id = p.atom_id where p.app = ? and p.version = ?`)
    .bind(app, version)
    .all<{ atom_id: string; label: string | null; paths_json: string; keys_json: string; kind: string | null }>();
  return results.map((r) => ({ op: r.atom_id, label: r.label, paths: JSON.parse(r.paths_json), keys: JSON.parse(r.keys_json), kind: r.kind }));
}

/**
 * This organization's search rows for some skills: the skill's name, what its sources (shared and this organization's)
 * say, its UI labels and notes. Shared rows (workspace NULL) are left as the import made them.
 */
async function reindex(db: D1Database, ws: string, app: string, skills: string[], v: ReturnType<typeof view>) {
  for (const id of skills) {
    const skill = await db.prepare(`select name, ops_json, workspace from skill where id = ?`).bind(id).first<{ name: string; ops_json: string; workspace: string | null }>();
    await db.prepare(`delete from skill_search where skill_id = ? and workspace = ?`).bind(id, ws).run();
    if (!skill) continue;
    const { results: said } = await db
      .prepare(
        `select c.say, seg.intent from teaches t join segment seg on seg.id = t.segment_id join source s on s.id = seg.source_id
         join claim c on c.source_id = s.id and instr(seg.steps_json, '"' || c.id || '"') > 0
         where t.skill_id = ? and s.workspace = ?`,
      )
      .bind(id, ws)
      .all<{ say: string | null; intent: string | null }>();
    if (!said.length && skill.workspace !== ws) continue; // nothing of this organization's left on a shared skill
    const { results: notes } = await db
      .prepare(`select n.text from note n join source s on s.id = n.source_id where n.skill_id = ? and s.workspace = ?`)
      .bind(id, ws)
      .all<{ text: string }>();
    const labels = (JSON.parse(skill.ops_json) as string[]).map((o) => v.ops.get(o)?.label ?? "");
    const body = [...said.flatMap((r) => [r.say ?? "", r.intent ?? ""]), ...labels, ...notes.map((n) => n.text)].filter(Boolean).join(" \n ");
    await db.prepare(`insert into skill_search (skill_id, app, workspace, intent, body) values (?,?,?,?,?)`).bind(id, app, ws, skill.name, body).run();
  }
}

/** Removes one of this organization's sources, and what only it taught. */
export async function removeSource(db: D1Database, ws: string, sid: string) {
  const src = await db.prepare(`select id, app, workspace from source where id = ?`).bind(sid).first<{ id: string; app: string; workspace: string | null }>();
  if (!src || src.workspace !== ws) return false;
  const { results } = await db
    .prepare(`select distinct t.skill_id from teaches t join segment s on s.id = t.segment_id where s.source_id = ?`)
    .bind(sid)
    .all<{ skill_id: string }>();
  await db.batch([db.prepare(`delete from note where source_id = ?`).bind(sid), db.prepare(`delete from source where id = ?`).bind(sid)]); // claims, segments, teaches, tutorial cascade
  for (const { skill_id } of results) {
    const left = await db.prepare(`select count(*) as n from teaches where skill_id = ?`).bind(skill_id).first<{ n: number }>();
    if (!left?.n) {
      await db.batch([
        db.prepare(`delete from skill_search where skill_id = ?`).bind(skill_id),
        db.prepare(`delete from skill where id = ? and workspace = ?`).bind(skill_id, ws),
      ]);
    } else {
      await reindex(db, ws, src.app, [skill_id], view(await placements(db, src.app, (await db.prepare(`select current_version as v from app where id = ?`).bind(src.app).first<{ v: string }>())!.v)));
    }
  }
  return true;
}

/** This organization's documents. */
export async function listSources(db: D1Database, ws: string) {
  const { results } = await db
    .prepare(
      `select s.id, s.title, s.url, s.added_at, a.id as app_id, a.name as app_name, a.workspace as app_workspace,
        (select count(distinct t.skill_id) from teaches t join segment g on g.id = t.segment_id where g.source_id = s.id) as skills,
        (select count(*) from claim c where c.source_id = s.id) as steps
       from source s join app a on a.id = s.app where s.workspace = ? order by s.added_at desc`,
    )
    .bind(ws)
    .all();
  return results.map((r) => ({ ...r, internal: r.app_workspace === ws }));
}
