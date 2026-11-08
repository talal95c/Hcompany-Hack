import { StrictMode, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Avatar } from "./cards";
import { type TutorialRow, auth, initials, navigate, usePath, useApi } from "./lib";
import { AuthPage, InvitePage, OnboardingPage } from "./pages/Auth";
import { CommunityPage } from "./pages/Community";
import { GetRioPage } from "./pages/GetRio";
import { HomePage } from "./pages/Home";
import { KnowledgePage } from "./pages/Knowledge";
import { LibraryPage } from "./pages/Library";
import { MembersPage } from "./pages/Members";
import { TokensPage } from "./pages/Tokens";
import { TutorialPage } from "./pages/Tutorial";
import { UsagePage } from "./pages/Usage";
import { I } from "./ui";
import "./styles.css";

const MAIN = [
  { path: "/home", label: "Home", icon: I.Home },
  { path: "/library", label: "Library", icon: I.Book },
  { path: "/community", label: "Community", icon: I.Globe },
  { path: "/knowledge", label: "Knowledge", icon: I.Layers },
];
const TEAM = [
  { path: "/members", label: "Members", icon: I.Users },
  { path: "/usage", label: "Insights", icon: I.Chart },
  { path: "/settings", label: "Settings", icon: I.Gear },
];
const GET_RIO = { path: "/get-rio", label: "Get the Mac app", icon: I.Download };

function App() {
  const path = usePath();
  const session = auth.useSession();
  const orgs = auth.useListOrganizations();
  const active = auth.useActiveOrganization();
  const spin = <div className="center"><span className="spinner" /></div>;

  if (session.isPending) return spin;
  const invite = path.match(/^\/invite\/([\w-]+)/)?.[1];
  if (!session.data) return <AuthPage mode={path === "/sign-up" || invite ? "sign-up" : "sign-in"} invite={!!invite} />;
  if (invite) return <InvitePage id={invite} />;
  if (path === "/new-organization") return <OnboardingPage again />;
  if (orgs.isPending || active.isPending) return spin;
  if (!active.data) {
    if (orgs.data?.length) {
      auth.organization.setActive({ organizationId: orgs.data[0]!.id });
      return spin;
    }
    return <OnboardingPage />;
  }
  return <Shell path={path} orgId={active.data.id} />;
}

function Shell({ path, orgId }: { path: string; orgId: string }) {
  const known = [...MAIN, ...TEAM, GET_RIO].some((p) => path.startsWith(p.path)) || path.startsWith("/t/");
  useEffect(() => {
    if (!known) navigate("/home", true);
  }, [known]);
  const me = useApi<{ role: string; canManage: boolean }>(`/me?org=${orgId}`);
  const canManage = !!me.data?.canManage;
  const tid = path.match(/^\/t\/([\w-]+)/)?.[1];
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("rio.side") === "collapsed";
    } catch {
      return false;
    }
  });
  const toggle = () =>
    setCollapsed((c) => {
      try {
        localStorage.setItem("rio.side", c ? "open" : "collapsed");
      } catch {
        // private mode: the choice lasts for this visit only
      }
      return !c;
    });

  return (
    <div className={`shell ${collapsed ? "is-collapsed" : ""}`}>
      <Rail path={path} collapsed={collapsed} onToggle={toggle} />
      <div className="frame">
        <Panel path={path} orgId={orgId} />
        <main className="main">
        <div className="page" key={`${orgId}-${tid ?? path}`}>
          {tid ? (
            <TutorialPage id={tid} />
          ) : path.startsWith("/library") ? (
            <LibraryPage />
          ) : path.startsWith("/community") ? (
            <CommunityPage />
          ) : path.startsWith("/knowledge") ? (
            <KnowledgePage canManage={canManage} />
          ) : path.startsWith("/members") ? (
            <MembersPage canManage={canManage} />
          ) : path.startsWith("/settings") ? (
            <TokensPage canManage={canManage} />
          ) : path.startsWith("/get-rio") ? (
            <GetRioPage />
          ) : path.startsWith("/usage") ? (
            <UsagePage />
          ) : (
            <HomePage />
          )}
        </div>
      </main>
      </div>
    </div>
  );
}

function NavLink({ to, label, icon: Icon, path, count, rail }: { to: string; label: string; icon: () => React.ReactNode; path: string; count?: number; rail?: boolean }) {
  return (
    <a
      href={to}
      title={label}
      className={`${rail ? "rail__btn" : "nav"} ${path.startsWith(to) ? "is-on" : ""}`}
      onClick={(e) => {
        e.preventDefault();
        navigate(to);
      }}
    >
      <Icon />
      {!rail && <span className="nav__label">{label}</span>}
      {count ? <span className="nav__count">{count}</span> : null}
    </a>
  );
}

