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
/** Below this width the sidebar becomes a top bar, and the full menu a drawer over the page. */
const PHONE = "(max-width: 860px)";

function useMedia(query: string) {
  const [match, setMatch] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const m = window.matchMedia(query);
    const change = () => setMatch(m.matches);
    change();
    m.addEventListener("change", change);
    return () => m.removeEventListener("change", change);
  }, [query]);
  return match;
}

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
  // Phones and small tablets: icons in a top bar; the logo opens the full menu as a drawer.
  const phone = useMedia(PHONE);
  const [drawer, setDrawer] = useState(false);
  const drawerOpen = phone && drawer;
  useEffect(() => setDrawer(false), [path, phone]);
  useEffect(() => {
    if (!drawerOpen) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && setDrawer(false);
    window.addEventListener("keydown", k);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", k);
      document.body.style.overflow = "";
    };
  }, [drawerOpen]);

  return (
    <div className={`shell ${collapsed ? "is-collapsed" : ""} ${drawerOpen ? "has-drawer" : ""}`}>
      <div className={`rail-slot ${!phone && !collapsed ? "is-pinned" : ""}`}>
        <Rail path={path} orgId={orgId} open={phone ? drawer : !collapsed} onToggle={phone ? () => setDrawer((d) => !d) : toggle} hover={!phone && collapsed} />
      </div>
      {drawerOpen && <div className="rail-scrim" onClick={() => setDrawer(false)} aria-hidden />}
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

function NavLink({ to, label, icon: Icon, path, count, short, className = "" }: { to: string; label: string; icon: () => React.ReactNode; path: string; count?: number; short?: boolean; className?: string }) {
  return (
    <a
      href={to}
      title={label}
      className={`rail__btn ${path.startsWith(to) ? "is-on" : ""} ${className}`}
      onClick={(e) => {
        e.preventDefault();
        navigate(to);
      }}
    >
      <Icon />
      {!short && <span className="nav__label">{label}</span>}
      {count ? <span className="nav__count">{count}</span> : null}
    </a>
  );
}

/** The sidebar, outside the app's card: icons only, or the full menu. The logo opens and closes it. */
function Rail({ path, orgId, open: pinned, onToggle, hover = false }: { path: string; orgId: string; open: boolean; onToggle: () => void; hover?: boolean }) {
  // Collapsed on a desktop: the menu opens while the pointer is over it, above the page (the logo pins it open).
  const [peek, setPeek] = useState(false);
  const open = pinned || (hover && peek);
  const user = auth.useSession().data?.user;
  const lib = useApi<{ tutorials: TutorialRow[] }>(`/tutorials?org=${orgId}`);
  const drafts = lib.data?.tutorials.filter((t) => t.visibility === "draft").length;
  const short = !open;
  return (
    <nav
      className={`rail ${open ? "is-open" : ""} ${hover && peek ? "is-peek" : ""}`}
      aria-label="Pages"
      onMouseEnter={() => hover && setPeek(true)}
      onMouseLeave={() => setPeek(false)}
    >
      <button className="rail__mark" onClick={onToggle} aria-expanded={open} aria-label={open ? "Collapse the menu" : "Expand the menu"} title={open ? "Collapse" : "Expand"}>
        <I.Mark />
        {open && <span className="rail__name">Rio</span>}
      </button>
      {open && <OrgSwitcher />}
      <button className="rail__btn rail__new" onClick={() => navigate("/home")} title="New tutorial">
        <I.Plus />
        {open && <span className="nav__label">New tutorial</span>}
      </button>
      {MAIN.map((p) => (
        <NavLink key={p.path} short={short} to={p.path} label={p.label} icon={p.icon} path={path} count={p.path === "/library" ? drafts : undefined} />
      ))}
      {open ? <div className="rail__label">Team</div> : <div className="rail__sep rail__team" />}
      {TEAM.map((p) => (
        <NavLink key={p.path} short={short} to={p.path} label={p.label} icon={p.icon} path={path} className="rail__team" />
      ))}
      <div className="rail__foot">
        <NavLink short={short} to={GET_RIO.path} label={GET_RIO.label} icon={GET_RIO.icon} path={path} />
        <div className="rail__me">
          <span title={user?.email ?? ""}>
            <Avatar name={user?.name || user?.email || "?"} />
          </span>
          {open && (
            <span className="who">
              <b>{user?.name}</b>
              <span>{user?.email}</span>
            </span>
          )}
          <button
            className="rail__btn rail__out"
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
      {/* Phones only (hidden by CSS on wider screens): an explicit menu button next to the logo's toggle. */}
      <button className="rail__btn rail__menu" onClick={onToggle} aria-expanded={open} aria-label={open ? "Close the menu" : "Open the menu"} title={open ? "Close" : "Menu"}>
        {open ? <I.Close /> : <I.PanelLeft />}
      </button>
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
