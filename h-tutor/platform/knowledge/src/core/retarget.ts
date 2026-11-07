// Re-targeting a skill to a version, ported from restep/kg/prove.py (resolve, navigation,
// instruction) and restep/kg/api.py (path, change_kind). Pure: the caller provides where an
// operator is in a version and what replaced it (from D1 in the Worker, from the inventories
// in the converter).
import { type Successor, type Where, combo, norm } from "./inventory.ts";

export interface Lookup {
  where(op: string, version: string): Where;
  successor(op: string, from: string, to: string): Successor | null;
}

export interface Grounding {
  nav_ops: string[];
  routine_ops: string[];
  menu_openers: string[];
  confirm_ops: string[];
}

/** A step as a source said it (restep's graph "steps"). */
export interface Claim {
  id: string;
  say: string | null;
  action: string | null;
  ui: string[];
  keys: string | null;
  value: string | null;
  t: number | null;
  source: string;
  version: string;
  op: string | null;
  variant?: string | null;
}

export interface SkillSource {
  source: string;
  t: number | null;
  end: number | null;
  version: string | null;
  steps: string[];
}

export interface Skill {
  id: string;
  intent: string;
  ops: string[];
  steps: string[]; // the skill's default step list
  sources: SkillSource[];
}

export interface PathStep {
  say: string | null;
  do: string;
  op: string | null;
  label: string | null;
  replaced: Successor | null;
  where: Where | null;
  was: { version: string; label: string | null; paths: string[]; via_keys: string[] } | null;
  routine: boolean;
  changed: boolean;
  missing: boolean;
  value: string | null;
  t: number | null;
  source: string;
}

// operators that start an interactive (modal) action: confirmed by a click or Enter
const MODAL = new Set([
  "object.duplicate_move", "mesh.duplicate_move", "mesh.extrude_region_move", "mesh.extrude_context_move", "mesh.loopcut_slide",
  "mesh.inset", "mesh.bevel", "mesh.knife_tool", "object.duplicate_move_linked", "mesh.rip_move", "mesh.extrude_vertices_move",
]);

const SKIP = /^(tool|prop|tab):/;

/** The operator that defines a skill: the last one that is not navigation, routine, or a setting. */
export function effectOp(ops: string[], g: Grounding): string | null {
  const core = ops.filter((o) => o && !g.nav_ops.includes(o) && !g.routine_ops.includes(o) && !SKIP.test(o));
  return core.at(-1) ?? ops.at(-1) ?? null;
}

/** The operator to use on this version: the same one, or its successor when it no longer exists there. */
export function resolve(L: Lookup, op: string | null, from: string | null | undefined, version: string): [string | null, Successor | null] {
  if (!op || !from || from === version) return [op, null];
  if (!L.where(op, version).missing) return [op, null];
  const s = L.successor(op, from, version);
  return s ? [s.op, s] : [op, null];
}

/** How a UI element differs between two versions: same, moved, renamed, new, gone. */
export function changeKind(o: Where | null, n: Where | null): string {
  if (!o || !n) return "same";
  if (n.missing) return "gone";
  if (o.missing) return "new";
  if ((o.label ?? "").toLowerCase() !== (n.label ?? "").toLowerCase()) return "renamed";
  if ((o.paths[0] ?? "").toLowerCase() !== (n.paths[0] ?? "").toLowerCase()) return "moved";
  return "same";
}

const KEYWORDS: Record<string, string> = {
  "middle mouse": "MIDDLEMOUSE", "middle click": "MIDDLEMOUSE", "scroll wheel click": "MIDDLEMOUSE", mmb: "MIDDLEMOUSE",
  "scroll wheel": "WHEELINMOUSE", "mouse wheel": "WHEELINMOUSE", scroll: "WHEELINMOUSE",
  "left click": "LEFTMOUSE", "left mouse": "LEFTMOUSE", lmb: "LEFTMOUSE", "right click": "RIGHTMOUSE", "right mouse": "RIGHTMOUSE",
  rmb: "RIGHTMOUSE", escape: "ESC", esc: "ESC", enter: "RET", return: "RET", tab: "TAB", space: "SPACE",
  spacebar: "SPACE", delete: "DEL", del: "DEL", backspace: "BACK_SPACE", tilde: "ACCENT_GRAVE", "`": "ACCENT_GRAVE",
  grave: "ACCENT_GRAVE", "numpad period": "NUMPAD_PERIOD", "numpad .": "NUMPAD_PERIOD", period: "PERIOD",
  home: "HOME", f12: "F12", f2: "F2", f3: "F3", "\\": "BACK_SLASH", backslash: "BACK_SLASH", "[": "LEFT_BRACKET",
  "]": "RIGHT_BRACKET", ";": "SEMI_COLON", "up arrow": "UP_ARROW", "down arrow": "DOWN_ARROW", "left arrow": "LEFT_ARROW",
  "right arrow": "RIGHT_ARROW", "page up": "PAGE_UP", "page down": "PAGE_DOWN", end: "END", "backspace key": "BACK_SPACE",
};
const DIGITS = ["ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE"];

