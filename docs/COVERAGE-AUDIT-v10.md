# COVERAGE-AUDIT-v10.md — v10.0 综合覆盖审计

> 综合 `docs/audits/AUDIT_BACKEND.md`、`talent-tool-mvp/docs/audits/AUDIT_FRONTEND.md`、`docs/audits/AUDIT_DATABASE.md`、`docs/audits/AUDIT_SECURITY.md`、`docs/audits/AUDIT_AI.md` 五份审查得到的"v10.0 综合体检"。  
> 基线: v9.1.0 (16 项做透 + 前端企业级 — 自我声明)  
> 范围: 后端 121,559 LOC、70+ 服务、120+ API router、530+ Postgres 表、6 IdP、16 Agent、30+ LLM prompts。  
> 真实测试未全量重跑,所有分数为工程估值。

---

## 1. 综合评级

| 维度 | v9.1 评级 | v10.0 目标 | 一句话结论 |
|---|---:|---:|---|
| **后端** | 6.1 / 10 | 8.0 / 10 | 功能面齐全;契约/隔离/错误语义/State machine 失控;P0 真假混杂 |
| **前端** | 2.4 / 5 (MVP++) | 4.0 / 5 | 代码量"企业级",工程基础设施 PoC 级:0 loading.tsx、0 global error.tsx、0 TanStack Query、3% SEO metadata |
| **数据库** | 6.4 / 10 | 8.0 / 10 | Schema 覆盖 131 表 + 314 索引;tenant_id 仅 30% 覆盖;RLS 部分表 USING 缺 WITH CHECK |
| **安全** | 6.5 / 10 (B+) | 7.5 / 10 | Tenant/RLS/JWT baseline 强;6 项 P0 真泄漏风险 (SAML 签名 strip、cryptography fail-fast、JWT 默认 secret、prompt injection、private-IP SSRF、GDPR breach) |
| **AI 集成** | 7.4 / 10 | 8.5 / 10 | 16 Agent + 4 子系统骨架齐;RAG/Multi-Agent 真模型覆盖率 ≈ 0;Mem0 pgvector RPC 缺;Workflow cycle/timeout 缺 |
| **总体** | **6.0 / 10** | **7.5 / 10** | **形式完整 + 真业务化不足**:v9.1 是"演示级 SaaS",v10.0 必须把"看上去 work"变成"真能用" |

---

## 2. Top 10 P0 问题 (跨模块)

> 出现 ≥ 3 份报告、或单报告 P0 中直接影响 production / SOC2 / GDPR 合规的问题。

| # | 问题 | 出现报告 | 影响 | 修复成本 |
|---|---|---|---|---|
| 1 | **tenant_id 仅 30% 表覆盖 (47 表只 26 张)**;47 张业务表继续靠 `organisation_id` 隔离 → 跨租户绕过 | DATABASE, SECURITY | 用户能构造 JOIN 错误列绕过 RLS,生产风险 | 中 (1-2 周) |
| 2 | **Agent 全部 hardcoded prompt + JSON.loads 后 dict 使用,无 Pydantic 强制契约;prompt injection 无防护** | BACKEND, SECURITY, AI | OCR/简历/RAG 内容直接喂 prompt;LLM 输出无 schema 校验 → 简历可控字段可劫持业务 | 中高 (2-3 周) |
| 3 | **JWT 默认 secret fallback + SAML 签名 strip + cryptography 缺 fail-fast + 弱 audit 装饰器 silent fail** (4 子项) | SECURITY | 一键 DB compromise / secret leak 风险 | 中 (1 周) |
| 4 | **RAG embedding/reranker 默认走 hash-bucket / lexical fallback,CI 0 真模型** | AI | 检索准确度 ≤ 50%,demo 准确度 > 85% 不可验证 | 中 (1-2 周) |
| 5 | **Plugin SDK 沙箱是同进程 monkey-patch,NetworkGuard allow=None 时默认放行,sandbox 在 Windows 失效** | BACKEND, AI, SECURITY | 私有化部署时恶意 plugin 可获 RDP / 数据泄露 / DoS | 高 (2-4 周;需独立进程/容器) |
| 6 | **Multi-Agent `default_executor` 是 stub (`_synthesize_decision`),4 场景"真实跑通" 实质是关键字算分** | AI | "5 人格 AI 模拟面试官" / "战略解码" 等对外宣称能力实际为伪 AI | 中 (1 周) |
| 7 | **WorkflowEngine 缺 DAG cycle detection + 节点 timeout + 多 workflow 并发;remember() 单实例** | BACKEND, AI | A→B→A 无限递归栈溢出;并发跑 2 个 workflow 第 2 个覆盖第 1 个;HumanNode 长等待不超时 | 中 (1-2 周) |
| 8 | **EventBus 缺 DLQ / 重试 / schema registry;Redis publish fire-and-forget;handler 错误仅 in-memory list** | BACKEND, AI | agent.completed 事件 broker 失败即丢;ProcessRestart 后无事故可见性 | 中 (1-2 周) |
| 9 | **fetch 后端 0 loading.tsx / 0 error.tsx / 0 全局 ErrorBoundary + 4193 行 mock-data 耦合生产 + 0 TanStack Query** | FRONTEND | 任意 API 慢 / 失败 → 30s 空白;任意 component throw → white screen | 中 (4-6 文件 + 50+ API 改造) |
| 10 | **get_supabase_admin() 在 80+ handler 中用,每处都可能绕过 RLS;tenant 上下文仅靠 middleware** | BACKEND, SECURITY | RLS bypass 风险高;Service role 与 tenant 解耦缺 hard 隔离 | 中 (1-2 周;需 RLS + GUC + repo 强制 tenant) |

