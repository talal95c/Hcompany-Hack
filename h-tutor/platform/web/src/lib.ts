import { organizationClient } from "better-auth/client/plugins";
import { createAuthClient } from "better-auth/react";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

export const auth = createAuthClient({ baseURL: window.location.origin, plugins: [organizationClient()] });

// ---------------------------------------------------------------- router

const listeners = new Set<() => void>();
window.addEventListener("popstate", () => listeners.forEach((l) => l()));

export function navigate(to: string, replace = false) {
  if (to === window.location.pathname + window.location.search) return;
  history[replace ? "replaceState" : "pushState"](null, "", to);
  listeners.forEach((l) => l());
}

export function usePath(): string {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => window.location.pathname,
  );
}

// ---------------------------------------------------------------- console API

export async function api<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const r = await fetch(`/api/app${path}`, {
    ...init,
    credentials: "include",
    headers: init?.json !== undefined ? { "content-type": "application/json" } : undefined,
    body: init?.json !== undefined ? JSON.stringify(init.json) : init?.body,
  });
  const v = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((v as { error?: string }).error ?? `Request failed (${r.status})`);
  return v as T;
}

/** Loads `path`, reloads on demand, and every `pollMs` while `poll(data)` is true. */
export function useApi<T>(path: string | null, poll?: (d: T) => boolean, pollMs = 3000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(() => {
    if (!path) return Promise.resolve();
    return api<T>(path)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));
  }, [path]);
  useEffect(() => {
    setData(null);
    reload();
  }, [reload]);
  useEffect(() => {
    if (!data || !poll?.(data)) return;
    const t = setTimeout(reload, pollMs);
    return () => clearTimeout(t);
  }, [data, poll, pollMs, reload]);
  return { data, error, reload };
}

// ---------------------------------------------------------------- types

export type Visibility = "draft" | "team" | "community";

export type TutorialRow = {
  id: string;
  kind: "youtube" | "page" | "goal";
  input: string;
  title: string | null;
  app: string | null;
  status: string;
  error: string | null;
  visibility: Visibility;
  publishedAt: number | null;
  remixOf: string | null;
  agentViewUrl?: string | null;
  thumbnail?: string | null;
  sources: { title: string; url: string; image?: string; site?: string }[];
  tutorial: RioTutorial | null;
  author: { id: string | null; name: string | null };
  org: string | null;
  likes: number;
  liked: boolean;
  learners: number;
  remixes: number;
  canEdit: boolean;
  createdAt: number;
  updatedAt: number;
  remixOfTutorial?: { id: string; title: string | null; org: string | null } | null;
};

export const isLive = (t: { status: string }) => !["ready", "failed"].includes(t.status);

export type RioTutorial = {
  id: string;
  title: string;
  app: { name: string };
  goal: string;
  language?: string;
  source_url?: string;
  credit?: { kind: string; title?: string; author?: string; url: string; thumbnail?: string };
  milestones: { id: string; goal: string; done_when: string; hints?: string[]; teach?: string; video_at?: number }[];
};

export type LibraryEntry = {
  id: string;
  title: string;
  app: string;
  goal: string;
  milestones: number;
  source_url: string | null;
  author_kind: string | null;
  recorded_on: string | null;
};

// ---------------------------------------------------------------- formatting

const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
export function ago(ms: number | null | undefined): string {
  if (!ms) return "Never";
  const s = (Date.now() - ms) / 1000;
  if (s < 45) return "Just now";
  const steps: [number, Intl.RelativeTimeFormatUnit][] = [
    [60, "second"],
    [3600, "minute"],
    [86400, "hour"],
    [604800, "day"],
    [2629800, "week"],
    [31557600, "month"],
    [Infinity, "year"],
  ];
  let prev = 1;
  for (const [limit, unit] of steps) {
    if (s < limit) return rtf.format(-Math.round(s / prev), unit);
    prev = limit;
  }
  return "";
}

export const initials = (s: string) =>
  s
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");

export const kindOf = (s: string): "youtube" | "page" | "goal" | null => {
  const t = s.trim();
  if (!t) return null;
  if (/(youtube\.com\/(watch|shorts|embed)|youtu\.be\/)/i.test(t)) return "youtube";
  if (/^https?:\/\//i.test(t)) return "page";
  return t.length > 3 ? "goal" : null;
};

export async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
