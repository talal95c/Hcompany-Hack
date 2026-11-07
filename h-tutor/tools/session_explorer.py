#!/usr/bin/env python3
"""Builds HTML pages to explore tutor sessions.

    python3 tools/session_explorer.py            # all sessions
    python3 tools/session_explorer.py --open     # then open the index

Reads `sessions/<id>/` (session.json, tutorial.json, events.jsonl, shots/)
and the simulator reports in `sim/results/*.json`, and writes:

- `sessions/index.html`: every session, filterable, with outcome and metrics;
  simulated runs show scenario, persona, seed and whether the check passed.
- `sessions/<id>/index.html`: one session as a timeline grouped by
  milestone: what Holo saw (screenshot with its point), what it chose and
  why, what the learner did, questions and answers, retries and warnings.

Pages are static and self-contained (no network), and stay next to the
screenshots they show: they are never committed (`sessions/` is ignored),
since screenshots show the learner's screen.
"""

from __future__ import annotations

import argparse
import html
import json
import statistics
import sys
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSIONS = ROOT / "sessions"
SIM_RESULTS = ROOT / "sim" / "results"


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def read_events(path: Path) -> list[dict]:
    events = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return events
    for line in lines:
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    return events


@dataclass
class Session:
    id: str
    dir: Path
    meta: dict
    tutorial: dict
    events: list[dict]
    sim: dict | None = None
    stats: dict = field(default_factory=dict)

    @property
    def started(self) -> str:
        ts = self.meta.get("started_at")
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "?"

    @property
    def outcome(self) -> str:
        return self.meta.get("outcome") or "?"


def load_sim_reports() -> dict[str, dict]:
    """Simulator reports keyed by session folder name."""
    by_session: dict[str, dict] = {}
    for path in sorted(SIM_RESULTS.glob("*.json")):
        for report in read_json(path, []):
            session = report.get("session")
            if session:
                by_session[Path(session).name] = report
    return by_session


def compute_stats(s: Session) -> dict:
    ev = s.events
    steps = [e for e in ev if e.get("type") == "step"]
    first_chunks = [e.get("ms", 0) for e in ev if e.get("type") == "holo_first_chunk"]
    milestones = s.tutorial.get("milestones", [])
    done = {e.get("milestone") for e in ev if e.get("type") == "milestone_done"}
    skipped = {e.get("milestone") for e in ev if e.get("type") == "milestone_skipped"}
    tokens = sum((e.get("tokens") or {}).get("prompt") or 0 for e in steps)
    model_ms = sum(e.get("model_ms") or e.get("latency_ms") or 0 for e in steps)
    return {
        "steps": len(steps),
        "milestones": len(milestones),
        "done": len(done & {m.get("id") for m in milestones}),
        "skipped": len(skipped),
        "questions": sum(e.get("type") == "learner_question" for e in ev),
        "challenges": sum(e.get("type") == "answer_challenged" for e in ev),
        "invalid": sum(e.get("type") == "invalid_action" for e in ev),
        "retries": sum(e.get("type") == "holo_retry" for e in ev),
        "stalls": sum(e.get("type") == "holo_retry" and "stalled" in str(e.get("error", "")) for e in ev),
        "rate_limited": sum(e.get("type") == "holo_rate_limited" for e in ev),
        "searches": sum(e.get("type") in ("search", "search_cached") for e in ev),
        "knowledge_hits": sum(e.get("type") in ("milestone_knowledge", "plan_knowledge") and bool(e.get("matches")) for e in ev),
        "prompt_tokens": tokens,
        "model_s": model_ms / 1000,
        "first_chunk_median_ms": int(statistics.median(first_chunks)) if first_chunks else None,
        "duration_s": s.meta.get("duration_s") or (ev[-1].get("t") if ev else 0),
        "no_effect": sum(e.get("type") == "action_outcome" and e.get("outcome") == "NoEffect" for e in ev),
    }


