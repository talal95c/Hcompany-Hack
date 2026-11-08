// Grounding a structured step on the software's inventory, ported from restep/kg/ingest.py
// (ground, _match_path, canonical). Pure: the caller hands in the inventory as placements.
//
// Kept from ReStep: modal keys are not actions; keys first (the tutorial's own shortcut);
// then UI words, the last label naming the action and the chain before it matching a real path;
// labels from other versions; the model's guess only if the software has that element;
// "enable/disable X" is a setting, not the X action; nothing below 0.5 confidence.
// Left out (Blender-specific, need its operator registry): enum variants, mesh/object twins,
// per-mode keymap contexts.
import { norm } from "./inventory.ts";
import { parseKeys } from "./retarget.ts";
import { combo } from "./inventory.ts";

/** One version's inventory, as the Worker stores it. */
export interface Placed {
  op: string;
  label: string | null;
  paths: string[]; // "Menu › Submenu › Item"
  keys: string[]; // "Ctrl+Shift+E"
  kind?: string | null;
}

export interface StructStep {
  t?: number | null;
  say?: string | null;
  action?: string | null;
  ui?: string[] | null;
  keys?: string | null;
  value?: string | number | null;
  op?: string | null;
}

export interface View {
  ops: Map<string, Placed>;
  labels: Map<string, Set<string>>; // normalized label -> ops (this version)
  otherLabels: Map<string, Set<string>>; // labels other versions used
  menus: Set<string>; // every non-final crumb of a path
  keys: Map<string, string[]>; // "Ctrl+B" -> ops
}

export function view(placed: Placed[], otherLabels: [string, string][] = []): View {
  const ops = new Map(placed.map((p) => [p.op, p]));
  const labels = new Map<string, Set<string>>();
  const add = (m: Map<string, Set<string>>, k: string, op: string) => k && (m.get(k) ?? m.set(k, new Set()).get(k)!).add(op);
  const menus = new Set<string>();
  const keys = new Map<string, string[]>();
  for (const p of placed) {
    add(labels, norm(p.label), p.op);
    for (const path of p.paths) {
      const parts = path.split(" › ");
      add(labels, norm(parts.at(-1)), p.op);
      if (parts.length >= 2) add(labels, norm(parts.slice(-2).join(" ")), p.op);
      for (const c of parts.slice(0, -1)) if (norm(c)) menus.add(norm(c));
    }
    if (p.kind === "page") {
      const name = p.paths[0]?.split(" › ").at(-1) ?? p.label ?? "";
      for (const a of [name, `${name} tab`, `${name} page`, `${name} screen`]) add(labels, norm(a), p.op);
    }
    for (const k of p.keys) (keys.get(k) ?? keys.set(k, []).get(k)!).push(p.op);
  }
  const other = new Map<string, Set<string>>();
  for (const [l, op] of otherLabels) add(other, l, op);
  return { ops, labels, otherLabels: other, menus, keys };
}

const IGNORED_UI = new Set(["3d viewport", "keyboard", "mouse", "properties panel", "screen", "page", "window"]);

/** -> [op, confidence, menu path] for one structured step, or [null, 0, null]. */
export function ground(v: View, step: StructStep, mainEditors: string[] = []): [string | null, number, string | null] {
  const say = (step.say ?? "").toLowerCase();
  const keysTxt = String(step.keys ?? "").toLowerCase();
  // modal keys belong to the running operation: X/Y/Z to lock an axis, Esc to cancel, Enter to confirm
  // (ReStep also looks for "click" in the sentence; in a back-office "click Confirm" is the action itself)
  if ((/\baxis\b/.test(say) && /^[xyz](\s*(,|or)\s*[xyz])*$/.test(keysTxt.trim() || "-")) || (/\b(cancel|confirm)\b/.test(say) && /esc|right|left|enter|click/.test(keysTxt)))
    return [null, 0, null];
  const alts = parseKeys(step.keys);
  if (alts.length >= 2 && alts.every(([ev]) => ["X", "Y", "Z"].includes(ev))) return [null, 0, null];
  const ui = (step.ui ?? []).filter((u) => u && !IGNORED_UI.has(norm(u)) && norm(u).length > 2);
  const guess = (step.op ?? "").trim();
  const cands = new Map<string, number>();
  const bump = (op: string, c: number) => cands.set(op, Math.max(cands.get(op) ?? 0, Math.round(c * 100) / 100));

  // 1. keys: the shortcut the source names
  const keySource = step.keys || (step.action === "key" && step.ui?.length ? step.ui[0] : "");
  for (const [ev, mods] of parseKeys(keySource)) {
    for (const op of v.keys.get(combo({ key: ev, mods })) ?? []) bump(op, op === guess ? 0.85 : 0.75);
  }
  // 2. UI words: the last label names the action, the chain before it must match one of its paths
  const opensMenu = step.action === "menu" || /\b(sub)?menu\b/.test(say);
  if (!["drag", "select"].includes(step.action ?? "")) {
    for (let i = ui.length; i > 0; i--) {
      if (opensMenu && v.menus.has(norm(ui[i - 1]))) continue; // "open the Orders menu": navigation to the next step
      for (const op of v.labels.get(norm(ui[i - 1])) ?? []) {
        const d = v.ops.get(op)!;
        if (step.action === "other" && d.kind !== "page") continue;
        let best = 0;
        for (const p of d.paths.length ? d.paths : [d.label ?? ""]) {
          const chain = p.split(" › ").map(norm);
          const hit = ui.filter((u) => chain.includes(norm(u))).length;
          const ed = !mainEditors.length || mainEditors.includes(p.split(" › ")[0]) ? 1 : 0.5;
          best = Math.max(best, (0.45 + (0.45 * hit) / Math.max(ui.length, 1)) * ed);
        }
        if (op === guess) best += 0.25;
        if (ui.length === 1 && d.paths[0] && d.paths[0].split(" › ").length > 1 && op !== guess && !step.keys) best = Math.min(best, 0.55);
        bump(op, best);
      }
      if (cands.size) break;
    }
  }
  // 2b. a label from another version ("Remove Doubles" in a newer guide): the element it named, if still here
  if (!["drag", "select", "other"].includes(step.action ?? "") && ui.length && norm(ui.at(-1)).split(" ").length >= 2 && Math.max(0, ...cands.values()) < 0.8) {
    for (const op of v.otherLabels.get(norm(ui.at(-1))) ?? []) if (v.ops.has(op)) bump(op, 0.7);
  }
  // 3. the model's guess, only if the software has it
  if (guess && v.ops.has(guess) && !cands.has(guess) && !(opensMenu && ui.slice(-1).some((u) => v.menus.has(norm(u))))) bump(guess, 0.55);
  if (!cands.size) return [null, 0, null];
  // "Enable Merge" is a setting of a panel, not the Merge action
  if (step.action === "set" || (/^(enable|disable|check|uncheck|tick|untick|turn (on|off)|toggle)\b/.test(say) && !/\bclick\b/.test(say))) {
    for (const [o, c] of cands) if (!/^(prop|tab):/.test(o) && v.ops.get(o)?.kind !== "setting") cands.set(o, Math.min(c, 0.45));
  }
  const [op, conf] = [...cands.entries()].reduce((a, b) => (b[1] > a[1] ? b : a));
  if (conf < 0.5) return [null, 0, null];
  return [op, Math.min(conf, 1), v.ops.get(op)?.paths[0] ?? null];
}

