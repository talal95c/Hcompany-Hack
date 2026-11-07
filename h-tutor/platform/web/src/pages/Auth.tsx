import { type FormEvent, useEffect, useState } from "react";
import { auth, navigate } from "../lib";
import { I } from "../ui";

function Brand() {
  return (
    <div className="auth__brand">
      <span className="brand__mark">
        <I.Mark />
      </span>
      Rio
    </div>
  );
}

export function AuthPage({ mode, invite }: { mode: "sign-in" | "sign-up"; invite?: boolean }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [m, setM] = useState(mode);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const r =
      m === "sign-up"
        ? await auth.signUp.email({ name: name.trim() || email.split("@")[0]!, email: email.trim(), password })
        : await auth.signIn.email({ email: email.trim(), password });
    setBusy(false);
    if (r.error) setError(r.error.message ?? "Something went wrong");
    else if (!invite) navigate("/home", true);
  }

  return (
    <div className="auth">
      <div className="auth__card">
        <Brand />
        <form className="auth__panel" onSubmit={submit}>
          <h1>{m === "sign-up" ? "Create your account" : "Welcome back"}</h1>
          <p className="sub">
            {invite
              ? "Sign in or create an account to join your team."
              : m === "sign-up"
                ? "Teach your team's software, on their screen."
                : "Sign in to the Rio console."}
          </p>
          {m === "sign-up" && (
            <div className="field">
              <label htmlFor="name">Name</label>
              <input id="name" className="input" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" placeholder="Ada Lovelace" />
            </div>
          )}
          <div className="field">
            <label htmlFor="email">Email</label>
            <input id="email" className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" placeholder="you@company.com" autoFocus />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              className="input"
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={m === "sign-up" ? "new-password" : "current-password"}
              placeholder={m === "sign-up" ? "At least 8 characters" : ""}
            />
          </div>
          {error && <div className="error">{error}</div>}
          <button className="btn btn--primary btn--block" disabled={busy}>
            {busy ? <span className="spinner" /> : m === "sign-up" ? "Create account" : "Sign in"}
          </button>
        </form>
        <div className="auth__switch">
          {m === "sign-up" ? "Already have an account? " : "New to Rio? "}
          <button
            onClick={() => {
              setM(m === "sign-up" ? "sign-in" : "sign-up");
              setError(null);
              if (!invite) navigate(m === "sign-up" ? "/sign-in" : "/sign-up", true);
            }}
          >
            {m === "sign-up" ? "Sign in" : "Create an account"}
          </button>
        </div>
      </div>
    </div>
  );
}

const slugify = (s: string) =>
  s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 40);

export function OnboardingPage({ again }: { again?: boolean }) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const base = slugify(name) || "team";
    const r = await auth.organization.create({ name: name.trim(), slug: `${base}-${Math.random().toString(36).slice(2, 6)}` });
    if (r.error || !r.data) {
      setBusy(false);
      return setError(r.error?.message ?? "Could not create the organization");
    }
    await auth.organization.setActive({ organizationId: r.data.id });
    navigate("/home", true);
  }

  return (
    <div className="auth">
      <div className="auth__card">
        <Brand />
        <form className="auth__panel" onSubmit={submit}>
          <h1>{again ? "New organization" : "Create your organization"}</h1>
          <p className="sub">Its tutorials, members and API tokens live here.</p>
          <div className="field">
            <label htmlFor="org">Organization name</label>
            <input id="org" className="input" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme Studio" autoFocus />
          </div>
          {error && <div className="error">{error}</div>}
          <button className="btn btn--primary btn--block" disabled={busy || !name.trim()}>
            {busy ? <span className="spinner" /> : "Create organization"}
          </button>
          {again && (
            <button type="button" className="btn btn--ghost btn--block" onClick={() => navigate("/home")}>
              Cancel
            </button>
          )}
        </form>
      </div>
    </div>
  );
}

type Invitation = { organizationName: string; inviterEmail: string; email: string; role: string; status: string };

export function InvitePage({ id }: { id: string }) {
  const [inv, setInv] = useState<Invitation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const session = auth.useSession();

  useEffect(() => {
    auth.organization.getInvitation({ query: { id } }).then((r) => {
      if (r.error) setError(r.error.message ?? "This invitation is not valid");
      else setInv(r.data as unknown as Invitation);
    });
  }, [id]);

  async function accept() {
    setBusy(true);
    const r = await auth.organization.acceptInvitation({ invitationId: id });
    if (r.error) {
      setBusy(false);
      return setError(r.error.message ?? "Could not join");
    }
    const orgId = (r.data as { member?: { organizationId?: string } })?.member?.organizationId;
    if (orgId) await auth.organization.setActive({ organizationId: orgId });
    navigate("/home", true);
  }

  return (
    <div className="auth">
      <div className="auth__card">
        <Brand />
        <div className="auth__panel">
          {error ? (
            <>
              <h1>Invitation unavailable</h1>
              <p className="sub">{error}</p>
              <p className="sub">
                It was sent to a specific email: you are signed in as <b>{session.data?.user.email}</b>.
              </p>
              <button className="btn btn--block" onClick={() => navigate("/home", true)}>
                Go to the console
              </button>
            </>
          ) : !inv ? (
            <div className="center" style={{ minHeight: 120 }}>
              <span className="spinner" />
            </div>
          ) : (
            <>
              <h1>Join {inv.organizationName}</h1>
              <p className="sub">
                {inv.inviterEmail} invited you as {inv.role}.
              </p>
              <button className="btn btn--primary btn--block" onClick={accept} disabled={busy}>
                {busy ? <span className="spinner" /> : `Join ${inv.organizationName}`}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
