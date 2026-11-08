// App icons shipped with Rio (src/assets/apps/, exported once with
// `cargo test --lib app_icons -- --ignored`): the palette never reads the computer.
import colors from "../assets/apps/colors.json";

const files = import.meta.glob("../assets/apps/*.png", { eager: true, query: "?url", import: "default" }) as Record<
  string,
  string
>;

const ICONS: Record<string, string> = {};
for (const [path, url] of Object.entries(files)) ICONS[path.split("/").pop()!.replace(/\.png$/, "")] = url;

/** Other names the same apps go by. */
const ALIASES: Record<string, string> = {
  docker: "docker-desktop",
  chrome: "google-chrome",
  vscode: "visual-studio-code",
  "vs-code": "visual-studio-code",
  settings: "system-settings",
  "system-preferences": "system-settings",
};

const slug = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

export type AppIcon = { src: string; color: string };

/** The icon of an app by its name ("Blender", "Docker", "Blender 4.2"), or null. */
export function appIcon(name: string): AppIcon | null {
  const full = slug(name);
  for (const k of [full, ALIASES[full], slug(name.split(/\s+/)[0] ?? ""), ALIASES[slug(name.split(/\s+/)[0] ?? "")]]) {
    if (k && ICONS[k]) return { src: ICONS[k], color: (colors as Record<string, string>)[k] ?? "#888888" };
  }
  return null;
}