/** Steps whose UI chain names an element: for a tool with no UI scan, the docs are the inventory. */
export function atomsFromSteps(appId: string, steps: StructStep[]): Placed[] {
  const out = new Map<string, Placed>();
  for (const s of steps) {
    const ui = (s.ui ?? []).map((u) => u.trim()).filter((u) => u && !IGNORED_UI.has(norm(u)));
    if (!ui.length || ["drag", "select", "other"].includes(s.action ?? "")) continue;
    const path = ui.join(" › ");
    const id = `${appId}:ui/${norm(path).replace(/ /g, "_")}`;
    const p = out.get(id) ?? { op: id, label: ui.at(-1)!, paths: [path], keys: [], kind: s.action === "set" ? "setting" : ui.length === 1 && /\b(page|tab|screen)\b/i.test(s.say ?? "") ? "page" : "menu" };
    for (const [ev, mods] of parseKeys(s.keys)) {
      const k = combo({ key: ev, mods });
      if (!p.keys.includes(k)) p.keys.push(k);
    }
    out.set(id, p);
  }
  return [...out.values()];
}

/** The structuring prompt, from restep/kg/ingest.py (STRUCT), for a written source about any tool. */
export function structPrompt(kind: string, app: string, text: string): string {
  return (
    `You turn a ${kind} about ${app} into a structured procedure graph.\n` +
    `Find every PATH: one concrete thing the reader learns to do (an intent, e.g. "Refund an order", "Export a report", ` +
    `"Add a user"). Ignore text that teaches no action. For each path list its STEPS: each step is ONE action the reader ` +
    `performs in the interface (open a menu chain, press a key combination, click a button or tab, set a field to a value, ` +
    `switch page, select). Use the exact UI words written, in "ui" only. Also collect the notes that matter (why, warnings, prerequisites).\n\n` +
    `${kind.charAt(0).toUpperCase() + kind.slice(1)}:\n${text}`
  );
}

export const STRUCT_SCHEMA = {
  type: "object",
  properties: {
    title: { type: "string" },
    // No "version" field: with nothing to write (most docs state none), Holo's constrained decoding pads it with
    // whitespace until max_tokens and the JSON never closes. The version comes from the person adding the doc.
    paths: {
      type: "array",
      items: {
        type: "object",
        properties: {
          intent: { type: "string", description: "imperative, max 6 words" },
          steps: {
            type: "array",
            items: {
              type: "object",
              properties: {
                say: { type: "string", description: "short imperative instruction" },
                action: { type: "string", enum: ["menu", "key", "click", "set", "mode", "select", "drag", "other"] },
                ui: { type: "array", items: { type: "string" }, description: "the UI words, outermost first: [Menu, Submenu, Item] or [Page, Button]" },
                keys: { type: "string", description: "a keyboard shortcut the text gives for this step (e.g. Ctrl+Shift+E), else empty. Never UI words." },
                value: { type: "string", description: "a value the reader types or picks (e.g. SPRING15, 15%, March 2026), else empty. Never the clicked element's name." },
              },
              required: ["say", "action", "ui", "keys", "value"],
            },
          },
          notes: { type: "array", items: { type: "string" } },
        },
        required: ["intent", "steps", "notes"],
      },
    },
  },
  required: ["title", "paths"],
};

/** Split a markdown doc on its headings into chunks of at most ~12k characters. */
export function chunkMarkdown(text: string, max = 12_000): string[] {
  const parts = text.split(/(?=^#{1,3}\s)/m);
  const out: string[] = [];
  let cur = "";
  for (const p of parts) {
    if (cur && cur.length + p.length > max) {
      out.push(cur);
      cur = "";
    }
    cur += p;
    while (cur.length > max) {
      out.push(cur.slice(0, max));
      cur = cur.slice(max);
    }
  }
  if (cur.trim()) out.push(cur);
  return out;
}