/** The icon rail, outside the app's card (Codex-style): pages, the panel toggle, install, account. */
function Rail({ path, collapsed, onToggle }: { path: string; collapsed: boolean; onToggle: () => void }) {
  const user = auth.useSession().data?.user;
  return (
    <nav className="rail" aria-label="Pages">
      <span className="rail__mark" aria-hidden>
        <I.Mark />
      </span>
      <button className={`rail__btn ${collapsed ? "" : "is-soft"}`} onClick={onToggle} aria-label={collapsed ? "Show the panel" : "Hide the panel"} title={collapsed ? "Show the panel" : "Hide the panel"}>
        <I.PanelLeft />
      </button>
      <div className="rail__sep" />
      {MAIN.map((p) => (
        <NavLink key={p.path} rail to={p.path} label={p.label} icon={p.icon} path={path} />
      ))}
      <div className="rail__sep" />
      {TEAM.map((p) => (
        <NavLink key={p.path} rail to={p.path} label={p.label} icon={p.icon} path={path} />
      ))}
      <div className="rail__foot">
        <NavLink rail to={GET_RIO.path} label={GET_RIO.label} icon={GET_RIO.icon} path={path} />
        <button
          className="rail__btn"
          title="Sign out"
          aria-label="Sign out"
          onClick={async () => {
            await auth.signOut();
            navigate("/sign-in", true);
          }}
        >
          <I.Logout />
        </button>
        <span title={user?.email ?? ""}>
          <Avatar name={user?.name || user?.email || "?"} />
        </span>
      </div>
    </nav>
  );
}

/** The panel inside the card: workspace, new tutorial, the team's recent tutorials. */
function Panel({ path, orgId }: { path: string; orgId: string }) {
  const lib = useApi<{ tutorials: TutorialRow[] }>(`/tutorials?org=${orgId}`);
  const recent = lib.data?.tutorials.slice(0, 12) ?? [];
  const page = [...MAIN, ...TEAM, GET_RIO].find((p) => path.startsWith(p.path));
  return (
    <aside className="panel">
      <OrgSwitcher />
      <button className="panel__row panel__new" onClick={() => navigate("/home")}>
        <I.Edit /> New tutorial
      </button>
      {page && page.path !== "/home" && <div className="panel__here">{page.label}</div>}
      <div className="panel__label">Recent tutorials</div>
      {lib.data && recent.length === 0 && <p className="panel__empty">Nothing yet. Paste a link on Home to make the first one.</p>}
      {recent.map((t) => (
        <a
          key={t.id}
          href={`/t/${t.id}`}
          className={`panel__row panel__item ${path === `/t/${t.id}` ? "is-on" : ""}`}
          onClick={(e) => {
            e.preventDefault();
            navigate(`/t/${t.id}`);
          }}
          title={t.title || t.input}
        >
          <span className="panel__text">{t.title || t.input}</span>
          {t.visibility === "draft" && <span className="panel__dot" aria-label="Draft" />}
        </a>
      ))}
      {recent.length > 0 && (
        <button className="panel__row panel__more" onClick={() => navigate("/library")}>
          Show all
        </button>
      )}
    </aside>
  );
}

function OrgSwitcher() {
  const orgs = auth.useListOrganizations();
  const active = auth.useActiveOrganization();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const name = active.data?.name ?? "…";
  return (
    <div className="org" ref={ref}>
      <button className="org__btn" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className="org__logo">{initials(name).slice(0, 1)}</span>
        <span className="org__name">{name}</span>
        <I.Chevron />
      </button>
      {open && (
        <div className="menu">
          {orgs.data?.map((o) => (
            <button
              key={o.id}
              onClick={async () => {
                setOpen(false);
                if (o.id !== active.data?.id) await auth.organization.setActive({ organizationId: o.id });
              }}
            >
              <span className="org__logo" style={o.id === active.data?.id ? undefined : { background: "var(--soft)", color: "var(--dim)" }}>
                {initials(o.name).slice(0, 1)}
              </span>
              {o.name}
            </button>
          ))}
          <hr />
          <button
            onClick={() => {
              setOpen(false);
              navigate("/new-organization");
            }}
          >
            <I.Plus /> New workspace
          </button>
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
