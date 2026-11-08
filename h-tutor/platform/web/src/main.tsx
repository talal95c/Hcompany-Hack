import { StrictMode, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
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

  return (
    <div className="shell">
      <Sidebar path={path} orgId={orgId} />
      <div className="frame">
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

function NavLink({ to, label, icon: Icon, path, count }: { to: string; label: string; icon: () => ReactNode; path: string; count?: number }) {
  return (
    <a
      href={to}
      title={label}
      className={`sb__link ${path.startsWith(to) ? "is-on" : ""}`}
      onClick={(e) => {
        e.preventDefault();
        navigate(to);
      }}
    >
      <Icon />
      <span className="sb__label">{label}</span>
      {count ? <span className="nav__count">{count}</span> : null}
    </a>
  );
}

/** 60 px of icons that widens to the full menu while hovered; on phones, a menu button and a sheet. */
function Sidebar({ path, orgId }: { path: string; orgId: string }) {
  const [open, setOpen] = useState(false);
  const [sheet, setSheet] = useState<"closed" | "open" | "closing">("closed");
  const closeSheet = () => {
    setSheet("closing");
    window.setTimeout(() => setSheet("closed"), 300);
  };
  useEffect(() => {
    setSheet((s) => (s === "open" ? "closing" : s));
    const t = window.setTimeout(() => setSheet((s) => (s === "closing" ? "closed" : s)), 300);
    return () => window.clearTimeout(t);
  }, [path]);
  return (
    <>
      <div className="sb-slot">
        <nav className={`sb ${open ? "is-open" : ""}`} aria-label="Pages" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
          <SidebarContent path={path} orgId={orgId} />
        </nav>
      </div>
      <div className="mbar">
        <span className="mbar__brand">
          <I.Mark /> Rio
        </span>
        <button className="mbar__menu" onClick={() => (sheet === "open" ? closeSheet() : setSheet("open"))} aria-label="Open the menu" aria-expanded={sheet === "open"}>
          <I.Menu />
        </button>
        {sheet !== "closed" && (
          <nav className={`msheet ${sheet === "closing" ? "is-closing" : ""}`} aria-label="Pages">
            <button className="msheet__close" onClick={closeSheet} aria-label="Close the menu">
              <I.Close />
            </button>
            <div className="sb is-open">
              <SidebarContent path={path} orgId={orgId} />
            </div>
          </nav>
        )}
      </div>
    </>
  );
}

function SidebarContent({ path, orgId }: { path: string; orgId: string }) {
  const user = auth.useSession().data?.user;
  const lib = useApi<{ tutorials: TutorialRow[] }>(`/tutorials?org=${orgId}`);
  const drafts = lib.data?.tutorials.filter((t) => t.visibility === "draft").length;
  return (
    <>
      <a
        href="/home"
        className="sb__mark"
        onClick={(e) => {
          e.preventDefault();
          navigate("/home");
        }}
      >
        <I.Mark />
        <span className="sb__label sb__name">Rio</span>
      </a>
      <OrgSwitcher />
      <button className="sb__link sb__new" onClick={() => navigate("/home")} title="New tutorial">
        <I.Plus />
        <span className="sb__label">New tutorial</span>
      </button>
      {MAIN.map((p) => (
        <NavLink key={p.path} to={p.path} label={p.label} icon={p.icon} path={path} count={p.path === "/library" ? drafts : undefined} />
      ))}
      <div className="sb__group">
        <span className="sb__label">Team</span>
      </div>
      {TEAM.map((p) => (
        <NavLink key={p.path} to={p.path} label={p.label} icon={p.icon} path={path} />
      ))}
      <div className="sb__foot">
        <NavLink to={GET_RIO.path} label={GET_RIO.label} icon={GET_RIO.icon} path={path} />
        <div className="sb__me">
          <span title={user?.email ?? ""}>
            <Avatar name={user?.name || user?.email || "?"} />
          </span>
          <span className="who sb__label">
            <b>{user?.name}</b>
            <span>{user?.email}</span>
          </span>
          <button
            className="sb__out sb__label"
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
      </div>
    </>
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
