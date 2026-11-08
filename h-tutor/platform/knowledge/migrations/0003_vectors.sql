-- One embedding per search row (skill_search): the shared row of a skill (workspace '')
-- and each organization's own row. text_hash tells when a row changed and needs a new vector.
create table skill_vector (
  skill_id text not null,
  workspace text not null default '',   -- '' = shared
  app text not null,
  model text not null,
  text_hash text not null,
  vec blob not null,                    -- Float32Array, unit length
  primary key (skill_id, workspace)
);
create index skill_vector_app_idx on skill_vector(app, workspace);
