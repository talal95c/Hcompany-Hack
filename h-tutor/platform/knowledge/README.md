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

`test/core.test.ts` checks the port against facts ReStep documents, and `test/ground.test.ts` checks grounding an internal tool on its own docs. Three examples:
- *Remove Doubles* (2.79) is *Merge by Distance* under *Mesh › Clean Up* (5.2).
- *Move to Layer* became *Move to Collection* because the M shortcut is the same.
- A 2.79 skill is re-targeted step by step.

Video ingestion (Gladia), proofs (sandbox) and the guide stay in ReStep. Ingesting **written docs** is ported (next section).

## An organization's own knowledge
`POST /ingest {workspace, app, version?, title?, text}` reads a Markdown document the way `restep/kg/ingest.py` reads a written
source. The code is in `src/ingest.ts` and `src/core/ground.ts`:
1. **Structure.** Holo turns the document into paths (one intent each) and steps, with the exact UI words, using ReStep's
   `STRUCT` prompt. A deterministic pass removes UI words the model put in place of a shortcut or a value. It also takes back a
   shortcut the document writes on the step's line when the model left it out.
2. **Inventory.** A tool with no UI scan, such as an internal back-office, gets its inventory from the docs: every menu chain
   becomes an element, with its shortcuts. ReStep builds DaVinci Resolve's inventory from its manual the same way.
3. **Grounding.** Each step is tied to an element by ReStep's rules: the shortcut first, then the label and its menu chain,
   then labels from other versions, and the model's guess only if the element exists, all above 0.5 confidence. The
   Blender-specific rules (enum variants, mesh/object twins) are left out.
4. **One skill per effect.** A path that ends on the same element as a known skill is merged into it. A studio's Blender
   procedure, for example, joins *Remove duplicate vertices*. Otherwise it becomes a new skill.

Everything an organization adds stays private. That covers its internal tools, its sources, its notes, the skills only it
teaches, and its rows in the search index. Other organizations still see the shared skill as before. `DELETE /sources/:id`
removes a document, and the skills only it taught go with it. Re-ingesting the same document replaces it.

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
| `POST /ingest` · `GET /sources` · `DELETE /sources/:id` | An organization's documents (always with `workspace`) |

## Load ReStep's data
```sh
npm run convert -- <restep checkout> data/knowledge.sql   # reads ReStep's files; no Python, no model call
npm run db:migrate:local && npm run db:load:local
npx wrangler dev --port 8788                            # the platform's wrangler dev connects to it
```
Run `npm test` with `RESTEP=<checkout>`.

To deploy, run `npx wrangler d1 create rio-knowledge` and put the id in `wrangler.toml`. Then run `npm run db:migrate`,
`npm run db:load` and `npm run deploy`. Deploy this Worker before the platform, which binds to it.
