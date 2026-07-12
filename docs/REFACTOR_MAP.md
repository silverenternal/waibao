# waibao v5.0 重构地图 (REFACTOR_MAP)

> 状态: 规划 v1 · 编制日期 2026-07-12 · 适用基线: v4.0
> 目标: 把 v4.0 的 16 Agent / 65 API / ~59 services / 12 维度 Provider / 1242 tests 体系, 收敛为可维护、可演进的 v5.0 布局。

---

## 0. 摘要 (TL;DR)

| 维度 | v4.0 (现状) | v5.0 (目标) | 收益 |
| --- | --- | --- | --- |
| services/ | 59 文件平铺 | 6 个 domain 子包 (jobseeker / employer / matching / billing / observability / integrations / platform) | 单目录 ≤12 文件, 关注点分离 |
| agents/ | runtime.py 一文件 764 行 13 类/函数 | core + llm + memory + observability 四子包 | 单一职责, 引入零成本 LLM 替换 |
| dead code | adapters/ 6 文件 / copilot/ 3 文件 / signals/ 4 文件 | copilot/ + signals/ 删除, adapters/ 留用并加文档 | 砍 7 个文件, 减 1242 tests 中 ~40 条死用例 |
| frontend | app/mind + app/mothership 与 employer 重叠; components 51 平铺 + 20 子目录 | mind → employer, mothership/admin → admin, components 按 3 域分组 | 路由数从 18 域 → 12 域 |
| DX | 无 setup() / 无 ErrorCode / 无 Storybook | `backend.setup()` 统一入口 + `core/errors.ErrorCode` + Storybook 8 | 新人 onboarding 从 1 天 → 2 小时 |

---

## 1. 服务拆包表 (services/ → services/<domain>/)

> 原则: 按 **业务主语 (subject) + 横切关注点 (cross-cutting)** 划分, 禁止出现"工具类"模糊包。
> 拆包后 `services/<domain>/__init__.py` 仅做 re-export, 不放业务逻辑。
> 兼容期 (≤ v5.1) 保留 `services/<old>.py` 转发 shim, 引用方零修改。