/** 'Shift + Middle Mouse Button' / 'Numpad 1' / 'Ctrl+A' / 'G' -> [[EVENT, 'mods']] (alternatives split on or / , /). */
export function parseKeys(text: string | null | undefined): [string, string][] {
  const out: [string, string][] = [];
  for (const alt of String(text ?? "").split(/\s+or\s+|,|\//)) {
    let t = alt.trim().toLowerCase().replace(/control/g, "ctrl").replace(/command/g, "ctrl").replace(/cmd/g, "ctrl").replace(/ button/g, "").replace(/ key/g, "");
    t = t.replace(/\b(ctrl|shift|alt|cmd)\s*-\s*/g, "$1+");
    if (!t) continue;
    const mods = ["ctrl", "shift", "alt"].filter((m) => new RegExp(`\\b${m}\\b`).test(t)).sort();
    const rest = t.replace(/\b(ctrl|shift|alt|hold|press|down|and|click on|the)\b|\+/g, " ").trim().replace(/\s+/g, " ");
    let ev: string | undefined;
    const m = rest.match(/^numpad\s*(\d)/);
    if (m) ev = "NUMPAD_" + m[1];
    else if (KEYWORDS[rest]) ev = KEYWORDS[rest];
    else if (/^[a-z]$/.test(rest)) ev = rest.toUpperCase();
    else if (/^\d$/.test(rest)) ev = DIGITS[Number(rest)];
    else if (/^f\d{1,2}$/.test(rest)) ev = rest.toUpperCase();
    else ev = Object.entries(KEYWORDS).find(([k]) => rest.includes(k))?.[1];
    if (ev) out.push([ev, mods.join("+")]);
  }
  return out;
}

/**
 * Menu navigation a tutorial spells out step by step ("Open the Mesh menu", "Choose Merge", "Select By Distance") is one
 * action: the action step takes this version's menu path that matches what the tutorial opened, and the navigation
 * steps before it are absorbed. -> index -> {absorbed} | {path}
 */
export function navigation(L: Lookup, g: Grounding, steps: Claim[], version: string): Map<number, { absorbed?: true; path?: string }> {
  const isAction = (x: Claim) => !!x.op && !g.routine_ops.includes(x.op) && !g.nav_ops.includes(x.op) && !g.menu_openers.includes(x.op);
  const last = (x: Claim) => norm(x.ui.at(-1) ?? "");
  const out = new Map<number, { absorbed?: true; path?: string }>();
  const chosen = new Map<number, string>();
  steps.forEach((s, j) => {
    if (!isAction(s)) return;
    const paths = L.where(resolve(L, s.op, s.version, version)[0]!, version).paths;
    if (!paths.length) return;
    const ctx = new Set(steps.slice(0, j + 1).flatMap((x) => x.ui.map(norm)));
    let best = paths[0];
    let bestScore = -Infinity;
    paths.forEach((p, i) => {
      const score = p.split(" › ").slice(0, -1).filter((c) => ctx.has(norm(c))).length * 1000 - i;
      if (score > bestScore) [best, bestScore] = [p, score];
    });
    if (s.variant && !norm(best).includes(norm(s.variant))) best = [...best.split(" › ").slice(0, -1), s.variant].join(" › ");
    chosen.set(j, best);
  });
  for (const j of [...chosen.keys()].sort((a, b) => b - a)) {
    if (out.get(j)?.absorbed) continue;
    out.set(j, { path: chosen.get(j) });
    const crumbs = new Set(chosen.get(j)!.split(" › ").slice(0, -1).map(norm));
    for (let i = j - 1; i >= 0; i--) {
      const x = steps[i];
      const same = !!x.op && resolve(L, x.op, x.version, version)[0] === resolve(L, steps[j].op, steps[j].version, version)[0];
      if ((crumbs.has(last(x)) && !same) || (x.op && g.menu_openers.includes(x.op) && i === j - 1)) {
        out.set(i, { absorbed: true });
        continue;
      }
      break;
    }
  }
  return out;
}

/** One line a person (or a computer-use agent) can follow on this version; null = nothing to do here. */
export function instruction(L: Lookup, g: Grounding, step: Claim, version: string, next?: Claim, prev?: Claim, pathHint?: string): string | null {
  let op = step.op;
  if (prev && op && prev.op === op && !g.menu_openers.includes(op)) {
    // the same operator twice in a row: the second step confirms the first
    const w = L.where(resolve(L, op, step.version, version)[0]!, version);
    return `Confirm with “${w.label ?? op}” if a confirmation appears`;
  }
  const psucc = prev?.op && !op ? resolve(L, prev.op, prev.version, version)[1] : null;
  if (psucc) return `${step.say ?? ""} (in ${version} this is done in the ${psucc.label} menu instead)`;
  if (op && g.menu_openers.includes(op) && next?.op) return version !== step.version ? null : (step.say ?? "");
  if (op && g.menu_openers.includes(op)) return step.keys ? `Press ${step.keys} to open the menu` : step.say;
  if (op === "object.mode_set" || op === "object.editmode_toggle")
    return (step.say ?? "").toLowerCase().includes("edit") ? "Make sure you are in Edit Mode (Tab toggles it)" : step.say;
  const old = op;
  let succ: Successor | null;
  [op, succ] = resolve(L, op, step.version, version);
  const w = op ? L.where(op, version) : null;
  const modal = (op && MODAL.has(op)) || (op ?? "").startsWith("transform.");
  let val = step.value ? (modal ? `, type ${step.value}` : ` and set it to ${step.value}`) : "";
  if (modal) val += ", then press Enter to confirm";
  if (!modal && op && g.confirm_ops.includes(op) && next?.op !== step.op) val += ", then confirm (click the button that appears)";
  const note = succ ? ` (${succ.label} replaces ${L.where(old!, step.version).label ?? old} here)` : "";
  if (!w || w.missing) return (step.say ?? "") + (op ? ` (not available in this version: ${op})` : "");
  if (succ?.key && step.action === "key") return `Press ${succ.key}${val}${note}`;
  if (step.action === "key" && (w.keys.length || w.via_keys.length)) {
    const said = parseKeys(step.keys).map(([key, mods]) => combo({ key, mods }));
    const key = said.find((k) => w.keys.includes(k)) ?? (w.keys.length ? w.keys : w.via_keys)[0];
    return `Press ${key}${val}${note}`;
  }
  if (w.paths.length) {
    const chosen = pathHint ?? w.paths[0];
    if (chosen.startsWith("Page bar › ")) return `Go to the ${chosen.split(" › ").at(-1)} page${val}${note}`;
    return `Open ${chosen}${val}${note}`;
  }
  if (w.via_keys.length) return `Press ${w.via_keys[0]}${val}${note}`;
  if (w.keys.length) return `Press ${w.keys[0]} (${w.label})${val}${note}`;
  return (step.say ?? op ?? "") + note;
}

/**
 * Which source's steps to show: the given source's (a tutorial shows its own steps, re-targeted); else a source made for
 * this very version; else the skill's default steps.
 */
function leadSteps(skill: Skill, claims: Map<string, Claim>, g: Grounding, version: string, source?: string | null): string[] {
  const grounded = (src: SkillSource) => src.steps.filter((x) => claims.get(x)?.op).length;
  if (source) {
    const src = skill.sources.find((x) => x.source === source);
    if (src?.steps.length) return src.steps;
  }
  const eff = effectOp(skill.ops, g);
  const directness = (src: SkillSource): number[] => {
    const st = src.steps.map((x) => claims.get(x));
    const ops = new Set(st.map((x) => x?.op).filter((o): o is string => !!o && !g.menu_openers.includes(o)));
    return [st.some((x) => x?.op === eff) ? 1 : 0, ops.size, grounded(src) / Math.max(st.length, 1), -st.length];
  };
  const native = skill.sources.filter((x) => x.version === version && grounded(x));
  if (native.length) {
    const cmp = (a: number[], b: number[]) => a.findIndex((v, i) => v !== b[i]);
    return native.reduce((best, x) => {
      const a = directness(x);
      const b = directness(best);
      const i = cmp(a, b);
      return i >= 0 && a[i] > b[i] ? x : best;
    }).steps;
  }
  return skill.steps;
}

/** A skill as steps for this version: each step's place now, and where it was in the version the source was made for. */
export function path(L: Lookup, g: Grounding, skill: Skill, claims: Map<string, Claim>, version: string, source?: string | null): PathStep[] {
  const ids = leadSteps(skill, claims, g, version, source).filter((x) => claims.has(x));
  const raw = ids.map((x) => claims.get(x)!);
  const nav = navigation(L, g, raw, version);
  const steps: PathStep[] = [];
  raw.forEach((s, i) => {
    if (nav.get(i)?.absorbed) return;
    const doText = instruction(L, g, s, version, raw[i + 1], i ? raw[i - 1] : undefined, nav.get(i)?.path);
    if (doText == null) return;
    const [op, succ] = resolve(L, s.op, s.version, version);
    let w = op ? L.where(op, version) : null;
    const hint = nav.get(i)?.path;
    if (w && hint) w = { ...w, paths: [hint, ...w.paths.filter((x) => x !== hint)] }; // the path the tutorial walked first
    const said = doText.match(/^Press (\S+)/);
    if (w && said && w.keys.includes(said[1])) w = { ...w, keys: [said[1], ...w.keys.filter((k) => k !== said[1])] };
    const orig = s.op && s.version !== version ? L.where(s.op, s.version) : null;
    const routine = !!s.op && (g.routine_ops.includes(s.op) || g.nav_ops.includes(s.op));
    steps.push({
      say: s.say,
      do: doText,
      op,
      label: w?.label ?? null,
      replaced: succ,
      where: w,
      was: orig ? { version: s.version, label: orig.label, paths: orig.paths.slice(0, 1), via_keys: orig.via_keys.slice(0, 1) } : null,
      routine,
      changed: !!(orig && w && !(s.op && g.routine_ops.includes(s.op)) && changeKind(orig, w) !== "same"),
      missing: !!w?.missing,
      value: s.value,
      t: s.t,
      source: s.source,
    });
  });
  return steps;
}
