import { useMemo, useState } from "react";
import { AppIcon } from "../appIcons";
import { TutorialCard } from "../cards";
import { type TutorialRow, isLive, navigate, useApi } from "../lib";
import { Head, I, Loading } from "../ui";

const TABS = [
  { id: "all", label: "All" },
  { id: "published", label: "Published" },
  { id: "draft", label: "Drafts" },
] as const;

const polling = (d: { tutorials: TutorialRow[] }) => d.tutorials.some(isLive);

export function LibraryPage() {
  const { data, error } = useApi<{ tutorials: TutorialRow[] }>("/tutorials", polling);
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("all");
  const [app, setApp] = useState<string | null>(null);
  const all = data?.tutorials ?? [];
  const apps = useMemo(() => [...new Set(all.map((t) => t.app).filter(Boolean))] as string[], [all]);
  const count = (id: string) => all.filter((t) => match(t, id)).length;
  const shown = all.filter((t) => match(t, tab) && (!app || t.app === app));

  return (
    <>
      <Head title="Library" sub="Everything your team made. Publish a draft when it is ready to teach.">
        <button className="btn btn--primary" onClick={() => navigate("/home")}>
          <I.Plus /> New tutorial
        </button>
      </Head>
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={tab === t.id ? "is-on" : ""} onClick={() => setTab(t.id)}>
            {t.label}
            {data && <span className="count">{count(t.id)}</span>}
          </button>
        ))}
      </div>
      {apps.length > 1 && (
        <div className="chips" style={{ marginBottom: 18 }}>
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
      ) : (
        <div className="grid">
          {shown.map((t) => (
            <TutorialCard key={t.id} t={t} />
          ))}
          <button className="card card--new" onClick={() => navigate("/home")}>
            <I.Plus />
            New tutorial
          </button>
        </div>
      )}
    </>
  );
}

function match(t: TutorialRow, tab: string) {
  if (tab === "published") return t.visibility !== "draft";
  if (tab === "draft") return t.visibility === "draft";
  return true;
}