def load_sessions() -> list[Session]:
    sims = load_sim_reports()
    sessions = []
    for d in sorted(SESSIONS.iterdir() if SESSIONS.exists() else [], reverse=True):
        if not d.is_dir() or not (d / "events.jsonl").exists():
            continue
        s = Session(
            id=d.name,
            dir=d,
            meta=read_json(d / "session.json", {}),
            tutorial=read_json(d / "tutorial.json", {}),
            events=read_events(d / "events.jsonl"),
            sim=sims.get(d.name),
        )
        start = next((e for e in s.events if e.get("type") == "sim_start"), None)
        if start and not s.sim:
            s.sim = {"scenario": start.get("scenario"), "persona": start.get("persona"), "seed": start.get("seed")}
        s.stats = compute_stats(s)
        sessions.append(s)
    return sessions


CSS = """
:root {
  --bg: #f6f6f4; --panel: #ffffff; --ink: #1b1b1a; --muted: #6b6a66; --line: #e3e2de;
  --accent: #2f5bd3; --accent-soft: #e8eefc; --ok: #1e7a46; --ok-soft: #e4f4ea;
  --warn: #9a5b00; --warn-soft: #fbf0dc; --bad: #b42318; --bad-soft: #fde8e6;
  --tutor: #eef1fb; --learner: #f1f7ef; --code: #f2f1ee;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #141413; --panel: #1d1d1b; --ink: #ecebe7; --muted: #9b9a95; --line: #2e2e2b;
    --accent: #7ea2ff; --accent-soft: #1f2840; --ok: #6ccf95; --ok-soft: #16301f;
    --warn: #f0b155; --warn-soft: #33270f; --bad: #ff8a80; --bad-soft: #3a1714;
    --tutor: #1c2131; --learner: #1b2a1d; --code: #242421;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
header.top { position: sticky; top: 0; z-index: 5; background: color-mix(in srgb, var(--bg) 92%, transparent);
  backdrop-filter: blur(8px); border-bottom: 1px solid var(--line); padding: 14px 24px; }
header.top h1 { margin: 0; font-size: 18px; font-weight: 650; letter-spacing: -0.01em; }
header.top .sub { color: var(--muted); font-size: 13px; margin-top: 2px; }
main { max-width: 1280px; margin: 0 auto; padding: 20px 24px 80px; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; margin-bottom: 18px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; }
.card .k { color: var(--muted); font-size: 12px; }
.card .v { font-size: 20px; font-weight: 650; font-variant-numeric: tabular-nums; }
.filters { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.filters input, .filters select { font: inherit; padding: 6px 10px; border: 1px solid var(--line);
  border-radius: 8px; background: var(--panel); color: var(--ink); }
.filters input { flex: 1; min-width: 200px; }
.table-wrap { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-size: 12px; color: var(--muted); font-weight: 600; background: var(--bg); }
td.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
tr:hover td { background: color-mix(in srgb, var(--accent-soft) 45%, transparent); }
.badge { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px; font-weight: 600;
  white-space: nowrap; background: var(--code); color: var(--muted); }
.badge.ok { background: var(--ok-soft); color: var(--ok); }
.badge.bad { background: var(--bad-soft); color: var(--bad); }
.badge.warn { background: var(--warn-soft); color: var(--warn); }
.badge.info { background: var(--accent-soft); color: var(--accent); }
.dim { color: var(--muted); }
.layout { display: grid; grid-template-columns: 260px 1fr; gap: 24px; align-items: start; }
@media (max-width: 860px) { .layout { grid-template-columns: 1fr; } nav.rail { position: static; } }
nav.rail { position: sticky; top: 80px; background: var(--panel); border: 1px solid var(--line);
  border-radius: 10px; padding: 10px; max-height: calc(100vh - 100px); overflow: auto; }
nav.rail h3 { margin: 4px 6px 8px; font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
nav.rail a { display: flex; gap: 8px; padding: 6px; border-radius: 6px; color: var(--ink); }
nav.rail a:hover { background: var(--accent-soft); text-decoration: none; }
nav.rail .mark { width: 18px; flex: none; text-align: center; }
.ms { margin: 26px 0 10px; padding: 10px 14px; border-left: 3px solid var(--accent); background: var(--panel);
  border-radius: 0 10px 10px 0; border-top: 1px solid var(--line); border-right: 1px solid var(--line);
  border-bottom: 1px solid var(--line); }
.ms h2 { margin: 0; font-size: 15px; }
.ms .when { color: var(--muted); font-size: 13px; }
.ev { display: grid; grid-template-columns: 64px 1fr; gap: 12px; margin: 10px 0; }
.ev .t { color: var(--muted); font-size: 12px; text-align: right; padding-top: 10px; font-variant-numeric: tabular-nums; }
.box { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; min-width: 0; }
.step { display: grid; grid-template-columns: minmax(0, 340px) 1fr; gap: 14px; }
.step.noshot { grid-template-columns: 1fr; }
@media (max-width: 1000px) { .step { grid-template-columns: 1fr; } }
.shot img { width: 100%; border-radius: 6px; border: 1px solid var(--line); cursor: zoom-in; display: block; }
.shot .cap { font-size: 12px; color: var(--muted); margin-top: 4px; }
.action { font-weight: 650; }
.instruction { font-size: 15px; margin: 4px 0 8px; }
.kv { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
details { margin-top: 8px; }
summary { cursor: pointer; color: var(--muted); font-size: 13px; }
pre { background: var(--code); border-radius: 8px; padding: 10px; overflow: auto; white-space: pre-wrap;
  word-break: break-word; font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; margin: 6px 0 0; }
.bubble { border-radius: 12px; padding: 8px 12px; max-width: 760px; }
.bubble.tutor { background: var(--tutor); }
.bubble.learner { background: var(--learner); }
.who { font-size: 12px; color: var(--muted); font-weight: 600; margin-bottom: 2px; }
.line { color: var(--muted); font-size: 13px; padding-top: 8px; }
.alert { border-left: 3px solid var(--warn); }
.alert.bad { border-left-color: var(--bad); }
.lightbox { position: fixed; inset: 0; background: rgba(0,0,0,.85); display: none; align-items: center;
  justify-content: center; z-index: 50; cursor: zoom-out; padding: 20px; }
.lightbox.open { display: flex; }
.lightbox img { max-width: 100%; max-height: 100%; border-radius: 6px; }
.hidden { display: none !important; }
.toolbar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.toolbar label { font-size: 13px; color: var(--muted); display: flex; gap: 6px; align-items: center; }
"""


