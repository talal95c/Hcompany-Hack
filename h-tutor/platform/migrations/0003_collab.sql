-- Collaboration: a tutorial is a draft until someone publishes it to the team
-- (Rio offers it) or to the community (every organization can find and remix it).
alter table "tutorial" add column "visibility" text not null default 'draft';  -- draft | team | community
alter table "tutorial" add column "publishedAt" integer;
alter table "tutorial" add column "remixOf" text;                               -- the community tutorial it was copied from
update "tutorial" set "visibility" = 'team', "publishedAt" = "updatedAt" where "status" = 'ready';
create index "tutorial_community_idx" on "tutorial" ("visibility", "publishedAt");

create table "tutorial_like" (
  "tutorialId" text not null references "tutorial" ("id") on delete cascade,
  "userId" text not null references "user" ("id") on delete cascade,
  "createdAt" integer not null,
  primary key ("tutorialId", "userId")
);