---

## 3. Top 20 P1 问题

| # | 问题 | 模块 | 出现 |
|---|---|---|---|
| 1 | 后端 API:640 路由仅 96 个 response_model,88 个路由文件完全缺响应模型 | BACKEND | BACKEND |
| 2 | 后端 Service 层: collaboration_room 1115 行 / predictive 846 行 / service_toggle 792 行 / billing 681 行 | BACKEND | BACKEND |
| 3 | 后端 ~874 个 `except Exception` + 130 个 `pass`,兜底密度过高 | BACKEND | BACKEND |
| 4 | 后端 Provider 失败后可能自动 mock fallback;mock 与生产不可分 | BACKEND | BACKEND |
| 5 | 后端可观测性 / Sentry / OTel init 失败仅 warn,生产可能"无追踪" | BACKEND | BACKEND |
| 6 | 数据库 RLS `FOR ALL USING` 缺 WITH CHECK (18 张表),UPDATE 路径可绕过 | DATABASE | DATABASE |
| 7 | 数据库跨迁移 trigger 函数重名 30+ 次 (`update_updated_at` vs `set_updated_at` vs `update_updated_at_column`),最后定义者胜出 | DATABASE | DATABASE |
| 8 | 数据库 pgvector 索引策略不一致 (HNSW vs IVFFlat vs 不同 m/ef) | DATABASE | DATABASE, AI |
| 9 | 数据库业务热点缺复合 / 部分 / INCLUDE 覆盖索引 (candidates、matches、tickets、emotion_timeline、room_messages) | DATABASE | DATABASE |
| 10 | 前端 SEO metadata 覆盖率 5/170 = 2.9% | FRONTEND | FRONTEND |
| 11 | 前端 i18n 覆盖率 ~5% (170 页面应有 800+ key,实际 ~150) | FRONTEND | FRONTEND |
| 12 | 前端表单无 react-hook-form / Zod,后端 Pydantic 与前端 drift | FRONTEND | FRONTEND |
| 13 | 前端 Storybook 业务组件覆盖率 ~20% (36+ 子目录 0 story) | FRONTEND | FRONTEND |
| 14 | 安全 SSO `link_by_email=True` 默认 + JIT default_org="default" → IdP alias takeover | SECURITY | SECURITY |
| 15 | 安全 SSO `expected_state` 默认 None → OIDC CSRF check 跳过 | SECURITY | SECURITY |
| 16 | 安全 webhook dispatcher 不 block private-IP (SSRF to 169.254.169.254 cloud metadata) | SECURITY | SECURITY |
| 17 | 安全 GDPR forget RPC 无 admin override (财务 7y、audit 7y);且无 breach 自动化 | SECURITY | SECURITY |
| 18 | 安全 PII 字段级加密覆盖率低 (users.email/phone/cv_text/journal.entry_text 仍明文) | SECURITY | SECURITY |
| 19 | AI Mem0 SupabaseBackend search 走 hash-bucket cosine (>1k 行 O(n) 全表扫) | AI | AI |
| 20 | AI Prompt v2 `record_metric` 手动调用;ConfigCenter 改 prompt 不热加载 | AI | AI |

---

## 4. P2 长期 / 重构期问题 (摘要)

