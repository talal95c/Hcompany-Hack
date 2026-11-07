// Converts a ReStep checkout into SQL for the knowledge Worker's D1 database.
// It reads ReStep's own files (graphs, UI scans, keymaps, manual inventories) and runs the
// ported core (src/core) to build each version's inventory, placements and successors.
// No model call, no Python: the same input always gives the same rows.
//
//   node --experimental-strip-types scripts/convert.ts <restep checkout> <out.sql> [app...]
import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { labelIndex, successor, where } from "../src/core/inventory.ts";
import { type AppMeta, loadInventory, versions } from "./restep-files.ts";
import { type Grounding, effectOp } from "../src/core/retarget.ts";

const [root, out, ...only] = process.argv.slice(2);
if (!root || !out) {
  console.error("usage: convert.ts <restep checkout> <out.sql> [app...]");
  process.exit(1);
}
const json = (p: string) => JSON.parse(readFileSync(p, "utf8"));
const maybe = (p: string) => (existsSync(p) ? json(p) : undefined);

// ---------------------------------------------------------------- loading

// ---------------------------------------------------------------- SQL

const lit = (v: unknown): string => {
  if (v === null || v === undefined) return "NULL";
  if (typeof v === "number") return Number.isFinite(v) ? String(v) : "NULL";
  if (typeof v === "boolean") return v ? "1" : "0";
  return `'${String(v).replace(/'/g, "''")}'`;
};

const lines: string[] = [];
function insert(table: string, cols: string[], rows: unknown[][]) {
  for (let i = 0; i < rows.length; i += 50) {
    const chunk = rows.slice(i, i + 50).map((r) => `(${r.map(lit).join(",")})`);
    lines.push(`insert or replace into ${table} (${cols.join(",")}) values\n${chunk.join(",\n")};`);
  }
}

// ---------------------------------------------------------------- one app

