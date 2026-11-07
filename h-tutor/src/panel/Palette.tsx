import { useEffect, useMemo, useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { api, type AppIcon, type TutorialSummary } from "./api";
import { IconClose, IconGrid } from "./icons";

const SOURCE_LABEL: Record<string, string> = {
  generated: "Généré",
  recorded: "Issu d'une session",
  youtube: "Depuis YouTube",
};

type Props = {
  tutorials: TutorialSummary[];
  onStart: (t: TutorialSummary) => void;
  onClose: () => void;
};

/**
 * The tutorial library as a ⌘K palette (OMNIA Campus' global search, itself
 * Mobbin-style): search on top, apps on the left, a plain
 * list of tutorials on the right. Arrows move, Enter starts, Esc closes.
 */
export default function Palette({ tutorials, onStart, onClose }: Props) {
  const reduced = useReducedMotion();
  const [query, setQuery] = useState("");
  const [app, setApp] = useState<string | null>(null);
  const [selected, setSelected] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  /** Only keyboard moves scroll the list (not opening it or hovering). */
  const keyMoved = useRef(false);

  useEffect(() => inputRef.current?.focus(), []);

  // The real icons of the installed apps (and their dominant colour).
  const [icons, setIcons] = useState<Record<string, AppIcon>>({});
  useEffect(() => {
    const seen = new Map<string, string | null>();
    for (const t of tutorials) if (!seen.has(t.app)) seen.set(t.app, t.bundle_id);
    api.appIcons([...seen.entries()]).then(setIcons).catch(() => {});
  }, [tutorials]);

  const apps = useMemo(() => {
    const counts = new Map<string, number>();
    for (const t of tutorials) counts.set(t.app, (counts.get(t.app) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [tutorials]);

  const results = useMemo(() => {
    const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
    return tutorials.filter((t) => {
      if (app && t.app !== app) return false;
      const hay = `${t.title} ${t.app} ${t.goal}`.toLowerCase();
      return terms.every((term) => hay.includes(term));
    });
  }, [tutorials, query, app]);

  useEffect(() => setSelected(0), [query, app]);

  const Icon = ({ app, size }: { app: string; size: number }) =>
    icons[app] ? (
      <img className="app-icon" src={icons[app].data_uri} width={size} height={size} alt="" draggable={false} />
    ) : (
      <span className="app-icon app-icon--fallback" style={{ width: size, height: size }}>
        {app.trim()[0]?.toUpperCase()}
      </span>
    );

  useEffect(() => {
    if (!keyMoved.current) return;
    keyMoved.current = false;
    listRef.current?.querySelector('[data-selected="true"]')?.scrollIntoView({ block: "nearest" });
  }, [selected]);

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      onClose();
    } else if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      e.preventDefault();
      keyMoved.current = true;
      setSelected((s) => Math.min(s + 1, results.length - 1));
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault();
      keyMoved.current = true;
      setSelected((s) => Math.max(s - 1, 0));
    } else if (e.key === "Enter" && results[selected]) {
      e.preventDefault();
      onStart(results[selected]);
    }
  }

  return (
    <motion.div
      className="palette"
      onKeyDown={onKeyDown}
      initial={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.95, filter: "blur(6px)" }}
      animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
      transition={{ duration: 0.24, ease: [0.23, 1, 0.32, 1] }}
    >
      <div className="palette__head">
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={app ? `Chercher un tuto ${app}` : "Chercher un tuto"}
          spellCheck={false}
        />
        <button className="tool" onClick={onClose} title="Fermer (esc)">
          <IconClose />
        </button>
      </div>

      <div className="palette__body">
        <nav className="palette__nav">
          <button className={`nav-item ${app === null ? "is-on" : ""}`} onClick={() => setApp(null)}>
            <span className="nav-dot">
              <IconGrid />
            </span>
            Tous
            <span className="nav-count">{tutorials.length}</span>
          </button>
          {apps.map(([name, count]) => (
            <button
              key={name}
              className={`nav-item ${app === name ? "is-on" : ""}`}
              onClick={() => setApp(app === name ? null : name)}
            >
              <Icon app={name} size={20} />
              <span className="nav-label">{name}</span>
              <span className="nav-count">{count}</span>
            </button>
          ))}
        </nav>

        <div className="palette__list" ref={listRef}>
          <div className="group-title">{app ?? (query ? "Résultats" : "Tutos")}</div>
          {results.length === 0 ? (
            <p className="palette__empty">Aucun tuto ne correspond. Ferme et tape ton objectif dans la barre : Holo en préparera un.</p>
          ) : (
            <div className="cards">
              {results.map((t, i) => {
                return (
                  <motion.button
                    key={t.id}
                    className="card"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.18, ease: [0.23, 1, 0.32, 1] }}
                    data-selected={i === selected}
                    onMouseEnter={() => setSelected(i)}
                    onClick={() => onStart(t)}
                  >
                    <span className="card__title">{t.title}</span>
                    <span className="card__meta">
                      <Icon app={t.app} size={16} />
                      {t.app} · {t.milestones} étapes
                      {SOURCE_LABEL[t.source] ? ` · ${SOURCE_LABEL[t.source]}` : ""}
                    </span>
                  </motion.button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <div className="palette__foot">
        <span>
          <kbd>↵</kbd> lancer
        </span>
        <span>
          <kbd>↑</kbd>
          <kbd>↓</kbd> naviguer
        </span>
        <span>
          <kbd>esc</kbd> fermer
        </span>
      </div>
    </motion.div>
  );
}