| # | 旧路径 | 新路径 | domain | 说明 |
| --- | --- | --- | --- | --- |
| 1 | services/resume_parser.py | services/jobseeker/resume_parser.py | jobseeker | 求职者简历解析 |
| 2 | services/plan_tracker.py | services/jobseeker/plan_tracker.py | jobseeker | 求职计划追踪 |
| 3 | services/learning_resources.py | services/jobseeker/learning_resources.py | jobseeker | 学习资源推荐 |
| 4 | services/offer_calculator.py | services/jobseeker/offer_calculator.py | jobseeker | Offer 测算 |
| 5 | services/negotiation_advisor.py | services/jobseeker/negotiation_advisor.py | jobseeker | 谈薪顾问 |
| 6 | services/ai_interviewer.py | services/jobseeker/ai_interviewer.py | jobseeker | AI 模拟面试 |
| 7 | services/video_processing.py | services/jobseeker/video_processing.py | jobseeker | 求职者端视频处理 |
| 8 | services/question_bank.py | services/jobseeker/question_bank.py | jobseeker | 题库 |
| 9 | services/profile_extractor.py | services/jobseeker/profile_extractor.py | jobseeker | 画像抽取 |
| 10 | services/video_interview_service.py | services/jobseeker/video_interview_service.py | jobseeker | 视频面试服务 (注: 旧名"video_interview"易与 employer 端冲突, 保持原文件名) |
| 11 | services/compliance_service.py | services/employer/compliance_service.py | employer | 合规审查 |
| 12 | services/ticket_service.py | services/employer/ticket_service.py | employer | 工单 |
| 13 | services/ats_sync.py | services/employer/ats_sync.py | employer | ATS 同步 |
| 14 | services/ats_sync_scheduler.py | services/employer/ats_sync_scheduler.py | employer | ATS 定时同步 |
| 15 | services/channel_attribution.py | services/employer/channel_attribution.py | employer | 渠道归因 |
| 16 | services/recruitment_funnel.py | services/employer/recruitment_funnel.py | employer | 招聘漏斗 |
| 17 | services/corp_sync.py | services/employer/corp_sync.py | employer | 企业数据同步 |
| 18 | services/dingtalk_sync.py | services/employer/dingtalk_sync.py | employer | 钉钉同步 |
| 19 | services/feishu_sync.py | services/employer/feishu_sync.py | employer | 飞书同步 |
| 20 | services/dingtalk_approval.py | services/employer/dingtalk_approval.py | employer | 钉钉审批 |
| 21 | services/calendar_sync.py | services/employer/calendar_sync.py | employer | 日历同步 |
| 22 | services/assessment_service.py | services/employer/assessment_service.py | employer | 评估服务 |
| 23 | services/background_check_service.py | services/employer/background_check_service.py | employer | 背调 |
| 24 | services/feedback_loop.py | services/matching/feedback_loop.py | matching | 匹配反馈环 |
| 25 | services/calibration.py | services/matching/calibration.py | matching | 匹配校准 |
| 26 | services/global_search.py | services/matching/global_search.py | matching | 全局搜索 |
| 27 | services/billing.py | services/billing/billing.py | billing | 计费 |
| 28 | services/telemetry.py | services/observability/telemetry.py | observability | 遥测 |
| 29 | services/metrics.py | services/observability/metrics.py | observability | 指标 |
| 30 | services/sentry.py | services/observability/sentry.py | observability | Sentry 集成 |
| 31 | services/audit.py | services/observability/audit.py | observability | 审计 |
| 32 | services/llm_cache.py | services/observability/llm_cache.py | observability | LLM 缓存 |
| 33 | services/llm_budget.py | services/observability/llm_budget.py | observability | LLM 预算 |
| 34 | services/cost_tracker.py | services/observability/cost_tracker.py | observability | 成本追踪 |
| 35 | services/collaboration_room.py | services/integrations/collaboration_room.py | integrations | 协作房间 |
| 36 | services/candidate_recommender.py | services/integrations/candidate_recommender.py | integrations | 候选人推荐 (与 matching/recommendation 解耦) |
| 37 | services/push_engine.py | services/integrations/push_engine.py | integrations | 推送引擎 |
| 38 | services/job_subscription.py | services/integrations/job_subscription.py | integrations | 职位订阅 |
| 39 | services/api_key.py | services/integrations/api_key.py | integrations | API Key |
| 40 | services/persona_memory.py | services/integrations/persona_memory.py | integrations | 人设记忆 |
| 41 | services/pii_field_encryption.py | services/integrations/pii_field_encryption.py | integrations | PII 字段加密 |
| 42 | services/pilot_invitation.py | services/integrations/pilot_invitation.py | integrations | Pilot 邀请 |
| 43 | services/funnel_events.py | services/integrations/funnel_events.py | integrations | 漏斗事件 |
| 44 | services/transcribe.py | services/integrations/transcribe.py | integrations | 语音转写 |
| 45 | services/file_storage.py | services/integrations/file_storage.py | integrations | 文件存储 |
| 46 | services/realtime_router.py | services/integrations/realtime_router.py | integrations | 实时路由 |
| 47 | services/i18n.py | services/platform/i18n.py | platform | 国际化 |
| 48 | services/permissions.py | services/platform/permissions.py | platform | 权限 |
| 49 | services/notify.py | services/platform/notify.py | platform | 通知 (聚合 services/notify/ 子包) |
| 50 | services/handoff.py | services/platform/handoff.py | platform | 交接 |
| 51 | services/collection.py | services/platform/collection.py | platform | 集合工具 |
| 52 | services/quote.py | services/platform/quote.py | platform | 报价 |
| 53 | services/credit_code_validator.py | services/platform/credit_code_validator.py | platform | 统一社会信用码 |
| 54 | services/crypto.py | services/platform/crypto.py | platform | 加密 |
| 55 | services/backup.py | services/platform/backup.py | platform | 备份 |
| 56 | services/region_router.py | services/platform/region_router.py | platform | 区域路由 |
| 57 | services/region_config.py | services/platform/region_config.py | platform | 区域配置 |