function convert(app: string) {
  const meta: AppMeta = json(join(root, "apps", app, "app.json"));
  const g = json(join(root, "kb", app, "graph.json"));
  const vs = versions(meta);
  const grounding: Grounding = {
    nav_ops: (meta.grounding?.nav_ops as string[]) ?? [],
    routine_ops: (meta.grounding?.routine_ops as string[]) ?? [],
    menu_openers: (meta.grounding?.menu_openers as string[]) ?? [],
    confirm_ops: (meta.grounding?.confirm_ops as string[]) ?? [],
  };
  const invs = new Map(vs.map((v) => [v, loadInventory(root, app, v)]));

  // Re-import replaces this app's shared rows (children go with their parents).
  lines.push(`delete from app where id = ${lit(app)};`);
  for (const t of ["placement", "atom_edge", "atom_label"]) lines.push(`delete from ${t} where app = ${lit(app)};`);
  lines.push(`delete from skill_search where app = ${lit(app)};`);

  insert("app", ["id", "name", "vendor", "current_version", "grounding", "imported_at"], [
    [app, meta.name, meta.vendor ?? null, meta.current_version ?? vs.at(-1), JSON.stringify(grounding), Date.now()],
  ]);
  insert(
    "app_version",
    ["app", "version", "label", "covers_from", "year"],
    // Versions compare number by number: Blender's "2.8" means 2.80, which must sort after 2.79.
    meta.versions.map((v) => [app, v.id, v.label ?? null, app === "blender" && v.covers_from === "2.8" ? "2.80" : (v.covers_from ?? "0"), v.year ?? null]),
  );

  // Atoms and their place in every version.
  const steps: Record<string, any> = g.steps;
  const stepOps = new Set<string>([...Object.values(steps).map((s) => s.op).filter(Boolean), ...Object.values<any>(g.paths).flatMap((p) => p.ops)]);
  const atoms = new Map<string, string>();
  const kindOf = (op: string, d?: { kind?: string }) => d?.kind ?? (op.includes(":") && !op.startsWith(`${app}:`) ? op.split(":")[0] : "operator");
  const placements: unknown[][] = [];
  const labels: unknown[][] = [];
  for (const [v, inv] of invs) {
    for (const [op, d] of Object.entries(inv.ops)) {
      atoms.set(op, kindOf(op, d));
      const w = where(inv, op);
      placements.push([op, app, v, w.label, JSON.stringify(w.paths), JSON.stringify(w.keys), JSON.stringify(w.via_keys)]);
    }
    for (const [label, ops] of labelIndex(inv)) for (const op of ops) labels.push([app, v, label, op]);
  }
  for (const op of stepOps) if (!atoms.has(op)) atoms.set(op, kindOf(op));
  insert("atom", ["id", "app", "kind"], [...atoms].map(([op, kind]) => [op, app, kind]));
  insert("placement", ["atom_id", "app", "version", "label", "paths_json", "keys_json", "via_keys_json"], placements);
  insert("atom_label", ["app", "version", "label_norm", "atom_id"], labels);

  // What replaced an operator a version dropped (for every pair of versions, the ops sources use).
  const edges: unknown[][] = [];
  for (const from of vs)
    for (const to of vs) {
      if (from === to) continue;
      for (const op of stepOps) {
        const s = successor(invs.get(from)!, invs.get(to)!, op);
        if (s) edges.push([op, s.op, "successor", app, from, to, s.label, s.why, s.key]);
      }
    }
  insert("atom_edge", ["src", "dst", "type", "app", "from_version", "to_version", "label", "evidence", "key"], edges);

  // Knowledge.
  insert(
    "source",
    ["id", "workspace", "app", "url", "kind", "title", "author", "language", "stated_version", "version", "added_at"],
    Object.values<any>(g.sources).map((s) => [s.id, null, app, s.url, s.kind, s.title, s.author ?? null, s.language, s.stated_version, s.version, s.added]),
  );
  const knownSources = new Set(Object.keys(g.sources));
  const claims = Object.values<any>(steps).filter((s) => knownSources.has(s.source));
  insert(
    "claim",
    ["id", "source_id", "say", "action", "ui_json", "keys", "value", "t", "version", "variant"],
    claims.map((s) => [s.id, s.source, s.say, s.action, JSON.stringify(s.ui ?? []), s.keys, s.value == null ? null : String(s.value), s.t, s.version, s.variant ?? null]),
  );
  insert("grounds", ["claim_id", "atom_id", "confidence"], claims.filter((s) => s.op).map((s) => [s.id, s.op, s.confidence ?? null]));

  // Skills, the passages that teach them, proofs.
  const notes = new Map<string, { source: string; kind: string; text: string; t: number | null }[]>();
  for (const [source, ns] of Object.entries<any[]>(g.notes ?? {}))
    for (const n of ns) (notes.get(n.path) ?? notes.set(n.path, []).get(n.path)!).push({ source, kind: n.kind, text: n.text, t: n.t ?? null });
  const skills: unknown[][] = [];
  const segments: unknown[][] = [];
  const teaches: unknown[][] = [];
  const proofs: unknown[][] = [];
  const noteRows: unknown[][] = [];
  const search: unknown[][] = [];
  for (const [pid, p] of Object.entries<any>(g.paths)) {
    skills.push([pid, app, p.intent, effectOp(p.ops, grounding), JSON.stringify(p.ops), JSON.stringify(p.steps ?? [])]);
    for (const s of p.sources) {
      if (!knownSources.has(s.source)) continue;
      const id = `${s.source}|${pid}`;
      segments.push([id, s.source, s.intent ?? p.intent, s.t ?? null, s.end ?? null, s.version ?? null, JSON.stringify(s.steps ?? [])]);
      teaches.push([id, pid]);
    }
    for (const [v, x] of Object.entries<any>(p.proofs ?? {})) proofs.push([pid, v, x.status]);
    for (const n of notes.get(pid) ?? []) noteRows.push([pid, n.source, n.kind, n.text, n.t]);
    // Searchable words: the skill's name, what every source says, the labels in every version, the notes.
    const said = p.sources.flatMap((s: any) => (s.steps ?? []).map((x: string) => steps[x]?.say ?? "")).concat(p.sources.map((s: any) => s.intent ?? ""));
    const labelsAll = p.ops.flatMap((o: string) => vs.map((v) => invs.get(v)!.ops[o]?.label ?? ""));
    const body = [...said, ...labelsAll, ...(notes.get(pid) ?? []).map((n) => n.text)].filter(Boolean).join(" \n ");
    search.push([pid, app, null, p.intent, body]);
  }
  insert("skill", ["id", "app", "name", "effect_atom", "ops_json", "steps_json"], skills);
  insert("segment", ["id", "source_id", "intent", "t_start", "t_end", "version", "steps_json"], segments);
  insert("teaches", ["segment_id", "skill_id"], teaches);
  insert("proof", ["skill_id", "version", "status"], proofs);
  insert("note", ["skill_id", "source_id", "kind", "text", "t"], noteRows);
  insert("skill_search", ["skill_id", "app", "workspace", "intent", "body"], search);
  insert(
    "tutorial",
    ["id", "app", "source_id", "title", "version", "skills_json"],
    Object.values<any>(g.tutorials)
      .filter((t) => knownSources.has(t.source))
      .map((t) => [t.id, app, t.source, t.title, t.version, JSON.stringify(t.paths.filter((x: string) => g.paths[x]))]),
  );

  const n = (rows: unknown[][]) => rows.length;
  console.log(
    `${app}: ${vs.join(", ")} · ${atoms.size} atoms, ${n(placements)} placements, ${n(edges)} successors, ${n(labels)} labels · ` +
      `${Object.keys(g.sources).length} sources, ${claims.length} claims, ${n(skills)} skills, ${n(segments)} segments, ` +
      `${Object.keys(g.tutorials).length} tutorials, ${n(noteRows)} notes`,
  );
}

const apps = readdirSync(join(root, "apps")).filter(
  (a) => existsSync(join(root, "apps", a, "app.json")) && existsSync(join(root, "kb", a, "graph.json")) && (!only.length || only.includes(a)),
);
for (const a of apps) convert(a);
writeFileSync(out, lines.join("\n") + "\n");
console.log(`-> ${out} (${Math.round(lines.join("\n").length / 1024)} KB)`);
