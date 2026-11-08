// Compares the knowledge Worker's search modes on questions people ask: exact words, paraphrases,
// French, an internal tool, and unrelated questions that must return nothing.
//
//   node --experimental-strip-types scripts/eval.ts [http://127.0.0.1:8788] [workspace]
// The workspace must have the Comptoir guide (test/fixtures/comptoir-guide.md) ingested.

const base = process.argv[2] ?? "http://127.0.0.1:8788";
const ws = process.argv[3] ?? "";

type Case = { q: string; app?: string; want: RegExp | null; kind: string };
const CASES: Case[] = [
  { kind: "exact", q: "remove doubles", app: "Blender", want: /duplicate vert|merge/i },
  { kind: "exact", q: "add a subdivision surface modifier", app: "Blender", want: /subdivision/i },
  { kind: "exact", q: "extrude a face", app: "Blender", want: /extrud/i },
  { kind: "paraphrase", q: "get rid of overlapping vertices", app: "Blender", want: /duplicate vert|merge|remove doubles/i },
  { kind: "paraphrase", q: "make my model look smoother", app: "Blender", want: /smooth|subdivi/i },
  { kind: "paraphrase", q: "put this object in another collection", app: "Blender", want: /collection|layer/i },
  { kind: "french", q: "comment supprimer les sommets en double", app: "Blender", want: /duplicate vert|merge|remove doubles/i },
  { kind: "french", q: "arrondir les bords", app: "Blender", want: /bevel/i },
  { kind: "french", q: "dupliquer un objet", app: "Blender", want: /duplicat/i },
  { kind: "french", q: "lisser un objet", app: "Blender", want: /smooth|subdivi/i },
  { kind: "exact", q: "add a cross dissolve between two clips", app: "DaVinci Resolve", want: /transition|dissolve/i },
  { kind: "paraphrase", q: "change the keyboard shortcuts", app: "DaVinci Resolve", want: /keyboard/i },
  { kind: "french", q: "couper un clip en deux", app: "DaVinci Resolve", want: /split|blade|cut/i },
  { kind: "french", q: "exporter ma vidéo finale", app: "DaVinci Resolve", want: /render|deliver|export/i },
  { kind: "internal", q: "refund an order", want: /refund/i },
  { kind: "internal", q: "give a customer their money back", want: /refund/i },
  { kind: "internal", q: "create a promo code", want: /discount/i },
  { kind: "internal", q: "rembourser un client", want: /refund/i },
  { kind: "internal", q: "renvoyer la facture au client", want: /invoice/i },
  { kind: "internal", q: "télécharger les commandes du mois en csv", want: /export/i },
  { kind: "unrelated", q: "configure the VPN on the office printer", want: null },
  { kind: "unrelated", q: "book a meeting room for tomorrow", want: null },
  { kind: "unrelated", q: "comment faire une pâte à pizza", want: null },
];

type Hit = { intent: string; app_name: string; match?: { words: boolean; cos: number | null } };

async function run(mode: string) {
  let h1 = 0, h3 = 0, rr = 0, asked = 0, falsePos = 0, ms = 0;
  const rows: string[] = [];
  for (const c of CASES) {
    const u = new URL("/search", base);
    u.searchParams.set("q", c.q);
    if (c.app) u.searchParams.set("app", c.app);
    u.searchParams.set("mode", mode);
    u.searchParams.set("limit", "5");
    if (process.env.MIN_COS) u.searchParams.set("min_cos", process.env.MIN_COS);
    if (ws) u.searchParams.set("workspace", ws);
    const t = Date.now();
    const r = (await (await fetch(u)).json()) as { results?: Hit[] };
    ms += Date.now() - t;
    const res = r.results ?? [];
    if (!c.want) {
      if (res.length) falsePos++;
      rows.push(`${res.length ? "✗" : "✓"} [${c.kind}] ${c.q} -> ${res.map((x) => x.intent).slice(0, 2).join(" | ") || "nothing"}`);
      continue;
    }
    asked++;
    const i = res.findIndex((x) => c.want!.test(x.intent));
    if (i === 0) h1++;
    if (i >= 0 && i < 3) h3++;
    if (i >= 0) rr += 1 / (i + 1);
    const top = res[0];
    rows.push(`${i === 0 ? "✓" : i > 0 ? "~" : "✗"} [${c.kind}] ${c.q} -> ${top ? `${top.intent} (${top.app_name}${top.match?.cos != null ? `, cos ${top.match.cos}` : ""})` : "nothing"}`);
  }
  return { mode, h1, h3, mrr: rr / asked, asked, falsePos, unrelated: CASES.length - asked, avgMs: Math.round(ms / CASES.length), rows };
}

const modes = (process.env.MODES ?? "fts,vec,hybrid").split(",");
const out = [];
for (const m of modes) out.push(await run(m));
for (const o of out) {
  console.log(`\n=== ${o.mode}`);
  for (const r of o.rows) console.log("  " + r);
}
console.log("\nmode     hit@1   hit@3   MRR    unrelated answered   avg ms");
for (const o of out)
  console.log(`${o.mode.padEnd(8)} ${`${o.h1}/${o.asked}`.padEnd(7)} ${`${o.h3}/${o.asked}`.padEnd(7)} ${o.mrr.toFixed(2).padEnd(6)} ${`${o.falsePos}/${o.unrelated}`.padEnd(20)} ${o.avgMs}`);

export {};
