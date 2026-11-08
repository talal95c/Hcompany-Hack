// Grounding steps of an internal tool on the inventory its own docs give (no Holo call).
import assert from "node:assert/strict";
import { test } from "node:test";
import { atomsFromSteps, ground, view } from "../src/core/ground.ts";

const steps = [
  { say: "Open Orders › All orders", action: "click", ui: ["Orders", "All orders"], keys: null },
  { say: "Click Actions › Mark as shipped or press Ctrl+Shift+S", action: "click", ui: ["Actions", "Mark as shipped"], keys: "Ctrl+Shift+S" },
  { say: "Click Confirm refund", action: "click", ui: ["Confirm refund"], keys: null },
  { say: "Check the customer's email address and click Send", action: "click", ui: ["Send"], keys: null },
  { say: "Paste the tracking number in Tracking number and click Confirm", action: "set", ui: ["Tracking number"], keys: null, value: "1Z999" },
];
const v = view(atomsFromSteps("acme-comptoir", steps));

test("the docs are the inventory: every UI chain becomes an element, with its shortcut", () => {
  const shipped = v.ops.get("acme-comptoir:ui/actions_mark_as_shipped")!;
  assert.deepEqual(shipped.paths, ["Actions › Mark as shipped"]);
  assert.deepEqual(shipped.keys, ["Ctrl+Shift+S"]);
});

test("steps ground on those elements; a back-office 'click Confirm' or 'click Send' is an action", () => {
  for (const s of steps) {
    const [op, conf] = ground(v, s);
    assert.ok(op, `ungrounded: ${s.say}`);
    assert.ok(conf >= 0.5);
  }
});

test("a shortcut alone finds its element", () => {
  const [op] = ground(v, { say: "Press Ctrl+Shift+S", action: "key", ui: [], keys: "Ctrl+Shift+S" });
  assert.equal(op, "acme-comptoir:ui/actions_mark_as_shipped");
});

test("ReStep's modal rule still holds: an axis key inside a transform is not an action", () => {
  assert.deepEqual(ground(v, { say: "Lock the movement to an axis", action: "key", ui: [], keys: "X, Y or Z" }), [null, 0, null]);
});
