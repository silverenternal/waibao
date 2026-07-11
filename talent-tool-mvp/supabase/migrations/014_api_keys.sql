-- API Keys + Usage (T803).
-- 第三方开发者通过 API Key 访问公开 API.

create table if not exists public.api_keys (
  id uuid primary key default gen_random_uuid(),
  organisation_id uuid not null,
  name text not null,
  -- 仅存哈希;明文只在创建瞬间返回给调用方.
  key_hash text not null,
  -- 明文前缀,用于在 UI 上标识 ("wb_live_xxxx..." -> 前 12 字符).
  key_prefix text not null,
  scopes text[] not null default '{}',
  rate_limit_per_min integer not null default 60,
  expires_at timestamptz,
  revoked_at timestamptz,
  last_used_at timestamptz,
  created_by uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists api_keys_org_idx
  on public.api_keys (organisation_id, revoked_at);
create index if not exists api_keys_hash_idx
  on public.api_keys (key_hash);

create table if not exists public.api_key_usage (
  id uuid primary key default gen_random_uuid(),
  api_key_id uuid not null references public.api_keys(id) on delete cascade,
  endpoint text not null,
  status_code integer not null,
  occurred_at timestamptz not null default now()
);

create index if not exists api_key_usage_key_idx
  on public.api_key_usage (api_key_id, occurred_at desc);
create index if not exists api_key_usage_endpoint_idx
  on public.api_key_usage (endpoint, occurred_at desc);

alter table public.api_keys enable row level security;
alter table public.api_key_usage enable row level security;

drop policy if exists api_keys_member_read on public.api_keys;
create policy api_keys_member_read on public.api_keys
  for select using (
    organisation_id::text = coalesce(
      current_setting('request.jwt.claims', true)::json->>'organisation_id',
      ''
    )
  );

drop policy if exists api_key_usage_member_read on public.api_key_usage;
create policy api_key_usage_member_read on public.api_key_usage
  for select using (
    exists (
      select 1 from public.api_keys k
      where k.id = api_key_usage.api_key_id
        and k.organisation_id::text = coalesce(
          current_setting('request.jwt.claims', true)::json->>'organisation_id',
          ''
        )
    )
  );

drop trigger if exists trg_api_keys_updated_at on public.api_keys;
create trigger trg_api_keys_updated_at
  before update on public.api_keys
  for each row execute function public.set_updated_at();

comment on table public.api_keys is 'T803 third-party developer API keys (hash-only)';
comment on table public.api_key_usage is 'T803 API key call audit';
