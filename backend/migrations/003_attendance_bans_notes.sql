create table if not exists attendance (
  id uuid primary key default gen_random_uuid(),
  community_id uuid not null references communities(id),
  identity_hash text not null,
  event_name text not null,
  event_date date not null,
  status text not null check (status in ('attended','no_show')),
  is_seed boolean not null default false,
  created_at timestamptz default now()
);
create index if not exists attendance_identity_hash on attendance(identity_hash);
alter table attendance enable row level security;
grant select, insert, delete on attendance to gatekeeper_community;
drop policy if exists attendance_community on attendance;
create policy attendance_community on attendance for select to gatekeeper_community
  using (community_id = nullif(current_setting('app.community_id', true),'')::uuid);
drop policy if exists attendance_insert on attendance;
create policy attendance_insert on attendance for insert to gatekeeper_community
  with check (community_id = nullif(current_setting('app.community_id', true),'')::uuid);
drop policy if exists attendance_delete on attendance;
create policy attendance_delete on attendance for delete to gatekeeper_community
  using (community_id = nullif(current_setting('app.community_id', true),'')::uuid);

create table if not exists community_bans (
  id uuid primary key default gen_random_uuid(),
  community_id uuid not null references communities(id),
  identity_hash text not null,
  identifier_type text not null,
  label text,
  reason text not null,
  created_by text not null default 'lead',
  created_at timestamptz default now(),
  unique(community_id, identity_hash)
);
create index if not exists community_bans_identity_hash on community_bans(identity_hash);
alter table community_bans enable row level security;
grant select, insert, delete on community_bans to gatekeeper_community;
drop policy if exists community_bans_community on community_bans;
create policy community_bans_community on community_bans for select to gatekeeper_community
  using (community_id = nullif(current_setting('app.community_id', true),'')::uuid);
drop policy if exists community_bans_insert on community_bans;
create policy community_bans_insert on community_bans for insert to gatekeeper_community
  with check (community_id = nullif(current_setting('app.community_id', true),'')::uuid);
drop policy if exists community_bans_delete on community_bans;
create policy community_bans_delete on community_bans for delete to gatekeeper_community
  using (community_id = nullif(current_setting('app.community_id', true),'')::uuid);

create table if not exists attendee_notes (
  id uuid primary key default gen_random_uuid(),
  community_id uuid not null references communities(id),
  identity_hash text not null,
  flag text null check (flag in ('great_volunteer','no_show','disruptive','watch','vip')),
  note text not null default '',
  visibility text not null check (visibility in ('private','shared')),
  author text not null default 'lead',
  is_seed boolean not null default false,
  created_at timestamptz default now()
);
create index if not exists attendee_notes_identity_hash on attendee_notes(identity_hash);
alter table attendee_notes enable row level security;
grant select, insert, delete on attendee_notes to gatekeeper_community;
drop policy if exists attendee_notes_community on attendee_notes;
create policy attendee_notes_community on attendee_notes for select to gatekeeper_community
  using (visibility = 'shared' or community_id = nullif(current_setting('app.community_id', true),'')::uuid);
drop policy if exists attendee_notes_insert on attendee_notes;
create policy attendee_notes_insert on attendee_notes for insert to gatekeeper_community
  with check (community_id = nullif(current_setting('app.community_id', true),'')::uuid);
drop policy if exists attendee_notes_delete on attendee_notes;
create policy attendee_notes_delete on attendee_notes for delete to gatekeeper_community
  using (community_id = nullif(current_setting('app.community_id', true),'')::uuid);
