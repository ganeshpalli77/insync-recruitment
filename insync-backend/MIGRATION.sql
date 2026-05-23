-- Insync Recruitment AI Resume Screener — Supabase schema.
-- Run once against a fresh project: psql $SUPABASE_DB_URL -f MIGRATION.sql
-- Or apply each statement via the Supabase MCP `apply_migration` tool.

-- Tables ---------------------------------------------------------------------

create table if not exists prospects (
  id uuid primary key default gen_random_uuid(),
  prospect_id text unique not null,
  email text,
  name text,
  company_name text,
  first_seen_at timestamptz not null default now(),
  last_active_at timestamptz,
  tool_use_count integer not null default 0,
  total_resumes_scored integer not null default 0,
  status text not null default 'cold',
  metadata jsonb not null default '{}'::jsonb
);

-- Idempotent in case the table already existed pre-Phase-8.
alter table prospects add column if not exists name text;

create table if not exists scoring_sessions (
  id uuid primary key default gen_random_uuid(),
  session_id text unique not null,
  prospect_id text references prospects(prospect_id) on delete set null,
  job_summary jsonb,
  candidate_count integer,
  total_processing_time_ms integer,
  total_tokens_used integer,
  total_cost_usd decimal(10, 6),
  created_at timestamptz not null default now(),
  ip_address text,
  user_agent text
);

create table if not exists candidate_scores (
  id uuid primary key default gen_random_uuid(),
  session_id text references scoring_sessions(session_id) on delete cascade,
  candidate_name text,
  score integer,
  score_band text,
  scoring_details jsonb,
  created_at timestamptz not null default now()
);

create table if not exists prospect_events (
  id uuid primary key default gen_random_uuid(),
  prospect_id text references prospects(prospect_id) on delete cascade,
  event_type text not null,
  event_data jsonb,
  triggered_crm_webhook boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists leads (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  prospect_id text references prospects(prospect_id) on delete set null,
  source text,
  metadata jsonb,
  created_at timestamptz not null default now(),
  contacted_at timestamptz,
  status text not null default 'new'
);

-- Indexes --------------------------------------------------------------------

create index if not exists idx_prospects_status on prospects(status);
create index if not exists idx_events_prospect on prospect_events(prospect_id);
create index if not exists idx_sessions_prospect on scoring_sessions(prospect_id);
create index if not exists idx_leads_status on leads(status);
create index if not exists idx_candidate_scores_session on candidate_scores(session_id);
create index if not exists idx_candidate_scores_score on candidate_scores(score desc);

-- Row Level Security ---------------------------------------------------------
-- Anonymous role may INSERT only. Service key (used by the backend) bypasses RLS.

alter table prospects enable row level security;
alter table scoring_sessions enable row level security;
alter table candidate_scores enable row level security;
alter table prospect_events enable row level security;
alter table leads enable row level security;

do $$ begin
  if not exists (select 1 from pg_policies where policyname = 'anon_insert_prospects') then
    create policy anon_insert_prospects on prospects for insert to anon with check (true);
  end if;
  if not exists (select 1 from pg_policies where policyname = 'anon_insert_sessions') then
    create policy anon_insert_sessions on scoring_sessions for insert to anon with check (true);
  end if;
  if not exists (select 1 from pg_policies where policyname = 'anon_insert_candidate_scores') then
    create policy anon_insert_candidate_scores on candidate_scores for insert to anon with check (true);
  end if;
  if not exists (select 1 from pg_policies where policyname = 'anon_insert_events') then
    create policy anon_insert_events on prospect_events for insert to anon with check (true);
  end if;
  if not exists (select 1 from pg_policies where policyname = 'anon_insert_leads') then
    create policy anon_insert_leads on leads for insert to anon with check (true);
  end if;
end $$;