def page(title: str, subtitle: str, body: str, script: str = "", back: str | None = None) -> str:
    nav = f'<a href="{esc(back)}">← All sessions</a> · ' if back else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title><style>{CSS}</style></head>
<body>
<header class="top"><h1>{esc(title)}</h1><div class="sub">{nav}{subtitle}</div></header>
<main>{body}</main>
<div class="lightbox" id="lightbox"><img alt=""></div>
<script>
const lb = document.getElementById("lightbox");
document.addEventListener("click", (e) => {{
  const img = e.target.closest("img[data-full]");
  if (img) {{ lb.querySelector("img").src = img.dataset.full; lb.classList.add("open"); return; }}
  if (e.target.closest("#lightbox")) lb.classList.remove("open");
}});
document.addEventListener("keydown", (e) => {{ if (e.key === "Escape") lb.classList.remove("open"); }});
{script}
</script></body></html>
"""


# ---------- index ----------


def outcome_badge(s: Session) -> str:
    if s.sim and "success" in s.sim:
        if s.sim.get("false_done") or (s.sim.get("tutor_done") and not s.sim.get("success")):
            return '<span class="badge bad">false done</span>'
        return '<span class="badge ok">check passed</span>' if s.sim["success"] else '<span class="badge bad">check failed</span>'
    kind = {"completed": "ok", "abandoned": "warn", "in_progress": "warn"}.get(s.outcome, "bad")
    return f'<span class="badge {kind}">{esc(s.outcome)}</span>'


def build_index(sessions: list[Session]) -> str:
    sims = [s for s in sessions if s.sim]
    passed = sum(bool(s.sim and s.sim.get("success")) for s in sims)
    completed = sum(s.outcome == "completed" for s in sessions)
    stalls = sum(s.stats["stalls"] for s in sessions)
    cards = f"""<div class="cards">
