import { useEffect, useState } from "react";
import { AppIcon, coverStyle } from "../appIcons";
import { TutorialCard } from "../cards";
import { type LibraryEntry, type TutorialRow, ago, api, navigate, useApi } from "../lib";
import { Head, I, Loading } from "../ui";

type Step = { do: string; changed: boolean; was?: { version: string; label: string | null } | null; routine: boolean; missing: boolean };
type Source = { id: string; title: string | null; kind: string | null; url: string | null; version: string | null; t?: number | null };
type Skill = { id: string; intent: string; sources: Source[]; proofs: Record<string, string>; changed: boolean; steps: Record<string, Step[]> };
type AppInfo = { id: string; name: string; versions: { id: string; label: string | null }[]; current_version: string };
type Overview = {
  global: { internal?: boolean; app: AppInfo; skills: number; sources: number; proven: number; atoms?: number; tutorials: LibraryEntry[] }[];
  created: { app: string; skills: number }[];
};
type Hit = { id: string; intent: string; app_name: string; score: number; proof: string | null; version: { id: string }; steps: { do: string }[]; sources: Source[] };

export function KnowledgePage() {
  const { data } = useApi<Overview>("/knowledge");
  const [tab, setTab] = useState<"global" | "created">(new URLSearchParams(window.location.search).get("tab") === "team" ? "created" : "global");
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);

  useEffect(() => {
    if (!q.trim()) return setHits(null);
    const t = setTimeout(() => {
      fetch(`/api/app/knowledge/search?q=${encodeURIComponent(q)}`, { credentials: "include" })
        .then((r) => r.json())
        .then((v: { results: Hit[] }) => setHits(v.results));
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  const shared = data ? { ...data, global: data.global.filter((g) => !g.internal) } : null;
  const teamTotal = data?.global.filter((g) => g.internal).reduce((a, g) => a + g.skills, 0) ?? 0;
  const globalTotal = shared?.global.reduce((a, g) => a + g.skills, 0) ?? 0;

  return (
    <>
      <Head title="Knowledge" sub="What Rio knows when someone asks for help: the global base, and your team's own docs. Tutorials people follow live in the Library." />
      <div className="ask">
        <I.Search />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask anything, in any language: “comment supprimer les doublons ?”" aria-label="Search the knowledge" />
        {q && (
          <button className="btn btn--sm btn--ghost" onClick={() => setQ("")}>
            Clear
          </button>
        )}
      </div>

      {hits ? (
        <div className="section" style={{ marginTop: 22 }}>
          <div className="section__title">
            <h2>What Rio would use</h2>
            <span>{hits.length ? `${hits.length} matches` : "Nothing yet: a good tutorial to create"}</span>
          </div>
          {hits.length === 0 ? (
            <div className="empty">
              <b>No knowledge about this yet</b>
              Rio would fall back on the web. Make it a tutorial so your team gets a proven path.
              <div>
                <button className="btn btn--primary" onClick={() => navigate(`/home?goal=${encodeURIComponent(q)}`)}>
                  Create a tutorial about it
                </button>
              </div>
            </div>
          ) : (
            <div className="skills">
              {hits.map((h) => (
                <div className="skill" key={h.id}>
                  <div className="skill__head" style={{ cursor: "default" }}>
                    <AppIcon name={h.app_name} />
                    <span className="skill__name">
                      {h.intent}
                      <small>
                        {h.app_name}
                        {h.version.id !== "any" ? ` ${h.version.id}` : ""} · {h.sources[0]?.title ?? "Your team"}
                      </small>
                    </span>
                    {h.proof === "PASS" && <span className="tag tag--ok">Proven</span>}
                    {h.version.id === "any" && <span className="tag">Your team</span>}
                  </div>
                  <div className="skill__body">
                    <ol className="skill__steps">
                      {h.steps.slice(0, 5).map((s, i) => (
                        <li key={i}>{s.do}</li>
                      ))}
                    </ol>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <>
          <div className="tabs" style={{ marginTop: 26 }}>
            <button className={tab === "global" ? "is-on" : ""} onClick={() => setTab("global")}>
              Global knowledge<span className="count">{globalTotal}</span>
            </button>
            <button className={tab === "created" ? "is-on" : ""} onClick={() => setTab("created")}>
              Your team's knowledge<span className="count">{teamTotal}</span>
            </button>
          </div>
          {!data || !shared ? <Loading /> : tab === "global" ? <Global data={shared} /> : <TeamKnowledge data={data} />}
        </>
      )}
    </>
  );
}

function Global({ data }: { data: Overview }) {
  const [appId, setAppId] = useState(data.global[0]?.app.id ?? null);
  const g = data.global.find((x) => x.app.id === appId);
  const [filter, setFilter] = useState("");
  const skills = useApi<{ app: AppInfo; skills: Skill[] }>(appId ? `/knowledge/skills?app=${appId}&q=${encodeURIComponent(filter)}` : null);
  const [version, setVersion] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [view, setView] = useState<"list" | "graph">(new URLSearchParams(window.location.search).get("view") === "graph" ? "graph" : "list");

  if (!g) return <div className="empty"><b>No global knowledge yet</b>The shared base comes from ReStep: tutorials, docs and threads, re-targeted to each version.</div>;
  const v = version ?? g.app.current_version;

  return (
    <>
      {data.global.length > 1 && (
        <div className="chips" style={{ marginBottom: 16 }}>
          {data.global.map((x) => (
            <button key={x.app.id} className={`chip ${x.app.id === appId ? "is-on" : ""}`} onClick={() => setAppId(x.app.id)}>
              <AppIcon name={x.app.name} /> {x.app.name}
            </button>
          ))}
        </div>
      )}
      <div className="hero" style={{ marginBottom: 16 }}>
        <div className="hero__cover" style={{ ...coverStyle(g.app.name), height: 96 }}>
          <AppIcon name={g.app.name} />
        </div>
        <div className="hero__body" style={{ paddingTop: 36 }}>
          <h2 className="hero__title" style={{ fontSize: 22 }}>{g.app.name}</h2>
          <p className="hero__goal">
            {g.internal
              ? `Learned from your team's ${g.sources === 1 ? "document" : `${g.sources} documents`}: every procedure tied to the buttons and menus they name. Only your organization sees it.`
              : `Learned from ${g.sources} ${g.sources === 1 ? "source" : "videos, docs and threads"}, re-targeted to each version: where every action is now, and where it used to be.`}
          </p>
        </div>
      </div>
      <div className="stats">
        <div className="stat"><div className="stat__value">{g.skills}</div><div className="stat__label">Skills</div></div>
        <div className="stat"><div className="stat__value">{g.sources}</div><div className="stat__label">Sources</div></div>
        {g.internal ? (
          <div className="stat"><div className="stat__value">{g.atoms ?? 0}</div><div className="stat__label">Buttons and menus</div></div>
        ) : (
          <div className="stat"><div className="stat__value">{g.proven}</div><div className="stat__label">Proven in a sandbox</div></div>
        )}
        <div className="stat"><div className="stat__value">{g.app.versions.length}</div><div className="stat__label">Versions</div></div>
      </div>

      <Atlas app={g.app} />

      <div className="section" style={{ marginTop: 28 }}>
        <div className="section__title">
          <h2>Skills</h2>
          <span>One effect each, taught by one or more sources</span>
          <div className="seg" style={{ marginLeft: "auto" }} role="group" aria-label="View">
            <button className={view === "list" ? "is-on" : ""} onClick={() => setView("list")}>List</button>
            <button className={view === "graph" ? "is-on" : ""} onClick={() => setView("graph")}>Graph</button>
          </div>
          <div className="seg" style={{ display: view === "graph" ? "none" : undefined }} role="group" aria-label="Version">
            {g.app.versions.map((x) => (
              <button key={x.id} className={x.id === v ? "is-on" : ""} onClick={() => setVersion(x.id)}>
                {x.id}
              </button>
            ))}
          </div>
        </div>
        {view === "graph" ? (
          <GraphView appId={g.app.id} />
        ) : (
        <>
        <div className="ask" style={{ marginBottom: 12 }}>
          <I.Search />
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder={`Filter ${g.app.name} skills`} aria-label="Filter skills" />
        </div>
        {!skills.data ? (
          <Loading />
        ) : (
          <div className="skills">
            {skills.data.skills.slice(0, 60).map((s) => {
              const isOpen = open === s.id;
              const steps = (s.steps[v] ?? []).filter((x) => !x.missing);
              return (
                <div className="skill" key={s.id}>
                  <button className="skill__head" onClick={() => setOpen(isOpen ? null : s.id)} aria-expanded={isOpen}>
                    <span className={`chev ${isOpen ? "is-open" : ""}`}><I.Right /></span>
                    <span className="skill__name">
                      {s.intent}
                      <small>{s.sources.length === 0 ? "From the software itself" : `${s.sources.length} ${s.sources.length === 1 ? "source" : "sources"}`}</small>
                    </span>
                    {s.changed && <span className="tag">Moved between versions</span>}
                    {s.proofs[v] === "PASS" && <span className="tag tag--ok">Proven on {v}</span>}
                  </button>
                  {isOpen && (
                    <div className="skill__body">
                      {steps.length ? (
                        <ol className="skill__steps">
                          {steps.map((st, i) => (
                            <li key={i}>
                              <span>
                                {st.do}
                                {st.changed && st.was?.label && (
                                  <span className="was">· was “{st.was.label}” in {st.was.version}</span>
                                )}
                              </span>
                            </li>
                          ))}
                        </ol>
                      ) : (
                        <p className="note">No steps for {v}.</p>
                      )}
                      <div className="hints" style={{ marginTop: 14 }}>
                        {s.sources.slice(0, 4).map((src) =>
                          src.url ? (
                            <a key={src.id} className="link" href={src.url} target="_blank" rel="noreferrer" style={{ marginRight: 12 }}>
                              {src.title ?? src.url} ↗
                            </a>
                          ) : null,
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
        </>
        )}
      </div>

      {g.tutorials.length > 0 && (
        <div className="section">
          <div className="section__title">
            <h2>Sources</h2>
            <span>The videos, docs and threads this knowledge comes from</span>
          </div>
          <div className="skills">
            {g.tutorials.map((t) => (
              <div className="skill" key={t.id}>
                <div className="skill__head" style={{ cursor: "default" }}>
                  <span className="source__icon">{t.author_kind === "video" ? <I.Play /> : <I.Page />}</span>
                  <span className="skill__name">
                    {t.title}
                    <small>
                      {t.milestones} skills{t.recorded_on && t.recorded_on !== "current" ? ` · made for ${t.recorded_on}` : ""}
                    </small>
                  </span>
                  {t.source_url && (
                    <a className="link" href={t.source_url} target="_blank" rel="noreferrer">Open ↗</a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

type Doc = { id: string; title: string; url: string | null; added_at: number; app_id: string; app_name: string; internal: boolean; skills: number; steps: number };
type Ingested = { title: string; app: { name: string; internal: boolean }; skills: number; new_skills: number; merged_into_known: number; steps: number; grounded: number; elapsed_s: number };

/** Your team's knowledge: docs about internal tools (or your way of using any tool), read into skills Rio uses first. */
function TeamKnowledge({ data }: { data: Overview }) {
  const docs = useApi<{ sources: Doc[] }>("/knowledge/docs");
  const [done, setDone] = useState<Ingested | null>(null);
  const internal = data.global.filter((g) => g.internal);
  const tools = [...new Set([...data.global.map((g) => g.app.name)])];
  return (
    <>
      <AddDoc tools={tools} onDone={(r) => { setDone(r); docs.reload(); }} />
      {done && (
        <div className="empty" style={{ textAlign: "left", marginTop: 12, borderStyle: "solid" }}>
          <b>Rio learned {done.skills} procedures from “{done.title}”</b>
          {done.grounded} of {done.steps} steps tied to {done.app.name}'s interface
          {done.merged_into_known ? `, ${done.merged_into_known} merged with what Rio already knew` : ""} · {done.elapsed_s}s.
          {done.app.internal ? ` ${done.app.name} is one of your internal tools: only your team sees it.` : ""}
        </div>
      )}
      <div className="section">
        <div className="section__title">
          <h2>Documents</h2>
          <span>Only your organization sees them</span>
        </div>
        {!docs.data ? (
          <Loading />
        ) : docs.data.sources.length === 0 ? (
          <div className="empty">
            <b>No documents yet</b>Add a guide about an internal tool above: Rio turns each procedure in it into knowledge.
          </div>
        ) : (
          <div className="skills">
            {docs.data.sources.map((d) => (
              <div className="skill" key={d.id}>
                <div className="skill__head" style={{ cursor: "default" }}>
                  <AppIcon name={d.app_name} />
                  <span className="skill__name">
                    {d.title}
                    <small>
                      {d.app_name}
                      {d.internal ? " (internal tool)" : ""} · {d.skills} procedures · {d.steps} steps · added {ago(d.added_at * 1000).toLowerCase()}
                    </small>
                  </span>
                  <button
                    className="btn btn--sm btn--ghost btn--danger"
                    onClick={async () => {
                      if (!confirm(`Remove “${d.title}”? What only this document taught goes with it.`)) return;
                      await api(`/knowledge/docs/${encodeURIComponent(d.id)}`, { method: "DELETE" }).catch((e: Error) => alert(e.message));
                      docs.reload();
                    }}
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      {internal.length > 0 && (
        <div className="section">
          <div className="section__title">
            <h2>Your internal tools</h2>
            <span>Their interface, as your docs describe it</span>
          </div>
          <Global data={{ ...data, global: internal }} />
        </div>
      )}
    </>
  );
}

function AddDoc({ tools, onDone }: { tools: string[]; onDone: (r: Ingested) => void }) {
  const [tool, setTool] = useState("");
  const [version, setVersion] = useState("");
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function file(f: File | undefined) {
    if (!f) return;
    setText(await f.text());
    setTitle(f.name.replace(/\.(md|markdown|txt)$/i, ""));
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api<Ingested>("/knowledge/docs", { method: "POST", json: { app: tool, version: version || undefined, title: title || undefined, text } });
      setText("");
      setTitle("");
      onDone(r);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="card-box" onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>Teach Rio your tools</h3>
        <p className="note" style={{ margin: "4px 0 0" }}>
          Paste or drop a Markdown guide. Rio reads every procedure in it, ties each step to the tool's buttons and menus, and uses it
          first when someone on your team asks.
        </p>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 10 }}>
        <div className="field">
          <label htmlFor="doc-tool">Tool</label>
          <input id="doc-tool" className="input" list="doc-tools" required value={tool} onChange={(e) => setTool(e.target.value)} placeholder="Comptoir, our CRM, Blender…" />
          <datalist id="doc-tools">
            {tools.map((t) => (
              <option key={t} value={t} />
            ))}
          </datalist>
        </div>
        <div className="field">
          <label htmlFor="doc-version">Version (optional)</label>
          <input id="doc-version" className="input" value={version} onChange={(e) => setVersion(e.target.value)} placeholder="2.0" />
        </div>
      </div>
      <div
        className="field"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          file(e.dataTransfer.files[0]);
        }}
      >
        <label htmlFor="doc-text">
          Document {title && <span className="faint">· {title}</span>}
        </label>
        <textarea id="doc-text" className="textarea" rows={7} required value={text} onChange={(e) => setText(e.target.value)} placeholder={"# Refund an order\n1. Open Orders › All orders…\n\nOr drop a .md file here."} style={{ fontFamily: "var(--mono)", fontSize: 12.5 }} />
      </div>
      {error && <div className="error">{error}</div>}
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <label className="btn" style={{ cursor: "pointer" }}>
          <I.Page /> Choose a file
          <input type="file" accept=".md,.markdown,.txt,text/markdown,text/plain" hidden onChange={(e) => file(e.target.files?.[0])} />
        </label>
        <button className="btn btn--primary" disabled={busy || !tool.trim() || text.trim().length < 80} style={{ marginLeft: "auto" }}>
          {busy ? <><span className="spinner" /> Rio is reading it…</> : "Add to knowledge"}
        </button>
      </div>
    </form>
  );
}

type Located = { op: string; label: string; where: { paths: string[]; keys: string[]; via_keys: string[] } | null; aka: string[]; replaced: { from: string; why: string } | null };

/** ReStep's atlas: a UI element by any name it has had, and where it is now. */
function Atlas({ app }: { app: AppInfo }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<Located[] | null>(null);
  useEffect(() => {
    if (q.trim().length < 3) return setRes(null);
    const t = setTimeout(() => {
      fetch(`/api/app/knowledge/locate?app=${app.id}&q=${encodeURIComponent(q)}`, { credentials: "include" })
        .then((r) => r.json())
        .then((v: { results: Located[] }) => setRes(v.results));
    }, 250);
    return () => clearTimeout(t);
  }, [q, app.id]);
  return (
    <div className="section" style={{ marginTop: 28 }}>
      <div className="section__title">
        <h2>Where is it now?</h2>
        <span>Any name a button or menu has had, in any version</span>
      </div>
      <div className="ask">
        <I.Search />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={app.id === "blender" ? "Remove Doubles, Move to Layer, Specials…" : `A ${app.name} menu or button`} aria-label="Find a UI element" />
      </div>
      {res && (
        <div className="skills" style={{ marginTop: 10 }}>
          {res.length === 0 && <p className="note">No UI element by that name.</p>}
          {res.map((r) => (
            <div className="skill" key={r.op}>
              <div className="skill__head" style={{ cursor: "default", alignItems: "flex-start" }}>
                <span className="skill__name">
                  {r.label}
                  {r.aka.length > 0 && <small>Formerly {r.aka.map((a) => `“${a}”`).join(", ")}</small>}
                  {r.replaced && <small>Replaces {r.replaced.from} ({r.replaced.why})</small>}
                </span>
                <span className="hints" style={{ marginTop: 0, justifyContent: "flex-end" }}>
                  {(r.where?.paths ?? []).slice(0, 2).map((p) => (
                    <span className="hint" key={p}>{p}</span>
                  ))}
                  {(r.where?.keys ?? []).slice(0, 1).map((k) => (
                    <span className="hint" key={k}>{k}</span>
                  ))}
                  {!r.where && <span className="tag tag--failed">Not in this version</span>}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

type GraphData = {
  app: { id: string; name: string; current_version: string } | null;
  sources: { id: string; title: string | null; kind: string | null; url: string | null }[];
  skills: { id: string; name: string; ops: string[]; sources: string[]; proven: boolean }[];
  atoms: { id: string; label: string; current: boolean }[];
};

const GRAPH_FILTERS = [
  { id: "all", label: "All skills" },
  { id: "multi", label: "Taught by several sources" },
  { id: "proven", label: "Proven" },
] as const;

/**
 * ReStep's graph: sources on the left, the skills they teach in the middle, the UI elements each skill uses on the
 * right (named as they are in the current version). Hover anything to follow its links.
 */
function GraphView({ appId }: { appId: string }) {
  const { data } = useApi<GraphData>(`/knowledge/graph?app=${appId}`);
  const [mode, setMode] = useState<(typeof GRAPH_FILTERS)[number]["id"]>("multi");
  const [focus, setFocus] = useState<string | null>(null);
  if (!data) return <Loading />;

  const skills = data.skills
    .filter((s) => (mode === "multi" ? s.sources.length > 1 : mode === "proven" ? s.proven : true))
    .sort((a, b) => b.sources.length - a.sources.length || a.name.localeCompare(b.name));
  const srcIds = [...new Set(skills.flatMap((s) => s.sources))];
  const sources = data.sources.filter((s) => srcIds.includes(s.id)).sort((a, b) => (a.title ?? "").localeCompare(b.title ?? ""));
  const atomIds = new Set(skills.flatMap((s) => s.ops));
  const atoms = data.atoms.filter((a) => atomIds.has(a.id)).sort((a, b) => a.label.localeCompare(b.label));

  const W = 980, RH = 30, TOP = 8, NW = 270, X = [0, 355, 710];
  const y = (i: number) => TOP + i * RH;
  const ys = new Map(sources.map((s, i) => [`s:${s.id}`, y(i)]));
  const yk = new Map(skills.map((s, i) => [`k:${s.id}`, y(i)]));
  const ya = new Map(atoms.map((a, i) => [`a:${a.id}`, y(i)]));
  const H = TOP * 2 + Math.max(sources.length, skills.length, atoms.length) * RH;

  // What the focused node is linked to (both directions, through skills).
  const lit = new Set<string>();
  if (focus) {
    lit.add(focus);
    const [kind, id] = [focus.slice(0, 1), focus.slice(2)];
    const via = skills.filter((s) => (kind === "k" ? s.id === id : kind === "s" ? s.sources.includes(id) : s.ops.includes(id)));
    for (const s of via) {
      lit.add(`k:${s.id}`);
      s.sources.forEach((x) => lit.add(`s:${x}`));
      s.ops.forEach((x) => lit.add(`a:${x}`));
    }
  }
  const on = (id: string) => !focus || lit.has(id);
  const edge = (x1: number, y1: number, x2: number, y2: number) => `M${x1},${y1 + 11} C${x1 + 50},${y1 + 11} ${x2 - 50},${y2 + 11} ${x2},${y2 + 11}`;
  const cut = (s: string, n = 38) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

  const node = (id: string, x: number, yy: number, label: string, extra?: React.ReactNode, dim?: boolean) => (
    <g
      key={id}
      className={`gnode ${on(id) ? "" : "is-dim"} ${focus === id ? "is-focus" : ""}`}
      transform={`translate(${x},${yy})`}
      onMouseEnter={() => setFocus(id)}
      onMouseLeave={() => setFocus(null)}
    >
      <rect width={NW} height={22} rx={7} />
      <text x={10} y={15} className={dim ? "is-old" : ""}>
        {cut(label)}
      </text>
      {extra}
    </g>
  );

  return (
    <div className="graph">
      <div className="graph__bar">
        <div className="chips">
          {GRAPH_FILTERS.map((f) => (
            <button key={f.id} className={`chip ${mode === f.id ? "is-on" : ""}`} onClick={() => setMode(f.id)}>
              {f.label}
            </button>
          ))}
        </div>
        <span className="note">
          {sources.length} sources · {skills.length} skills · {atoms.length} UI elements ({data.app?.current_version})
        </span>
      </div>
      <div className="graph__cols">
        <span>Sources</span>
        <span>Skills</span>
        <span>UI elements, as they are now</span>
      </div>
      <div className="graph__scroll">
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`${data.app?.name} knowledge graph: ${sources.length} sources, ${skills.length} skills, ${atoms.length} UI elements`}>
          <g className="gedges">
            {skills.map((s) => {
              const k = `k:${s.id}`;
              const yy = yk.get(k)!;
              return (
                <g key={k}>
                  {s.sources.map((x) => {
                    const y1 = ys.get(`s:${x}`);
                    return y1 == null ? null : <path key={x} className={on(`s:${x}`) && on(k) && (!focus || lit.has(k)) ? "is-lit" : ""} d={edge(X[0] + NW, y1, X[1], yy)} />;
                  })}
                  {s.ops.map((o) => {
                    const y2 = ya.get(`a:${o}`);
                    return y2 == null ? null : <path key={o} className={on(k) && on(`a:${o}`) && (!focus || lit.has(k)) ? "is-lit" : ""} d={edge(X[1] + NW, yy, X[2], y2)} />;
                  })}
                </g>
              );
            })}
          </g>
          {sources.map((s) => node(`s:${s.id}`, X[0], ys.get(`s:${s.id}`)!, `${s.kind === "video" ? "▶ " : ""}${s.title ?? s.id}`))}
          {skills.map((s) =>
            node(
              `k:${s.id}`,
              X[1],
              yk.get(`k:${s.id}`)!,
              s.name,
              <>
                {s.sources.length > 1 && (
                  <text x={NW - 10} y={15} textAnchor="end" className="gcount">
                    {s.sources.length}
                  </text>
                )}
                {s.proven && <circle cx={NW - (s.sources.length > 1 ? 26 : 12)} cy={11} r={3.5} className="gproof" />}
              </>,
            ),
          )}
          {atoms.map((a) => node(`a:${a.id}`, X[2], ya.get(`a:${a.id}`)!, a.label, undefined, !a.current))}
        </svg>
      </div>
      <p className="note" style={{ marginTop: 10 }}>
        The number on a skill counts the sources teaching it; a dot means ReStep proved it in a sandbox. Greyed elements no longer exist in{" "}
        {data.app?.current_version}.
      </p>
    </div>
  );
}
