alter table blocklist_entries enable row level security;

do $$ begin
  if not exists (select 1 from pg_roles where rolname='gatekeeper_community') then
    create role gatekeeper_community nologin;
  end if;
end $$;
grant usage on schema public to gatekeeper_community;
grant select, insert, update on blocklist_entries to gatekeeper_community;
grant select, insert on appeals to gatekeeper_community;
grant select on communities to gatekeeper_community;
drop policy if exists community_read on blocklist_entries;
create policy community_read on blocklist_entries for select to gatekeeper_community
  using (status in ('confirmed','appealed') or reporting_community_id = nullif(current_setting('app.community_id', true),'')::uuid);
drop policy if exists community_insert on blocklist_entries;
create policy community_insert on blocklist_entries for insert to gatekeeper_community
  with check (reporting_community_id = nullif(current_setting('app.community_id', true),'')::uuid and status = 'pending');
drop policy if exists community_update on blocklist_entries;
create policy community_update on blocklist_entries for update to gatekeeper_community
  using (reporting_community_id = nullif(current_setting('app.community_id', true),'')::uuid);

do $$ begin
  execute format('grant gatekeeper_community to %I', current_user);
exception when insufficient_privilege or undefined_object then
  raise notice 'Could not grant gatekeeper_community to current user; configure SET ROLE permission for the app role';
end $$;
