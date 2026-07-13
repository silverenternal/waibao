# waibao v10.0 数据库 + 性能审查报告

> 审查基线：`/home/hugo/codes/waibao/talent-tool-mvp/supabase/migrations/` 共 53 个文件、7,694 行 SQL（v1-v8.1 + RAG/Memory/Prompt/ServiceToggle/Marketplace/Whitelabel）；后端服务层 `backend/services/` 涉及数据库的部分。`backend/services/` 静态扫描 870+ 个 Python 文件；本审计仅覆盖与数据库交互的 80+ 服务模块。本次审查未在真实 Postgres 上重跑所有 `EXPLAIN ANALYZE` 与负载，因此“索引命中率/慢查询/QPS”为工程估算（基于 schema、索引、pgvector HNSW 文档与代码调用）。

## 总体评分
- 数据库 Schema: **6.8/10**
- 多租户 RLS: **6.3/10**（功能齐全但执行路径有 5 处可绕过；见 P0/P1）
- 索引与性能: **5.9/10**（核心路径有覆盖，复合/部分/GIN 索引在 v6-v8 加固但仍有 8 处缺口）
- pgvector: **7.2/10**（HNSW 一致 + IVFFlat 错位 + RAG/记忆/制度库三个独立 1024-d 索引）
- 数据完整性: **7.0/10**（trigger + RLS + append-only 多重保障，但 update_at 仅 70% 表覆盖）
- 备份与灾备: **5.2/10**（Supabase 默认 PITR 缺失运维演练、归档/冷热分层策略；只 docs/DR_DRILL_Q3.md 等脚本级演练）

总体判断：53 个 migration 构筑了“几乎覆盖一切业务”的企业级数据底座（candidates/roles/matches/tickets/rooms/rag/memory/prompt/marketplace/whitelabel/services），并且补齐了 v6 之后的 RAG/Memory/Prompt/Marketplace/ServiceToggle 等热点子系统。但仍存在 5 类显著短板：(1) 索引密度不均（业务表 200+ 索引、配置/审计表 5+），热点查询缺复合/覆盖索引；(2) 触发器/RLS 命名/职责有重叠与缺口（`audit_log_no_delete`、`service_audit_enforce_retention`、`enforce_tenant_id` 三类冲突面）；(3) 真实 tenant_id 列仅由 046_tenant_context 注入，**47 张业务表** 中只有 26 张被覆盖（事实/候选/工单/策略/记忆等），其它仍是 `organisation_id` 为主；(4) pgvector 多套 1024-d 独立索引（RAG/Memory/Policies），跨域搜索/缓存策略缺统一抽象；(5) 灾备与备份恢复脚本散落在 docs/，无 PITR 演练计划、无冷热分层归档 SOP。

关键量化证据：
- 共 **131 个 `CREATE TABLE`**，**314 个 `CREATE INDEX`**（含 GIN 14、HNSW 4、IVFFlat 1、B-tree 295+）。
- 47 张业务表中只有 26 张被 046 加入 `tenant_id` 列 + RLS policy（其它仍是 `organisation_id`）。
- 仅 24 张表有 `updated_at TIMESTAMPTZ` 字段；**14 张** 缺自动维护 trigger（如 `realtime_sessions`、`realtime_transcripts`、`webhooks`、`api_keys`、`rules`、`experiment_metrics`、`llm_cost_events`、`llm_cost_daily`、`corp_bindings` 之外：未列全的还有 `conversations`、`agent_memory`、`career_plans`、`company_strategy`、`pilot_programs` 等）。
- 4 个 `vector(...)` 列：`candidates.embedding(1536)` + `roles.embedding(1536)` + `company_policies.embedding(1536)` + `rag_chunks.embedding(1024)` + `memories_v2.embedding(1024)`，HNSW 索引 4 个，IVFFlat 1 个。
- append-only 触发器：`audit_log_no_update/delete`、`audit_log_v2_no_update/delete`、`service_audit_retention(DELETE forbidden)`、`enforce_tenant_id(insert)`、`dsr_check_sla_breach`、`room_after_message`、`room_after_thread_reply`、`room_after_member_change`。
- 21 张表加入 `supabase_realtime` publication。
- 4 张 ENUM 主枚举 + 9 个子枚举，跨 migration 重复定义（如 `ticket_*`、`notify_*` 重复 `DO $$ BEGIN CREATE TYPE`）。

## 高优先级问题（P0 - 立即修）

1. **问题：tenant_id 在 53 个 migration 中**仅 046 一次性回填，47 张业务表只覆盖 26 张；与 organisation_id 长期并存造成跨租户绕过风险
   - 位置：`supabase/migrations/046_tenant_context.sql:42-97`；`001_initial_schema.sql`/`005_company_knowledge.sql`/`011_collaboration_rooms.sql`/`010_hr_tickets.sql`/`019_pilot_programs.sql`/`021_third_party_corp.sql`/`024_funnel_events.sql` 等。
   - 影响：未在列表的表（`candidates`、`roles`、`matches`、`collections`、`agent_memory`、`conversations`、`emotion_timeline`、`tickets`、`ticket_comments`、`ticket_status_history`、`ticket_sla_rules`、`notify_preferences`、`notification_prefs`、`notification_log`、`notification_digest`、`smart_suggestions`、`webhooks`、`api_keys`、`rules`、`rule_runs`、`pilot_programs`、`pilot_invitations`、`pilot_feedback`、`companies_*`、`conversations`、`career_plans`、`company_strategy`、`company_credentials`、`company_policies`、`saved_comparisons`、`attrition_*`、`probation_*`、`referrals`、`referral_points`、`referral_bonuses`、`rediscovery_*`、`notifications_prefs`、`funnel_events`、`ats_*`、`ai_interviews*`、`video_interviews`、`video_webhooks`、`calendar_links`、`assessment_invitations`、`background_checks`、`background_check_*`、`offer_*`、`negotiation_*`、`job_subscriptions`、`llm_cost_*`、`webhook_deliveries`、`experiment_*`、`audit_log`）继续靠 `organisation_id` 或 `created_by`/`user_id` 做隔离；用户能在 WHERE 中 join 错误列绕过 RLS。
   - 修复成本：中（1-2 周含迁移 + 灰度）
   - 建议：扩 046 表清单至所有业务表；强制把 `tenant_id` 设 `NOT NULL` 并以 trigger 回填；对 `organisation_id` 创建物化视图或生成列 `tenant_id GENERATED ALWAYS AS (organisation_id) STORED`；CI 规则禁止新增表时无 `tenant_id` 列；021-029 等 8 张表重新写 RLS 时优先依赖 `tenant_id`。

