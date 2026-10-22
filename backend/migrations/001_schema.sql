create schema if not exists gatekeeper; set search_path to gatekeeper;

create table if not exists communities (
  id uuid primary key default gen_random_uuid(),
  slug text unique not null,
  name text not null,
  description text not null default '',
  rules jsonb not null default '[]'::jsonb,
  reconsider_cooldown_days int not null default 60,
  is_seed boolean not null default false
);

create table if not exists categories (
  id uuid primary key default gen_random_uuid(),
  community_id uuid not null references communities(id) on delete cascade,
  slug text not null,
  name text not null,
  quota int not null default 0,
  bypass_quota boolean not null default false,
  unique(community_id, slug)
);

create table if not exists applicants (
  id uuid primary key default gen_random_uuid(),
  community_id uuid not null references communities(id) on delete cascade,
  name text not null,
  email text not null,
  phone text,
  github text,
  devpost text,
  chat_handle text,
  what_build text not null,
  category text not null,
  status text not null check (status in ('accepted','ask','declined','waitlisted')),
  decision_source text not null check (decision_source in ('auto','lead')),
  final_score double precision not null default 0,
  confidence double precision not null default 0,
  recommendation jsonb not null default '{}'::jsonb,
  features jsonb not null default '{}'::jsonb,
  decline_reason text,
  decided_at timestamptz,
  reconsider_after timestamptz,
  previous_decline jsonb,
  reconsidered boolean not null default false,
  created_at timestamptz not null default now(),
  is_seed boolean not null default false
);
create index if not exists applicants_community_created on applicants(community_id, created_at desc);
create index if not exists applicants_community_status on applicants(community_id, status);

create table if not exists decisions (
  id uuid primary key default gen_random_uuid(),
  applicant_id uuid not null references applicants(id) on delete cascade,
  community_id uuid not null references communities(id) on delete cascade,
  verdict text not null check (verdict in ('accept','decline','ask_more')),
  reason_category text,
  note text,
  source text not null check (source in ('lead','auto','seed')),
  features jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  is_seed boolean not null default false
);
create index if not exists decisions_training on decisions(community_id, source, verdict);

create table if not exists notifications (
  id uuid primary key default gen_random_uuid(),
  community_id uuid not null references communities(id) on delete cascade,
  applicant_id uuid references applicants(id) on delete cascade,
  kind text not null,
  message text not null,
  read boolean not null default false,
  created_at timestamptz not null default now(),
  is_seed boolean not null default false
);

create table if not exists blocklist_entries (
  id uuid primary key default gen_random_uuid(),
  identifier_hash text not null,
  identifier_type text not null check (identifier_type in ('phone','email','github','handle')),
  evidence text not null,
  links text[] not null default '{}',
  reporting_community_id uuid not null references communities(id),
  status text not null check (status in ('pending','confirmed','appealed','removed')),
  created_at timestamptz not null default now(),
  is_seed boolean not null default false
);
create index if not exists blocklist_identifier_hash on blocklist_entries(identifier_hash);

create table if not exists appeals (
  id uuid primary key default gen_random_uuid(),
  entry_id uuid not null references blocklist_entries(id) on delete cascade,
  contact text not null,
  message text not null,
  status text not null check (status in ('open','upheld','rejected')),
  created_at timestamptz not null default now()
);

create table if not exists model_runs (
  id uuid primary key default gen_random_uuid(),
  community_id uuid not null references communities(id) on delete cascade,
  n_decisions int not null,
  n_accept int not null,
  n_decline int not null,
  trained_at timestamptz not null default now(),
  coefficients jsonb not null default '[]'::jsonb
);