<div class="card"><div class="k">Sessions</div><div class="v">{len(sessions)}</div></div>
<div class="card"><div class="k">Tutor said done</div><div class="v">{completed}</div></div>
<div class="card"><div class="k">Simulated runs</div><div class="v">{len(sims)}</div></div>
<div class="card"><div class="k">Sim check passed</div><div class="v">{passed}/{len([s for s in sims if 'success' in s.sim])}</div></div>
<div class="card"><div class="k">Tutor steps</div><div class="v">{sum(s.stats['steps'] for s in sessions)}</div></div>
<div class="card"><div class="k">Holo stalls</div><div class="v">{stalls}</div></div>
</div>"""
    rows = []
    for s in sessions:
        st = s.stats
        sim = ""
        if s.sim:
            sim = f'<span class="badge info">{esc(s.sim.get("scenario"))}</span> {esc(s.sim.get("persona"))} · seed {esc(s.sim.get("seed"))}'
        flags = []
        if st["challenges"]:
            flags.append(f'<span class="badge warn">{st["challenges"]} challenged</span>')
        if st["stalls"]:
            flags.append(f'<span class="badge warn">{st["stalls"]} stalls</span>')
        if st["invalid"]:
            flags.append(f'<span class="badge warn">{st["invalid"]} invalid</span>')
        kind = "sim" if s.sim else "live"
        search = " ".join(
            str(x) for x in [s.meta.get("title"), s.meta.get("app"), s.meta.get("goal"), s.id, s.sim and s.sim.get("persona")]
        ).lower()
        rows.append(f"""<tr data-kind="{kind}" data-outcome="{esc(s.outcome)}" data-search="{esc(search)}">
<td class="num">{esc(s.started)}</td>
<td><a href="{esc(s.id)}/index.html">{esc(s.meta.get('title') or s.id)}</a><div class="dim">{esc(s.meta.get('app'))} · {esc(s.meta.get('language') or '')}</div></td>
<td>{outcome_badge(s)}</td>
<td>{sim}</td>
<td class="num">{st['done']}/{st['milestones']}</td>
<td class="num">{st['steps']}</td>
<td class="num">{st['questions']}</td>
<td class="num">{st['duration_s']:.0f}s</td>
<td class="num">{st['prompt_tokens'] / 1000:.0f}k</td>
<td>{' '.join(flags)}</td></tr>""")
    body = f"""{cards}
<div class="filters">
  <input id="q" placeholder="Filter by title, app, goal, persona…" autofocus>
  <select id="kind"><option value="">Live and simulated</option><option value="live">Live only</option><option value="sim">Simulated only</option></select>
  <select id="outcome"><option value="">Any outcome</option><option>completed</option><option>abandoned</option><option>in_progress</option><option>sim-stopped</option><option>sim-error</option></select>
</div>
<div class="table-wrap"><table><thead><tr><th>Started</th><th>Session</th><th>Outcome</th><th>Simulation</th><th>Milestones</th>
<th>Steps</th><th>Questions</th><th>Duration</th><th>Prompt tokens</th><th>Flags</th></tr></thead>
<tbody id="rows">{''.join(rows)}</tbody></table></div>"""
    script = """
