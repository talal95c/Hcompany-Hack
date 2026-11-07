#!/usr/bin/env node
// Admin for the Rio platform's KV store, through wrangler.
//
//   node scripts/admin.mjs upload shared <export.json>...   ReStep knowledge for every organization
//   node scripts/admin.mjs upload <orgId> <export.json>...  knowledge for one organization
// API tokens are made in the console (API tokens page).
//
// Add --remote to write to Cloudflare; the default is the local `wrangler dev` store.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const args = process.argv.slice(2).filter((a) => a !== "--remote");
const where = process.argv.includes("--remote") ? "--remote" : "--local";
const [cmd, org, ...rest] = args;

function wrangler(...a) {
  return execFileSync("npx", ["wrangler", "kv", "key", ...a, "--binding=KB", where], { encoding: "utf8" });
}

function put(key, value) {
  const f = join(mkdtempSync(join(tmpdir(), "rio-kv-")), "v.json");
  writeFileSync(f, typeof value === "string" ? value : JSON.stringify(value));
  wrangler("put", key, "--path", f);
}

function get(key) {
  try {
    return JSON.parse(wrangler("get", key, "--text"));
  } catch {
    return null;
  }
}

if (!org || !/^[A-Za-z0-9_-]+$/.test(org)) {
  console.error("usage: admin.mjs upload <shared|orgId> <export.json>...  [--remote]");
  process.exit(1);
}

if (cmd === "upload") {
  const apps = new Set(get(`kb:${org}:apps`) ?? []);
  for (const file of rest) {
    const raw = readFileSync(file, "utf8");
    const data = JSON.parse(raw);
    put(`kb:${org}:${data.app.id}`, raw);
    apps.add(data.app.id);
    console.log(`${org}: ${data.app.name}, ${Object.keys(data.skills).length} skills, ` +
      `${Object.keys(data.tutorials).length} tutorials`);
  }
  put(`kb:${org}:apps`, [...apps]);
  console.log(`${org} apps: ${[...apps].join(", ")} (${where.slice(2)})`);
} else {
  console.error(`unknown command ${cmd}`);
  process.exit(1);
}
