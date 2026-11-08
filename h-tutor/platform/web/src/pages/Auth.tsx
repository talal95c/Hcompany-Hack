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

function GoogleLogo() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  );
}

// Google sends errors back as ?error=<code> on the page that started the sign-in.
function errorFromUrl(): string | null {
  const code = new URLSearchParams(window.location.search).get("error");
  if (!code) return null;
  return code === "access_denied" ? "Google sign-in was cancelled" : `Google sign-in failed (${code})`;
}

export function AuthPage({ mode, invite }: { mode: "sign-in" | "sign-up"; invite?: boolean }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(errorFromUrl);
  const [busy, setBusy] = useState(false);
  const [m, setM] = useState(mode);
  const [google, setGoogle] = useState(false);

  useEffect(() => {
    fetch("/api/providers")
      .then((r) => (r.ok ? r.json() : null))
      .then((p: { google?: boolean } | null) => setGoogle(!!p?.google))
      .catch(() => setGoogle(false));
  }, []);

  async function withGoogle() {
    setBusy(true);
    setError(null);
    // Back to the invitation after Google, otherwise to the console.
    const here = window.location.pathname;
    const r = await auth.signIn.social({ provider: "google", callbackURL: invite ? here : "/home", errorCallbackURL: here });
    // On success the browser leaves for Google; we only get here on an error.
    if (r?.error) {
      setBusy(false);
      setError(r.error.message ?? "Could not reach Google");
    }
  }

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
          {google && (
            <>
              <button type="button" className="btn btn--block auth__google" onClick={withGoogle} disabled={busy}>
                <GoogleLogo />
                Continue with Google
              </button>
              <div className="auth__or">or</div>
            </>
          )}
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
