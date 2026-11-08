import { useEffect, useRef, useState } from "react";
import { AppIcon, coverStyle } from "../appIcons";
import { Avatar, VIS } from "../cards";
import { type RioTutorial, type TutorialRow, type Visibility, ago, api, auth, isLive, navigate, useApi } from "../lib";
import { I, Loading } from "../ui";

type Milestone = RioTutorial["milestones"][number];

const STAGES: Record<TutorialRow["kind"], { id: string; label: string }[]> = {
  youtube: [
    { id: "queued", label: "Fetching the video" },
    { id: "transcribing", label: "Listening to the video (Gladia)" },
    { id: "designing", label: "Writing the milestones (Holo)" },
  ],
  page: [
    { id: "queued", label: "Reading the page and finding the app" },
    { id: "browsing", label: "H's web agent is reading the guide" },
    { id: "designing", label: "Writing the milestones (Holo)" },
  ],
  goal: [
    { id: "queued", label: "Finding the app" },
    { id: "browsing", label: "H's web agent is reading the official docs" },
    { id: "designing", label: "Writing the milestones (Holo)" },
  ],
};

export function TutorialPage({ id }: { id: string }) {
  const { data: t, error, reload } = useApi<TutorialRow>(`/tutorials/${id}`, isLive, 2500);
  const [toast, setToast] = useState<string | null>(null);
  const say = (m: string) => {
    setToast(m);
    setTimeout(() => setToast(null), 2200);
  };

  if (error) return <div className="empty"><b>Tutorial not found</b>It may have been deleted, or it belongs to another team.</div>;
  if (!t) return <Loading />;

  return (
    <div className="page--narrow" style={{ margin: "0 auto" }}>
      <button className="back" onClick={() => history.length > 1 ? history.back() : navigate("/library")}>
        <I.Back /> Back
      </button>
      {isLive(t) ? (
        <Working t={t} />
      ) : t.status === "failed" ? (
        <Failed t={t} onRetry={reload} />
      ) : (
        <Ready t={t} reload={reload} say={say} />
      )}
      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}

function Working({ t }: { t: TutorialRow }) {
  const stages = STAGES[t.kind];
  const at = Math.max(0, stages.findIndex((s) => s.id === t.status));
  return (
    <>
      <div className="hero">
        <div className={`hero__cover ${t.thumbnail ? "hero__cover--video" : ""}`} style={coverStyle(t.app)}>
          {t.thumbnail && <img className="hero__thumb" src={t.thumbnail} alt="" />}
          <AppIcon name={t.app} />
        </div>
        <div className="hero__body">
          <h1 className="hero__title">{t.title ?? "New tutorial"}</h1>
          <p className="hero__goal">{t.input}</p>
        </div>
      </div>
      <div className="progress" style={{ marginTop: 16 }}>
        <h3>Rio is making your tutorial</h3>
        <ol>
          {stages.map((s, i) => (
            <li key={s.id} className={i < at ? "is-done" : i === at ? "is-now" : ""}>
              <span className="dot">{i < at && <I.Check />}</span>
              {s.label}
            </li>
          ))}
          <li>
            <span className="dot" />
            Ready to review
          </li>
        </ol>
        <p className="note" style={{ margin: "18px 0 0" }}>
          {t.status === "browsing" ? "The agent browses like a person: a few minutes. " : "Usually under a minute. "}
          You can leave this page: it keeps going.
          {t.agentViewUrl && (
            <>
              {" "}
              <a className="link" href={t.agentViewUrl} target="_blank" rel="noreferrer">
                Watch the agent live ↗
              </a>
            </>
          )}
        </p>
      </div>
    </>
  );
}

function Failed({ t, onRetry }: { t: TutorialRow; onRetry: () => void }) {
  return (
    <div className="empty" style={{ textAlign: "left" }}>
      <b>Rio couldn't make this tutorial</b>
      <p style={{ margin: "4px 0 0" }}>{t.error}</p>
      <p className="faint" style={{ margin: "6px 0 0", fontSize: 13 }}>{t.input}</p>
      {t.canEdit && (
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn--primary" onClick={async () => { await api(`/tutorials/${t.id}/retry`, { method: "POST" }); onRetry(); }}>
            Try again
          </button>
          <button className="btn btn--ghost btn--danger" onClick={async () => { await api(`/tutorials/${t.id}`, { method: "DELETE" }); navigate("/library", true); }}>
            Delete
          </button>
        </div>
      )}
    </div>
  );
}

function Ready({ t, reload, say }: { t: TutorialRow; reload: () => void; say: (m: string) => void }) {
  const tut = t.tutorial!;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<RioTutorial>(tut);
  const [saving, setSaving] = useState(false);
  const [liked, setLiked] = useState({ on: t.liked, n: t.likes });
  const activeOrg = auth.useActiveOrganization().data?.name;
  const fromElsewhere = !t.canEdit && t.org !== activeOrg;

  async function save() {
    setSaving(true);
    try {
      await api(`/tutorials/${t.id}`, { method: "PATCH", json: { title: draft.title, goal: draft.goal, milestones: draft.milestones } });
      setEditing(false);
      reload();
      say("Saved");
    } catch (e) {
      say((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="hero">
        <div className={`hero__cover ${t.thumbnail ? "hero__cover--video" : ""}`} style={coverStyle(t.app)}>
          {t.thumbnail && <img className="hero__thumb" src={t.thumbnail} alt="" />}
          <AppIcon name={t.app} />
        </div>
        <div className="hero__body">
          {editing ? (
            <>
              <input className="hero__title-input" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} aria-label="Title" />
              <textarea className="textarea hero__goal-input" rows={2} value={draft.goal} onChange={(e) => setDraft({ ...draft, goal: e.target.value })} aria-label="Goal" />
            </>
          ) : (
            <>
              <h1 className="hero__title">{tut.title}</h1>
              <p className="hero__goal">{tut.goal}</p>
              <Credit t={t} />
            </>
          )}
          <div className="hero__by">
            <span className="person">
              <Avatar name={t.author.name} size="sm" />
              {t.author.name ?? "Someone"}
            </span>
            {fromElsewhere && t.org && <span>at {t.org}</span>}
            <span>{t.publishedAt ? `Published ${ago(t.publishedAt).toLowerCase()}` : `Created ${ago(t.createdAt).toLowerCase()}`}</span>
            <span>{tut.milestones.length} milestones</span>
            {t.learners > 0 && <span>{t.learners} learners</span>}
            {t.remixes > 0 && <span>Remixed {t.remixes}×</span>}
            {t.remixOfTutorial && (
              <a className="link" href={`/t/${t.remixOfTutorial.id}`} onClick={(e) => { e.preventDefault(); navigate(`/t/${t.remixOfTutorial!.id}`); }}>
                Remixed from {t.remixOfTutorial.title}
              </a>
            )}
          </div>
          <div className="hero__actions">
            {editing ? (
              <>
                <button className="btn btn--primary" onClick={save} disabled={saving}>
                  {saving ? <span className="spinner" /> : "Save changes"}
                </button>
                <button className="btn btn--ghost" onClick={() => { setDraft(tut); setEditing(false); }}>
                  Cancel
                </button>
              </>
            ) : (
              <>
                {t.canEdit && <Publish t={t} onChange={(v) => { reload(); say(v === "draft" ? "Back to draft" : v === "team" ? "Published to your team: Rio offers it now" : "Shared with the community"); }} />}
                {fromElsewhere && (
                  <button className="btn btn--primary" onClick={async () => { const r = await api<{ id: string }>(`/tutorials/${t.id}/remix`, { method: "POST" }); navigate(`/t/${r.id}`); }}>
                    <I.Remix /> Remix for my team
                  </button>
                )}
                <button
                  className={`btn like ${liked.on ? "is-on" : ""}`}
                  onClick={async () => { const r = await api<{ liked: boolean; likes: number }>(`/tutorials/${t.id}/like`, { method: "POST" }); setLiked({ on: r.liked, n: r.likes }); }}
                  aria-pressed={liked.on}
                >
                  <I.Heart /> {liked.n > 0 ? liked.n : "Like"}
                </button>
                {t.canEdit && (
                  <button className="btn" onClick={() => { setDraft(tut); setEditing(true); }}>
                    <I.Edit /> Edit
                  </button>
                )}
                {t.canEdit && (
                  <button
                    className="btn btn--ghost btn--danger"
                    style={{ marginLeft: "auto" }}
                    onClick={async () => { if (confirm(`Delete “${tut.title}”?`)) { await api(`/tutorials/${t.id}`, { method: "DELETE" }); navigate("/library", true); } }}
                  >
                    Delete
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      <div className="section" style={{ marginTop: 28 }}>
        <div className="section__title">
          <h2>Milestones</h2>
          <span>Rio checks each one on the learner's screen before moving on</span>
        </div>
        {editing ? <EditSteps steps={draft.milestones} onChange={(m) => setDraft({ ...draft, milestones: m })} /> : <Steps t={t} />}
      </div>

      {t.sources.length > 0 && (
        <div className="section" style={{ marginTop: 28 }}>
          <div className="section__title">
            <h2>Sources</h2>
          </div>
          <div className="sources">
            {t.sources.map((s) =>
              s.url ? (
                <a key={s.url} className="source" href={s.url} target="_blank" rel="noreferrer">
                  {s.image ? (
                    <img className="source__thumb" src={s.image} alt="" loading="lazy" referrerPolicy="no-referrer" onError={(e) => (e.currentTarget.style.display = "none")} />
                  ) : (
                    <span className="source__icon">{t.kind === "youtube" ? <I.Play /> : <I.Page />}</span>
                  )}
                  <span className="source__text">
                    {s.title || s.url}
                    {s.site && <small>{s.site}</small>}
                  </span>
                  <span className="faint" style={{ marginLeft: "auto" }}>↗</span>
                </a>
              ) : (
                <div key={s.title} className="source">
                  <span className="source__icon"><I.Search /></span>
                  <span className="dim">{s.title}</span>
                </div>
              ),
            )}
          </div>
        </div>
      )}
    </>
  );
}

function Steps({ t }: { t: TutorialRow }) {
  const video = (s?: number) => (t.kind === "youtube" && s != null ? `${t.input}${t.input.includes("?") ? "&" : "?"}t=${s}s` : null);
  return (
    <ol className="steps">
      {t.tutorial!.milestones.map((m, i) => {
        const at = video(m.video_at);
        return (
          <li className="step" key={m.id}>
            <span className="step__n">{i + 1}</span>
            <div>
              <div className="step__goal">{m.goal}</div>
              <div className="step__done">
                <b>Done when</b> {m.done_when.charAt(0).toLowerCase() + m.done_when.slice(1)}
              </div>
              {!!m.hints?.length && (
                <div className="hints">
                  {m.hints.map((h) => (
                    <span className="hint" key={h}>{h}</span>
                  ))}
                </div>
              )}
              {m.teach && <div className="step__teach">{m.teach}</div>}
              {at && (
                <a className="link" href={at} target="_blank" rel="noreferrer" style={{ display: "inline-block", marginTop: 10 }}>
                  Watch at {Math.floor(m.video_at! / 60)}:{String(m.video_at! % 60).padStart(2, "0")} ↗
                </a>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function EditSteps({ steps, onChange }: { steps: Milestone[]; onChange: (m: Milestone[]) => void }) {
  const set = (i: number, patch: Partial<Milestone>) => onChange(steps.map((m, j) => (j === i ? { ...m, ...patch } : m)));
  const move = (i: number, d: number) => {
    const next = [...steps];
    const [m] = next.splice(i, 1);
    next.splice(i + d, 0, m!);
    onChange(next);
  };
  return (
    <ol className="steps">
      {steps.map((m, i) => (
        <li className="step" key={`${m.id}-${i}`}>
          <span className="step__n">{i + 1}</span>
          <div className="step__edit">
            <input className="input" value={m.goal} onChange={(e) => set(i, { goal: e.target.value })} placeholder="What the learner does, e.g. “Add a torus”" aria-label="Milestone goal" />
            <input className="input" value={m.done_when} onChange={(e) => set(i, { done_when: e.target.value })} placeholder="Done when… (what Rio sees on screen)" aria-label="Done when" />
            <textarea
              className="textarea"
              rows={2}
              value={(m.hints ?? []).join("\n")}
              onChange={(e) => set(i, { hints: e.target.value.split("\n") })}
              placeholder="Hints, one per line: menu paths, shortcuts"
              aria-label="Hints"
            />
            <input className="input" value={m.teach ?? ""} onChange={(e) => set(i, { teach: e.target.value })} placeholder="Something worth explaining (optional)" aria-label="Lesson" />
            <div className="step__tools">
              <button className="btn btn--sm btn--ghost" disabled={i === 0} onClick={() => move(i, -1)}>Move up</button>
              <button className="btn btn--sm btn--ghost" disabled={i === steps.length - 1} onClick={() => move(i, 1)}>Move down</button>
              <button className="btn btn--sm btn--ghost btn--danger" style={{ marginLeft: "auto" }} onClick={() => onChange(steps.filter((_, j) => j !== i))}>
                Remove
              </button>
            </div>
          </div>
        </li>
      ))}
      <button className="card card--new" style={{ minHeight: 64 }} onClick={() => onChange([...steps, { id: `m${steps.length + 1}`, goal: "", done_when: "", hints: [] }])}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <I.Plus /> Add a milestone
        </span>
      </button>
    </ol>
  );
}

function Publish({ t, onChange }: { t: TutorialRow; onChange: (v: Visibility) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const current = VIS[t.visibility];
  async function choose(v: Visibility) {
    setOpen(false);
    if (v === t.visibility) return;
    await api(`/tutorials/${t.id}`, { method: "PATCH", json: { visibility: v } });
    onChange(v);
  }
  return (
    <div className="publish" ref={ref}>
      <button className={`btn ${t.visibility === "draft" ? "btn--primary" : ""}`} onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <current.icon />
        {t.visibility === "draft" ? "Publish" : current.label}
      </button>
      {open && (
        <div className="menu">
          {(Object.keys(VIS) as Visibility[]).map((v) => {
            const o = VIS[v];
            return (
              <button key={v} onClick={() => choose(v)}>
                <o.icon />
                <span>
                  <b>{v === "draft" ? "Keep as draft" : o.label}</b>
                  <span className="menu__hint">{o.hint}</span>
                </span>
                {v === t.visibility && <span className="check"><I.Check /></span>}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** Credit to the video a tutorial was made from: its title, its author, a link to watch it. */
function Credit({ t }: { t: TutorialRow }) {
  if (t.kind !== "youtube") return null;
  const c = t.tutorial?.credit;
  const [srcTitle, srcAuthor] = (t.sources[0]?.title ?? "").split(" · ");
  const title = c?.title ?? srcTitle;
  const author = c?.author ?? srcAuthor;
  return (
    <p className="credit">
      <I.Play /> From the video{" "}
      <a className="link" href={c?.url ?? t.input} target="_blank" rel="noreferrer">
        {title ? `“${title}”` : "on YouTube"} ↗
      </a>
      {author ? ` by ${author}` : ""}
    </p>
  );
}
