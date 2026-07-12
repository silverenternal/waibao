-- T1106: Pilot 试用框架 (program + invitation + feedback).
-- 用于招募试用合作方:创建 pilot、邀请用户、收集反馈 / NPS。

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- pilot_programs: 一次试用合作 (一个 organisation 一次合作)
-- ---------------------------------------------------------------------------
create table if not exists public.pilot_programs (
  id uuid primary key default gen_random_uuid(),
  organisation_id uuid references public.organisations(id) on delete cascade,
  name text not null,
  description text,
  status text not null default 'recruiting',  -- 'recruiting' | 'active' | 'completed' | 'cancelled'
  started_at timestamptz,
  ended_at timestamptz,
  target_nps int default 50,                  -- 试用期目标 NPS
  max_users int default 20,                   -- 试用最大用户数
  metadata jsonb not null default '{}'::jsonb,  -- 联系人 / 试用合同 / 备注
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint pilot_programs_status_chk
    check (status in ('recruiting', 'active', 'completed', 'cancelled'))
);

create index if not exists pilot_programs_org_idx
  on public.pilot_programs (organisation_id);
create index if not exists pilot_programs_status_idx
  on public.pilot_programs (status);

-- ---------------------------------------------------------------------------
-- pilot_invitations: 邀请记录
-- ---------------------------------------------------------------------------
create table if not exists public.pilot_invitations (
  id uuid primary key default gen_random_uuid(),
  program_id uuid not null references public.pilot_programs(id) on delete cascade,
  email text not null,
  role text not null default 'jobseeker',     -- 'jobseeker' | 'employer' | 'observer'
  invite_token text not null unique,          -- URL token, secure random
  invited_by uuid references public.users(id) on delete set null,
  invited_at timestamptz not null default now(),
  accepted_at timestamptz,
  status text not null default 'pending',     -- 'pending' | 'accepted' | 'expired' | 'revoked'
  expires_at timestamptz not null default (now() + interval '14 days'),
  metadata jsonb not null default '{}'::jsonb,
  constraint pilot_invitations_status_chk
    check (status in ('pending', 'accepted', 'expired', 'revoked'))
);

create index if not exists pilot_invitations_program_idx
  on public.pilot_invitations (program_id);
create index if not exists pilot_invitations_email_idx
  on public.pilot_invitations (email);
create index if not exists pilot_invitations_token_idx
  on public.pilot_invitations (invite_token);

-- ---------------------------------------------------------------------------
-- pilot_feedback: 试用期反馈 (NPS / 主动留言 / 问卷答案)
-- ---------------------------------------------------------------------------
create table if not exists public.pilot_feedback (
  id uuid primary key default gen_random_uuid(),
  program_id uuid references public.pilot_programs(id) on delete cascade,
  user_id uuid references public.users(id) on delete set null,
  category text not null,                    -- 'nps' | 'bug' | 'feature_request' | 'praise' | 'survey'
  score int,                                  -- NPS 0-10, 或 1-5 评分
  comment text,
  feature_used text,                          -- 涉及功能 (匹配 / 协作房间 / Copilot ...)
  metadata jsonb not null default '{}'::jsonb, -- 问卷答案、来源页面等
  created_at timestamptz not null default now()
);

create index if not exists pilot_feedback_program_idx
  on public.pilot_feedback (program_id, created_at desc);
create index if not exists pilot_feedback_category_idx
  on public.pilot_feedback (category, created_at desc);
create index if not exists pilot_feedback_user_idx
  on public.pilot_feedback (user_id);

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
alter table public.pilot_programs     enable row level security;
alter table public.pilot_invitations  enable row level security;
alter table public.pilot_feedback     enable row level security;

-- pilot_programs: admin 全权, talent_partner 只读自己的 organisation
drop policy if exists pilot_programs_admin_all on public.pilot_programs;
create policy pilot_programs_admin_all on public.pilot_programs
  for all using (
    exists (select 1 from public.users u where u.id = auth.uid() and u.role = 'admin')
  ) with check (
    exists (select 1 from public.users u where u.id = auth.uid() and u.role = 'admin')
  );

drop policy if exists pilot_programs_partner_read on public.pilot_programs;
create policy pilot_programs_partner_read on public.pilot_programs
  for select using (
    exists (
      select 1 from public.users u
      where u.id = auth.uid()
        and u.role = 'talent_partner'
        and u.organisation_id = pilot_programs.organisation_id
    )
  );

-- pilot_invitations: admin 全权, 被邀请者可通过 token 自己 accept
drop policy if exists pilot_invitations_admin_all on public.pilot_invitations;
create policy pilot_invitations_admin_all on public.pilot_invitations
  for all using (
    exists (select 1 from public.users u where u.id = auth.uid() and u.role = 'admin')
  ) with check (
    exists (select 1 from public.users u where u.id = auth.uid() and u.role = 'admin')
  );

drop policy if exists pilot_invitations_self_accept on public.pilot_invitations;
create policy pilot_invitations_self_accept on public.pilot_invitations
  for update using (status = 'pending')
  with check (status in ('accepted', 'expired', 'revoked'));

-- pilot_feedback: 任何登录用户可插入自己的反馈;admin 全部可读;用户读自己的
drop policy if exists pilot_feedback_self_insert on public.pilot_feedback;
create policy pilot_feedback_self_insert on public.pilot_feedback
  for insert with check (user_id = auth.uid() or user_id is null);

drop policy if exists pilot_feedback_self_read on public.pilot_feedback;
create policy pilot_feedback_self_read on public.pilot_feedback
  for select using (user_id = auth.uid());

drop policy if exists pilot_feedback_admin_read on public.pilot_feedback;
create policy pilot_feedback_admin_read on public.pilot_feedback
  for select using (
    exists (select 1 from public.users u where u.id = auth.uid() and u.role = 'admin')
  );

-- updated_at 触发器
create or replace function public.pilot_programs_touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists pilot_programs_touch_updated_at on public.pilot_programs;
create trigger pilot_programs_touch_updated_at
  before update on public.pilot_programs
  for each row execute function public.pilot_programs_touch_updated_at();