const q = document.getElementById("q"), kind = document.getElementById("kind"), outcome = document.getElementById("outcome");
function filter() {
  const text = q.value.trim().toLowerCase();
  for (const tr of document.querySelectorAll("#rows tr")) {
    const show = (!text || tr.dataset.search.includes(text)) && (!kind.value || tr.dataset.kind === kind.value)
      && (!outcome.value || tr.dataset.outcome === outcome.value);
    tr.classList.toggle("hidden", !show);
  }
}
for (const el of [q, kind, outcome]) el.addEventListener("input", filter);
"""
    subtitle = f"Generated {datetime.now():%Y-%m-%d %H:%M} from <code>sessions/</code> and <code>sim/results/</code>"
    return page("Rio sessions", subtitle, body, script)


# ---------- one session ----------


def shot_html(s: Session, rel: str | None, caption: str = "") -> str:
    if not rel:
        return ""
    marked = rel.replace(".jpg", "-marked.jpg")
    src = marked if (s.dir / marked).exists() else rel
    if not (s.dir / src).exists():
        return ""
    return (
        f'<div class="shot"><img loading="lazy" src="{esc(src)}" data-full="{esc(src)}" alt="Screenshot {esc(rel)}">'
        f'<div class="cap">{esc(src)}{" · " + esc(caption) if caption else ""}</div></div>'
    )


def args_html(args: dict, shown: str) -> str:
    skip = {"instruction"}
    parts = [
        f'<span class="badge">{esc(k)}: {esc(v)}</span>'
        for k, v in args.items()
        if k not in skip and v not in ("", None) and v != shown
    ]
    return f'<div class="kv">{"".join(parts)}</div>' if parts else ""


def step_html(s: Session, e: dict, outcome: dict | None) -> str:
    action = e.get("action") or {}
    name = action.get("name", "?")
    args = action.get("args") or {}
    tokens = e.get("tokens") or {}
    metrics = [f'{e.get("latency_ms", 0) / 1000:.1f}s']
    if e.get("requests"):
        metrics.append(f'{e["requests"]} req')
    if e.get("invalid"):
        metrics.append(f'{e["invalid"]} invalid')
    if e.get("searches"):
        metrics.append(f'{e["searches"]} search')
    if tokens.get("prompt"):
        metrics.append(f'{tokens["prompt"]} prompt tok')
    if tokens.get("cached"):
        metrics.append(f'{tokens["cached"]} cached')
    if e.get("context_tokens_est"):
        metrics.append(f'est. ctx {e["context_tokens_est"]}')
    out = ""
    if outcome:
        o = outcome.get("outcome")
        kind = {"Changed": "ok", "NoEffect": "bad", "Unknown": "warn", "Superseded": "warn"}.get(o, "")
        label = {"Changed": "screen changed after", "NoEffect": "no visible effect", "Unknown": "too small to judge",
                 "Superseded": "superseded"}.get(o, o)
        out = f'<span class="badge {kind}">{esc(label)}</span>'
    kind = "ok" if name == "answer" else "info"
    hint = '<span class="badge warn">no pointer</span>' if args.get("show_pointer") is False else ""
    shown = args.get("instruction") or args.get("content") or args.get("question") or ""
    shot = shot_html(s, e.get("shot"))
    body = f"""<div class="step box{'' if shot else ' noshot'}" id="step-{esc(e.get('t'))}">
{shot}
<div><div><span class="badge {kind} action">{esc(name)}</span> {hint} {out}</div>
<div class="instruction">{esc(shown)}</div>
{args_html(args, shown)}
<div class="kv">{''.join(f'<span class="badge">{esc(m)}</span>' for m in metrics)}</div>
{f'<details><summary>Reasoning</summary><pre>{esc(e.get("reasoning"))}</pre></details>' if e.get("reasoning") else ''}
</div></div>"""
    return body


def model_call_html(e: dict, label: str) -> str:
    response = e.get("response")
    return f"""<div class="box"><span class="badge info">{esc(label)}</span> <span class="dim">{esc(e.get('model'))} · {e.get('latency_ms', 0) / 1000:.1f}s</span>
