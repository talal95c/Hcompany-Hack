import assert from "node:assert/strict";
import { test } from "node:test";
import { type AppData, listTutorials, resolveApps, resolveVersion, rioTutorial, search } from "../src/kb.ts";

const step = (d: string, extra = {}) => ({ do: d, paths: [], keys: [], changed: false, missing: false, routine: false, ...extra });

const blender: AppData = {
  format: 1,
  app: {
    id: "blender",
    name: "Blender",
    bundle_id: "org.blenderfoundation.blender",
    versions: [
      { id: "2.79b", label: "Blender 2.79b", covers_from: "0" },
      { id: "5.2.3", label: "Blender 5.2.3 LTS", covers_from: "2.80" },
    ],
    current_version: "5.2.3",
  },
  skills: {
    p_merge: {
      intent: "Remove duplicate vertices",
      words: ["remove", "duplicate", "vertices", "merge", "distance", "doubles", "clean"],
      intent_words: ["remove", "duplicate", "vertices"],
      sources: [{ id: "yt_a", title: "Clean meshes", kind: "video", url: "https://youtu.be/a", version: "2.79b", language: "en", t: 42.5 }],
      proofs: { "5.2.3": "PASS" },
      steps: {
        "2.79b": [step("Specials › Remove Doubles")],
        "5.2.3": [
          step("Press Tab to enter Edit Mode", { routine: true }),
          step("Mesh › Clean Up › Merge by Distance", { changed: true, was: { version: "2.79b", label: "Remove Doubles", paths: [], via_keys: [] } }),
        ],
      },
    },
    p_bevel: {
      intent: "Bevel the edges",
      words: ["bevel", "edges", "round", "corners"],
      intent_words: ["bevel", "edges"],
      sources: [],
      proofs: {},
      steps: { "5.2.3": [step("Edge › Bevel Edges")] },
    },
  },
  tutorials: {
    t_yt_a: {
      title: "Clean meshes",
      recorded_on: "2.79b",
      source: { id: "yt_a", title: "Clean meshes", kind: "video", url: "https://youtu.be/a", version: "2.79b", language: "en" },
      paths: ["p_merge", "p_bevel"],
    },
  },
};

test("versions: the newest version covering the learner's", () => {
  assert.deepEqual(resolveVersion(blender.app, "Blender 4.2"), { id: "5.2.3", requested: "4.2", exact: false });
  assert.deepEqual(resolveVersion(blender.app, "5.2"), { id: "5.2.3", requested: "5.2", exact: true });
  assert.equal(resolveVersion(blender.app, "2.79").id, "2.79b");
  assert.deepEqual(resolveVersion(blender.app, null), { id: "5.2.3", requested: null, exact: false });
});

test("apps: free-text names match, unknown apps match nothing", () => {
  assert.equal(resolveApps([blender], "Blender 4.2").length, 1);
  assert.equal(resolveApps([blender], "blend").length, 1);
  assert.equal(resolveApps([blender], "Figma").length, 0);
  assert.equal(resolveApps([blender], "").length, 1);
});

test("search: finds a renamed operator by its old name, re-targeted", () => {
  const [hit] = search([blender], ["remove doubles"], { app: "Blender 4.2" });
  assert.equal(hit.id, "p_merge");
  assert.equal(hit.version.id, "5.2.3");
  assert.equal(hit.proof, "PASS");
  assert.match(hit.steps[1].do, /Merge by Distance/);
});

test("search: plural matches, intent words weigh more, empty for nothing", () => {
  assert.equal(search([blender], ["bevels"])[0].id, "p_bevel");
  assert.equal(search([blender], ["xyzzy"]).length, 0);
  assert.equal(search([blender], ["merge"], { app: "Figma" }).length, 0);
});

test("search: French words fold accents, English keywords rescue them", () => {
  assert.equal(search([blender], ["arrondir les bords"]).length, 0);
  assert.equal(search([blender], ["arrondir les bords", "bevel edges"])[0].id, "p_bevel");
});

test("tutorials: listed with Rio ids, converted to milestones", () => {
  const [s] = listTutorials([blender]);
  assert.equal(s.id, "rio:blender:t_yt_a");
  assert.equal(s.milestones, 2);
  const t = rioTutorial([blender], s.id, "Blender 4.2")!;
  assert.equal(t.milestones.length, 2);
  assert.equal(t.milestones[0].goal, "Remove duplicate vertices");
  assert.deepEqual(t.milestones[0].hints, ['Mesh › Clean Up › Merge by Distance (changed: it was "Remove Doubles" in 2.79b)']);
  assert.equal(t.milestones[0].video_at, 42);
  assert.equal(rioTutorial([blender], "rio:blender:nope"), null);
  assert.equal(rioTutorial([blender], "finder-new-folder"), null);
});

test("search: filler words never match on their own", () => {
  assert.equal(search([blender], ["configure the VPN on the printer"]).length, 0);
  assert.equal(search([blender], ["comment supprimer les doublons"]).length, 0);
});

test("search: one shared word out of many is not a match", () => {
  assert.equal(search([blender], ["vpn printer configure network edges"]).length, 0);
  assert.equal(search([blender], ["bevel edges tutorial"])[0].id, "p_bevel");
});
