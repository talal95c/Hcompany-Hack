// The same app icons as the Rio app (h-tutor/src/assets/apps), with each
// icon's own colour to tint tutorial covers.
import colors from "../../../src/assets/apps/colors.json";

const files = import.meta.glob("../../../src/assets/apps/*.png", { eager: true, query: "?url", import: "default" }) as Record<string, string>;
const ICONS: Record<string, string> = {};
for (const [path, url] of Object.entries(files)) ICONS[path.split("/").pop()!.replace(/\.png$/, "")] = url;
const COLORS = colors as Record<string, string>;

const ALIASES: Record<string, string> = { docker: "docker-desktop", chrome: "google-chrome", vscode: "visual-studio-code", "vs-code": "visual-studio-code", settings: "system-settings" };
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

function key(name: string): string | null {
  const first = slug(name.split(/\s+/)[0] ?? "");
  for (const k of [slug(name), ALIASES[slug(name)], first, ALIASES[first]]) if (k && ICONS[k]) return k;
  return null;
}

export function AppIcon({ name, className = "app-icon" }: { name: string | null; className?: string }) {
  const k = name ? key(name) : null;
  return k ? <img className={className} src={ICONS[k]} alt="" /> : <span className={`${className} app-icon--empty`}>{(name ?? "?").trim()[0]?.toUpperCase() ?? "?"}</span>;
}

/** A soft wash of the app's colour, for covers. */
export function coverStyle(name: string | null): React.CSSProperties {
  const k = name ? key(name) : null;
  const c = (k && COLORS[k]) || "#9a958c";
  return { background: `radial-gradient(120% 140% at 30% 0%, ${c}38 0%, ${c}14 55%, #f7f6f3 100%)` };
}
