-- Rio platform tables. Organizations and users are better-auth's (0001_auth.sql).

-- API tokens for the Rio app. Only the SHA-256 of a token is stored; the token
-- itself is shown once, when it is created.
create table "api_token" (
  "id" text not null primary key,
  "organizationId" text not null references "organization" ("id") on delete cascade,
  "name" text not null,
  "hash" text not null unique,
  "prefix" text not null,            -- first characters, to recognize a token in the list
  "createdBy" text references "user" ("id") on delete set null,
  "createdAt" integer not null,      -- ms since epoch
  "lastUsedAt" integer,
  "revokedAt" integer
);
create index "api_token_org_idx" on "api_token" ("organizationId");

-- Tutorials made by the platform from a YouTube video, a documentation page or a
-- goal (Linkup web search). `status` walks queued -> transcribing|reading|searching
-- -> designing -> ready | failed; `job` holds the intermediate results.
create table "tutorial" (
  "id" text not null primary key,
  "organizationId" text not null references "organization" ("id") on delete cascade,
  "kind" text not null,              -- youtube | page | goal
  "input" text not null,             -- the URL or the goal
  "title" text,
  "app" text,
  "status" text not null,
  "error" text,
  "job" text,                        -- JSON: Gladia id, transcript, page text, search results
  "data" text,                       -- JSON: the tutorial in Rio's format, when ready
  "sources" text,                    -- JSON: [{title, url}]
  "createdBy" text references "user" ("id") on delete set null,
  "createdAt" integer not null,
  "updatedAt" integer not null,
  "leaseUntil" integer not null default 0  -- a worker owns the job until then
);
create index "tutorial_org_idx" on "tutorial" ("organizationId", "createdAt");
create index "tutorial_pending_idx" on "tutorial" ("status", "leaseUntil");

-- What happens in Rio, for the usage page: searches (from /v1/search) and the
-- events the app reports (tutorial started, milestone skipped, finished...).
create table "usage_event" (
  "id" integer primary key autoincrement,
  "organizationId" text not null references "organization" ("id") on delete cascade,
  "kind" text not null,              -- search | tutorial_started | milestone_done | milestone_skipped | tutorial_finished | tutorial_abandoned
  "tutorialId" text,
  "tutorialTitle" text,
  "milestone" text,
  "query" text,
  "app" text,
  "results" integer,
  "createdAt" integer not null
);
create index "usage_org_idx" on "usage_event" ("organizationId", "createdAt");
