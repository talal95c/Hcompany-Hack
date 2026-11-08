import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";
import { AppIcon, coverStyle } from "./appIcons";
import { type TutorialRow, api, initials, isLive, kindOf, navigate } from "./lib";
import { I } from "./ui";

export function Avatar({ name, size = "" }: { name: string | null; size?: "" | "sm" | "lg" }) {
  return <span className={`avatar ${size ? `avatar--${size}` : ""}`}>{initials(name || "?").slice(0, 2)}</span>;
}

export const VIS = {
  draft: { label: "Draft", hint: "Only your team sees it here. Rio does not offer it yet.", icon: I.Lock },
  team: { label: "Published to your team", hint: "Everyone in your organization can learn it in Rio.", icon: I.Team },
  community: { label: "Shared with the community", hint: "Every Rio team can find it, learn it and remix it.", icon: I.Globe },
} as const;

const STAGE: Record<string, string> = { queued: "Starting", transcribing: "Listening to the video", browsing: "Reading the docs", designing: "Writing the steps", failed: "Failed" };

export function StatusTag({ t, glass }: { t: TutorialRow; glass?: boolean }) {
  if (isLive(t)) return <span className={`tag tag--live ${glass ? "tag--glass" : ""}`}>{STAGE[t.status] ?? "Working"}…</span>;
  if (t.status === "failed") return <span className="tag tag--failed">Couldn't create</span>;
  if (t.visibility === "draft") return <span className={`tag ${glass ? "tag--glass" : ""}`}>Draft</span>;
  if (t.visibility === "community") return <span className={`tag ${glass ? "tag--glass" : ""}`}>Community</span>;
  return null;
}

export function TutorialCard({ t, showOrg }: { t: TutorialRow; showOrg?: boolean }) {
  const name = t.tutorial?.title ?? t.title ?? t.input;
  return (
    <a
      className="card"
      href={`/t/${t.id}`}
      onClick={(e) => {
        e.preventDefault();
        navigate(`/t/${t.id}`);
      }}
    >
      <div className={`card__cover ${t.thumbnail ? "card__cover--video" : ""}`} style={coverStyle(t.app)}>
        {t.thumbnail ? (
          <>
            <img className="card__thumb" src={t.thumbnail} alt="" loading="lazy" referrerPolicy="no-referrer" />
            <span className="card__app"><AppIcon name={t.app} /></span>
          </>
        ) : (
          <AppIcon name={t.app} />
        )}
        <span className="card__badge">
          <StatusTag t={t} glass />
        </span>
      </div>
      <div className="card__body">
        <div className="card__title">{name}</div>
        <div className="card__meta">
          <span className="who-sm">
            <Avatar name={t.author.name} size="sm" />
            <span>{showOrg && t.org ? t.org : (t.author.name ?? "Someone")}</span>
          </span>
          <span className="card__stats">
            {t.tutorial && (
              <span title="Milestones">
                <I.Steps /> {t.tutorial.milestones.length}
              </span>
            )}
            {t.learners > 0 && (
              <span title="Learners">
                <I.Learners /> {t.learners}
              </span>
            )}
            {t.likes > 0 && (
              <span title="Likes">
                <I.Heart /> {t.likes}
              </span>
            )}
          </span>
        </div>
      </div>
    </a>
  );
}

const KIND = {
  youtube: { label: "YouTube video", icon: I.Play },
  page: { label: "Documentation page", icon: I.Page },
  goal: { label: "Goal · Rio searches the web", icon: I.Search },
} as const;

/** One box for any source: a video, a doc page, or just what the team should learn. */
export function Composer({ initial = "", autoFocus, placeholder }: { initial?: string; autoFocus?: boolean; placeholder?: string }) {
  const [text, setText] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const kind = kindOf(text);
  const K = kind ? KIND[kind] : null;

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    if (!kind || busy) return;
    setBusy(true);
    setError(null);
    try {
      const t = await api<{ id: string }>("/tutorials", { method: "POST", json: { input: text } });
      navigate(`/t/${t.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <form className="composer" onSubmit={submit}>
      <textarea
        value={text}
        autoFocus={autoFocus}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKey}
        rows={2}
        placeholder={placeholder ?? "Paste a YouTube link or a doc page, or describe what your team should learn…"}
        aria-label="New tutorial"
      />
      <div className="composer__bar">
        {error ? (
          <span className="error">{error}</span>
        ) : K ? (
          <span className="composer__kind">
            <K.icon />
            {K.label}
          </span>
        ) : null}
        <button className="btn btn--primary composer__send" disabled={!kind || busy} aria-label="Create tutorial">
          {busy ? <span className="spinner" /> : <I.Up />}
        </button>
      </div>
    </form>
  );
}

type Recognition = { lang: string; interimResults: boolean; continuous: boolean; start(): void; stop(): void; onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null; onend: (() => void) | null };

/**
 * The Rio bar from the Mac app, on the web: the same dark pill, spark, input,
 * library and mic buttons. Whatever you type becomes a tutorial.
 */
export function RioBar({ initial = "" }: { initial?: string }) {
  const [text, setText] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const rec = useRef<Recognition | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const kind = kindOf(text);
  const Speech = (window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition }).SpeechRecognition ??
    (window as unknown as { webkitSpeechRecognition?: new () => Recognition }).webkitSpeechRecognition;

  useEffect(() => () => rec.current?.stop(), []);

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    if (!kind || busy) return;
    setBusy(true);
    setError(null);
    try {
      const t = await api<{ id: string }>("/tutorials", { method: "POST", json: { input: text } });
      navigate(`/t/${t.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  function toggleMic() {
    if (listening) return rec.current?.stop();
    if (!Speech) return;
    const r = new Speech();
    r.lang = navigator.language;
    r.interimResults = true;
    r.continuous = false;
    r.onresult = (e) => setText(Array.from(e.results).map((x) => x[0]!.transcript).join(" "));
    r.onend = () => {
      setListening(false);
      input.current?.focus();
    };
    rec.current = r;
    r.start();
    setListening(true);
  }

  return (
    <div className="riobar-wrap">
      <form className="riobar" onSubmit={submit}>
        <span className="riobar__lead">{busy ? <span className="spinner" /> : <I.Spark />}</span>
        <input
          ref={input}
          value={text}
          autoFocus
          onChange={(e) => setText(e.target.value)}
          placeholder={listening ? "Listening…" : "Ask or learn anything, or paste a YouTube link"}
          aria-label="New tutorial"
          spellCheck={false}
        />
        {kind && !busy && <span className="riobar__hint">{KIND[kind].label.split(" ·")[0]}</span>}
        <button type="button" className="riobar__tool" title="Library" onClick={() => navigate("/library")}>
          <I.Grid />
        </button>
        {Speech && (
          <button type="button" className={`riobar__tool ${listening ? "is-rec" : ""}`} title={listening ? "Stop listening" : "Dictate"} onClick={toggleMic}>
            <I.Mic />
          </button>
        )}
        <button className="riobar__key" disabled={!kind || busy} aria-label="Create tutorial">
          <I.Enter />
        </button>
      </form>
      {error && <p className="error" style={{ textAlign: "center", margin: "10px 0 0" }}>{error}</p>}
    </div>
  );
}
