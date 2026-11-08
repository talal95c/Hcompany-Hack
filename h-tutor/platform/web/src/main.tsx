import { StrictMode, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Avatar } from "./cards";
import { type TutorialRow, auth, initials, navigate, usePath, useApi } from "./lib";
import { AuthPage, InvitePage, OnboardingPage } from "./pages/Auth";
import { CommunityPage } from "./pages/Community";
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
  const known = [...MAIN, ...TEAM].some((p) => path.startsWith(p.path)) || path.startsWith("/t/");
  useEffect(() => {
    if (!known) navigate("/home", true);
  }, [known]);
  const me = useApi<{ role: string; canManage: boolean }>(`/me?org=${orgId}`);
  const canManage = !!me.data?.canManage;
  const tid = path.match(/^\/t\/([\w-]+)/)?.[1];

  return (
    <div className="shell">
      <Sidebar path={path} orgId={orgId} />
      <main className="main">
        <div className="page" key={`${orgId}-${tid ?? path}`}>
          {tid ? (
            <TutorialPage id={tid} />
          ) : path.startsWith("/library") ? (
            <LibraryPage />
          ) : path.startsWith("/community") ? (
            <CommunityPage />
          ) : path.startsWith("/knowledge") ? (
            <KnowledgePage />
          ) : path.startsWith("/members") ? (
            <MembersPage canManage={canManage} />
          ) : path.startsWith("/settings") ? (
            <TokensPage canManage={canManage} />
          ) : path.startsWith("/usage") ? (
            <UsagePage />
          ) : (
            <HomePage />
          )}
        </div>
      </main>
    </div>
  );
}

function NavLink({ to, label, icon: Icon, path, count }: { to: string; label: string; icon: () => React.ReactNode; path: string; count?: number }) {
  return (
    <a
      href={to}
      className={`nav ${path.startsWith(to) ? "is-on" : ""}`}
      onClick={(e) => {
        e.preventDefault();
        navigate(to);
      }}
    >
      <Icon />
      {label}
      {count ? <span className="nav__count">{count}</span> : null}
    </a>
  );
}

function Sidebar({ path, orgId }: { path: string; orgId: string }) {
  const user = auth.useSession().data?.user;
  const lib = useApi<{ tutorials: TutorialRow[] }>(`/tutorials?org=${orgId}`);
  const drafts = lib.data?.tutorials.filter((t) => t.visibility === "draft").length;
  return (
    <nav className="side">
      <div className="brand">
        <span className="brand__mark">
          <I.Mark />
        </span>
        Rio
      </div>
      <OrgSwitcher />
      <button className="btn btn--primary side__new" onClick={() => navigate("/home")}>
        <I.Plus /> New tutorial
      </button>
      {MAIN.map((p) => (
        <NavLink key={p.path} to={p.path} label={p.label} icon={p.icon} path={path} count={p.path === "/library" ? drafts : undefined} />
      ))}
      <div className="side__label">Team</div>
      {TEAM.map((p) => (
        <NavLink key={p.path} to={p.path} label={p.label} icon={p.icon} path={path} />
      ))}
      <div className="side__foot">
        <Avatar name={user?.name || user?.email || "?"} />
        <span className="who">
          <b>{user?.name}</b>
          <span>{user?.email}</span>
        </span>
        <button
          className="btn btn--ghost btn--sm"
          title="Sign out"
          aria-label="Sign out"
          onClick={async () => {
            await auth.signOut();
            navigate("/sign-in", true);
          }}
        >
          <I.Logout />
        </button>
      </div>
    </nav>
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
