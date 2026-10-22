create table if not exists attendee_likes (
  id uuid primary key default gen_random_uuid(),
  community_id uuid not null references communities(id),
  identity_hash text not null,
  is_seed boolean not null default false,
  created_at timestamptz default now(),
  unique(community_id, identity_hash)
);
create index if not exists attendee_likes_identity_hash on attendee_likes(identity_hash);
alter table attendee_likes enable row level security;
grant select, insert, delete on attendee_likes to gatekeeper_community;
drop policy if exists attendee_likes_community on attendee_likes;
create policy attendee_likes_community on attendee_likes for select to gatekeeper_community
  using (community_id = nullif(current_setting('app.community_id', true),'')::uuid);
drop policy if exists attendee_likes_insert on attendee_likes;
create policy attendee_likes_insert on attendee_likes for insert to gatekeeper_community
  with check (community_id = nullif(current_setting('app.community_id', true),'')::uuid);
drop policy if exists attendee_likes_delete on attendee_likes;
create policy attendee_likes_delete on attendee_likes for delete to gatekeeper_community
  using (community_id = nullif(current_setting('app.community_id', true),'')::uuid);
