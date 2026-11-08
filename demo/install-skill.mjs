import { constants } from "node:fs";
import { copyFile, mkdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const demos = {
  textedit: "./textedit-courses/skill.json",
  excel: "./excel-courses/skill.json",
};
const name = process.argv[2] ?? "textedit";
if (!Object.hasOwn(demos, name) || process.argv.length > 3) {
  throw new Error("Usage : npm run demo:skill -- [textedit|excel]");
}
const source = new URL(demos[name], import.meta.url);
const fixture = await readFile(source);
const skill = JSON.parse(fixture);
// Mirrors skills::dir(): there is no environment override in the app.
const root = new URL("../skills/", import.meta.url);
const folder = new URL(`${skill.tutorial_id}/`, root);
const target = new URL("skill.json", folder);

await mkdir(root, { recursive: true });
try {
  await mkdir(folder);
} catch (error) {
  if (error.code !== "EEXIST") throw error;
  const existing = await readFile(target).catch(() => null);
  if (!existing?.equals(fixture)) {
    throw new Error(`Installation refusée : ${fileURLToPath(folder)} existe avec un contenu différent. Sauvegarde ou déplace ce dossier avant de réessayer. Aucun fichier remplacé.`);
  }
  console.log(`Démo déjà installée (inchangée) : ${fileURLToPath(target)}`);
  process.exit(0);
}
await copyFile(source, target, constants.COPYFILE_EXCL);
console.log(`Démo installée : ${fileURLToPath(target)}`);
