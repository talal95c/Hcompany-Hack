// The atomic layer of ReStep's graphs, ported from restep/kg/inventory.py:
// what the software itself says its UI is, per version. An operator (mesh.remove_doubles,
// resolve:menu/edit/undo) is the version-independent identity of an action; its label,
// menu paths and shortcuts are what change between versions.
//
// Pure functions over parsed files, so the converter (Node) and the Worker share them.

export const EDITORS: Record<string, string> = {
  VIEW3D: "3D Viewport", TOPBAR: "Top bar", IMAGE: "Image Editor", NODE: "Node Editor", OUTLINER: "Outliner",
  PROPERTIES: "Properties", SEQUENCER: "Video Sequencer", GRAPH: "Graph Editor", DOPESHEET: "Dope Sheet",
  TEXT: "Text Editor", INFO: "Info", CLIP: "Movie Clip", NLA: "NLA", FILEBROWSER: "File Browser",
};
export const KEYNAMES: Record<string, string> = {
  LEFTMOUSE: "Left click", RIGHTMOUSE: "Right click", MIDDLEMOUSE: "Middle click", SPACE: "Space", TAB: "Tab",
  RET: "Enter", DEL: "Delete", ESC: "Esc", ACCENT_GRAVE: "`", ONE: "1", TWO: "2", THREE: "3", FOUR: "4",
  FIVE: "5", SIX: "6", SEVEN: "7", EIGHT: "8", NINE: "9", ZERO: "0", NUMPAD_PERIOD: "Numpad .",
  PERIOD: ".", COMMA: ",", SLASH: "/", MINUS: "-", PLUS: "+", BACK_SLASH: "\\",
  LEFT_BRACKET: "[", RIGHT_BRACKET: "]", SEMI_COLON: ";", QUOTE: "'", UP_ARROW: "Up", DOWN_ARROW: "Down",
  LEFT_ARROW: "Left", RIGHT_ARROW: "Right", PAGE_UP: "Page Up", PAGE_DOWN: "Page Down", END: "End",
};
const TABS: Record<string, string> = {
  render: "Render", output: "Output", view_layer: "View Layer", render_layer: "Render Layers", scene: "Scene",
  world: "World", object: "Object", modifier: "Modifiers", particle: "Particles", physics: "Physics",
  constraint: "Object Constraints", data: "Object Data", material: "Material", texture: "Texture", bone: "Bone",
  shaderfx: "Effects", collection: "Collection", tool: "Tool", bone_constraint: "Bone Constraints",
};