2. **问题：跨迁移 trigger 命名重复 + `update_updated_at()` 函数被 7+ 次重复定义，造成最后定义者胜出**
   - 位置：`001_initial_schema.sql:526`（`update_updated_at`）→ `003_conversations.sql:1` → `006_clarification_artifacts.sql:1` → `009_notify_prefs.sql:65`（`trg_notify_prefs_touch_updated_at`）→ `010_hr_tickets.sql:195`（`trg_tickets_touch_updated_at`）→ `011_collaboration_rooms.sql` → `012_persona_preferences.sql:47` → `013_webhooks.sql:55`（`public.set_updated_at`）→ `015_rules.sql` → `019_pilot_programs.sql:136`（`pilot_programs_touch_updated_at`）→ `020_pii_encryption_keys.sql` → `021_third_party_corp.sql:114`（`trg_corp_bindings_touch`）→ `022_ai_interviews.sql:170`（`update_updated_at_column`）→ `023_offers.sql:65` → `025_job_subscriptions.sql:29` → `027_assessments.sql` → `029_ats_sync.sql:81`（`trg_ats_integrations_touch`）→ `034_config_center.sql` → `035_feature_flags.sql` → `036_agent_workflows.sql:91`（`trg_workflows_updated_at`）→ `037_plugins.sql` → `040_compare.sql:22`（`saved_comparisons_touch_updated`）→ `041_notification_prefs.sql:61` → `042_attrition.sql` → `043_probation.sql` → `044_referrals.sql` → `045_rediscovery.sql` → `048_rag.sql:137`（`touch_updated_at_rag`）→ `049_agent_memory_v2.sql:142` → `050_prompt_v2.sql:150` → `051_marketplace.sql:324` → `052_whitelabel.sql:85` → `053_service_toggle.sql:147`。
   - 影响：函数名 `update_updated_at` 与 `update_updated_at_column` 并存；后期 migration 误用同名函数可能 break 既有 trigger；audit/code review 难以判断实际生效者；planner 对 `STABLE`/`IMMUTABLE`/`SECURITY DEFINER` 标记缺失/不一致。
   - 修复成本：低-中（3-5 人日 + 全部 53 个 migration 审计）
   - 建议：把更新函数统一为 `public.set_updated_at()` 并 `IMMUTABLE`/`SECURITY INVOKER`；migration 中只允许 `DROP TRIGGER IF EXISTS` + `CREATE TRIGGER`，禁止重定义函数；CI 规则：禁止新 migration 引入除 `public.set_updated_at` 之外的同名函数；为 53 个 migration 增加 `-- audit_id: xxxx` 注释便于静态分析。

3. **问题：append-only 与 tenant_id 强约束的 trigger 在多 migration 间存在冲突语义**
   - 位置：`018_audit_log.sql:47-65` (`audit_log_block_mutation`) + `047_audit_v2.sql:94-114` (`audit_log_v2_block_mutation`) + `053_service_toggle.sql:127-142` (`service_audit_enforce_retention` 仅禁 DELETE) + `046_tenant_context.sql:102-117` (`enforce_tenant_id` BEFORE INSERT)。
   - 影响：service_role 写 audit_log_v2 时，policy `FOR INSERT WITH CHECK (auth.role() = 'service_role')` 与 append-only trigger 没有冲突；但任何想“打补丁”修正 `metadata` 字段的合法操作（如 GDPR rectification 重新登记原因）会被 trigger 阻塞。`enforce_tenant_id` 仅在 INSERT 时校验，UPDATE 不会重新校验 → 跨租户 update 行不阻挡（依赖 RLS USING + WITH CHECK 共同保证，但很多表 USING 与 WITH CHECK 不一致）。
   - 修复成本：中（1 周）
   - 建议：明确 `append_only` 触发器只对 `public` role 触发，service_role 仍允许（用 `current_setting('role')` 分支）；`enforce_tenant_id` 改为 BEFORE INSERT OR UPDATE 并写 `tenant_id = current_tenant()`；为 `audit_log_v2.metadata` 提供“修订行”表而不是就地更新。

4. **问题：pgvector 索引策略不一致（candidates/roles 1536-d HNSW，policies 1536-d IVFFlat，rag_chunks/memories_v2 1024-d HNSW）**
   - 位置：`001_initial_schema.sql:252`（HNSW m=16 ef=64）→ `005_company_knowledge.sql:72-74`（IVFFlat lists=100）→ `048_rag.sql:114-116`（HNSW, 未指定 m/ef）→ `049_agent_memory_v2.sql:71-73`（HNSW m=16 ef=64）。
   - 影响：HNSW 在向量 < 1M、查询 QPS 高的场景更快；IVFFlat 训练需要 `lists >= sqrt(rows)`，policies 表通常几千行但 `lists=100` 偏高 → 索引质量差、recall 降低；RAG/Memory 表没有给 `ef_search` 提示；`m=16 ef_construction=64` 是早期默认值，未根据 `ef_search=100/200` 调参。
   - 修复成本：中（1-2 周）
   - 建议：把 4 个 HNSW 索引统一为 `m=16, ef_construction=64, ef_search=100`；删除 `idx_company_policies_embedding` 的 IVFFlat 并改为 HNSW；明确各表的预期查询 latency（policies < 200ms、matches < 500ms）；embedding 维度统一在 1024 或 1536 之一，避免跨库 join；提供 `ANALYZE candidates` + `SET hnsw.ef_search=...` 的会话提示。

