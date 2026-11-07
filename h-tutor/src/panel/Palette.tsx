import { useEffect, useMemo, useRef, useState } from "react";
import { api, type AppIcon, type TutorialSummary } from "./api";
import { IconClose } from "./icons";

/** One hue family per app, picked from its name (stable across runs). */
const HUES = [
  { tile: ["#38bdf8", "#0369a1"], sheet: "#0369a1", soft: "#0c4a6e" }, // sky
  { tile: ["#a78bfa", "#6d28d9"], sheet: "#6d28d9", soft: "#4c1d95" }, // violet
  { tile: ["#34d399", "#047857"], sheet: "#047857", soft: "#064e3b" }, // emerald
  { tile: ["#fb7185", "#be123c"], sheet: "#be123c", soft: "#881337" }, // rose
  { tile: ["#fbbf24", "#b45309"], sheet: "#b45309", soft: "#78350f" }, // amber
  { tile: ["#e879f9", "#a21caf"], sheet: "#a21caf", soft: "#701a75" }, // fuchsia
  { tile: ["#22d3ee", "#0e7490"], sheet: "#0e7490", soft: "#164e63" }, // cyan
  { tile: ["#fb923c", "#c2410c"], sheet: "#c2410c", soft: "#7c2d12" }, // orange
];

/** Each app gets its own hue: by its rank among the library's apps. */
function hueOf(apps: string[], app: string) {
  const i = apps.indexOf(app);
  return HUES[(i < 0 ? 0 : i) % HUES.length];
}

const SOURCE_LABEL: Record<string, string> = {
  generated: "Generated",
  recorded: "From a session",
  youtube: "From YouTube",
};

type Props = {
  tutorials: TutorialSummary[];
  onStart: (t: TutorialSummary) => void;
  onClose: () => void;
};

/**
 * The tutorial library as a ⌘K palette (OMNIA Campus' global search, itself
 * Mobbin-style): search on top, apps on the left, colourful app tiles and
 * tutorial cards on the right. Arrows move, Enter starts, Esc closes.
 */
export default function Palette({ tutorials, onStart, onClose }: Props) {
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

  const appNames = useMemo(() => apps.map(([name]) => name), [apps]);
  /** Colours of an app: from its real icon when we have it. */
  const hue = (app: string) => {
    const c = icons[app]?.color;
    if (!c) return hueOf(appNames, app);
    return { tile: [c, c], sheet: c, soft: `color-mix(in srgb, ${c} 45%, #000)` };
  };
  const Icon = ({ app, size }: { app: string; size: number }) =>
    icons[app] ? (
      <img className="app-icon" src={icons[app].data_uri} width={size} height={size} alt="" draggable={false} />
    ) : (
      <span
        className="app-icon app-icon--fallback"
        style={{ width: size, height: size, background: `linear-gradient(145deg, ${hue(app).tile[0]}, ${hue(app).tile[1]})` }}
      >
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
      setSelected((s) => Math.min(s + (e.key === "ArrowDown" ? 2 : 1), results.length - 1));
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault();
      keyMoved.current = true;
      setSelected((s) => Math.max(s - (e.key === "ArrowUp" ? 2 : 1), 0));
    } else if (e.key === "Enter" && results[selected]) {
      e.preventDefault();
      onStart(results[selected]);
    }
  }

  return (
    <div className="palette" onKeyDown={onKeyDown}>
      <div className="palette__head">
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={app ? `Search ${app} tutorials` : "Search tutorials"}
          spellCheck={false}
        />
        <button className="tool" onClick={onClose} title="Close (esc)">
          <IconClose />
        </button>
      </div>

      <div className="palette__body">
        <nav className="palette__nav">
          <button className={`nav-item ${app === null ? "is-on" : ""}`} onClick={() => setApp(null)}>
            <span className="nav-dot nav-dot--all" />
            All
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
          {!query && !app && apps.length > 0 && (
            <>
              <div className="group-title">Apps</div>
              <div className="tiles">
                {apps.map(([name]) => (
                  <button key={name} className="app-tile" onClick={() => setApp(name)} title={name}>
                    <Icon app={name} size={64} />
                    <span className="app-tile__name">{name}</span>
                  </button>
                ))}
              </div>
            </>
          )}

          <div className="group-title">{app ?? (query ? "Results" : "Tutorials")}</div>
          {results.length === 0 ? (
            <p className="palette__empty">No tutorial matches. Close and type your goal in the bar: Holo will plan one.</p>
          ) : (
            <div className="cards">
              {results.map((t, i) => {
                const h = hue(t.app);
                const wide = !query && !app && i === 0 && results.length > 2;
                return (
                  <button
                    key={t.id}
                    className={`card ${wide ? "card--wide" : ""}`}
                    data-selected={i === selected}
                    onMouseEnter={() => setSelected(i)}
                    onClick={() => onStart(t)}
                  >
                    <span className="card__title">{t.title}</span>
                    <span className="card__meta">
                      <Icon app={t.app} size={16} />
                      {t.app} · {t.milestones} milestones
                      {SOURCE_LABEL[t.source] ? ` · ${SOURCE_LABEL[t.source]}` : ""}
                    </span>
                    <span className="card__sheet card__sheet--back" style={{ background: h.soft }} />
                    <span className="card__sheet" style={{ background: h.sheet }}>
                      {Array.from({ length: Math.min(t.milestones, 5) }, (_, k) => (
                        <span key={k} className="sheet-row">
                          <span className="sheet-dot" />
                          <span className="sheet-line" style={{ width: `${82 - ((k * 23) % 40)}%` }} />
                        </span>
                      ))}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <div className="palette__foot">
        <span>
          <kbd>↵</kbd> start
        </span>
        <span>
          <kbd>←</kbd>
          <kbd>→</kbd> move
        </span>
        <span>
          <kbd>esc</kbd> close
        </span>
      </div>
    </div>
  );
}