/** Same as restep's `norm`: lowercase, anything but a-z0-9 becomes a space. */
export const norm = (s: unknown) =>
  String(s ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

const title = (s: string) => s.toLowerCase().replace(/(^|[^a-z])([a-z])/g, (_, a, b) => a + b.toUpperCase());

export interface KeyItem {
  key?: string;
  mods?: string;
  value?: string | null;
  keymap?: string;
  op?: string;
  props?: { name?: string } & Record<string, unknown>;
}

export function combo(it: { key?: string; mods?: string }): string {
  const key = it.key ?? "";
  const k = KEYNAMES[key] ?? title(key.replace("NUMPAD_", "Numpad "));
  const m = (it.mods ?? "")
    .split("+")
    .filter(Boolean)
    .map((x) => (x !== "oskey" ? x.charAt(0).toUpperCase() + x.slice(1) : "Cmd"));
  return [...m, k].join("+");
}

type MenuItem = { kind: string; ref: string; text?: string | null };
export type Menus = Record<string, { label?: string | null; items: MenuItem[] }>;
type Panel = { label?: string; parent?: string; space?: string; region?: string; category?: string; context?: string; items?: MenuItem[] };

/** Raw files of one app version, as restep stores them. */
export interface VersionFiles {
  menus?: Menus; // apps/<app>/menus/menus_<v>.json
  oplabels?: Record<string, string>; // apps/<app>/menus/oplabels_<v>.json
  ui?: { menus: Menus; op_labels: Record<string, string>; panels: Record<string, Panel> }; // kb/<app>/ui_<v>.json
  keymaps?: KeyItem[]; // kb/<app>/keymaps_<v>.json items
  generic?: { ops: Record<string, { label: string; paths?: string[][]; kind?: string }> }; // apps/<app>/inventory_<v>.json
}

export interface OpPath {
  path: string[];
  menu?: string;
  panel?: string;
  editor: string;
}
export interface Op {
  op: string;
  label: string;
  kind?: string;
  paths: OpPath[];
  menus: string[];
  keys: { keys: string; context?: string }[];
  via_keys: { keys: string; context?: string; then: string; menu: string }[];
}
export interface Inventory {
  ops: Record<string, Op>;
  menus: Record<string, { label?: string | null; keys: { keys: string; context?: string }[] }>;
  rawMenus: Menus;
  keymaps: KeyItem[];
}

/** Menus: bundled UI scripts UNION the scan inside the running software; labels: the software's own registry first. */
function files(f: VersionFiles) {
  const menus: Menus = structuredClone(f.menus ?? {});
  let labels: Record<string, string> = { ...(f.oplabels ?? {}) };
  let panels: Record<string, Panel> = {};
  if (f.ui) {
    for (const [mid, m] of Object.entries(f.ui.menus)) {
      const cur = (menus[mid] ??= { label: m.label, items: [] });
      const seen = new Set(cur.items.map((i) => `${i.kind}|${i.ref}`));
      cur.items.push(...m.items.filter((i) => (i.kind === "op" || i.kind === "menu") && !seen.has(`${i.kind}|${i.ref}`)));
      cur.label = cur.label || m.label;
    }
    labels = { ...labels, ...Object.fromEntries(Object.entries(f.ui.op_labels).filter(([, v]) => v)) };
    panels = f.ui.panels;
  }
  return { menus, labels, keys: f.keymaps ?? [], panels };
}

function panelChain(pid: string, panels: Record<string, Panel>, depth = 0): string[] {
  const p = panels[pid];
  if (!p || depth > 4) return [];
  if (p.parent) return [...panelChain(p.parent, panels, depth + 1), p.label ?? ""];
  const { space, region } = p;
  let head: string[];
  if (space === "PROPERTIES") head = ["Properties", TABS[p.context ?? ""] ?? title((p.context ?? "").replace(/_/g, " "))];
  else if (space === "VIEW_3D" && region === "TOOLS") head = ["Tool Shelf (T)", ...(p.category ? [p.category] : [])];
  else if (space === "VIEW_3D" && region === "UI") head = ["Sidebar (N)", ...(p.category ? [p.category] : [])];
  else head = [EDITORS[(space ?? "").replace(/_/g, "")] ?? title((space ?? "").replace(/_/g, " "))];
  return [...head, p.label ?? ""];
}

const propLabel = (ref: string, text?: string | null) =>
  text || title(ref.split(".").pop()!.replace(/_/g, " ")).replace("Use ", "");

const same = (a: string[], b: string[]) => a.length === b.length && a.every((x, i) => x === b[i]);

/** Apps without an operator registry (DaVinci Resolve): the inventory scanned from the official manual. */
function genericInventory(f: VersionFiles): Inventory {
  const ops: Record<string, Op> = {};
  for (const [op, d] of Object.entries(f.generic!.ops)) {
    ops[op] = {
      op,
      label: d.label,
      kind: d.kind ?? "menu",
      menus: [],
      keys: [],
      via_keys: [],
      paths: (d.paths ?? [])
        .filter((p) => p.length && !p.some((x) => /keyboard shortcut|^menu$/i.test(x)))
        .map((p) => ({ path: p, menu: p[0] ?? "", editor: p[0] ?? "" })),
    };
  }
  for (const it of f.keymaps ?? []) {
    if (it.op && ops[it.op] && it.key) ops[it.op].keys.push({ keys: combo(it), context: it.keymap });
  }
  return { ops, menus: {}, rawMenus: {}, keymaps: f.keymaps ?? [] };
}

export function inventory(f: VersionFiles): Inventory {
  if (f.generic) return genericInventory(f);
  const { menus, labels, keys, panels } = files(f);
  const parents = new Map<string, [string, string | null | undefined][]>();
  for (const [mid, m] of Object.entries(menus)) {
    for (const it of m.items) if (it.kind === "menu") (parents.get(it.ref) ?? parents.set(it.ref, []).get(it.ref)!).push([mid, it.text]);
  }
  const labelOf = (mid: string, text?: string | null) => text || menus[mid]?.label || "";

  const chains = (mid: string, depth = 0, seen: string[] = []): string[][] => {
    if (depth > 6 || seen.includes(mid)) return [[]];
    const ps = parents.get(mid) ?? [];
    if (!ps.length) {
      const low = mid.toLowerCase();
      if (low.includes("context_menu") || low.includes("specials")) return low.includes("context_menu") ? [["Right-click menu"]] : [[labelOf(mid)]];
      const lab = labelOf(mid);
      return lab ? [[lab]] : [[]];
    }
    const out: string[][] = [];
    for (const [p, text] of ps) for (const c of chains(p, depth + 1, [...seen, mid])) out.push([...c, labelOf(mid, text)]);
    return out;
  };

  const menuKeys = new Map<string, { keys: string; context?: string }[]>();
  const opKeys = new Map<string, { keys: string; context?: string }[]>();
  for (const it of keys) {
    if (["wm.call_menu", "wm.call_menu_pie", "wm.call_panel"].includes(it.op ?? "") && it.props?.name) {
      (menuKeys.get(it.props.name) ?? menuKeys.set(it.props.name, []).get(it.props.name)!).push({ keys: combo(it), context: it.keymap });
    } else if (it.op && ["PRESS", "CLICK", null, undefined].includes(it.value as string)) {
      (opKeys.get(it.op) ?? opKeys.set(it.op, []).get(it.op)!).push({ keys: combo(it), context: it.keymap });
    }
  }

  const ops: Record<string, Op> = {};
  const blank = (op: string, label: string): Op => ({ op, label, paths: [], menus: [], keys: [], via_keys: [] });
  for (const [mid, m] of Object.entries(menus)) {
    const head = mid.split("_MT_")[0];
    const editor = EDITORS[head] ?? title(head);
    for (const it of m.items) {
      if (it.kind !== "op") continue;
      const op = it.ref;
      const lab = it.text || labels[op] || op;
      const d = (ops[op] ??= blank(op, labels[op] || lab));
      for (const c of chains(mid)) {
        const path = [...c.filter(Boolean), lab];
        if (!d.paths.some((p) => same(p.path, path))) d.paths.push({ path, menu: mid, editor });
      }
      d.menus.push(mid);
      for (const mk of menuKeys.get(mid) ?? []) d.via_keys.push({ keys: mk.keys, context: mk.context, then: lab, menu: labelOf(mid) });
    }
  }
  for (const [pid, pnl] of Object.entries(panels)) {
    const chain = panelChain(pid, panels).filter(Boolean);
    const editor = chain[0] ?? "Properties";
    for (const it of pnl.items ?? []) {
      let op: string;
      let lab: string;
      if (it.kind === "op") [op, lab] = [it.ref, it.text || labels[it.ref] || it.ref];
      else if (it.kind === "prop") [op, lab] = ["prop:" + it.ref, propLabel(it.ref, it.text)];
      else continue;
      const d = (ops[op] ??= blank(op, op.startsWith("prop:") ? lab : labels[op] || lab));
      const path = [...chain, lab];
      if (!d.paths.some((p) => same(p.path, path))) d.paths.push({ path, panel: pid, editor });
    }
  }
  for (const [ctx, tab] of Object.entries(TABS)) {
    if (Object.values(panels).some((p) => p.space === "PROPERTIES" && p.context === ctx))
      ops["tab:" + ctx] = { ...blank("tab:" + ctx, tab), paths: [{ path: ["Properties", tab + " tab"], editor: "Properties" }] };
  }
  for (const k of Object.keys(ops)) if (k.startsWith("prop:NoneType")) delete ops[k];
  for (const [op, ks] of opKeys) (ops[op] ??= blank(op, labels[op] || op)).keys = ks.slice(0, 6);
  for (const [op, lab] of Object.entries(labels)) ops[op] ??= blank(op, lab);
  for (const [mid, mks] of menuKeys) {
    // a menu drawn in C, named after its operator: M opens OBJECT_MT_move_to_collection
    const i = mid.indexOf("_MT_");
    const op = i >= 0 ? `${mid.slice(0, i).toLowerCase()}.${mid.slice(i + 4)}` : null;
    if (op && ops[op] && !ops[op].keys.length) ops[op].keys = mks.slice(0, 3).map((mk) => ({ keys: mk.keys, context: mk.context }));
  }
  for (const d of Object.values(ops)) {
    // the operator's own label first, the main editors first, short paths first
    const rank = (p: OpPath) => [!["3D Viewport", "Properties"].includes(p.editor) ? 1 : 0, norm(p.path.at(-1)) !== norm(d.label) ? 1 : 0, p.path.length];
    d.paths.sort((a, b) => {
      const ra = rank(a);
      const rb = rank(b);
      return ra[0] - rb[0] || ra[1] - rb[1] || ra[2] - rb[2];
    });
    d.paths = d.paths.slice(0, 6);
  }
  return {
    ops,
    menus: Object.fromEntries(Object.entries(menus).map(([mid, m]) => [mid, { label: m.label, keys: menuKeys.get(mid) ?? [] }])),
    rawMenus: menus,
    keymaps: keys,
  };
}

/** How to reach an operator: its label, up to 3 menu paths, direct shortcuts, and menu shortcuts. */
export interface Where {
  op: string;
  label: string | null;
  paths: string[];
  keys: string[];
  via_keys: string[];
  missing: boolean;
}

export function where(inv: Inventory, op: string): Where {
  const d = inv.ops[op];
  if (!d) return { op, label: null, paths: [], keys: [], via_keys: [], missing: true };
  return {
    op,
    label: d.label,
    paths: d.paths.slice(0, 3).map((p) => p.path.join(" › ")),
    keys: [...new Set(d.keys.map((k) => k.keys))].slice(0, 3),
    via_keys: [...new Set(d.via_keys.filter((k) => k.keys.toLowerCase() !== "app").map((k) => `${k.keys} › ${k.then}`))].slice(0, 3),
    missing: false,
  };
}

/** normalized label -> operators (menu items, labels, app pages, properties, tabs): grounding words people use. */
export function labelIndex(inv: Inventory): Map<string, Set<string>> {
  const idx = new Map<string, Set<string>>();
  const add = (k: string, op: string) => k && (idx.get(k) ?? idx.set(k, new Set()).get(k)!).add(op);
  for (const [op, d] of Object.entries(inv.ops)) {
    add(norm(d.label), op);
    for (const p of d.paths) {
      add(norm(p.path.at(-1)), op);
      if (p.path.length >= 2) add(norm(p.path.slice(-2).join(" ")), op);
    }
    if (d.kind === "page") {
      const name = d.paths[0]?.path.at(-1) ?? d.label;
      for (const a of [name, `${name} tab`, `${name} page`, `${name} room`, `${name} workspace`, `page ${name}`, `onglet ${name}`]) add(norm(a), op);
    }
    if (op.startsWith("prop:")) add(norm(op.split(".").pop()!.replace(/_/g, " ")), op);
    if (op.startsWith("tab:")) for (const a of [d.label, `${d.label} tab`, `${d.label} properties`]) add(norm(a), op);
  }
  return idx;
}

const MOUSE_EVENTS = ["MOUSE", "WHEEL", "TWEAK", "TRACKPAD", "NDOF"];
const MENU_CALLS = ["wm.call_menu", "wm.call_menu_pie", "wm.call_panel"];

function keyIndex(inv: Inventory) {
  const idx = new Map<string, { op?: string; context?: string; props?: KeyItem["props"] }[]>();
  for (const it of inv.keymaps) {
    if (!it.key) continue;
    const k = `${it.key}|${(it.mods ?? "").split("+").filter(Boolean).sort().join("+")}`;
    (idx.get(k) ?? idx.set(k, []).get(k)!).push({ op: it.op, context: it.keymap, props: it.props });
  }
  return idx;
}

export interface Successor {
  op: string;
  label: string;
  why: string;
  key: string | null;
}

/**
 * An operator missing from the new version: what took its place, from the software's own evidence.
 * 1. the same shortcut in the same keymap context now runs another operator (a menu call resolves to its operator);
 * 2. otherwise an operator of the same module whose name shares most words.
 */
export function successor(oldInv: Inventory, newInv: Inventory, op: string): Successor | null {
  const neu = newInv.ops;
  if (neu[op] || /^(tool|prop|tab):/.test(op)) return null;
  const ko = keyIndex(oldInv);
  const kn = keyIndex(newInv);
  const votes = new Map<string, number>();
  const why = new Map<string, [string, string | null]>();
  for (const [k, its] of ko) {
    const [ev, mods] = k.split("|");
    if (MOUSE_EVENTS.some((m) => ev.includes(m)) || mods.includes("oskey")) continue;
    for (const it of its) {
      if (it.op !== op) continue;
      for (const x of kn.get(k) ?? []) {
        if (x.context !== it.context) continue;
        let c: string | null | undefined = x.op;
        if (c && MENU_CALLS.includes(c) && x.props?.name) {
          const mid = x.props.name;
          const sep = mid.includes("_MT_") ? "_MT_" : "_PT_";
          const i = mid.indexOf(sep);
          const guess = i >= 0 ? `${mid.slice(0, i).toLowerCase()}.${mid.slice(i + 4)}` : null;
          const items = (newInv.rawMenus[mid]?.items ?? []).filter((y) => y.kind === "op").map((y) => y.ref);
          c = guess && neu[guess] ? guess : new Set(items).size === 1 ? items[0] : null;
        }
        if (c && neu[c] && c !== op) {
          votes.set(c, (votes.get(c) ?? 0) + 1);
          const key = [...mods.split("+").filter(Boolean).map((m) => m.charAt(0).toUpperCase() + m.slice(1)), KEYNAMES[ev] ?? ev].join("+");
          why.set(c, [`same shortcut ${key} in ${it.context}`, key]);
        }
      }
    }
  }
  if (!votes.size) {
    const [mod, name = ""] = op.split(/\.(.*)/s);
    const words = new Set(name.split("_"));
    let best: [number, string | null] = [0, null];
    for (const o of Object.keys(neu)) {
      const [m2, n2 = ""] = o.split(/\.(.*)/s);
      if (m2 !== mod) continue;
      const w2 = new Set(n2.split("_"));
      const inter = [...words].filter((w) => w2.has(w)).length;
      const score = inter / new Set([...words, ...w2]).size;
      // Python's max over (score, op): ties go to the greater name
      if (score > best[0] || (score === best[0] && best[1] !== null && o > best[1])) best = [score, o];
    }
    if (best[0] >= 0.5 && best[1]) {
      votes.set(best[1], 1);
      why.set(best[1], ["same module, closest name", null]);
    }
  }
  if (!votes.size) return null;
  const c = [...votes.entries()].sort((a, b) => b[1] - a[1])[0][0];
  return { op: c, label: neu[c].label, why: why.get(c)![0], key: why.get(c)![1] };
}