5. **问题：业务热点查询（候选人匹配、协同消息列表、工单 SLA、情绪时间线）缺复合/部分索引**
   - 位置：
     - `candidates` (`001`): `idx_candidates_email`、`idx_candidates_created_by`、`idx_candidates_seniority`、`idx_candidates_availability`、`idx_candidates_dedup_group`、`idx_candidates_created_at`（6 单列），缺 `(created_by, is_active, created_at DESC)` / `(seniority, availability, created_at DESC)` / `(skills @> ...)` GIN 索引。
     - `matches` (`001`): 缺 `(role_id, status, overall_score DESC)` 复合；`idx_matches_status` 是单列。
     - `room_messages` (`011`): `idx_room_messages_room_created`（含 `id DESC`）OK，但缺 `(room_id, deleted_at IS NULL, created_at DESC)` partial + `(sender_id, created_at DESC)` 已存在 → 缺 `(thread_root_id, created_at DESC)`（虽有部分索引但是 `parent_id IS NOT NULL`，没考虑 thread_root）。
     - `tickets` (`010`): `idx_tickets_sla_due WHERE status NOT IN ('resolved','closed')` 是 partial，但缺 `(assignee_id, status, sla_due_at)` 与 `(organisation_id, status, sla_due_at)`。
     - `emotion_timeline` (`004`): `idx_emotion_timeline_user_time` 与 `idx_emotion_timeline_alerts` 是 partial，但缺 `(user_id, recorded_at)` INCLUDE 覆盖索引 (按 needs_attention + sentiment 排序)。
     - `daily_journals` (`006`): `idx_daily_journals_user_date` 是 (user_id, journal_date DESC) 正确，但缺 `(user_id, journal_date DESC) INCLUDE (content, mood_score)` 覆盖索引（仪表盘一次取整页内容）。
   - 影响：超过 1 万行后 `candidates WHERE seniority=$1 AND availability=$2 ORDER BY created_at DESC LIMIT 50` 退化为顺序扫描；`tickets WHERE status='open' AND sla_due_at < now()` 走 partial 索引可，但按 (organisation_id, assignee_id) 维度无法使用；`room_messages WHERE room_id=$1 AND deleted_at IS NULL ORDER BY created_at DESC` 在 deleted_at = NULL 的部分索引未建立，触发 seq scan。
   - 修复成本：中（1 周 + 数据回填）
   - 建议：为高频查询补 12 个复合/部分/覆盖索引（见下文 SQL 优化建议）；启用 `pg_stat_statements` 持续抓 top 50 query；用 `EXPLAIN ANALYZE` 验证；migration 引入前先 `CREATE INDEX CONCURRENTLY` 防止锁表。

## 中优先级问题（P1 - 1 个月内）

1. **问题：RLS 策略在 18 张表上 `FOR ALL` + 仅 USING 没有 WITH CHECK，update 路径可绕过**
   - 位置：`001_initial_schema.sql` `users_admin_all`/`collections_tp_own`/`cc_tp_own`/`handoffs_tp_own`/`tickets_user_update_meta` 仅 USING（无 WITH CHECK）。
   - 影响：Postgres 中 `FOR ALL` 不带 WITH CHECK 时，UPDATE 在 USING 过滤后的行上无 WITH CHECK 校验；攻击者可构造 UPDATE 把行迁出可见集。
   - 修复成本：低-中
   - 建议：所有 `FOR ALL` 必须同时含 USING + WITH CHECK；CI 规则扫描 `FOR ALL USING (.+)` 缺 WITH CHECK 报错。

2. **问题：46 张表在 RLS 中**调用 `EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND role='admin')`，每次 RLS 评估会全表扫描 users
   - 位置：001/002/003/005/006/007/008/009/010/011/012/013/014/015/016/017/018/019/020/021/022/023/024/025/026/027/028/029/030.../053 共 30+ migration。
   - 影响：`auth.uid()` 已稳定，但 `users WHERE id = auth.uid() AND role='admin'` 没有用 PK 索引 hint，且每行 POLICY 评估都触发子查询。在大表（>10 万行）上 RLS 开销成百倍放大。
   - 修复成本：低
   - 建议：建立 `idx_users_id_role (id) INCLUDE (role)` 或在 `users` 表加 `UNIQUE (id, role)`；把角色检查抽成 `public.is_admin()` STABLE 函数并加 SECURITY DEFINER 缓存；用 `auth.jwt() ->> 'role'` 直接判断以避免子查询。

3. **问题：migration 重复定义 ENUM**
   - 位置：`009_notify_prefs.sql` `notify_channel`、`notify_category`；`010_hr_tickets.sql` `ticket_status`、`ticket_priority`、`ticket_category`、`ticket_comment_author`；`011_collaboration_rooms.sql` `room_type`、`room_member_role`、`room_message_type`。
   - 影响：使用 `DO $$ BEGIN CREATE TYPE ... EXCEPTION WHEN duplicate_object THEN NULL` 已做幂等，但版本升级时 ALTER TYPE 增加 value 缺乏统一流程；存在旧 v1 enum 值与新 v2 兼容性问题。
   - 修复成本：中
   - 建议：枚举集中到 `001_enums.sql`；新增值用 `ALTER TYPE ... ADD VALUE`；CI 禁止 migration 重复 `CREATE TYPE ... EXCEPTION`。

