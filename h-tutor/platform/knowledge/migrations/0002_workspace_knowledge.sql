-- An organization's own knowledge: internal tools and private docs.
-- NULL workspace = shared by every organization (ReStep's graphs).
alter table app add column workspace text;        -- an internal tool belongs to one organization
alter table skill add column workspace text;      -- a skill only private sources teach
alter table tutorial add column workspace text;   -- a private doc read as a whole
create index app_workspace_idx on app(workspace);
create index skill_workspace_idx on skill(app, workspace);
create index source_workspace_idx on source(workspace, app);