<details><summary>Prompt</summary><pre>{esc(e.get('prompt'))}</pre></details>
<details><summary>Response</summary><pre>{esc(json.dumps(response, ensure_ascii=False, indent=2) if not isinstance(response, str) else response)}</pre></details></div>"""


def event_html(s: Session, e: dict, outcomes: dict) -> str | None:
    t = e.get("type")
    if t == "step":
        return step_html(s, e, outcomes.get(id(e)))
    if t == "learner":
        return f'<div class="bubble learner"><div class="who">Learner</div>{esc(e.get("event"))}</div>'
    if t == "sim_action":
        bits = [esc(e.get("action"))]
        if e.get("action") in ("click", "type"):
            bits.append(f'({round(e.get("x", 0))}, {round(e.get("y", 0))})')
        if e.get("text"):
            bits.append(f'“{esc(e["text"])}”')
        if e.get("keys"):
            bits.append(f'<kbd>{esc(e["keys"])}</kbd>')
        hit = '<span class="badge ok">on target</span>' if e.get("hit") else ""
        changed = '<span class="badge ok">screen changed</span>' if e.get("changed") else '<span class="badge">no change</span>'
        return f'<div class="line">Simulated hand: {" ".join(bits)} {hit} {changed}</div>'
    if t == "sim_learner":
        if "response" not in e:
            return None  # the same decision, also logged as a debug string
        response = e.get("response")
        decision = response if isinstance(response, dict) else {}
        what = decision.get("move", "?")
        detail = decision.get("reply") or decision.get("text") or decision.get("keys") or ""
        return f"""<div class="line">Simulated learner decides <b>{esc(what)}</b> {esc(decision.get('action', ''))} {esc(detail)}