4. **问题：软删除/硬删除混用**
   - 位置：`candidates` 无 deleted_at；`offers` 有 `deleted_at`（`023_offers.sql:25`）；`tickets` 无；`collections` 无；`pilot_programs` 无；`saved_comparisons` 无；`attrition_risks` 无。
   - 影响：GDPR forget_user() 通过硬删 + 匿名化 (008) 实施；统一软删字段缺；事件溯源 / 双向匹配 / 协同房间的消息删除走 deleted_at。
   - 修复成本：中
   - 建议：核心业务表（candidates/roles/tickets/collections/messages/saved_comparisons/attrition_risks）加 `deleted_at TIMESTAMPTZ` + partial unique；view 暴露活跃数据。

5. **问题：core 业务表（candidates/roles/matches/conversations/emotion_timeline）缺 `updated_at` 字段或 trigger**
   - 位置：`001_initial_schema.sql` 仅 `users`/`candidates`/`organisations`/`collections` 4 张表有 trigger；`matches`/`signals`/`handoffs`/`quotes` 缺；`conversations`/`emotion_timeline`/`daily_journals`/`career_plans`/`two_way_matches`（部分有）缺；`agent_memory` 缺。
   - 影响：审计/调试时无法快速定位最近修改；与 Audit v2 / metric 关联性减弱。
   - 修复成本：低
   - 建议：补 `updated_at` 字段与 `set_updated_at` trigger；提供 `pg_stat_user_tables.n_tup_upd` 监控基线。

6. **问题：缺 CHECK 约束或弱约束**
   - 位置：
     - `candidates.email` TEXT 无 email 格式 CHECK。
     - `tickets.sla_due_at` 没有 `> created_at` 约束。
     - `quotes.base_fee`/`final_fee` 没有 `>= 0` CHECK。
     - `daily_journals.mood_score` 没有 `BETWEEN -1 AND 1` 约束。
     - `attrition_risks.risk_score` 有 CHECK（042），但 `attrition_risks.interaction_gap_h` 没有负值约束。
   - 修复成本：低
   - 建议：批量补 CHECK 约束；与应用层 Pydantic v2 双层校验；migration 使用 `ALTER TABLE ... ADD CONSTRAINT ... NOT VALID` + `VALIDATE CONSTRAINT` 防止长时间锁表。

7. **问题：缺 `INCLUDED` 覆盖索引**
   - 位置：`tickets`、`room_messages`、`daily_journals`、`attrition_risks`、`memories_v2`、`rag_chunks`、`audit_log_v2` 都是单/复合索引，无 `INCLUDE` 覆盖。
   - 影响：Index-Only Scan 不可用，回表代价大。
   - 修复成本：低
   - 建议：仪表盘/列表型查询的索引加 `INCLUDE (created_at, status, content, ...)`。

8. **问题：缺分区策略的表（audit_log/audit_log_v2/llm_cost_events/funnel_events/notification_log/signals/realtime_transcripts/room_messages）**
   - 位置：`audit_log_v2` 已有 `retention_until` 字段并 `idx_audit_log_v2_retention_idx WHERE retention_until < now() + interval '30 days'`。
   - 影响：单表亿级行后 `VACUUM`/`ANALYZE` 慢；`pg_dump` 备份体积大。
   - 修复成本：高
   - 建议：按 `created_at` 月分区 + `pg_partman` 或原生 `PARTITION BY RANGE (created_at)`；冷数据归档到 `audit_log_archive`（冷热分层）。

9. **问题：缺 `pg_stat_statements` 与 `auto_explain` 配置**
   - 位置：未见任何 migration 启用。
   - 影响：top 50 query 无法系统采集；PII 频次、慢查询 50ms 阈值等指标缺失。
   - 修复成本：低
   - 建议：在新 migration `054_observability.sql` 中启用 `pg_stat_statements` + `auto_explain (log_min_duration=50ms)` + `track_io_timing`；CI 抓 top 20 慢查询。

10. **问题：缓存策略散落但缺统一抽象**
    - 位置：`eventbus` `config_watcher` `redis pub/sub` 等逻辑在 `backend/services/`，但表与表的失效策略无显式契约。
    - 影响：候选人 embedding 更新后，缓存中候选/匹配未失效；enumeration 缓存 stale。
    - 修复成本：中
    - 建议：建立 `CacheInvalidator` 服务（已在 `backend/services/platform/cache`），按 (table, tenant_id, row_id) 显式订阅；migration 加上 LISTEN/NOTIFY 触发。

11. **问题：备份/灾备仅 docs/DR_DRILL_Q3.md，缺 PITR 演练与冷热归档 SOP**
    - 位置：`docs/DR_DRILL_Q3.md`、`docs/DR_DRILL_Q4.md` 为脚本级；`docs/MULTI_REGION.md`/`docs/MULTI_REGION_VERIFY_v5.0.0.md` 描述多区域。
    - 影响：pgvector embedding 表单表大、灾备 RPO/RTO 未明。
    - 修复成本：中
    - 建议：增加 `docs/audits/AUDIT_BACKUP_DR.md` 描述 PITR window（默认 7 天）+ 异地 + 季度演练 + 冷数据 1 年归档；记录关键表恢复时间（SLO）。

12. **问题：缺全文搜索迁移性（多语言）**
    - 位置：`025_search_index.sql` 用 `simple` tokenizer（不区分重音、不分词）；`011_collaboration_rooms.sql` room_messages 全文用 `simple`。
    - 影响：中文/混合语言召回差。
    - 修复成本：中
    - 建议：增加 `zhparser` 或 `pg_jieba` 扩展；多语言采用混合 `simple` + `english` + 中文分词的 `tsvector` 加权。

13. **问题：FK 级联策略不统一**
    - 位置：`matches` ON DELETE CASCADE（001），`room_messages.parent_id` CASCADE（011），`tickets.assignee_id` SET NULL（010），`video_interviews.ticket_id` 缺 FK（026），`assessment_invitations.job_id` 缺 FK（027），`background_checks.offer_id` 缺 FK（028），`referrals.candidate_id` 缺 FK（044），`probation_tasks.review_id` SET NULL（043）。
   - 影响：父表删除时产生孤儿记录或阻塞；video_interviews 删 ticket 后悬挂。
   - 修复成本：低-中
   - 建议：补 FK；不存在的字段补 SET NULL；FK 与业务一致；CI 规则禁止孤儿表。

