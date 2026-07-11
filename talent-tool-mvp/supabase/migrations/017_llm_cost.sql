-- LLM cost 监控 (T806) — 持久化 per tenant / provider / model / day 维度.
-- 与 backend/services/cost_tracker.py 配套.

create table if not exists public.llm_cost_events (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null default 'default',
  provider text not null default 'unknown',
  model text not null default 'unknown',
  cost_usd double precision not null default 0,
  occurred_at timestamptz not null default now()
);

create index if not exists llm_cost_events_tenant_time_idx
  on public.llm_cost_events (tenant_id, occurred_at desc);
create index if not exists llm_cost_events_provider_time_idx
  on public.llm_cost_events (provider, occurred_at desc);

create table if not exists public.llm_cost_daily (
  tenant_id text not null,
  provider text not null,
  model text not null,
  cost_usd double precision not null default 0,
  occurred_on date not null,
  updated_at timestamptz not null default now(),
  primary key (tenant_id, provider, model, occurred_on)
);

create index if not exists llm_cost_daily_tenant_idx
  on public.llm_cost_daily (tenant_id, occurred_on desc);
create index if not exists llm_cost_daily_provider_idx
  on public.llm_cost_daily (provider, occurred_on desc);

-- RLS: 仅 service_role 读写.
alter table public.llm_cost_events enable row level security;
alter table public.llm_cost_daily enable row level security;

drop policy if exists llm_cost_events_service_role_all on public.llm_cost_events;
create policy llm_cost_events_service_role_all on public.llm_cost_events
  for all using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists llm_cost_daily_service_role_all on public.llm_cost_daily;
create policy llm_cost_daily_service_role_all on public.llm_cost_daily
  for all using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');
