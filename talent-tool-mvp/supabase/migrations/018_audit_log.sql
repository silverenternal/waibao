-- 审计日志 (T1004): 记录所有 PII 访问、GDPR 操作、敏感数据修改.
-- append-only: 仅 INSERT,禁止 UPDATE / DELETE (用 RLS + trigger 双重保证).

create extension if not exists "pgcrypto";

create table if not exists public.audit_log (
  id uuid primary key default gen_random_uuid(),
  user_id uuid,                              -- 被访问资源的拥有者 (PII subject)
  actor_user_id uuid,                        -- 发起访问的用户
  action text not null,                      -- 'read' | 'create' | 'update' | 'delete' | 'export' | 'forget' | 'login' ...
  resource_type text not null,               -- 'candidate' | 'role' | 'journal' | 'ticket' | 'message' | 'gdpr' ...
  resource_id text,                          -- resource PK (uuid 或 string)
  ip_address inet,
  user_agent text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists audit_log_user_id_idx
  on public.audit_log (user_id, created_at desc);
create index if not exists audit_log_actor_idx
  on public.audit_log (actor_user_id, created_at desc);
create index if not exists audit_log_resource_idx
  on public.audit_log (resource_type, resource_id, created_at desc);
create index if not exists audit_log_action_idx
  on public.audit_log (action, created_at desc);

-- RLS: 仅 admin 可读; service_role 可写.
alter table public.audit_log enable row level security;

drop policy if exists audit_log_admin_select on public.audit_log;
create policy audit_log_admin_select on public.audit_log
  for select using (
    exists (
      select 1 from public.users u
      where u.id = auth.uid() and u.role = 'admin'
    )
  );

drop policy if exists audit_log_service_role_insert on public.audit_log;
create policy audit_log_service_role_insert on public.audit_log
  for insert with check (auth.role() = 'service_role');

-- 阻止 UPDATE / DELETE: revoke 普通角色权限 + 用 trigger 拦截 service_role 误操作
revoke update, delete on public.audit_log from authenticated, anon;

create or replace function public.audit_log_block_mutation()
returns trigger
language plpgsql
as $$
begin
  raise exception 'audit_log is append-only; % not allowed', tg_op
    using errcode = 'P0001';
end;
$$;

drop trigger if exists audit_log_no_update on public.audit_log;
create trigger audit_log_no_update
  before update on public.audit_log
  for each row execute function public.audit_log_block_mutation();

drop trigger if exists audit_log_no_delete on public.audit_log;
create trigger audit_log_no_delete
  before delete on public.audit_log
  for each row execute function public.audit_log_block_mutation();