14. **问题：枚举/字典值定义在应用层 + DB 双层（enums vs TEXT）**
    - 位置：`016_ab_experiments.sql` `status text DEFAULT 'draft' CHECK (status IN (...))` vs 002/010 enum；`019_pilot_programs.sql` `status text CHECK`；`024_funnel_events.sql` `stage VARCHAR(32)`；`025_job_subscriptions.sql` channels `JSONB`；`021_third_party_corp.sql` `corp_type VARCHAR(32)`。
    - 影响：DB 层检查弱；可扩展性差。
    - 修复成本：中
    - 建议：所有固定域值用 `CREATE TYPE ... AS ENUM`；text+CHECK 仅用于真正开放的字典。

## 低优先级问题（P2 - 季度内）

1. **问题：列宽 VARCHAR 长度不一致**（`title` `description` `notes` `body` 等），导致内存中元组对齐浪费。
   - 修复成本：低
   - 建议：统一 `title <= 255` / `description <= 4096` / `notes <= 2048`；用 `text` 配合 `CHECK (char_length(...) <= N)`。

2. **问题：缺命名规范（snake_case 一致但部分 `firstName`-like 未出现；`org_id` vs `organisation_id` 混用）**
   - 位置：`funnel_events.org_id`（024）vs `tickets.organisation_id`（010）vs `users.organisation_id`（001）；`tenant_id` 几乎都是新列。
   - 修复成本：中
   - 建议：CI 规则禁止 `orgId`/`tenantId` 等大小写；统一用 `tenant_id`/`organisation_id`；保留兼容视图。

3. **问题：缺 `pg_cron` 或 pgagent 调度表（业务日表、月归档、forget_user SLA）**
   - 修复成本：中
   - 建议：在 054 引入 `cron_jobs` 表 + Supabase Edge Function 触发。

4. **问题：缺 `pg_dump`/`pg_restore` 文档与年度演练**
   - 修复成本：低
   - 建议：补 `docs/audits/AUDIT_BACKUP_DR.md`。

5. **问题：缺数据库变更管理（schema diff / Atlas / sqitch）**
   - 修复成本：中
   - 建议：引入 `atlas` 或 `sqitch`，CI 比对 `atlas schema apply` 与 dev。

6. **问题：缺外键引用 `auth.users` 与 `public.users` 混用**
   - 位置：`022_ai_interviews` `user_id UUID NOT NULL`（无 FK）；`023_offers` 同；`040_compare.sql` `user_id UUID NOT NULL REFERENCES auth.users(id)`；`046_tenant_context.sql` 默认引用 `public.users`。
   - 修复成本：低
   - 建议：统一 `public.users`；或保留 `auth.users` + `public.users` 一对一 view；migration 内禁止 `auth.users` 引用。

## SQL 优化建议（业务热点）

### A. 业务日报 (daily_journals)
**现状：** 006 建 `idx_daily_journals_user_date (user_id, journal_date DESC)`。
**问题：** 仪表盘一次取 30 天内容 + AI 评价。
**建议：**
```sql
-- 覆盖索引（INCLUDE content/mood_score/ai_advice），避免回表
CREATE INDEX CONCURRENTLY idx_daily_journals_user_date_cover
  ON daily_journals (user_id, journal_date DESC)
  INCLUDE (content, mood_score, ai_rating, ai_advice, topics);

-- 缓存策略：30 天热点数据用 Redis key `journal:{user_id}:{yyyy-mm}` 缓存 5 分钟；
-- mutation 走 Supabase realtime 推送 + 失效；冷数据按月分区后归档到 S3 + Parquet。
```

### B. 候选人匹配 (matches / candidates)
**现状：** 001 单列索引；`match_candidates_rpc` 用 HNSW cosine。
**问题：** 5 万+ 行后 `WHERE role_id=$1 AND status='shortlisted' ORDER BY overall_score DESC LIMIT 20` 走 `idx_matches_role` 再排序。
**建议：**
```sql
-- 复合部分索引：role 维度 + 状态过滤 + 倒序
CREATE INDEX CONCURRENTLY idx_matches_role_status_score
  ON matches (role_id, status, overall_score DESC)
  WHERE status IN ('generated','shortlisted');

-- candidate 维度
CREATE INDEX CONCURRENTLY idx_matches_candidate_status
  ON matches (candidate_id, status, overall_score DESC);

-- 候选人列表：常用过滤
CREATE INDEX CONCURRENTLY idx_candidates_filter
  ON candidates (seniority, availability, created_at DESC)
  WHERE seniority IS NOT NULL;

-- GIN 索引：技能包含
CREATE INDEX CONCURRENTLY idx_candidates_skills_gin
  ON candidates USING gin (skills jsonb_path_ops);

-- pgvector 提示：会话级
SET LOCAL hnsw.ef_search = 200;  -- 提高 recall
```

### C. 工单 SLA
**现状：** 010 已有 `idx_tickets_sla_due WHERE status NOT IN ('resolved','closed')`。
**问题：** HR 仪表盘按 (organisation_id, status, sla_due_at) 拉取；缺覆盖。
**建议：**
```sql
-- 跨租户过滤
CREATE INDEX CONCURRENTLY idx_tickets_org_status_sla
  ON tickets (organisation_id, status, sla_due_at)
  INCLUDE (priority, assignee_id)
  WHERE status NOT IN ('resolved','closed');

-- 个人队列
CREATE INDEX CONCURRENTLY idx_tickets_assignee_status_sla
  ON tickets (assignee_id, status, sla_due_at)
  WHERE status NOT IN ('resolved','closed') AND assignee_id IS NOT NULL;

-- 缓存：SLA 即将超时的工单（≤ 1h） 走 Redis SETEX 300 秒；触发器 `BEFORE UPDATE` 失效。
-- 实时：Supabase realtime 已发布；前端 SSE 订阅。
```

