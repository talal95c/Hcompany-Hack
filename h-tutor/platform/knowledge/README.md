# Rio knowledge

A Cloudflare Worker that only searches. It holds [ReStep](https://github.com/Wassbdr/restep)'s graphs in D1 and runs
ReStep's core, ported to TypeScript, to answer one question: *how do I do this, in my version?*

## What is ported
| ReStep (Python) | Here |
|---|---|
| `kg/inventory.py`: inventory, label index, `where`, `successor` | `src/core/inventory.ts` |
| `kg/prove.py`: `resolve`, `navigation`, `instruction` | `src/core/retarget.ts` |
| `kg/api.py`: `path`, `change_kind`, lead steps, `locate` / `atom_now` | `src/core/retarget.ts`, `src/index.ts` |
| `kg/ingest.py`: `effect_op`, `parse_keys` | `src/core/retarget.ts` |

`test/core.test.ts` checks the port against facts ReStep documents. Three examples:
- *Remove Doubles* (2.79) is *Merge by Distance* under *Mesh › Clean Up* (5.2).
- *Move to Layer* became *Move to Collection* because the M shortcut is the same.
- A 2.79 skill is re-targeted step by step.

Ingestion (Gladia, Holo), proofs (sandbox) and the guide stay in ReStep. This Worker reads what they produce.

## Storage
The schema in `migrations/0001_knowledge.sql` follows ReStep's design, in three layers:
- **Knowledge**: sources, segments and claims, per workspace. `NULL` means the source is shared by every organization.
- **Actions**: atoms, their placement in each version, and successor edges. The software itself provides this layer.
- **Bridge**: grounds and teaches. This layer is derived and can be recomputed.

On top of these layers:
- `skill_search` is a full-text index (FTS5) over each skill's name, what sources say about it, and its labels in every
  version. The index has a `workspace` column, so one organization's sources never appear in another's results.
- Ids are ReStep's own, so a re-import replaces rows instead of duplicating them.

## API (service binding only, no public URL)
| Route | Returns |
|---|---|
| `GET /search?q=&alt=&app=&version=&workspace=` | Skills for a goal, each with its steps for the learner's version |
| `GET /skills?app=&q=` · `GET /skills/:id?version=&source=` | Browse skills, or get one re-targeted to a version |
| `GET /tutorials?app=` · `GET /tutorials/:id?version=&format=rio` | Sources read as whole tutorials, optionally in Rio's milestone format |
| `GET /locate?app=&q=&version=` | Where a UI element is now, under any name it has had |
| `GET /graph?app=` | ReStep's graph view: sources → skills → UI atoms, each atom labelled as it is now |
| `GET /apps` | Apps, versions and sizes |

## Load ReStep's data
```sh
npm run convert -- <restep checkout> data/knowledge.sql   # reads ReStep's files; no Python, no model call
npm run db:migrate:local && npm run db:load:local
npx wrangler dev --port 8788                            # the platform's wrangler dev connects to it
```
Run `npm test` with `RESTEP=<checkout>`.

To deploy, run `npx wrangler d1 create rio-knowledge` and put the id in `wrangler.toml`. Then run `npm run db:migrate`,
`npm run db:load` and `npm run deploy`. Deploy this Worker before the platform, which binds to it.
