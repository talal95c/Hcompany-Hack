import { type ReactNode, useEffect, useState } from "react";
import { copy } from "./lib";

// ---------------------------------------------------------------- icons (1.6px strokes, 16px)

const P = { width: 16, height: 16, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" } as const;
export const I = {
  // Rio's mark (h-tutor/brand/rio-mark-black.svg).
  Mark: () => (
    <svg viewBox="0 0 96 84" aria-hidden>
      <path d="M24 0H84V40L64 60V20H24V60L0 84V24ZM24 60H64L96 84H48Z" fill="currentColor" />
    </svg>
  ),
  Book: () => (
    <svg {...P} className="nav__icon">
      <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5zM4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5" />
    </svg>
  ),
  Users: () => (
    <svg {...P} className="nav__icon">
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20c.8-3.5 3.4-5.5 6.5-5.5s5.7 2 6.5 5.5M16 4.8a3.5 3.5 0 0 1 0 6.4M18 14.8c1.8.7 3 2.5 3.5 5.2" />
    </svg>
  ),
  Key: () => (
    <svg {...P} className="nav__icon">
      <circle cx="8" cy="15" r="4.5" />
      <path d="M11.2 11.8L20 3M16.5 6.5l3 3M14 9l2 2" />
    </svg>
  ),
  Chart: () => (
    <svg {...P} className="nav__icon">
      <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
    </svg>
  ),
  Home: () => (
    <svg {...P} className="nav__icon">
      <path d="M4 10.5L12 4l8 6.5V20a1 1 0 0 1-1 1h-4.5v-6h-5v6H5a1 1 0 0 1-1-1z" />
    </svg>
  ),
  Globe: () => (
    <svg {...P} className="nav__icon">
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z" />
    </svg>
  ),
  Layers: () => (
    <svg {...P} className="nav__icon">
      <path d="M12 3l9 5-9 5-9-5zM3 13l9 5 9-5" />
    </svg>
  ),
  Gear: () => (
    <svg {...P} className="nav__icon">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
    </svg>
  ),
  Heart: () => (
    <svg {...P} width={14} height={14}>
      <path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z" />
    </svg>
  ),
  Learners: () => (
    <svg {...P} width={14} height={14}>
      <path d="M2 9l10-5 10 5-10 5zM6 11v5c3.5 2.5 8.5 2.5 12 0v-5" />
    </svg>
  ),
  Steps: () => (
    <svg {...P} width={14} height={14}>
      <path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01" />
    </svg>
  ),
  Back: () => (
    <svg {...P} width={14} height={14}>
      <path d="M15 18l-6-6 6-6" />
    </svg>
  ),
  Right: () => (
    <svg {...P} width={14} height={14} className="chev">
      <path d="M9 18l6-6-6-6" />
    </svg>
  ),
  Up: () => (
    <svg {...P} width={16} height={16} strokeWidth={2.2}>
      <path d="M12 19V5M6 11l6-6 6 6" />
    </svg>
  ),
  Check: () => (
    <svg {...P} width={12} height={12} strokeWidth={2.6}>
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </svg>
  ),
  Edit: () => (
    <svg {...P} width={14} height={14}>
      <path d="M4 20h4L19 9l-4-4L4 16zM14 6l4 4" />
    </svg>
  ),
  Remix: () => (
    <svg {...P} width={14} height={14}>
      <path d="M7 4v10a4 4 0 0 0 4 4h6M14 15l3 3-3 3M17 4v4" />
    </svg>
  ),
  Lock: () => (
    <svg {...P} width={14} height={14}>
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </svg>
  ),
  Team: () => (
    <svg {...P} width={14} height={14}>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20c.8-3.5 3.4-5.5 6.5-5.5s5.7 2 6.5 5.5M16 4.8a3.5 3.5 0 0 1 0 6.4M18 14.8c1.8.7 3 2.5 3.5 5.2" />
    </svg>
  ),
  Spark: () => (
    <svg {...P} width={15} height={15}>
      <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
    </svg>
  ),
  Grid: () => (
    <svg {...P} width={15} height={15}>
      <rect x="4" y="4" width="6.5" height="6.5" rx="1.6" />
      <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.6" />
      <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.6" />
      <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.6" />
    </svg>
  ),
  Mic: () => (
    <svg {...P} width={15} height={15}>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </svg>
  ),
  Enter: () => (
    <svg {...P} width={14} height={14}>
      <path d="M20 5v7a3 3 0 0 1-3 3H5M9 11l-4 4 4 4" />
    </svg>
  ),
  Plus: () => (
    <svg {...P} width={14} height={14} strokeWidth={2}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  ),
  Close: () => (
    <svg {...P}>
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  ),
  Chevron: () => (
    <svg {...P} width={14} height={14} className="faint">
      <path d="M8 10l4-4 4 4M8 14l4 4 4-4" />
    </svg>
  ),
  Logout: () => (
    <svg {...P} width={15} height={15}>
      <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 16l-4-4 4-4M6 12h10" />
    </svg>
  ),
  Play: () => (
    <svg {...P} width={13} height={13}>
      <path d="M7 5l12 7-12 7z" fill="currentColor" />
    </svg>
  ),
  Page: () => (
    <svg {...P} width={13} height={13}>
      <path d="M6 3h8l4 4v14H6zM14 3v4h4M9 12h6M9 16h6" />
    </svg>
  ),
  Search: () => (
    <svg {...P} width={13} height={13}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M20 20l-4.2-4.2" />
    </svg>
  ),
  Download: () => (
    <svg {...P} className="nav__icon">
      <path d="M12 3v12M7 10l5 5 5-5M4 19h16" />
    </svg>
  ),
  Copy: () => (
    <svg {...P} width={14} height={14}>
      <rect x="8" y="8" width="12" height="12" rx="2.5" />
      <path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8" />
    </svg>
  ),
};

// ---------------------------------------------------------------- pieces

export function Modal({ title, onClose, children, foot }: { title: string; onClose: () => void; children: ReactNode; foot?: ReactNode }) {
  useEscape(onClose);
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal__head">
          <h2>{title}</h2>
          <button className="btn btn--ghost btn--sm" style={{ marginLeft: "auto" }} onClick={onClose} aria-label="Close">
            <I.Close />
          </button>
        </div>
        <div className="modal__body">{children}</div>
        {foot && <div className="modal__foot">{foot}</div>}
      </div>
    </div>
  );
}

export function Drawer({ onClose, head, children }: { onClose: () => void; head: ReactNode; children: ReactNode }) {
  useEscape(onClose);
  return (
    <div className="drawer-wrap" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside className="drawer" role="dialog" aria-modal="true">
        <div className="drawer__head">
          <div style={{ flex: 1, minWidth: 0 }}>{head}</div>
          <button className="btn btn--ghost btn--sm" onClick={onClose} aria-label="Close">
            <I.Close />
          </button>
        </div>
        <div className="drawer__body">{children}</div>
      </aside>
    </div>
  );
}

function useEscape(fn: () => void) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && fn();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [fn]);
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      className="btn btn--sm"
      onClick={async () => {
        if (await copy(text)) {
          setDone(true);
          setTimeout(() => setDone(false), 1400);
        }
      }}
    >
      <I.Copy />
      {done ? "Copied" : label}
    </button>
  );
}

export function Head({ title, sub, children }: { title: string; sub?: ReactNode; children?: ReactNode }) {
  return (
    <div className="head">
      <div>
        <h1>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
      {children && <div className="head__actions">{children}</div>}
    </div>
  );
}

export const Loading = () => (
  <div className="center" style={{ minHeight: 200 }}>
    <span className="spinner" />
  </div>
);