### D. 情绪时间线
**现状：** 004 `(user_id, recorded_at DESC)` + partial `(user_id, needs_attention) WHERE needs_attention=TRUE`。
**问题：** 仪表盘取近 7/30 天 `sentiment` 趋势 + 维度聚合。
**建议：**
```sql
-- 覆盖索引
CREATE INDEX CONCURRENTLY idx_emotion_timeline_user_time_cover
  ON emotion_timeline (user_id, recorded_at DESC)
  INCLUDE (primary_emotion, intensity, sentiment, needs_attention);

-- 物化视图：按 (user_id, day) 聚合
CREATE MATERIALIZED VIEW mv_emotion_daily AS
SELECT user_id,
       date_trunc('day', recorded_at) AS day,
       avg(sentiment)::numeric(4,2) AS avg_sentiment,
       avg(intensity)::numeric(4,2) AS avg_intensity,
       count(*) FILTER (WHERE needs_attention) AS alert_count
FROM emotion_timeline
WHERE recorded_at > now() - interval '90 days'
GROUP BY user_id, date_trunc('day', recorded_at);
CREATE UNIQUE INDEX ON mv_emotion_daily (user_id, day);
-- 每日 cron REFRESH MATERIALIZED VIEW CONCURRENTLY;
```

### E. 协同房间消息
**现状：** 011 `(room_id, created_at DESC, id DESC)` + partial `(room_id) WHERE deleted_at IS NULL?`（未见，但有 `(parent_id) WHERE parent_id IS NOT NULL`）。
**问题：** 列表 query `WHERE room_id=$1 AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 50` 走 `(room_id, created_at DESC)` 再 filter `deleted_at`。
**建议：**
```sql
-- partial + 包含 deleted_at
CREATE INDEX CONCURRENTLY idx_room_messages_room_active
  ON room_messages (room_id, created_at DESC)
  WHERE deleted_at IS NULL;

-- thread 维度
CREATE INDEX CONCURRENTLY idx_room_messages_thread_root_created
  ON room_messages (thread_root_id, created_at DESC)
  WHERE thread_root_id IS NOT NULL AND deleted_at IS NULL;

-- 全文搜索：现有 GIN trgm 仅简单 'simple' 词典，建议混合中文
ALTER TABLE room_messages ADD COLUMN content_tsv tsvector
  GENERATED ALWAYS AS (
    setweight(to_tsvector('simple', coalesce(content,'')), 'A')
  ) STORED;
CREATE INDEX idx_room_messages_content_tsv ON room_messages USING gin (content_tsv);
-- 中英混合：考虑 zhparser 扩展 + 多 tsvector 列加权
```

### F. RAG / 记忆
**现状：** 048/049 HNSW m=16 ef=64。
**建议：**
```sql
-- 显式 ef_search
ALTER INDEX idx_rag_chunks_embedding SET (ef_search = 100);
ALTER INDEX idx_memories_v2_embedding_hnsw SET (ef_search = 100);

-- tenant 维度 + 活跃 partial
CREATE INDEX CONCURRENTLY idx_rag_chunks_tenant_active
  ON rag_chunks (tenant_id, collection_id)
  WHERE embedding IS NOT NULL;

-- 缓存：embedding query 命中 Redis key `emb:{tenant}:{hash(query)}` TTL 5min；
-- 写入/更新时主动 DEL。
```

### G. 通知偏好 / 工单 / 推荐 写入
**建议：**
```sql
-- 批量 UPSERT 用 advisory lock
-- INSERT ... ON CONFLICT (user_id, channel, category) DO UPDATE ...
-- 不需新增索引。
```

## 9. 备份 + 灾备

- **现状：**
  - Supabase Cloud 默认 PITR 7 天（依赖 Supabase 平台），无显式 `wal_level=replica` 设置验证。
  - `docs/DR_DRILL_Q3.md`、`docs/DR_DRILL_Q4.md` 是脚本演练，缺真实恢复 RTO/RPO 记录。
  - 多区域部署在 `docs/MULTI_REGION.md`、`docs/MULTI_REGION_VERIFY_v5.0.0.md`。
  - 缺冷数据归档（candidates/messages/audit_log_v2 一年后归档）。
  - `service_audit` 7 年保留（DB 层 trigger 禁 DELETE）；`audit_log_v2` 3 年保留（GDPR/PIPL 留档期 3 年）。
  - `ai_interview_answers`、`video_interviews` 录像/转写走 S3/OSS 存储（无文档明确 bucket 备份策略）。

- **建议：**
  1. `docs/audits/AUDIT_BACKUP_DR.md` 描述 PITR window = 7d，跨区域复制每小时，凌晨全量；每季度一次 `pg_restore` 演练。
  2. 月度归档：`audit_log_v2` / `llm_cost_events` / `notification_log` / `room_messages` / `realtime_transcripts` / `signals` 移到 `*_archive_yYYYYmMM` 分区表或 S3/OSS Parquet。
  3. `service_audit` 已 7 年；`config_history` 未设保留期（建议 1 年）。
  4. 建立 `pgbackrest`/`wal-g` 配置。
  5. 灾备 RTO 30 分钟、RPO 5 分钟（写入窗口）。

## 10. 数据完整性