**已存在的子包 (services/notify/、services/webhook/、services/rule_engine/) 不动**, 已在目标位置; 仅平铺的 57 个 .py 进入迁移。迁移后 services 顶层只保留 `__init__.py` 与已存在 3 个子包, 平铺文件 0。

迁移校验清单 (per file):
- 顶部 import 路径必须改为相对当前 domain 的 `from ..observability.xxx import ...`
- 业务代码 0 改动 (接口签名保持)
- 旧路径放置 shim: `from services.jobseeker.resume_parser import *  # noqa: F401,F403`
- 测试不动, 但新增 `tests/test_services_layout.py` 校验不存在 services/<old>.py 平铺文件

---

## 2. agents/ 拆包 (runtime.py → 4 子包)

> 现状: `backend/agents/runtime.py` 764 行, 13 个顶层符号, 4 个独立职责混在一起。

### 2.1 顶层符号表

| 行 | 符号 | 类别 | 目标子包 |
| --- | --- | --- | --- |
| 36 | `LLMResponse` (dataclass) | LLM 数据契约 | agents/llm/types.py |
| 55 | `_dict_messages_to_provider` | LLM 适配 | agents/llm/adapter.py |
| 96 | `_provider_response_to_agent` | LLM 适配 | agents/llm/adapter.py |
| 108 | `MemoryScope` (Enum) | 记忆域 | agents/memory/scope.py |
| 115 | `AgentInput` (dataclass) | 协议 | agents/core/protocol.py |
| 129 | `AgentOutput` (dataclass) | 协议 | agents/core/protocol.py |
| 147 | `ToolCall` (dataclass) | 协议 | agents/core/protocol.py |
| 157 | `BaseAgent` (ABC, 含 memory 字段) | 核心 | agents/core/base.py |
| 272 | `_is_mock_provider` | LLM 内部 | agents/llm/adapter.py |
| 276 | `_resolve_provider_by_name` | LLM 内部 | agents/llm/adapter.py |
| 294 | `_wrap_legacy_openai_client` | LLM 内部 | agents/llm/adapter.py |
| 360 | `_DummyProvider` | LLM 内部 | agents/llm/adapter.py |
| 379 | `LLMClient` | LLM 客户端 | agents/llm/client.py |

### 2.2 目标目录

```
backend/agents/
├── __init__.py                 # 保留 re-export: BaseAgent, LLMClient, AgentInput, AgentOutput, ToolCall, MemoryScope
├── core/                       # 协议 + 抽象基类
│   ├── __init__.py
│   ├── protocol.py             # AgentInput / AgentOutput / ToolCall
│   ├── base.py                 # BaseAgent (含 memory 字段委托)
│   └── registry.py             # (新) AgentRegistry, 从 agents/registry.py 移入
├── llm/                        # LLM 客户端
│   ├── __init__.py
│   ├── types.py                # LLMResponse
│   ├── adapter.py              # provider <-> agent 适配 + 3 个内部 helper
│   └── client.py               # LLMClient
├── memory/                     # 记忆
│   ├── __init__.py
│   ├── scope.py                # MemoryScope
│   ├── store.py                # (从 agents/memory.py 拆出 BaseStore)
│   └── backends/
│       ├── redis.py            # 已有, 移入
│       └── memory.py           # 内存后端
├── observability/              # 追踪
│   ├── __init__.py
│   ├── tracing.py              # (从 agents/tracing.py 移入, 加强)
│   └── cost.py                 # (新) 单 Agent cost 计量
├── react.py                    # 保留, 改为 from .core.base import BaseAgent
├── boot.py                     # 保留, 改为 from .llm.client import LLMClient
├── semantic_router.py          # 保留
├── llm_extractor.py            # 保留
├── toolkit.py                  # 保留
└── tests/                      # 78 tests 拆到对应子包
```

### 2.3 拆包原则

- 公开 API 保持不变, `from agents.runtime import BaseAgent` 在 v5.0~v5.1 双轨
- `BaseAgent.memory` 字段改为 `BaseAgent.memory: MemoryStore` 委托, 不再在 base.py 直接 import MemoryStore 实现
- `_DummyProvider` 移到 `llm/adapter.py` 内并改名为 `DummyProvider` (去掉前导下划线, 在测试中被 import)
- `registry.py` (顶层) 合并到 `core/registry.py`, 旧路径转发

