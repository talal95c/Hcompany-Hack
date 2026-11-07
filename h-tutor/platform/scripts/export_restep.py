"""Exports a ReStep knowledge graph for the Rio platform.

For each skill: its search words (ReStep's own index), sources, proofs, and its
steps re-targeted to EVERY version of the app by ReStep's `path()`. For each
tutorial: its skills, in order. The platform serves this file as is and never
runs ReStep, so the Worker stays a small search over precomputed data.

    uv run --python 3.11 --with httpx --with openai --with python-dotenv \
        python platform/scripts/export_restep.py <restep checkout> platform/data/blender.json [blender]
"""
import json
import os
import sys
import time
from pathlib import Path

restep = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
app_id = sys.argv[3] if len(sys.argv) > 3 else "blender"
sys.path.insert(0, str(restep))
os.chdir(restep)

import apps  # noqa: E402
from kg import api as kg, store  # noqa: E402

# macOS bundle ids, so Rio shows the installed app's icon.
BUNDLE_IDS = {"blender": "org.blenderfoundation.blender"}
# Version numbers compare number by number on the platform: Blender's "2.8"
# means 2.80, which must sort after 2.79.
COVERS_FROM = {("blender", "2.8"): "2.80"}

meta = apps.app_meta(app_id)
versions = apps.versions(app_id)
g = store.load(app_id)
docs, _ = kg._search_index(app_id, g.get("updated"))


def step(s):
    w = s.get("where") or {}
    return {
        "do": s["do"],
        "label": s.get("label"),
        "paths": (w.get("paths") or [])[:2],
        "keys": (w.get("keys") or [])[:2],
        "was": s.get("was"),
        "changed": bool(s.get("changed")),
        "missing": bool(s.get("missing")),
        "replaced": s.get("replaced"),
        "routine": bool(s.get("routine")),
        "t": s.get("t"),
        "source": s.get("source"),
    }


skills, failed = {}, []
for pid, p in g["paths"].items():
    words, intent = docs[pid]
    steps = {}
    for v in versions:
        try:
            steps[v] = [step(s) for s in kg.path(app_id, pid, v)["steps"]]
        except Exception as e:  # one broken skill must not stop the export
            failed.append(f"{pid}@{v}: {type(e).__name__}: {e}")
    if not steps:
        continue
    skills[pid] = {
        "intent": p["intent"],
        "words": sorted(words),
        "intent_words": sorted(intent),
        "sources": [{**kg._src(g, s["source"]), "t": s.get("t"), "end": s.get("end")} for s in p["sources"]],
        "proofs": {v: x.get("status") for v, x in (p.get("proofs") or {}).items()},
        "steps": steps,
    }

tutorials = {
    tid: {
        "title": t["title"],
        "recorded_on": t.get("version"),
        "source": kg._src(g, t["source"]),
        "paths": [x for x in t["paths"] if x in skills],
    }
    for tid, t in g["tutorials"].items()
}

data = {
    "format": 1,
    "exported_at": int(time.time()),
    "app": {
        "id": app_id,
        "name": meta["name"],
        "bundle_id": BUNDLE_IDS.get(app_id),
        "versions": [{"id": v["id"], "label": v.get("label"), "covers_from": COVERS_FROM.get((app_id, v.get("covers_from", "0")), v.get("covers_from", "0"))}
                     for v in meta.get("versions", [])],
        "current_version": apps.current_version(app_id),
    },
    "skills": skills,
    "tutorials": {k: v for k, v in tutorials.items() if v["paths"]},
}
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
print(f"{app_id}: {len(skills)} skills, {len(data['tutorials'])} tutorials, {len(versions)} versions "
      f"-> {out} ({out.stat().st_size // 1024} KB)")
for f in failed:
    print("  skipped", f)
