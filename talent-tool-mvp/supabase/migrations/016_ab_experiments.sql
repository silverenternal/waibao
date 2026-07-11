-- A/B 实验框架数据持久化 (T805)
-- 与 backend/services/ab_test.py 字段保持同步.

create table if not exists public.experiments (
  id uuid primary key default gen_random_uuid(),
  name text unique not null,
  description text not null default '',
  primary_metric text not null default 'match.score',
  status text not null default 'draft',  -- draft | running | stopped | completed
  salt text not null default 'recruittech-ab-default-salt',
  variants jsonb not null default '[]'::jsonb,  -- [{"name","weight","config"}]
  metadata jsonb not null default '{}'::jsonb,
  started_at timestamptz,
  ended_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint experiments_status_chk
    check (status in ('draft', 'running', 'stopped', 'completed'))
);

create index if not exists experiments_status_idx
  on public.experiments (status, started_at desc);

create table if not exists public.experiment_assignments (
  experiment_id uuid not null references public.experiments(id) on delete cascade,
  user_id text not null,
  variant text not null,
  assigned_at timestamptz not null default now(),
  primary key (experiment_id, user_id)
);

create index if not exists experiment_assignments_exp_idx
  on public.experiment_assignments (experiment_id, variant);

create table if not exists public.experiment_metrics (
  id uuid primary key default gen_random_uuid(),
  experiment_id uuid not null references public.experiments(id) on delete cascade,
  variant text not null,
  metric_name text not null,
  value double precision not null,
  user_id text,  -- 可选,聚合时用
  context jsonb not null default '{}'::jsonb,
  recorded_at timestamptz not null default now()
);

create index if not exists experiment_metrics_lookup_idx
  on public.experiment_metrics (experiment_id, metric_name, variant, recorded_at desc);

-- RLS: 默认 admin 全权, anon 拒绝 (admin API 用 service role key).
alter table public.experiments enable row level security;
alter table public.experiment_assignments enable row level security;
alter table public.experiment_metrics enable row level security;

-- 仅 service_role 可读写;前端访问需要通过后端 admin API.
drop policy if exists experiments_service_role_all on public.experiments;
create policy experiments_service_role_all on public.experiments
  for all using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists experiment_assignments_service_role_all on public.experiment_assignments;
create policy experiment_assignments_service_role_all on public.experiment_assignments
  for all using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists experiment_metrics_service_role_all on public.experiment_metrics;
create policy experiment_metrics_service_role_all on public.experiment_metrics
  for all using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

-- updated_at 自动维护
drop trigger if exists trg_experiments_updated_at on public.experiments;
create trigger trg_experiments_updated_at
  before update on public.experiments
  for each row execute function public.set_updated_at();
