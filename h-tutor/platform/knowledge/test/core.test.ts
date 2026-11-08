// The ported core against facts ReStep documents (needs a ReStep checkout: RESTEP=<path>).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { where, successor } from "../src/core/inventory.ts";
import { type Claim, type Grounding, type Lookup, type Skill, path } from "../src/core/retarget.ts";
import { loadInventory, versions } from "../scripts/restep-files.ts";

const root = process.env.RESTEP;
const skip = !root && "set RESTEP to a ReStep checkout";

test("Remove Doubles (2.79) is Merge by Distance in Mesh › Clean Up (5.2)", { skip }, () => {
  const old = loadInventory(root!, "blender", "2.79b");
  const now = loadInventory(root!, "blender", "5.2.3");
  const w = where(now, "mesh.remove_doubles");
  assert.equal(w.label, "Merge by Distance");
  assert.ok(w.paths.some((p) => p.includes("Clean Up › Merge by Distance")), w.paths.join(" | "));
  assert.equal(where(old, "mesh.remove_doubles").label, "Remove Doubles");
});

test("M in Object Mode: Move to Layer (2.79) became Move to Collection", { skip }, () => {
  const s = successor(loadInventory(root!, "blender", "2.79b"), loadInventory(root!, "blender", "5.2.3"), "object.move_to_layer");
  assert.equal(s?.op, "object.move_to_collection");
  assert.match(s!.why, /same shortcut M/);
});

test("a 2.79 skill re-targeted to 5.2.3, every step placed", { skip }, () => {
  const g = JSON.parse(readFileSync(join(root!, "kb/blender/graph.json"), "utf8"));
  const meta = JSON.parse(readFileSync(join(root!, "apps/blender/app.json"), "utf8"));
  const invs = new Map(versions(meta).map((v) => [v, loadInventory(root!, "blender", v)]));
  const L: Lookup = {
    where: (op, v) => where(invs.get(v)!, op),
    successor: (op, from, to) => successor(invs.get(from)!, invs.get(to)!, op),
  };
  const gr: Grounding = { nav_ops: [], routine_ops: [], menu_openers: [], confirm_ops: [], ...meta.grounding };
  const [pid, p] = Object.entries<any>(g.paths).find(([, p]) => p.ops.includes("mesh.remove_doubles"))!;
  const skill: Skill = { id: pid, intent: p.intent, ops: p.ops, steps: p.steps, sources: p.sources };
  const claims = new Map<string, Claim>(Object.values<any>(g.steps).map((s) => [s.id, { ...s, ui: s.ui ?? [] }]));
  const steps = path(L, gr, skill, claims, "5.2.3");
  console.log(p.intent, "->", steps.map((s) => s.do));
  assert.ok(steps.some((s) => /Merge by Distance/.test(s.do) || /Merge by Distance/.test(s.label ?? "")));
});
