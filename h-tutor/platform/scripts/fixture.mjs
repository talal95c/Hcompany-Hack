// Writes data/fixture-blender.json: a two-skill knowledge base for local tests.
import { writeFileSync } from "node:fs";
const step = (d, extra = {}) => ({ do: d, paths: [], keys: [], changed: false, missing: false, routine: false, ...extra });
const data = {
  format: 1,
  app: { id: "blender", name: "Blender", bundle_id: "org.blenderfoundation.blender",
    versions: [{ id: "2.79b", label: "Blender 2.79b", covers_from: "0" }, { id: "5.2.3", label: "Blender 5.2.3 LTS", covers_from: "2.80" }],
    current_version: "5.2.3" },
  skills: {
    p_merge: { intent: "Remove duplicate vertices", words: ["remove", "duplicate", "vertices", "merge", "distance", "doubles", "clean"],
      intent_words: ["remove", "duplicate", "vertices"],
      sources: [{ id: "yt_a", title: "Clean meshes", kind: "video", url: "https://www.youtube.com/watch?v=nIoXOplUvAw", version: "2.79b", language: "en", t: 42.5 }],
      proofs: { "5.2.3": "PASS" },
      steps: { "2.79b": [step("W › Remove Doubles")],
        "5.2.3": [step("Press Tab to enter Edit Mode", { routine: true }),
          step("Mesh › Clean Up › Merge by Distance", { changed: true, was: { version: "2.79b", label: "Remove Doubles", paths: [], via_keys: [] } })] } },
    p_bevel: { intent: "Bevel the edges", words: ["bevel", "edges", "round", "corners"], intent_words: ["bevel", "edges"],
      sources: [], proofs: {}, steps: { "5.2.3": [step("Edge › Bevel Edges (Ctrl+B)")] } },
  },
  tutorials: { t_yt_a: { title: "Clean meshes", recorded_on: "2.79b",
    source: { id: "yt_a", title: "Clean meshes", kind: "video", url: "https://www.youtube.com/watch?v=nIoXOplUvAw", version: "2.79b", language: "en" },
    paths: ["p_merge", "p_bevel"] } },
};
writeFileSync(new URL("../data/fixture-blender.json", import.meta.url), JSON.stringify(data));
console.log("data/fixture-blender.json");
