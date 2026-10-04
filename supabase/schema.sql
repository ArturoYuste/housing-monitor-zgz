-- Housing Monitor schema for Supabase (Postgres)
-- Run this in the Supabase SQL editor once.

create table if not exists public.properties (
  id text primary key,
  data jsonb not null,
  updated_at timestamptz not null default now()
);

create table if not exists public.app_config (
  id text primary key,
  data jsonb not null,
  updated_at timestamptz not null default now()
);

create index if not exists properties_data_status_idx
  on public.properties ((data->>'status'));

create index if not exists properties_data_portal_idx
  on public.properties ((data->>'portal'));

-- Optional: allow service role full access (default with service key).
-- If using anon key later, add RLS policies carefully.
alter table public.properties enable row level security;
alter table public.app_config enable row level security;

-- Service role bypasses RLS. For anon/authenticated, deny by default.
