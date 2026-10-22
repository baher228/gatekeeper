alter table applicants add column if not exists status_token text;
alter table applicants add column if not exists lead_question text;
alter table applicants add column if not exists applicant_reply text;
alter table applicants add column if not exists applicant_reply_at timestamptz;
alter table applicants alter column status_token set default replace(gen_random_uuid()::text,'-','') || replace(gen_random_uuid()::text,'-','');
update applicants set status_token = replace(gen_random_uuid()::text,'-','') || replace(gen_random_uuid()::text,'-','') where status_token is null;
create unique index if not exists applicants_status_token on applicants(status_token);
