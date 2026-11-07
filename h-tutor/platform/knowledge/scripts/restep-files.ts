// Reading a ReStep checkout's files (shared by the converter and the tests).
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { type Inventory, type VersionFiles, inventory } from "../src/core/inventory.ts";
import type { Grounding } from "../src/core/retarget.ts";

const json = (p: string) => JSON.parse(readFileSync(p, "utf8"));
const maybe = (p: string) => (existsSync(p) ? json(p) : undefined);

export interface AppMeta {
  id: string;
  name: string;
  vendor?: string;
  versions: { id: string; label?: string; year?: number; covers_from?: string }[];
  current_version?: string;
  grounding?: Partial<Grounding> & Record<string, unknown>;
}

/** Versions oldest first, as restep sorts them (year, then the numbers in the id). */
export function versions(meta: AppMeta): string[] {
  const key = (v: AppMeta["versions"][number]) => [v.year ?? 0, ...(v.id.match(/\d+/g) ?? []).map(Number)];
  return [...meta.versions]
    .sort((a, b) => {
      const ka = key(a);
      const kb = key(b);
      for (let i = 0; i < Math.max(ka.length, kb.length); i++) if ((ka[i] ?? -1) !== (kb[i] ?? -1)) return (ka[i] ?? -1) - (kb[i] ?? -1);
      return 0;
    })
    .map((v) => v.id);
}

export function loadInventory(root: string, app: string, v: string): Inventory {
  const f: VersionFiles = {
    menus: maybe(join(root, "apps", app, "menus", `menus_${v}.json`)),
    oplabels: maybe(join(root, "apps", app, "menus", `oplabels_${v}.json`)),
    ui: maybe(join(root, "kb", app, `ui_${v}.json`)),
    keymaps: maybe(join(root, "kb", app, `keymaps_${v}.json`))?.items,
    generic: maybe(join(root, "apps", app, `inventory_${v}.json`)),
  };
  return inventory(f);
}