<details><summary>Learner model</summary><pre>{esc(json.dumps(response, ensure_ascii=False, indent=2))}</pre></details></div>"""
    if t == "learner_question":
        return f'<div class="bubble learner"><div class="who">Learner asks</div>{esc(e.get("question"))}</div>'
    if t == "explain":
        extra = ""
        if e.get("show"):
            extra += f' <span class="badge info">shows {esc(e["show"][0])}</span>'
        if e.get("intent") and e["intent"] != "question":
            extra += f' <span class="badge">{esc(e["intent"])}</span>'
        if e.get("remember"):
            extra += f' <span class="badge warn">remembers: {esc(e["remember"])}</span>'
        return f'<div class="bubble tutor"><div class="who">Tutor answers{extra}</div>{esc(e.get("say"))}</div>'
    if t == "ask_learner":
        opts = " / ".join(e.get("options") or [])
        return f'<div class="bubble tutor"><div class="who">Tutor asks the learner</div>{esc(e.get("question"))}{(" <span class=dim>(" + esc(opts) + ")</span>") if opts else ""}</div>'
    if t == "answer_challenged":
        return '<div class="box alert"><b>Answer challenged</b> <span class="dim">— Holo said done but nothing the learner did had a visible effect</span></div>'
    if t == "invalid_action":
        return f'<div class="box alert"><b>Invalid response</b> <span class="dim">{esc(e.get("reason"))} · finish {esc(e.get("finish_reason"))}</span></div>'
    if t == "holo_retry":
        return f'<div class="box alert bad"><b>Holo retry {esc(e.get("attempt"))}</b> <span class="dim">{esc(e.get("error"))}</span></div>'
    if t in ("holo_hedge", "holo_rate_limited", "stale_step", "reveal", "language", "tutorial_blocked", "sim_error"):
        data = {k: v for k, v in e.items() if k not in ("t", "type")}
        kind = "bad" if t in ("sim_error", "tutorial_blocked") else ""
        return f'<div class="box alert {kind}"><b>{esc(t.replace("_", " "))}</b> <span class="dim">{esc(json.dumps(data, ensure_ascii=False))}</span></div>'
    if t in ("search", "search_cached"):
        return f'<div class="line">🔎 Search <b>{esc(e.get("query"))}</b> in {esc(e.get("app"))} <span class="badge">{esc(e.get("backend"))}</span>{" <span class=badge>cached</span>" if t == "search_cached" else ""}</div>'
    if t in ("plan", "ask", "locate", "knowledge"):
        return model_call_html(e, t)
    if t in ("milestone_knowledge", "plan_knowledge"):
        where = "for this milestone" if t == "milestone_knowledge" else "for the plan"
        matches = e.get("matches") or []
        if e.get("error"):
            return f'<div class="box alert bad"><b>Knowledge base failed {where}</b> <span class="dim">{esc(e["error"])}</span></div>'
        if not matches:
            return f'<div class="line">📚 Knowledge base {where}: nothing relevant for “{esc(e.get("query") or e.get("goal"))}”</div>'
        items = "".join(f'<span class="badge ok">{esc(m)}</span> ' for m in matches)
        return f'<div class="box">📚 <b>Knowledge base {where}</b> <span class="dim">“{esc(e.get("query") or e.get("goal"))}”</span><div class="kv">{items}</div></div>'
    if t == "knowledge_error":
        return f'<div class="box alert bad"><b>Knowledge base failed</b> <span class="dim">{esc(e.get("query"))}: {esc(e.get("error"))}</span></div>'
    if t == "tutorial_done":
        return '<div class="box"><span class="badge ok">Tutorial done</span></div>'
    if t == "saved_as_tutorial":
        return f'<div class="line">Saved as tutorial {esc(e.get("tutorial_id"))} v{esc(e.get("version"))}</div>'
    return None  # milestone markers, ax, first-chunk timings, sim_start: shown elsewhere


def build_session(s: Session, index_href: str) -> str:
    milestones = s.tutorial.get("milestones", [])
    status: dict[str, str] = {}
    evidence: dict[str, str] = {}
    for e in s.events:
        if e.get("type") == "milestone_done":
            status[e.get("milestone")] = "done"
            evidence[e.get("milestone")] = e.get("evidence", "")
        elif e.get("type") == "milestone_skipped":
            status[e.get("milestone")] = "skipped"
        elif e.get("type") == "milestone_start":
            status.setdefault(e.get("milestone"), "started")

    # Each action's outcome (judged on the next screenshot) is shown on its step.
    outcomes: dict[int, dict] = {}
    last_step: dict[str, dict] = {}
    for e in s.events:
        if e.get("type") == "step" and (e.get("action") or {}).get("name") != "answer":
            last_step[e.get("milestone")] = e
        elif e.get("type") == "action_outcome" and e.get("milestone") in last_step:
            outcomes[id(last_step.pop(e.get("milestone")))] = e

    rail = ['<h3>Milestones</h3>']
    for m in milestones:
        st = status.get(m.get("id"), "todo")
        mark = {"done": "✓", "skipped": "–", "started": "→"}.get(st, "·")
        rail.append(f'<a href="#ms-{esc(m.get("id"))}"><span class="mark">{mark}</span><span>{esc(m.get("goal"))}</span></a>')

    blocks = []
    goals = {m.get("id"): m for m in milestones}
    for e in s.events:
        t = e.get("type")
        if t == "milestone_start":
            m = goals.get(e.get("milestone"), {})
            st = status.get(e.get("milestone"), "")
            badge = {"done": '<span class="badge ok">done</span>', "skipped": '<span class="badge warn">skipped</span>'}.get(
                st, '<span class="badge">not finished</span>'
            )
            hints = f'<div class="when">Known path: {esc("; ".join(m.get("hints") or []))}</div>' if m.get("hints") else ""
            blocks.append(
                f'<div class="ms" id="ms-{esc(e.get("milestone"))}"><h2>{esc(e.get("goal") or m.get("goal"))} {badge}</h2>'
                f'<div class="when">Done when: {esc(m.get("done_when"))}</div>{hints}</div>'
            )
            continue
        if t in ("milestone_done", "milestone_skipped"):
            kind = "ok" if t == "milestone_done" else "warn"
            blocks.append(
                f'<div class="ev"><div class="t">{e.get("t", 0):.1f}s</div><div class="box"><span class="badge {kind}">'
                f'{"Milestone done" if kind == "ok" else "Milestone skipped"}</span> {esc(e.get("evidence"))}</div></div>'
            )
            continue
        inner = event_html(s, e, outcomes)
        if inner:
            blocks.append(f'<div class="ev" data-type="{esc(t)}"><div class="t">{e.get("t", 0):.1f}s</div><div>{inner}</div></div>')

    st = s.stats
    sim = ""
    if s.sim:
        sim = (
            f'<div class="card"><div class="k">Simulation</div><div class="v" style="font-size:15px">{esc(s.sim.get("scenario"))}</div>'
            f'<div class="dim">{esc(s.sim.get("persona"))} · seed {esc(s.sim.get("seed"))}</div></div>'
        )
    first_chunk = f'{st["first_chunk_median_ms"]} ms' if st["first_chunk_median_ms"] is not None else "–"
    cards = f"""<div class="cards">
