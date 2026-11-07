-- Rio knowledge: ReStep's graphs, split the way ReStep's design splits them.
-- 1. knowledge (sources -> segments -> claims): what was said, per workspace (NULL = shared)
-- 2. actions (atoms -> placements per version, successor edges): what the software says it is
-- 3. bridge (grounds, teaches): derived, recomputable
-- Ids are ReStep's own, so a re-import replaces rows instead of duplicating them.

create table app (
  id text primary key,
  name text not null,
  vendor text,
  current_version text not null,
  grounding text not null,        -- JSON: nav_ops, routine_ops, menu_openers, confirm_ops
  imported_at integer not null
);
create table app_version (
  app text not null references app(id) on delete cascade,
  version text not null,
  label text,
  covers_from text not null default '0',  -- the oldest version this one stands for ("2.80")
  year integer,
  primary key (app, version)
);

-- ===== 1. knowledge
create table source (
  id text primary key,            -- yt_<id> | src_<sha1(url)>
  workspace text,                 -- NULL: shared by every organization
  app text not null references app(id) on delete cascade,
  url text, kind text, title text, author text, language text,
  stated_version text, version text,
  added_at real
);
create table segment (            -- a passage of a source that teaches one skill
  id text primary key,            -- <source>|<skill>
  source_id text not null references source(id) on delete cascade,
  intent text,
  t_start real, t_end real,
  version text,
  steps_json text not null        -- ordered claim ids
);
create table claim (              -- a step as it was said
  id text primary key,
  source_id text not null references source(id) on delete cascade,
  say text, action text,
  ui_json text, keys text, value text, t real,
  version text not null,
  variant text
);

-- ===== 2. actions
create table atom (
  id text primary key,            -- the operator id (mesh.merge, resolve:menu/edit/undo, prop:..., tab:...)
  app text not null references app(id) on delete cascade,
  kind text                       -- operator | menu | page | prop | tab | tool
);
create table placement (          -- where an atom is in one version
  atom_id text not null,
  app text not null,
  version text not null,
  label text,
  paths_json text not null,       -- ["Mesh › Clean Up › Merge by Distance", ...]
  keys_json text not null,        -- ["Ctrl+B"]
  via_keys_json text not null,    -- ["W › Remove Doubles"]
  primary key (app, version, atom_id)
);
create table atom_edge (
  src text not null, dst text not null,
  type text not null,             -- successor
  app text not null,
  from_version text not null, to_version text not null,
  label text, evidence text, key text,
  primary key (app, src, from_version, to_version, type)
);
create table atom_label (         -- every name a UI element has had: "where is Remove Doubles now?"
  app text not null, version text not null, label_norm text not null, atom_id text not null,
  primary key (app, version, label_norm, atom_id)
);
create table skill (
  id text primary key,
  app text not null references app(id) on delete cascade,
  name text not null,             -- ReStep's merged intent for the effect
  effect_atom text,
  ops_json text not null,
  steps_json text not null        -- the default claim ids
);
create table proof (
  skill_id text not null references skill(id) on delete cascade,
  version text not null,
  status text not null,           -- PASS | FAIL
  primary key (skill_id, version)
);
create table tutorial (            -- a source read as a whole: its skills in order
  id text primary key,
  app text not null references app(id) on delete cascade,
  source_id text not null references source(id) on delete cascade,
  title text, version text,
  skills_json text not null
);
create table note (               -- what sources say about a skill (explanations, warnings)
  skill_id text not null references skill(id) on delete cascade,
  source_id text not null,
  kind text, text text not null, t real
);

-- ===== 3. bridge (derived)
create table grounds (
  claim_id text primary key references claim(id) on delete cascade,
  atom_id text not null,
  confidence real
);
create table teaches (
  segment_id text primary key references segment(id) on delete cascade,
  skill_id text not null references skill(id) on delete cascade
);

-- ===== search: skills by their name, what sources say, and UI labels of every version
create virtual table skill_search using fts5(
  skill_id unindexed, app unindexed, workspace unindexed,
  intent, body,
  tokenize = 'porter unicode61 remove_diacritics 2'
);

create index claim_source_idx on claim(source_id);
create index segment_source_idx on segment(source_id);
create index teaches_skill_idx on teaches(skill_id);
create index edge_dst_idx on atom_edge(app, dst);
create index label_atom_idx on atom_label(app, atom_id);
