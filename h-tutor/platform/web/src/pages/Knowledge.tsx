import { useEffect, useState } from "react";
import { AppIcon, coverStyle } from "../appIcons";
import { TutorialCard } from "../cards";
import { type LibraryEntry, type TutorialRow, navigate, useApi } from "../lib";
import { Head, I, Loading } from "../ui";

type Step = { do: string; changed: boolean; was?: { version: string; label: string | null } | null; routine: boolean; missing: boolean };
type Source = { id: string; title: string | null; kind: string | null; url: string | null; version: string | null; t?: number | null };
type Skill = { id: string; intent: string; sources: Source[]; proofs: Record<string, string>; changed: boolean; steps: Record<string, Step[]> };
type AppInfo = { id: string; name: string; versions: { id: string; label: string | null }[]; current_version: string };
type Overview = {
  global: { app: AppInfo; skills: number; sources: number; proven: number; tutorials: LibraryEntry[] }[];
  created: { app: string; skills: number }[];
};
type Hit = { id: string; intent: string; app_name: string; score: number; proof: string | null; version: { id: string }; steps: { do: string }[]; sources: Source[] };

export function KnowledgePage() {
  const { data } = useApi<Overview>("/knowledge");
  const [tab, setTab] = useState<"global" | "created">("global");
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

  const createdTotal = data?.created.reduce((a, c) => a + c.skills, 0) ?? 0;
  const globalTotal = data?.global.reduce((a, g) => a + g.skills, 0) ?? 0;

  return (
    <>
      <Head title="Knowledge" sub="Everything Rio knows when your team asks for help: the global base, and what your team created." />
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
              Created by your team<span className="count">{createdTotal}</span>
            </button>
          </div>
          {!data ? <Loading /> : tab === "global" ? <Global data={data} /> : <Created data={data} />}
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
          <p className="hero__goal">Learned from {g.sources} {g.sources === 1 ? "source" : "videos, docs and threads"}, re-targeted to each version: where every action is now, and where it used to be.</p>
        </div>
      </div>
      <div className="stats">
        <div className="stat"><div className="stat__value">{g.skills}</div><div className="stat__label">Skills</div></div>
        <div className="stat"><div className="stat__value">{g.sources}</div><div className="stat__label">Sources</div></div>
        <div className="stat"><div className="stat__value">{g.proven}</div><div className="stat__label">Proven in a sandbox</div></div>
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
            <h2>Source tutorials</h2>
            <span>What the global base learned from</span>
          </div>
          <div className="skills">
            {g.tutorials.map((t) => (
              <div className="skill" key={t.id}>
                <div className="skill__head" style={{ cursor: "default" }}>
                  <span className="source__icon"><I.Play /></span>
                  <span className="skill__name">
                    {t.title}
                    <small>{t.milestones} skills · recorded on {t.recorded_on ?? "?"}</small>
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

function Created({ data }: { data: Overview }) {
  const team = useApi<{ tutorials: TutorialRow[] }>("/tutorials");
  const published = team.data?.tutorials.filter((t) => t.status === "ready" && t.visibility !== "draft") ?? [];
  if (!team.data) return <Loading />;
  if (!published.length)
    return (
      <div className="empty">
        <b>Your team hasn't published anything yet</b>
        Published tutorials become knowledge: when someone asks Rio, Holo gets your team's way first.
        <div>
          <button className="btn btn--primary" onClick={() => navigate("/library")}>Go to the library</button>
        </div>
      </div>
    );
  return (
    <>
      <p className="note" style={{ margin: "0 0 16px" }}>
        {data.created.reduce((a, c) => a + c.skills, 0)} milestones from {published.length} published tutorials. Each one answers
        questions in Rio, before the global base and the web.
      </p>
      <div className="grid">
        {published.map((t) => (
          <TutorialCard key={t.id} t={t} />
        ))}
      </div>
    </>
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
