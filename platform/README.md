# Rio platform

One Cloudflare Worker that does three jobs:
- it serves **the console**, where an organization manages its tutorials, members, API tokens and usage (React + better-auth);
- it serves **the Rio API** (`/v1`), which the desktop app calls with a token;
- it **makes tutorials** from a YouTube link (Gladia, then Holo), a documentation page (H web agent `h/web-surfer-pro` when the page needs a browser, then Holo) or a goal (H deep-search agent `h/deep-search-pro`, Linkup as fallback, then Holo). Where Rio uses Linkup: see [Web search](../README.md#web-search-h-agents-and-linkup).

| Piece | Where |
|---|---|
| Accounts (email + password, or Google), organizations, members, invitations | better-auth on D1 (`src/auth.ts`, `migrations/0001_auth.sql`) |
| API tokens, tutorials, usage events | D1 (`migrations/0002_rio.sql`) |
| Global knowledge (ReStep) | The `knowledge/` Worker (D1 and ReStep's core ported), through the `KNOWLEDGE` service binding |
| Tutorial jobs | `src/ingest.ts`: one step per call, with a lease; run by console polls and a cron every minute |
| Covers | A video's thumbnail; for a page or a goal, the `og:image` of the first source page that has one (read from its `<head>`, https only, 5 s at most per page) |
| Console | `web/` (Vite + React), served as static assets |

## Rio API
Every route except `/v1/health` needs `Authorization: Bearer <token>`. Tokens are created in the console. Only the SHA-256 of a
token is stored, and the token itself is shown once.

| Route | Returns |
|---|---|
| `GET /v1/apps` | The apps the organization can search: the shared ones (Blender, DaVinci Resolve, tools other teams shared) and its own tools |
| `GET /v1/search?q=&app=&version=` | The best skills for a goal, with steps for the learner's version, proof status and sources. Searches ReStep knowledge and the organization's own tutorials. `app` takes an app's name (any case, `Blender 5.2` works) or id from `/v1/apps`; an app the organization cannot see returns 404 with the list of those it can |
| `GET /v1/tutorials` | The organization's tutorials and the shared library, as Rio palette entries |
| `GET /v1/tutorials/<id>?version=` | One tutorial in Rio's milestone format |
| `POST /v1/events` | `tutorial_started`, `milestone_done`, `milestone_skipped`, `tutorial_finished` and `tutorial_abandoned` events, for the usage page |

## Run it locally
```sh
npm install
cp .dev.vars.example .dev.vars              # then fill in the keys
npm run db:migrate:local
(cd knowledge && npm run convert -- <restep checkout> data/knowledge.sql && npm run db:migrate:local && npm run db:load:local)
(cd knowledge && npx wrangler dev --port 8788)   # global knowledge, in another terminal
npm run dev                                 # console and API on http://127.0.0.1:8787
npm test                                    # search, versions, tutorial conversion (offline)
```
Create an account, then an organization and a token. Put the token in Rio's `.env`:
`RIO_API_URL=http://127.0.0.1:8787` and `RIO_API_TOKEN=rio_…`.

## Deploy
```sh
npx wrangler login
npx wrangler d1 create rio                  # put the id in wrangler.toml
(cd knowledge && npm run deploy)      # first: the platform binds to it
npm run db:migrate
for k in BETTER_AUTH_SECRET HAI_API_KEY GLADIA_API_KEY LINKUP_API_KEY; do npx wrangler secret put $k; done
npx wrangler secret put BETTER_AUTH_URL     # https://rio.vignemale.com (the route in wrangler.toml)
npm run deploy
```

## Google sign-in (optional)
The "Continue with Google" button shows only when `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are both set.
1. Google Cloud Console → APIs & Services → OAuth consent screen: user type *External* (or *Internal* for one Workspace),
   scopes `openid`, `email`, `profile` only. These are non-sensitive, so *Publish app* takes effect without review.
   A logo triggers brand verification: leave it out to publish at once.
2. Credentials → Create OAuth client ID → *Web application*, with these authorized redirect URIs:
   `http://127.0.0.1:8787/api/auth/callback/google` and `https://rio.vignemale.com/api/auth/callback/google`.
3. Put the ID and secret in `.dev.vars`, and in production:
   `npx wrangler secret put GOOGLE_CLIENT_ID` then `npx wrangler secret put GOOGLE_CLIENT_SECRET`.

Signing in with Google on an email that already has a password account links to that account.
An invitation is for one email: the Google account must use that email to accept it.

## Data
- `knowledge/scripts/convert.ts` converts a ReStep checkout into the knowledge Worker's D1, using ReStep's core ported to TypeScript.
- `npm run migration:auth` regenerates the better-auth SQL from its schema after a better-auth upgrade.

## Security
- Each organization reads only its own data: every query is filtered by the organization of the session or the token.
- Members can read. Owners and admins manage tutorials, members and tokens, and share the team's own tools with every organization (any organization's admin can do it: there is no platform-wide review yet).
- API keys are Worker secrets: they are never in D1, responses or the console.
- There is no email service yet, so invitations are links shown in the console.
