import { readFileSync, readdirSync } from "node:fs";
import assert from "node:assert/strict";

const css = readFileSync(new URL("../src/panel/styles.css", import.meta.url), "utf8");
const radii = [...new Set([...css.matchAll(/border-radius:\s*([^;]+);/g)].map(m => m[1]))].sort();
assert.deepEqual(radii, ["0", "14px", "20px", "2px", "50%", "8px", "999px"]);
const hex = [...new Set(css.match(/#[\da-f]{6}\b/gi))];
const chromatic = hex.filter(c => {
  const rgb = [1,3,5].map(i => parseInt(c.slice(i,i+2),16));
  return Math.max(...rgb)-Math.min(...rgb) > 20;
});
assert.deepEqual(chromatic.sort(), ["#d9420b", "#ff7a1a", "#ffc078"]);
assert.equal((css.match(/linear-gradient\(/g) ?? []).length, 1);
assert.equal((css.match(/var\(--grad\)/g) ?? []).length, 1);
const chrome = ["App.tsx", "Palette.tsx", "Dictaphone.tsx", "icons.tsx"].map(f => readFileSync(new URL(`../src/panel/${f}`, import.meta.url), "utf8")).join("");
assert.equal((chrome.match(/\p{Extended_Pictographic}/gu) ?? []).length, 0);
const dist = new URL("../dist/", import.meta.url);
assert(!readdirSync(dist).some(f => /gallery|dev/.test(f)));
const assets = readdirSync(new URL("assets/", dist)).filter(f => /\.(js|css)$/.test(f));
assert(!assets.some(f => /Material study|study-background|données de démonstration/.test(readFileSync(new URL(`assets/${f}`, dist), "utf8"))));
console.log("PASS accent hues: 1 orange family (3 send-gradient stops); other chromatic colours: 0");
console.log("PASS surface/card/control radii: 20/14/8px; pills: 999px; geometric exceptions: 0/2px/50%");
console.log("PASS emoji in chrome: 0; gradients without brand reason: 0 (1 send gradient)");
console.log("PASS gallery HTML, mock data and background CSS absent from production bundle");