---

## 3. Dead code 评估

> 方法: `git log --since="30 days ago"` + 全仓 `grep` 引用; 同时检查 `tests/` 中是否有覆盖。

### 3.1 adapters/  —  **保留, 但补文档**

```
backend/main.py:21:    from adapters.registry import init_adapters
backend/api/admin.py:95:   # Get health status for all registered adapters
backend/api/admin.py:125:  from adapters.registry import adapter_registry
backend/pipelines/normalize.py:7:  from adapters.base import AdapterCandidate
backend/pipelines/ingest.py:7-8:    from adapters.base import AdapterCandidate; from adapters.registry import adapter_registry
backend/services/quote.py:245:       # sourced from multiple adapters (注释)
```

- git log 30 天: 0 commits (但有 v1.0 历史 commit 0685b76)
- 生产代码引用: **6 处真实使用** (main.py, admin.py, pipelines/*2, quote.py 注释)
- 测试引用: test_adapters.py + test_pipelines.py
- **结论: NOT dead** — 是 pipelines 层的核心抽象。**保留**, 但补 `adapters/README.md` 说明 Bullhorn/Hubspot/LinkedIn 是 mock 实现, 真实接入需走 `services/employer/ats_sync.py`。

### 3.2 copilot/  —  **删除**

```
$ grep -rln "from backend.copilot\|from .copilot" backend/ --include="*.py"
(无输出)
```

- git log 30 天: 0 commits
- 生产引用: 0
- 测试引用: 0
- 三个文件: `executor.py`, `formatter.py`, `parser.py` 共 ~250 行
- **结论: DEAD**。删除 3 个文件, 节省 250 行 + 潜在 5-8 条死测试。

### 3.3 signals/  —  **删除**

```
$ grep -rln "from backend.signals\|from .signals" backend/ --include="*.py"
(无输出)
```

- git log 30 天: 0 commits
- 生产引用: 0
- 测试引用: 0
- 四个文件: `analytics.py`, `embedding_updater.py`, `feedback_loop.py`, `tracker.py` 共 ~400 行
- **结论: DEAD**。删除 4 个文件; 真的需要信号埋点时, 复用 `services/observability/telemetry.py`。

### 3.4 评估汇总

| 模块 | git 30d | 生产引用 | 测试引用 | 处置 |
| --- | --- | --- | --- | --- |
| adapters/ | 0 | 6 | 2 文件 | 保留 + 补 README |
| copilot/ | 0 | 0 | 0 | **删除** (3 文件, ~250 行) |
| signals/ | 0 | 0 | 0 | **删除** (4 文件, ~400 行) |

合计清理 ~650 行死代码 + 估计 12-20 条死测试。

---

## 4. Frontend 整合

> 现状: 18 个 app 域, components 51 平铺 + 20 子目录。

### 4.1 路由合并

| 旧路径 | 新路径 | 理由 |
| --- | --- | --- |
| app/mind/candidates | app/employer/candidates | mind 本就是 employer 的 B 端心智模型别名 |
| app/mind/dashboard | app/employer/dashboard | 同上 |
| app/mind/pipeline | app/employer/pipeline | 招聘漏斗即 employer 域 |
| app/mind/quotes | app/employer/quotes | 报价即 employer 域 |
| app/mind/roles (含 roles/new) | app/employer/roles | 重复 |
| app/mothership/admin/* (13 路由) | app/admin/* | "mothership"是品牌名, 不是路由前缀; admin 全局唯一 |
| app/mothership/* (其余 9 路由) | 评估: 与 employer/jobseeker 重叠, 走 #4.3 决策 |

**mind 重叠评估**: 5/5 子路由在 employer/ 已有等价物 → 整目录废弃。
**mothership/admin 重叠评估**: 13 子路由在 admin 域可独立存在 → 整段迁出 mothership。
**mothership 剩余**: candidates/collections/dashboard/handoffs/matching/pilot/recommendations/analytics 中,
- `mothership/analytics` → `app/admin/analytics` (与 mothership/admin/analytics 合并, 单点)
- `mothership/matching` → `app/employer/matching` (与 admin/matching-quality 解耦, 前者是用户态, 后者是治理态)
- 其余 7 路由 → 评估后 **删除** (与 employer/jobseeker 重复)

### 4.2 components/ 重组 (51 平铺 → 3 域 + shared)

```
frontend/components/
├── jobseeker/             # 求职者端组件
│   ├── ResumeUpload.tsx
│   ├── ProfileCard.tsx
│   ├── ProfileCompleteness.tsx
│   ├── OfferBreakdown.tsx
│   ├── OfferComparisonTable.tsx
│   ├── NegotiationScript.tsx
│   ├── InterviewQuestion.tsx
│   ├── JournalAdviceList.tsx
│   ├── JournalWarningTimeline.tsx
│   ├── VoiceRecorder.tsx
│   ├── VoiceWaveform.tsx
│   ├── VideoInterviewRecorder.tsx
│   ├── EmotionChip.tsx
│   ├── EmotionEventDetail.tsx
│   ├── EmotionTriggerCorrelation.tsx
│   ├── EmotionWeekSummary.tsx
│   ├── FieldHighlight.tsx
│   ├── ContradictionBadge.tsx
│   ├── NeedsList.tsx
│   ├── QuickSurvey.tsx
│   ├── SubscriptionForm.tsx
│   ├── SubscriptionMatch.tsx
│   ├── ReasoningTrace.tsx
│   ├── ScheduleVideoInterview.tsx (求职者预约)
│   ├── InterviewFeedback.tsx
│   ├── ActionItemTracker.tsx
│   └── FollowUpQuestions.tsx
├── employer/              # 雇主端组件
│   ├── ATSConflictResolver.tsx
│   ├── ATSIntegrationCard.tsx
│   ├── ATSSyncStatus.tsx
│   ├── BackgroundCheckStatus.tsx
│   ├── CalendarSync.tsx
│   ├── RecommendedCandidate.tsx
│   ├── FunnelFilter.tsx
│   ├── AssessmentReport.tsx
│   ├── GlobalSearchBar.tsx
│   ├── GlobalSearchPalette.tsx
│   ├── SearchResultItem.tsx
│   ├── SalaryChart.tsx
│   ├── VideoMeetingCard.tsx
│   └── EscalateToHumanButton.tsx
├── shared/                # 跨域组件 (从现有 sub-dirs 汇总)
│   ├── SkipToMain.tsx
│   ├── ServiceWorkerRegister.tsx
│   ├── OfflineBanner.tsx
│   ├── InstallPrompt.tsx
│   ├── ThemeProvider.tsx
│   ├── LocaleSwitcher.tsx
│   ├── OnboardingChecklist.tsx
│   ├── ProductTour.tsx
│   ├── FeedbackWidget.tsx
│   ├── JsonLd.tsx
│   └── charts/ (整体迁入)
└── index.ts               # barrel re-export, 旧路径兼容
```

20 个子目录 (`api-keys/`, `audit/`, `cost/`, `experiments/`, `jd/`, `legal/`, `match/`, `matching/`, `mind/`, `mothership/`, `plan/`, `policy/`, `rooms/`, `rules/`, `shared/`, `strategy/`, `tickets/`, `ui/`, `webhooks/`) 评估:
- `mind/` `mothership/` `matching/` → 与上面规则冲突, **删除** (分散组件上提到 employer/shared)
- `ui/` `shared/` `charts/` → 保留, 作为 shared 子层
- `match/` → 与 `matching/` 合并, 统一命名 `matching/`, 归 employer
- 其余 13 个子目录 → 组件迁到对应域后, 空目录删除

### 4.3 Storybook (新增)

- 引入 Storybook 8 + Vite builder
- 范围: `components/jobseeker/` + `components/employer/` + `components/shared/`
- v5.0 MVP: 至少为 30 个最常用组件写 story (ResumeUpload, OfferBreakdown, ProfileCard, GlobalSearchBar 等)
- 接入 CI: `pnpm storybook:test` 用 chromatic 做 visual regression

---

## 5. DX 增量 (无 setup() / 无 ErrorCode / 无 Storybook)

### 5.1 统一入口 `backend.setup()`

```python
# backend/setup.py  (新)
def setup_app(env: str | None = None) -> FastAPI:
    """统一装配入口, 替代 main.py 中 200+ 行的 startup 编排。
    顺序: config → logging → providers → db → adapters → services → agents → api → middleware
    """
```

- 收益: main.py 从 ~250 行 → ~30 行
- 强制: 所有 v5.0+ 新增服务在 `setup_app()` 中显式注册 (DI 容器用 `dishka` 替换手写)

### 5.2 ErrorCode 体系 (新 `backend/core/errors.py`)

```python
class ErrorCode(str, Enum):
    # 通用
    INTERNAL = "internal_error"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    VALIDATION = "validation_error"
    RATE_LIMITED = "rate_limited"
    # 域
    RESUME_PARSE_FAILED = "resume_parse_failed"
    LLM_BUDGET_EXCEEDED = "llm_budget_exceeded"
    ATS_CONFLICT = "ats_conflict"
    COMPLIANCE_BLOCKED = "compliance_blocked"
    # ...按 domain 收口
```

- 全局 exception handler: 把任意 Exception 序列化为 `{code, message, trace_id, details?}`
- 与现有 `errors/` 包共存, 渐进迁移

### 5.3 Storybook (见 #4.3)

---

## 6. 重构执行顺序 (8 周路线)

> 总周期: 8 周 (2 个月), 5 个里程碑, 每里程碑后做完整回归 + 灰度。
> 原则: **low-risk 先, IO boundary 后, frontend 单独窗口**。

| 周次 | 里程碑 | 内容 | 准入 | 准出 |
| --- | --- | --- | --- | --- |
| W1 | M1 · 基础设施 | (a) `backend/setup()` 骨架 + `core/errors.py` (b) shim 工具脚本 `tools/migrate_service.py` (c) CI 加 `test_services_layout` 守卫 | 1242 tests 全绿 | 基础守卫就位 |
| W2 | M2 · dead code | 删 `copilot/` + `signals/`, 同步删死测试, 跑全套 pytest | 删除前 1242 全绿 | 删除后 1230+ 全绿, 覆盖率不降 |
| W3 | M3 · services 拆包 (1/2) | jobseeker + employer + matching 三包 (24 文件) | M2 通过 | 24 文件迁移 + 24 shim + 1242 全绿 |
| W4 | M4 · services 拆包 (2/2) | billing + observability + integrations + platform 四包 (33 文件) | M3 通过 | 57 文件全迁, 顶层 services/ 平铺 = 0 |
| W5 | M5 · agents 拆包 | runtime.py → core/llm/memory/observability 四子包, 同步 78 tests 拆 | M4 通过 | 1242 tests 全绿, 任意 agent 启动延迟 < 50ms |
| W6 | M6 · Frontend 路由 | app/mind/* → app/employer/*, app/mothership/admin/* → app/admin/*, 写 301/308 重定向 | M5 通过 | Next.js build 通过, 路由数从 18 域 → 12 域 |
| W7 | M7 · Frontend components | 51 平铺 → 3 域, 引入 Storybook 8, 写 30 个核心 story | M6 通过 | Storybook build + chromatic 跑通 |
| W8 | M8 · 收尾 | (a) 文档: REFACTOR_MAP + CHANGELOG v5.0 (b) 性能回归 (c) 安全审计 (d) 删除所有 shim, 升 minor 为 5.0 | M7 通过 | 1242+ tests 全绿, p95 延迟不退化 |

### 6.1 灰度策略

- W3 ~ W5 (后端): 影子流量 10% → 50% → 100%, 关键路径对比 p50/p95
- W6 ~ W7 (前端): Next.js Middleware 做 A/B, 旧路径返 308 → 新路径

---

## 7. 风险评估

| 风险 | 等级 | 触发条件 | 缓解 |
| --- | --- | --- | --- |
| **services shim 与新包循环 import** | M | Python 相对 import + re-export 易死锁 | CI 加 `import-services-all` 测试, 启动时遍历所有 services.* 模块 |
| **agents/runtime.py 拆分后 BaseAgent 公开字段破坏子类** | H | 16 个 Agent 都在 `__init__` 里 super().__init__() 设字段, 字段重排会导致 MRO 错位 | W5 用 libCST 做 AST diff, 强制 `super().__init__` 调用参数顺序对齐; 灰度期间保留 2 周旧 `agents.runtime` shim |
| **mind/mothership 路由删除后外链 404** | M | 客户邮件/IM 中大量带 mind 链接 | W6 全部做 308 重定向, 同时在 NGINX 层兜底 `try_files` |
| **adapters/ 误判 dead 后反悔成本** | L | 已确认为 NOT dead, 不删 | 文档化 `adapters/README.md`, 列出 6 个生产引用点 |
| **Storybook 引入拖慢 CI** | L | chromatic visual regression 慢 | 仅对 P0 组件 (10 个) 跑 chromatic, 其余只跑 interaction test |
| **删 copilot/signals 误杀隐藏依赖** | M | 存在动态 import `importlib.import_module('backend.copilot.xxx')` | 删前全仓 `grep -r "import_module.*copilot\|import_module.*signals"`, 必为 0 |
| **服务拆包后 DI 容器 (FastAPI Depends) 路径不一致** | H | 65 个 API 文件, shim 路径 vs 新路径 Depends 解析开销 | W1 引入 dishka, 一次性统一容器; shim 期间性能对比 |
| **frontend components 平铺后 import 路径全部变更** | M | 51 个文件 × N 个引用点, 数千处 import 需改 | 用 jscodeshift codemod 自动改, 灰度期间 barrel `components/index.ts` 兼容 |

### 7.1 回滚预案

- W3 ~ W5: 任意 M 里程碑失败, shim 不删可立即回滚, 5 分钟内回到 v4.0 行为
- W6 ~ W7: NGINX 切回旧路由前缀, 5 分钟内回滚
- 数据无破坏性变更, 零回滚成本

---

## 8. 验收清单 (Definition of Done for v5.0)

- [ ] `services/` 顶层平铺文件数 = 0
- [ ] `services/` 子包数 ≤ 7 (jobseeker/employer/matching/billing/observability/integrations/platform)
- [ ] `agents/runtime.py` 行数 ≤ 200 (仅保留 public re-export + docstring)
- [ ] 4 个 agents 子包 (core/llm/memory/observability) 各 ≤ 400 行
- [ ] `copilot/` `signals/` 不存在
- [ ] `adapters/README.md` 存在, 列出 6 个生产引用点
- [ ] `backend/setup.py` 存在, main.py ≤ 50 行
- [ ] `backend/core/errors.py` 存在, ErrorCode ≥ 20 个
- [ ] `app/mind` 不存在, 全部 308 → `app/employer`
- [ ] `app/mothership` 不存在, 全部 308 → `app/admin` 或 `app/employer`
- [ ] `components/{jobseeker,employer,shared}/` 三目录, 平铺 0
- [ ] Storybook 8 跑通, ≥ 30 个 story
- [ ] 1242+ tests 全绿, 覆盖率不降
- [ ] p95 延迟不高于 v4.0 基线

---

## 9. 附录: 自动化脚本清单

| 脚本 | 用途 | 触发 |
| --- | --- | --- |
| `tools/migrate_service.py` | 单服务迁移: 创建新包, 移动文件, 生成 shim | M3-M4 |
| `tools/check_agents_layout.py` | 校验 runtime.py 行数 + 4 子包存在 | M5 |
| `tools/codemod_component_imports.ts` | jscodeshift 改 components/ import 路径 | M7 |
| `tools/verify_dead_code.py` | 扫 dead code 候选, 输出报告 | M2 |
| `.github/workflows/refactor-gate.yml` | CI 守卫: services 平铺 = 0 / agents runtime 行数 / components 域分类 | 全程 |

---

*本文件由 v5.0 重构总规划师维护, 任何执行偏差需在 CHANGELOG v5.0 中留痕。*