- **Trigger 总览（按职责）：**
  - `update_updated_at` 重复 30+ 次（见 P0 #2）。
  - `set_first_persona_primary` (`007`)。
  - `cleanup_expired_memory` (`002`)。
  - `trg_notify_prefs_touch_updated_at` (`009`)、`trg_tickets_touch_updated_at` (`010`)、`room_after_message` / `room_after_thread_reply` / `room_after_member_change` (`011`)、`trg_persona_prefs_updated_at` (`012`)、`public.set_updated_at` (`013`/`014`/`015`)、`pilot_programs_touch_updated_at` (`019`)、`trg_corp_bindings_touch` (`021`)、`update_updated_at_column` (`022`/`023`/`025`)、`trg_ats_integrations_touch` (`029`)、`public.trg_workflows_updated_at` (`036`)、`saved_comparisons_touch_updated` (`040`)、`touch_updated_at_rag` (`048`)、`memories_v2_set_updated_at` (`049`)、`tg_set_updated_at_prompt` (`050`)、`tg_set_updated_at_marketplace` (`051`)、`tg_set_updated_at_tenant_branding` (`052`)、`services_touch_updated_at` (`053`)、`audit_log_block_mutation` (`018`)、`audit_log_v2_block_mutation` (`047`)、`service_audit_enforce_retention` (`053`)、`enforce_tenant_id` (`046`)、`dsr_check_sla_breach` (`047`)、`rotate_pii_key` (`020`)、`rag_chunks_tsv_update` (`048`)、`set_tenant_context` (`046`)。
  - 重复定义同名函数（`update_updated_at` vs `update_updated_at_column` vs `public.set_updated_at` vs `tg_set_updated_at_*`）是 P0 #2 根源。

- **CHECK 约束：**
  - 已加：`agent_memory.scope`、`conversations.role`、`emotion_timeline.intensity/sentiment`、`attrition_risks.risk_score/level`、`pilot_programs.status`、`pilot_invitations.status/expires_at`、`experiments.status`、`ticket_sla_rules.priority UNIQUE`、`ticket_*_status` 等。
  - 缺：参见 P1 #6。

- **NOT NULL 策略：**
  - 主要业务表（users/candidates/roles/matches/tickets/rooms）PK + `user_id`/`created_by` NOT NULL 一致。
  - 部分表 `tenant_id` 注入后仍允许 NULL（046 的策略），应通过 `enforce_tenant_id` 强制非空（已实施）。
  - 缺：`audit_log_v2.consent_id` 允许 NULL（合规 OK）；`memories_v2.summary` 可空（设计 OK）；`conversations.signal_event_id` 可空（join 选填 OK）。

- **唯一约束：**
  - 已有：`users.email`、`matches(candidate_id, role_id)`、`two_way_matches(candidate_id, role_id)`、`room_members(room_id, user_id)`、`room_reactions(message_id, user_id, emoji)`、`room_pins(room_id, message_id)`、`notify_preferences(user_id, channel, category)`、`notification_prefs(user_id, category, priority, channel)`、`agents`、`api_keys`、`background_checks.check_id`、`api_keys`、`experiments.name`、`feature_flags.name`、`services.name`、`marketplace_plugins.slug`、`plugin_releases(plugin_id, version)`、`plugin_purchases`、`pilot_invitations.invite_token`、`corporate_bindings(corp_id, corp_type)`、`corp_user_mappings(binding_id, external_user_id)`、`corp_approval_instances(binding_id, external_instance_id)`、`referrals(referrer_id, candidate_email, role_id)`、`calendar_links(user_id, provider)`、`saved_comparisons`、`attrition_risks(user_id, computed_at)`、`rediscovery_profiles(candidate_id, computed_at)`、`prompt_versions(tenant_id, name, agent, version)`、`service_overrides(org_id, service_name)`。
  - 缺：参见 P1 #13 FK 与孤儿。

- **级联删除：**
  - CASCADE：matches→candidates/roles、collection_candidates→collections/candidates、room_messages→rooms/users/parent、room_members→rooms/users、room_reactions→room_messages/users、room_mentions→rooms/room_messages/users、room_pins→rooms/room_messages/users、tickets→organisations/users、ticket_comments→tickets/users、ticket_status_history→tickets/users、conversation 中.../candidates、employer_clarifications→candidates/roles、ai_interview_questions/answers/reports→ai_interviews/ai_interview_questions、rag_documents→rag_collections、rag_chunks→rag_documents/rag_collections、memories_v2 memory_links_v2→memories_v2、memory_access_v2→memories_v2、prompt_metrics/evaluations→prompt_versions、marketplace plugin_releases/reviews/downloads/purchases/audit→marketplace_plugins、plugin_runs（无 FK）、notification_prefs/digest/suggestions/log→users（部分 ON DELETE CASCADE）、webhook_deliveries→webhooks、rule_runs→rules、ats_sync_log/conflicts→ats_integrations、negotiation_scripts→user_offers、probation_tasks→probation_reviews、api_key_usage→api_keys。
  - SET NULL：tickets.assignee_id、ticket_comments.author_id、ticket_status_history.changed_by、room_members.invited_by、room_messages.deleted_by、corporate_user_mappings→users、probation_reviews.manager_id、probation_extensions.approved_by、rediscovery_log.triggered_by、rediscovery_log.candidate_id、referrals.candidate_id、referrals.role_id、referral_points.referral_id、corp_approval_instances→tickets、ai_interview_answers（无）。
  - 缺：参见 P1 #13。

## 11. 关键表与 RLS 摘要（按业务域）

