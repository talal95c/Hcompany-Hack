import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { listen } from "@tauri-apps/api/event";
import { api, errorText, type AutopilotView } from "../panel/api";
import "@fontsource-variable/geist";
import "../panel/styles.css";
import "./styles.css";

function Notch() {
  const [view, setView] = useState<AutopilotView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let disposed = false;
    let received = false;
    const subscription = listen<AutopilotView>("autopilot:view", ({ payload }) => {
      received = true;
      if (!disposed) { setView(payload); setError(null); }
    });
    subscription.then(() => api.autopilotView()).then((snapshot) => {
      if (!disposed && !received) setView(snapshot);
    }).catch((e) => { if (!disposed) setError(errorText(e)); });
    return () => { disposed = true; subscription.then((off) => off()); };
  }, []);

  async function act(command: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try { await command(); } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  }

  return (
    <section className={`notch notch--${view?.phase ?? "hidden"}`} aria-live="polite" aria-label="Rio le fait pour toi">
      <div className="notch__brand" aria-hidden="true">
        <svg width="16" height="14" viewBox="0 0 96 84" fill="currentColor">
          <path d="M24 0H84V40L64 60V20H24V60L0 84V24Z M24 60H64L96 84H48Z" />
        </svg>
        <span>RIO LE FAIT POUR TOI</span>
      </div>
      {view?.phase === "expanded" ? (
        <>
          <h1>Tu veux que je fasse : <span>{view.title}</span> ?</h1>
          <p className="notch__goal" title={view.goal}>{view.goal}</p>
          <div className="notch__actions">
            <button className="notch__secondary" disabled={busy} onClick={() => act(api.autopilotDecline)}>Pas maintenant <kbd>esc</kbd></button>
            <button className="notch__primary" disabled={busy} onClick={() => act(() => api.autopilotAccept(view.skill_id))}>Oui</button>
          </div>
        </>
      ) : (
        <>
          <div className="notch__task">
            <h1>{view?.title}</h1>
            {!view?.outcome && <button className="notch__stop" disabled={busy} onClick={() => act(api.autopilotStop)}>Arrêter</button>}
          </div>
          <p className="notch__status">{view?.outcome ? view.message : `Étape ${view?.index ?? 0}/${view?.total ?? 0} · ${view?.label ?? ""}`}</p>
          <progress className="notch__progress" aria-label="Progression de la tâche" max={view?.total || 1} value={view?.outcome === "completed" ? view.total : view?.index ?? 0} />
        </>
      )}
      {error && <p className="notch__error" role="alert">{error}</p>}
    </section>
  );
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(<React.StrictMode><Notch /></React.StrictMode>);
