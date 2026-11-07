import { type FormEvent, useState } from "react";
import { ago, api, useApi } from "../lib";
import { CopyButton, Head, Loading, Modal } from "../ui";

type Token = { id: string; name: string; prefix: string; createdAt: number; lastUsedAt: number | null; createdBy: string | null };

export function TokensPage({ canManage }: { canManage: boolean }) {
  const { data, error, reload } = useApi<{ tokens: Token[] }>("/tokens");
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<string | null>(null);
  const url = window.location.origin;

  return (
    <>
      <Head title="Settings" sub="Connect the Rio app on your team's computers to this workspace.">
        {canManage && (
          <button className="btn btn--light" onClick={() => setCreating(true)}>
            New token
          </button>
        )}
      </Head>
      {error ? (
        <div className="error">{error}</div>
      ) : !data ? (
        <Loading />
      ) : data.tokens.length === 0 ? (
        <div className="empty">
          <b>No tokens</b>
          Create one, then put it in Rio's <span className="mono">.env</span> to search your knowledge and list your tutorials.
        </div>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Token</th>
                <th>Created by</th>
                <th>Created</th>
                <th>Last used</th>
                {canManage && <th />}
              </tr>
            </thead>
            <tbody>
              {data.tokens.map((t) => (
                <tr key={t.id}>
                  <td style={{ fontWeight: 500 }}>{t.name}</td>
                  <td className="mono dim">{t.prefix}…</td>
                  <td className="dim">{t.createdBy ?? "—"}</td>
                  <td className="dim">{ago(t.createdAt)}</td>
                  <td className="dim">{ago(t.lastUsedAt)}</td>
                  {canManage && (
                    <td className="actions">
                      <button
                        className="btn btn--sm btn--ghost btn--danger"
                        onClick={async () => {
                          if (!confirm(`Revoke "${t.name}"? Rio apps using it lose access immediately.`)) return;
                          await api(`/tokens/${t.id}`, { method: "DELETE" });
                          reload();
                        }}
                      >
                        Revoke
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="section">
        <div className="section__title">
          <h2>How to connect Rio</h2>
        </div>
        <div className="code">{`# Rio's .env\nRIO_API_URL=${url}\nRIO_API_TOKEN=rio_…`}</div>
      </div>

      {creating && (
        <CreateModal
          onClose={() => setCreating(false)}
          onCreated={(token) => {
            setCreating(false);
            setCreated(token);
            reload();
          }}
        />
      )}
      {created && (
        <Modal title="Copy your token" onClose={() => setCreated(null)} foot={<button className="btn btn--light" onClick={() => setCreated(null)}>I saved it</button>}>
          <p className="note" style={{ margin: 0 }}>
            This is the only time it is shown. Store it somewhere safe: anyone with it can read this organization's knowledge.
          </p>
          <div className="secret">
            <code>{created}</code>
            <CopyButton text={created} />
          </div>
          <div className="code">{`RIO_API_URL=${url}\nRIO_API_TOKEN=${created}`}</div>
          <div>
            <CopyButton text={`RIO_API_URL=${url}\nRIO_API_TOKEN=${created}`} label="Copy .env lines" />
          </div>
        </Modal>
      )}
    </>
  );
}

function CreateModal({ onClose, onCreated }: { onClose: () => void; onCreated: (token: string) => void }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api<{ token: string }>("/tokens", { method: "POST", json: { name: name.trim() } });
      onCreated(r.token);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }
  return (
    <Modal title="New API token" onClose={onClose}>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div className="field">
          <label htmlFor="tok-name">Name</label>
          <input id="tok-name" className="input" required autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Design team laptops" />
        </div>
        {error && <div className="error">{error}</div>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn--primary" disabled={busy || !name.trim()}>
            {busy ? <span className="spinner" /> : "Create token"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
