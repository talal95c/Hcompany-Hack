import { type FormEvent, useCallback, useEffect, useState } from "react";
import { auth, initials } from "../lib";
import { CopyButton, Head, Loading, Modal } from "../ui";

type Member = { id: string; role: string; createdAt: string | Date; user: { id: string; name: string; email: string } };
type Invitation = { id: string; email: string; role: string; status: string; expiresAt: string | Date };
type Full = { members: Member[]; invitations: Invitation[] };

const ROLES = ["member", "admin", "owner"];
const inviteLink = (id: string) => `${window.location.origin}/invite/${id}`;

export function MembersPage({ canManage }: { canManage: boolean }) {
  const [org, setOrg] = useState<Full | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [inviting, setInviting] = useState(false);
  const [link, setLink] = useState<{ email: string; url: string } | null>(null);
  const me = auth.useSession().data?.user.id;

  const load = useCallback(async () => {
    const r = await auth.organization.getFullOrganization();
    if (r.error) setError(r.error.message ?? "Could not load the organization");
    else setOrg(r.data as unknown as Full);
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const run = async (p: Promise<{ error: { message?: string } | null }>) => {
    const r = await p;
    if (r.error) alert(r.error.message ?? "Something went wrong");
    load();
  };

  const pending = org?.invitations.filter((i) => i.status === "pending") ?? [];
  return (
    <>
      <Head title="Members" sub="People who manage tutorials and see usage.">
        {canManage && (
          <button className="btn btn--light" onClick={() => setInviting(true)}>
            Invite member
          </button>
        )}
      </Head>
      {error ? (
        <div className="error">{error}</div>
      ) : !org ? (
        <Loading />
      ) : (
        <>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Member</th>
                  <th>Role</th>
                  <th>Joined</th>
                  {canManage && <th />}
                </tr>
              </thead>
              <tbody>
                {org.members.map((m) => (
                  <tr key={m.id}>
                    <td>
                      <div className="cell-title">
                        <span className="avatar">{initials(m.user.name || m.user.email)}</span>
                        <div style={{ minWidth: 0 }}>
                          <b>
                            {m.user.name} {m.user.id === me && <span className="faint" style={{ display: "inline" }}>(you)</span>}
                          </b>
                          <span>{m.user.email}</span>
                        </div>
                      </div>
                    </td>
                    <td>
                      {canManage && m.user.id !== me ? (
                        <select
                          className="select select--sm"
                          value={m.role}
                          onChange={(e) => run(auth.organization.updateMemberRole({ memberId: m.id, role: e.target.value as "member" }))}
                          aria-label={`Role of ${m.user.email}`}
                        >
                          {ROLES.map((r) => (
                            <option key={r} value={r}>
                              {cap(r)}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span className="badge badge--plain">{cap(m.role)}</span>
                      )}
                    </td>
                    <td className="dim">{new Date(m.createdAt).toLocaleDateString("en", { day: "numeric", month: "short", year: "numeric" })}</td>
                    {canManage && (
                      <td className="actions">
                        {m.user.id !== me && (
                          <button
                            className="btn btn--sm btn--ghost btn--danger"
                            onClick={() => confirm(`Remove ${m.user.email} from the organization?`) && run(auth.organization.removeMember({ memberIdOrEmail: m.id }))}
                          >
                            Remove
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {pending.length > 0 && (
            <div className="section">
              <div className="section__title">
                <h2>Pending invitations</h2>
                <span>Share the link: there is no email service yet</span>
              </div>
              <table className="table">
                <tbody>
                  {pending.map((i) => (
                    <tr key={i.id}>
                      <td>
                        <div className="cell-title">
                          <span className="avatar">{initials(i.email)}</span>
                          <div>
                            <b>{i.email}</b>
                            <span>
                              Invited as {i.role} · expires {new Date(i.expiresAt).toLocaleDateString("en", { day: "numeric", month: "short" })}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td className="actions">
                        <CopyButton text={inviteLink(i.id)} label="Copy link" />{" "}
                        {canManage && (
                          <button className="btn btn--sm btn--ghost btn--danger" onClick={() => run(auth.organization.cancelInvitation({ invitationId: i.id }))}>
                            Cancel
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {inviting && (
        <InviteModal
          onClose={() => setInviting(false)}
          onInvited={(email, id) => {
            setInviting(false);
            setLink({ email, url: inviteLink(id) });
            load();
          }}
        />
      )}
      {link && (
        <Modal title="Invitation ready" onClose={() => setLink(null)} foot={<button className="btn btn--light" onClick={() => setLink(null)}>Done</button>}>
          <p className="note" style={{ margin: 0 }}>
            Send this link to <b style={{ color: "var(--text)" }}>{link.email}</b>. They sign up with that email and join right away.
          </p>
          <div className="secret">
            <code>{link.url}</code>
            <CopyButton text={link.url} />
          </div>
        </Modal>
      )}
    </>
  );
}

function InviteModal({ onClose, onInvited }: { onClose: () => void; onInvited: (email: string, id: string) => void }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    const r = await auth.organization.inviteMember({ email: email.trim(), role: role as "member" });
    setBusy(false);
    if (r.error || !r.data) return setError(r.error?.message ?? "Could not invite");
    onInvited(email.trim(), (r.data as { id: string }).id);
  }
  return (
    <Modal title="Invite a member" onClose={onClose}>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div className="field">
          <label htmlFor="inv-email">Email</label>
          <input id="inv-email" className="input" type="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} placeholder="teammate@company.com" />
        </div>
        <div className="field">
          <label htmlFor="inv-role">Role</label>
          <select id="inv-role" className="select" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="member">Member · sees tutorials and usage</option>
            <option value="admin">Admin · also manages tutorials, members and tokens</option>
          </select>
        </div>
        {error && <div className="error">{error}</div>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn--primary" disabled={busy}>
            {busy ? <span className="spinner" /> : "Create invitation"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
