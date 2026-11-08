-- The organization that created an app from its docs. It stays the owner once the app is shared with every
-- organization (workspace NULL), so it can keep adding to it, remove its docs, or make it private again.
alter table app add column owner text;
update app set owner = workspace where workspace is not null;
