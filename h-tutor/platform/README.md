# Rio platform

One Cloudflare Worker that does three jobs:
- it serves **the console**, where an organization manages its tutorials, members, API tokens and usage (React + better-auth);
- it serves **the Rio API** (`/v1`), which the desktop app calls with a token;
- it **makes tutorials** from a YouTube link (Gladia, then Holo), a documentation page (Holo) or a goal (Linkup, then Holo).

| Piece | Where |
|---|---|
| Accounts, organizations, members, invitations | better-auth on D1 (`src/auth.ts`, `migrations/0001_auth.sql`) |
| API tokens, tutorials, usage events | D1 (`migrations/0002_rio.sql`) |
| ReStep knowledge (exports) | KV: `kb:shared:<app>` for every organization, `kb:<orgId>:<app>` for one |
| Tutorial jobs | `src/ingest.ts`: one step per call, with a lease; run by console polls and a cron every minute |
| Console | `web/` (Vite + React), served as static assets |

## Rio API
Every route except `/v1/health` needs `Authorization: Bearer <token>`. Tokens are created in the console. Only the SHA-256 of a
token is stored, and the token itself is shown once.

| Route | Returns |
|---|---|
| `GET /v1/search?q=&app=&version=` | The best skills for a goal, with steps for the learner's version, proof status and sources. Searches ReStep knowledge and the organization's own tutorials |
| `GET /v1/tutorials` | The organization's tutorials and the shared library, as Rio palette entries |
| `GET /v1/tutorials/<id>?version=` | One tutorial in Rio's milestone format |
| `POST /v1/events` | `tutorial_started`, `milestone_done`, `milestone_skipped`, `tutorial_finished` and `tutorial_abandoned` events, for the usage page |

## Run it locally
```sh
npm install
cp .dev.vars.example .dev.vars              # then fill in the keys
npm run db:migrate:local
node scripts/admin.mjs upload shared data/blender.json   # optional: ReStep knowledge
npm run dev                                 # console and API on http://127.0.0.1:8787
npm test                                    # search, versions, tutorial conversion (offline)
```
Create an account, then an organization and a token. Put the token in Rio's `.env`:
`RIO_API_URL=http://127.0.0.1:8787` and `RIO_API_TOKEN=rio_…`.

## Deploy
```sh
npx wrangler login
npx wrangler d1 create rio                  # put the id in wrangler.toml
npx wrangler kv namespace create KB         # same
npm run db:migrate
for k in BETTER_AUTH_SECRET HAI_API_KEY GLADIA_API_KEY LINKUP_API_KEY; do npx wrangler secret put $k; done
npx wrangler secret put BETTER_AUTH_URL     # https://rio-platform.<account>.workers.dev
npm run deploy
```

## Data
- `scripts/export_restep.py` exports a ReStep checkout, with each skill's steps re-targeted to every version by ReStep itself.
- `npm run migration:auth` regenerates the better-auth SQL from its schema after a better-auth upgrade.

## Security
- Each organization reads only its own data: every query is filtered by the organization of the session or the token.
- Members can read. Owners and admins manage tutorials, members and tokens.
- API keys are Worker secrets: they are never in D1, KV, responses or the console.
- There is no email service yet, so invitations are links shown in the console.