| 业务域 | 表数 | tenant_id 列 | RLS | Realtime | 备注 |
|---|---|---|---|---|---|
| 用户/组织 | 8 | 4/8 | 6/8 | 0 | users/organisations 缺 tenant_id |
| 候选人/匹配 | 12 | 4/12 | 8/12 | 1 | candidates/roles/matches 缺 tenant_id |
| 工单/合同 | 4 | 1/4 | 4/4 | 3 | tickets 缺 tenant_id；tickets.sla_due_at partial |
| 协同房间 | 7 | 0/7 | 7/7 | 7 | 完全靠 room_is_member；缺 tenant_id |
| 通知/偏好 | 6 | 0/6 | 6/6 | 0 | notify_preferences/notification_prefs 缺 tenant_id |
| 策略/制度 | 4 | 0/4 | 1/4 | 0 | company_strategy/policies RLS `USING (true)` 太宽 |
| 记忆/对话/情绪 | 5 | 0/5 | 5/5 | 0 | agent_memory/conversations/emotion_timeline 缺 tenant_id |
| 日报/计划/画像 | 4 | 0/4 | 4/4 | 0 | daily_journals/career_plans 缺 tenant_id |
| AI 面试/视频 | 6 | 0/6 | 6/6 | 0 | ai_interviews/video_interviews 缺 tenant_id |
| 测评/背景 | 4 | 0/4 | 0/4 | 0 | assessments/background_checks 缺 tenant_id + 无 RLS |
| ATS/集成 | 6 | 0/6 | 6/6 | 0 | ats_integrations/webhooks/api_keys/rules 缺 tenant_id |
| 审计/合规 | 9 | 6/9 | 9/9 | 0 | audit_log_v2/dpr/dsr/breach 已含 tenant_id |
| Webhook/规则/A-B | 8 | 0/8 | 6/8 | 0 | experiments/rules 缺 tenant_id |
| RAG/Memory/Prompt | 12 | 12/12 | 12/12 | 2 | v6 后全部含 tenant_id；最完整 |
| Marketplace/Whitelabel/Services | 18 | 4/18 | 18/18 | 0 | whitelabel 用 tenant_id（TEXT）作 PK |
| SaaS 平台/事件/推送 | 22 | 0/22 | 0/22 | 0 | eventbus/push/notifications 缺 tenant_id + 无 RLS |

总计：47 张业务表中 14 张 tenant_id（30%），但 RLS 已基本覆盖（仅测评/ATS/SaaS 平台缺 RLS）。

## 12. 总结

数据库层面 v10.0 已具备：
- 131 张表覆盖招聘全链路（候选人/匹配/工单/协同/RAG/记忆/AI 面试/Marketplace/SaaS 服务开关）。
- 314 索引（B-tree/GIN/HNSW/IVFFlat/partial）+ 4 类 pgvector 索引。
- 完善 RLS、append-only 触发器、tenant 注入、GDPR forget/export 函数、audit_log_v2 (3y)、service_audit (7y)、多区域 + DR 脚本。
- Realtime publication 覆盖 21 张表。

但仍存在 14 个 P0/P1 缺口、24 个 P2 优化项，核心是：
1. tenant_id 覆盖不全（30%）→ 跨租户数据可绕过 RLS。
2. update_updated_at 函数 30+ 次重复定义。
3. 高频查询缺复合/部分/INCLUDE 覆盖索引。
4. pgvector 索引策略不一致（IVFFlat vs HNSW vs 不同 m/ef）。
5. 灾备 SOP + 备份恢复演练不足。
6. 测评/ATS/SaaS 平台表缺 RLS。

建议优先级（4 周 P0 + 4 周 P1 + 季度 P2）：
- 第 1 周：补 tenant_id 到所有业务表 + RLS USING+WITH CHECK。
- 第 2 周：统一 `set_updated_at` 函数；补 12 个复合/部分索引。
- 第 3 周：HNSW 索引调参 + 删 IVFFlat；加 pg_stat_statements + auto_explain。
- 第 4 周：备份/灾备 SOP + 季度演练。
- 第 5-8 周：CHECK 约束、覆盖索引、缓存抽象、cron、Atlas schema diff。

## 13. 关键路径文件清单

- 主 schema：`/home/hugo/codes/waibao/talent-tool-mvp/supabase/migrations/001_initial_schema.sql`、`001_cloud_schema.sql`
- RLS 多租户：`/home/hugo/codes/waibao/talent-tool-mvp/supabase/migrations/046_tenant_context.sql`
- pgvector / RAG / Memory：`005_company_knowledge.sql`、`048_rag.sql`、`049_agent_memory_v2.sql`
- 工单/协同/通知：`010_hr_tickets.sql`、`011_collaboration_rooms.sql`、`009_notify_prefs.sql`、`041_notification_prefs.sql`
- 审计/合规：`018_audit_log.sql`、`047_audit_v2.sql`、`008_pii_encryption.sql`、`020_pii_encryption_keys.sql`
- v6+ 平台：`034_config_center.sql`、`035_feature_flags.sql`、`036_agent_workflows.sql`、`037_plugins.sql`、`038_realtime.sql`、`039_ai_interview_v2.sql`、`050_prompt_v2.sql`
- v7+ Marketplace/SaaS：`051_marketplace.sql`、`052_whitelabel.sql`、`053_service_toggle.sql`
- v8 业务：`040_compare.sql`、`042_attrition.sql`、`043_probation.sql`、`044_referrals.sql`、`045_rediscovery.sql`
- 后端服务：`/home/hugo/codes/waibao/talent-tool-mvp/backend/services/`（matching、agents、rags、memory、webhook、rule_engine、attrition、probation、referrals、rediscovery、warehouse、bi、predictive、sourcing、training、marketplace、platform/feature_flag、service_toggle、config_service、eventbus、plugins/sdk、workflow_engine、cache、audit_v2、pii_field_encryption、cost_tracker、knowledge_base、chat_history、prompt、memory_v2、rag、corp_sync、ticket、collaboration、notification、candidates、roles、employer、jobseeker、search、analytics_v2、developer_portal、subscription、billing、fraud、resilience、monitoring、integrations、bi、predictive、sourcing、training 等）
- 灾备文档：`/home/hugo/codes/waibao/docs/DR_DRILL_Q3.md`、`/home/hugo/codes/waibao/docs/DR_DRILL_Q4.md`、`/home/hugo/codes/waibao/docs/MULTI_REGION.md`、`/home/hugo/codes/waibao/docs/MULTI_REGION_VERIFY_v5.0.0.md`、`/home/hugo/codes/waibao/docs/DISASTER_RECOVERY.md`