<div class="card"><div class="k">Outcome</div><div class="v" style="font-size:15px">{outcome_badge(s)}</div></div>{sim}
<div class="card"><div class="k">Milestones</div><div class="v">{st['done']}/{st['milestones']}</div></div>
<div class="card"><div class="k">Tutor steps</div><div class="v">{st['steps']}</div></div>
<div class="card"><div class="k">No-effect actions</div><div class="v">{st['no_effect']}</div></div>
<div class="card"><div class="k">Questions</div><div class="v">{st['questions']}</div></div>
<div class="card"><div class="k">Knowledge used</div><div class="v">{st['knowledge_hits']}</div></div>
<div class="card"><div class="k">Duration</div><div class="v">{st['duration_s']:.0f}s</div></div>
<div class="card"><div class="k">Holo time (steps)</div><div class="v">{st['model_s']:.0f}s</div></div>
<div class="card"><div class="k">Prompt tokens</div><div class="v">{st['prompt_tokens'] / 1000:.0f}k</div></div>
<div class="card"><div class="k">First chunk (median)</div><div class="v">{first_chunk}</div></div>
<div class="card"><div class="k">Retries · stalls</div><div class="v">{st['retries']} · {st['stalls']}</div></div>
</div>"""
    toolbar = """<div class="toolbar">
<label><input type="checkbox" id="show-sim" checked> Simulated learner details</label>
<label><input type="checkbox" id="show-infra" checked> Retries and warnings</label>
</div>"""
    body = f"""{cards}
<div class="layout"><nav class="rail">{''.join(rail)}</nav>
<div>{toolbar}<p class="dim">Goal: {esc(s.meta.get('goal') or s.tutorial.get('goal'))}</p>{''.join(blocks) or '<p class="dim">No events.</p>'}</div></div>"""
    script = """
const toggle = (box, types) => box.addEventListener("change", () => {
  for (const el of document.querySelectorAll(".ev[data-type]"))
    if (types.includes(el.dataset.type)) el.classList.toggle("hidden", !box.checked);
});
toggle(document.getElementById("show-sim"), ["sim_learner", "sim_action"]);
toggle(document.getElementById("show-infra"), ["holo_retry", "holo_hedge", "holo_rate_limited", "invalid_action"]);
"""
    subtitle = f"{esc(s.started)} · {esc(s.meta.get('app'))} · {esc(s.id)}"
    return page(s.meta.get("title") or s.id, subtitle, body, script, back=index_href)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--open", action="store_true", help="open the index in the browser")
    args = parser.parse_args()
    sessions = load_sessions()
    if not sessions:
        print(f"No sessions in {SESSIONS}")
        return 1
    for s in sessions:
        (s.dir / "index.html").write_text(build_session(s, "../index.html"), encoding="utf-8")
    index = SESSIONS / "index.html"
    index.write_text(build_index(sessions), encoding="utf-8")
    print(f"{len(sessions)} sessions → {index}")
    if args.open:
        webbrowser.open(index.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
