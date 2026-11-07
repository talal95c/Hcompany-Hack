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
          <div className="seg" style={{ marginLeft: "auto" }} role="group" aria-label="Version">
            {g.app.versions.map((x) => (
              <button key={x.id} className={x.id === v ? "is-on" : ""} onClick={() => setVersion(x.id)}>
                {x.id}
              </button>
            ))}
          </div>
        </div>
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
