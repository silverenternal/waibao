-- Webhook subscription + delivery log (T802).

create table if not exists public.webhooks (
  id uuid primary key default gen_random_uuid(),
  organisation_id uuid not null,
  name text not null,
  url text not null,
  secret text not null,
  events text[] not null default '{}',
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  description text
);

create index if not exists webhooks_org_idx on public.webhooks (organisation_id, active);
create index if not exists webhooks_events_idx on public.webhooks using gin (events);

create table if not exists public.webhook_deliveries (
  id uuid primary key default gen_random_uuid(),
  webhook_id uuid not null references public.webhooks(id) on delete cascade,
  event_type text not null,
  payload jsonb not null,
  status text not null default 'pending',
  attempts int not null default 0,
  last_attempt_at timestamptz,
  response_code int,
  response_body text,
  created_at timestamptz not null default now(),
  last_error text
);

create index if not exists webhook_deliveries_webhook_idx
  on public.webhook_deliveries (webhook_id, created_at desc);
create index if not exists webhook_deliveries_status_idx
  on public.webhook_deliveries (status, created_at desc);

-- RLS helpers: service_role bypasses RLS so the API can use it directly.
alter table public.webhooks enable row level security;
alter table public.webhook_deliveries enable row level security;

-- Policy: members of the organisation can read their webhooks.
drop policy if exists webhooks_member_read on public.webhooks;
create policy webhooks_member_read on public.webhooks
  for select using (
    organisation_id::text = coalesce(
      current_setting('request.jwt.claims', true)::json->>'organisation_id',
      ''
    )
  );

-- Service role bypasses RLS (handled by service key in API).

-- Update timestamp trigger
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_webhooks_updated_at on public.webhooks;
create trigger trg_webhooks_updated_at
  before update on public.webhooks
  for each row execute function public.set_updated_at();

comment on table public.webhooks is 'T802 webhook subscriptions';
comment on table public.webhook_deliveries is 'T802 webhook delivery audit + dead-letter store';
