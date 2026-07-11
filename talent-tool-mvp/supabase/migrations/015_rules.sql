-- Rule engine persistence (T804).
-- 与 backend/services/rule_engine/dsl.py 字段保持同步.

create table if not exists public.rules (
  id uuid primary key default gen_random_uuid(),
  organisation_id uuid not null,
  name text not null,
  description text not null default '',
  trigger text not null,
  -- ConditionGroup JSON;AND/OR/NOT 嵌套,最多 3 层 (UI 与 evaluator 校验).
  condition jsonb,
  actions jsonb not null default '[]'::jsonb,
  enabled boolean not null default true,
  cooldown_seconds integer not null default 0,
  tags text[] not null default '{}',
  last_triggered_at timestamptz,
  trigger_count integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists rules_org_idx
  on public.rules (organisation_id, enabled);
create index if not exists rules_trigger_idx
  on public.rules (trigger) where enabled = true;

create table if not exists public.rule_runs (
  id uuid primary key default gen_random_uuid(),
  rule_id uuid not null references public.rules(id) on delete cascade,
  organisation_id uuid not null,
  trigger text not null,
  context_snapshot jsonb not null default '{}'::jsonb,
  matched boolean not null,
  actions_executed jsonb not null default '[]'::jsonb,
  duration_ms integer not null default 0,
  error text,
  occurred_at timestamptz not null default now()
);

create index if not exists rule_runs_rule_idx
  on public.rule_runs (rule_id, occurred_at desc);
create index if not exists rule_runs_org_idx
  on public.rule_runs (organisation_id, occurred_at desc);

alter table public.rules enable row level security;
alter table public.rule_runs enable row level security;

drop policy if exists rules_member_read on public.rules;
create policy rules_member_read on public.rules
  for select using (
    organisation_id::text = coalesce(
      current_setting('request.jwt.claims', true)::json->>'organisation_id',
      ''
    )
  );

drop policy if exists rule_runs_member_read on public.rule_runs;
create policy rule_runs_member_read on public.rule_runs
  for select using (
    organisation_id::text = coalesce(
      current_setting('request.jwt.claims', true)::json->>'organisation_id',
      ''
    )
  );

drop trigger if exists trg_rules_updated_at on public.rules;
create trigger trg_rules_updated_at
  before update on public.rules
  for each row execute function public.set_updated_at();

comment on table public.rules is 'T804 webhook-triggered automation rules';
comment on table public.rule_runs is 'T804 audit trail of rule evaluations';