> 与 v10.0 关系弱,v11.0+ 长期治理。

- memory `_on_profile_updated` 把每个字段写 1 条 FACT (memory 表爆炸) — AI
- Plugin SDK `_call_with_timeout` ThreadPool 跑 install,僵尸线程无法 kill — AI
- 数据库分区表缺 (audit_log / llm_cost_events / notification_log 需按月分区) — DATABASE
- 数据库缺 pg_cron / pgagent 调度 — DATABASE
- 后端 dataclass/dict 跨层,缺 contracts 包 Pydantic Single source of truth — BACKEND
- 数据库缺 Atlas / Sqitch schema diff CI — DATABASE
- 前端真实 Realtime / SSE hook 分散 (use-event + useRealtimeSession + sse) — FRONTEND
- 前端 Storybook Chromatic visual regression — FRONTEND
- 安全 Sentry beforeSend PII scrubber — SECURITY
- 安全 idle timeout + device fingerprint on refresh — SECURITY

---

## 5. "形式完整但实际 MVP" 功能 (真伪对比)

> 表象上 v9.1 已经交付,但真实业务跑不通的核心功能。

| # | 功能 | 形式 vs 实际 | 业务影响 | 修复 |
|---|---|---|---|---|
| 1 | **RAG 检索准确度 > 85%** (v7.0 宣传) | 形式:`RagService` + RRF + reranker 全齐;实际:`_embed_llama_index` 走 SHA-256 hash bucket,reranker `0.6*cosine + 0.3*coverage + 0.1*score` lexical 兜底 | 客户上传文档检索根本搜不到正确片段 | T5009 真模型 fixture (BGE-small + reranker-base) + Recall@K 断言 |
| 2 | **Mem0 长期记忆跨 Agent** (v7.0 宣传) | 形式:`MemoryStore` + FACT/PREFERENCE/EVENT/SUMMARY;实际:`EntityExtractor` 全 regex,`SupabaseBackend.search` 走 in-process `_hash_embed` cosine,>1k 行 P95 不可控 | Mem0 = "假记忆" → profile_agent 用 top-8 召回污染 prompt | T5009 pgvector `match_memories` RPC + MemoryExtractor 接 LLM |
| 3 | **Multi-Agent 4 场景真实跑通** (v7.0 宣传) | 形式:4×4×4 scenario/pattern/consensus;实际:`default_executor` 是 stub `_synthesize_decision` 关键字算分 ("strong"+"senior"+7.5) | 简历评分 / 偏见审查 / Offer 谈判 = 伪 AI;CI 测试通过 ≠ 真业务对齐 | T5009 注入真实 LLM executor + `test_multiagent_real_llm.py` |
| 4 | **Plugin 沙箱安全** (v6.0 宣传) | 形式:RestrictedPython + AST blacklist + NetworkGuard + FilesystemGuard;实际:`NetworkGuard` allow=None 时直接 return (默认放行);Windows `ResourceLimiter._supported = False`;签名验证缺 | 私有化部署时恶意 plugin 可获取 cloud metadata / 数据泄露 | T5004 强制独立容器 (gVisor/firecracker) + SignatureVerifier |
| 5 | **Workflow Engine 并行/可恢复** (v6.0 宣传) | 形式:DAG + Pause/Resume + Templates;实际:fan-out 顺序执行;`remember()` 单实例覆盖前一个;无 cycle detection;无节点 timeout | 用户提交 100 个并发 workflow,第 1 个 resume() 找不到定义;A→B→A 栈溢出 | T5008 Tarjan cycle + asyncio.wait_for + WorkflowStore 持久化 |
| 6 | **Audit decorator** (`@audit`/`@audit_pii`) | 形式:v5.0 + v7.0 已上;实际:失败仅 `logger.warning`,`except:` broad → 静默通过 | SOC2 不可信,GDPR 审计可被旁路 | T5007 `@audit` 失败 raise alert;CI grep select("*") on PII tables |
| 7 | **PII 字段级加密** (v8.0) | 形式:Fernet AES-128 + HMAC 已上;实际:`cryptography` 缺时 fallback HMAC+nonce (仅 integrity ≠ encrypt);production 环境 fail-fast 缺失;`cv_text` / `users.email` / `journal.entry_text` 仍未加密 | PII 在生产泄漏即罚款 | T5007 production fail-fast + KMS / Vault |
| 8 | **GDPR forget (Art. 17)** | 形式:RPC `forget_user` 已上;实际:无 admin override (财务/audit 7y 不可全删);无 soft-delete 30d 缓冲;无 idempotency | 用户撤回请求 → 审计/财务记录强行丢失,违反 SOC2 | T5007 RPC 加 legal_obligation 跳过 + 30d grace |
| 9 | **Prompt v2 A/B + 热更新** (v7.0) | 形式:`traffic_pct` weighted bucket + shift_traffic;实际:`PromptService` 单例 `_SERVICE`,ConfigCenter `config.changed` event 未订阅 → 改 prompt 需重启 | A/B test 改 prompt 必须停机 | T5009 订阅 `config.changed` pub/sub + eval runner |
| 10 | **Tenant 隔离** (v8.0 T2601) | 形式:RLS + middleware;实际:80+ handler 用 `get_supabase_admin()` service-role key 绕过 RLS;47 张业务表只 26 张有 tenant_id | 跨租户数据可被构造 JOIN 绕过 | T5003 tenant_id 全表覆盖 + repo 强制 tenant 参数 |
| 11 | **前端"企业级" UX** (v9.1 自我声明) | 形式:170 page + 100+ 组件 + shadcn/ui;实际:0 loading.tsx + 0 error.tsx + 4193 行 mock-data 进生产 + 0 TanStack Query + 5/170 metadata = 3% | 用户进 dashboard 看到 30s 空白 → 流失 80% | T5005 全局 error.tsx + 5 个 loading.tsx + TanStack Query + SEO metadata 全覆盖 |
| 12 | **i18n 3 语言** (zh/en/ja) | 形式:3 个 messages json 各 ~310 行;实际:170 页面 + 100 组件,`useTranslations` 仅 5 个调用点 | 切 ja-JP = 仍是英文或中文 → 实际单语产品 | T5005 i18n 全覆盖 + ESLint fail build on hardcoded string |
| 13 | **表单客户端验证** | 形式:50+ 表单;实际:全部 `useState`,无 react-hook-form / Zod;后端 Pydantic 与前端 drift | 表单与 Pydantic 不一致 → 用户填了被服务端 422 拒 | T5005 react-hook-form + Zod schemas (与 backend Pydantic 同步) |
| 14 | **Workflow Database 持久化** | 形式:`InMemoryWorkflowStore` 是默认,可插拔;实际:生产无 Supabase 实现,`remember()` 单实例 | 重启后 workflow 状态全丢;客户 24h HR 审批中即中断 | T5008 Supabase `WorkflowStore` 持久化 + checkpoint |
| 15 | **Event schema 注册表** (v6.0) | 形式:30+ event 名称覆盖;实际:字段靠 docstring,`run_id` 在 `agent.completed` vs `multiagent.task.completed` 含义不同 | 新增 agent 时字段漂移;下游 consumer 解析错误 | T5008 eventbus/schemas.py + Pydantic `EventPayload` + CI orphan check |

