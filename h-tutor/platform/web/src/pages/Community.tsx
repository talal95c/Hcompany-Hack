import { useMemo, useState } from "react";
import { AppIcon } from "../appIcons";
import { TutorialCard } from "../cards";
import { type TutorialRow, useApi } from "../lib";
import { Head, I, Loading } from "../ui";

const SORTS = [
  { id: "popular", label: "Popular" },
  { id: "new", label: "Newest" },
] as const;

export function CommunityPage() {
  const { data, error } = useApi<{ tutorials: TutorialRow[] }>("/community");
  const [q, setQ] = useState("");
  const [app, setApp] = useState<string | null>(null);
  const [sort, setSort] = useState<"popular" | "new">("popular");
  const all = data?.tutorials ?? [];
  const apps = useMemo(() => [...new Set(all.map((t) => t.app).filter(Boolean))] as string[], [all]);
  const shown = all
    .filter((t) => (!app || t.app === app) && `${t.title} ${t.app} ${t.tutorial?.goal ?? ""}`.toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => (sort === "new" ? (b.publishedAt ?? 0) - (a.publishedAt ?? 0) : b.likes + b.learners - (a.likes + a.learners)));

  return (
    <>
      <Head title="Community" sub="Tutorials other teams shared. Learn them, like them, remix them for your team." />
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 18 }}>
        <div className="ask" style={{ flex: "1 1 320px" }}>
          <I.Search />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search community tutorials" aria-label="Search community tutorials" />
        </div>
        <div className="seg" role="group" aria-label="Sort">
          {SORTS.map((s) => (
            <button key={s.id} className={sort === s.id ? "is-on" : ""} onClick={() => setSort(s.id)}>
              {s.label}
            </button>
          ))}
        </div>
      </div>
      {apps.length > 0 && (
        <div className="chips" style={{ marginBottom: 20 }}>
          <button className={`chip ${!app ? "is-on" : ""}`} onClick={() => setApp(null)}>
            All apps
          </button>
          {apps.map((a) => (
            <button key={a} className={`chip ${app === a ? "is-on" : ""}`} onClick={() => setApp(app === a ? null : a)}>
              <AppIcon name={a} /> {a}
            </button>
          ))}
        </div>
      )}
      {error ? (
        <div className="error">{error}</div>
      ) : !data ? (
        <Loading />
      ) : shown.length === 0 ? (
        <div className="empty">
          <b>{all.length ? "No match" : "The community is just getting started"}</b>
          {all.length ? "Try another word or app." : "Open one of your tutorials and choose “Share with the community” to be the first."}
        </div>
      ) : (
        <div className="grid">
          {shown.map((t) => (
            <TutorialCard key={t.id} t={t} showOrg />
          ))}
        </div>
      )}
    </>
  );
}