---

## 6. 长期 Vision (P3 之后)

- 多端 agent: 移动原生 app / 桌面端 agent runner
- 商业化: SOC2 Type II / ISO 27001 / EU-US Data Boundary / Marketplace 全开放
- AI 自主 Agent: 自我规划 + 自我评估 + RLHF 闭环
- 跨企业 Talent Graph: 跨租户同岗位人才池 (Opt-in)
- Industry Vertical: 金融、医疗、互联网 3 套 domain package

---

## 7. v10.0 范围边界 (明确不做)

> v10.0 = 企业化升级,不做范围蔓延。

| 不做 | 原因 |
|---|---|
| 新业务功能 (新 16 项) | 已做透;v9.1 16 项 + v8.1 P2 已覆盖 |
| 新开源项目发布 | 单仓库迭代,避免分叉 |
| 新增端 (小程序/钉钉/企微除外已就位) | 5 端已稳定 |
| 商业化 (付费 tier / 合同 / billing 升级) | SOC2+ 之后再开 |
| 新 LLM provider 接入 (除 Anomaly/Vllm/LocalAI) | Provider 抽象已稳定 |
| 新数据库 (ClickHouse/Snowflake 之外) | 已用 Supabase Postgres + Cube + ClickHouse |
| 重写 agent 框架 | 当前 16 Agent 调通优于一锅重写 |

---

## 8. 后续交付物

- `docs/COVERAGE-AUDIT-v10.md` (本文)
- `/home/hugo/codes/waibao/todo.json` (v10.0,5 phases / 25-30 tasks)
