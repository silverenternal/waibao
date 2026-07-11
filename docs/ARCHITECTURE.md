# 系统架构

## 🏛️ 总体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js 16)                         │
│                                                                       │
│   /jobseeker        /employer (8 modules)        /match               │
│   ├ chat UI         ├ vision                    ├ dual score viz     │
│   ├ journal         ├ compliance                └ realtime           │
│   ├ plan            ├ talent_brief                └ SocketProvider    │
│   └ profile         ├ job_spec                                        │
│                     ├ policy                                          │
│                     ├ multiparty                                      │
│                     └ hr_service                                      │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │ HTTP / WebSocket
┌──────────────────────────────────▼──────────────────────────────────┐
│                     Backend (FastAPI + 16 Agents)                      │
│                                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │ Semantic    │  │ ReAct       │  │ LLM         │  │ Agent       │  │
│  │ Router      │  │ Framework   │  │ Extractors  │  │ Runtime     │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  │
│                                                                         │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐       │
│  │ Jobseeker 6 Agent│  │ Employer 9 Agent │  │ Matching 1 Agent │      │
│  │ Profile/Intake   │  │ Persona/Compliance│  │ MutualEvaluator │      │
│  │ Journal/Emotion  │  │ Vision/Brief/Spec │  └──────────────────┘      │
│  │ Clarifier/Planner│  │ Policy/MultiParty │                             │
│  └──────────────────┘  │ EmployerClarifier │                             │
│                        │ HRService         │                             │
│                        └──────────────────┘                             │
│                                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │ Memory 3-tier│  │ Tool Registry│  │ Tracing    │  │ Cost Control│  │
│  │ short/working │  │ db/llm/notify│  │ OpenTelemetry│  │ per-user    │  │
│  │ /long_term    │  │ /ocr/search  │  │ spans      │  │ budget      │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────┐
│                   Supabase (PostgreSQL + pgvector)                     │
│                                                                         │
│   agent_memory  ·  conversations  ·  emotion_timeline                  │
│   company_strategy/credentials/policies                               │
│   candidate_clarifications  ·  employer_clarifications                │
│   daily_journals  ·  career_plans  ·  two_way_matches                │
│   user_personas  ·  RLS policies  ·  GDPR functions                   │
│                                                                         │
│   Realtime subscriptions  ·  Auth (JWT)  ·  Storage (CV files)         │
└─────────────────────────────────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────┐
│                       External Services                                  │
│   OpenAI GPT-4o  ·  text-embedding-3-small                              │
│   工商信息查询  ·  OCR 服务  · 邮件 / 钉钉 / 飞书 / 企业微信             │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                (via Providers 抽象层)
                                   │
┌──────────────────────────────────▼──────────────────────────────────┐
│            providers/  —  7 capability × N vendor                       │
│                                                                          │
│   LLM        : openai | anthropic | deepseek | zhipu | tongyi | moonshot │
│   Embedding  : openai | zhipu | tongyi                                   │
│   Vision     : gpt4v | qwen_vl                                           │
│   OCR        : tencent | baidu | aliyun | gpt4v (fallback)               │
│   STT        : whisper | aliyun                                         │
│   Notify     : smtp | dingtalk | feishu | wecom | webhook                │
│   Lookup     : tianyancha | qichacha                                     │
│                                                                          │
│   @with_resilience: retry | circuit-breaker | rate-limit | cost | metric │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 数据流

### 求职者旅程
```
简历上传 → Intake Agent(引导建档)
         ↓
      Profile Agent(LLM 抽取 + memory 持久化)
         ↓
用户输入文本 → SemanticRouter(embedding 路由)
         ↓
     [情绪] → Emotion Agent(LLM 识别 + 共情 + 风险告警)
     [日记] → DailyJournal Agent(AI 评价 + 建议)
     [澄清] → Clarifier Agent(多步推理 + 反思)
     [规划] → CareerPlanner Agent(短期/中期/长期)
         ↓
     Clarifier 综合 → career_plans / candidate_clarifications
```

### 用人单位旅程
```
老板上传愿景 → Vision Agent(4 层解构)
            ↓
        公司战略存储
            ↓
老板描述人才 → TalentBrief Agent(+ LLM 偏见检测)
            ↓
部门细化 JD → JobSpec Agent(结构化 + 检测过度)
            ↓
多方讨论 → MultiParty Agent(汇总 + 冲突调解)
            ↓
制度上传 → Policy Agent(分类 + RAG)
            ↓
Employer Clarifier → employer_clarifications
```

### 双向匹配
```
候选人画像 (candidate_clarifications) ─┐
                                       ├─→ Two-Way Matcher ─→ harmonic_score
岗位画像 (employer_clarifications) ─────┘                       ↓
                                                    two_way_matches 表
                                                          ↓
面试后 → MutualEvaluator → mutual_score + recommendation
                                                          ↓
                                            Feedback Loop → 画像更新
                                                          ↓
                                              Calibration → 校准建议
```

---

## 🧩 核心模块详解

### 1. Agent Runtime (`backend/agents/runtime.py`)
所有智能体的基类,统一:
- 输入/输出协议 (`AgentInput` / `AgentOutput`)
- 工具注册
- 三层记忆
- Cost 控制 + Retry
- Tracing span

### 2. Semantic Router (`backend/agents/semantic_router.py`)
- **意图向量**:每个 agent 用 3-5 个自然语言句子描述,LLM 嵌入
- **路由**:用户输入 → 嵌入 → 余弦相似度 → top-k
- **降级**:低分时 LLM 意图理解兜底

### 3. ReAct Framework (`backend/agents/react.py`)
- Thought → Action → Observation 循环
- 工具调用(基于 OpenAI function calling 风格)
- 自我反思(每轮结束前审视方向)

### 4. LLM Extractors (`backend/agents/llm_extractor.py`)
- `extract_resume`: 简历结构化抽取(替代正则)
- `detect_emotion`: 情绪识别(替代词典)
- `detect_biases`: 偏见检测(替代词表)
- `understand_intent`: 意图理解(替代关键词路由)
- `synthesize_profile`: 多源画像综合

### 5. Memory System (`backend/agents/memory.py`)
- **short_term**: 进程内,1 小时 TTL
- **working**: Redis(预留),跨调用保留
- **long_term**: Supabase `agent_memory` 表,永久

### 6. Matching (`backend/matching/`)
- `two_way.py`: 双向打分(求职者↔岗位)
- `harmonic_score.py`: 调和/几何/算术均值工具
- 调和值惩罚弱侧:双方都满意才高分

---

## 🔐 安全架构

### 数据加密
- PII 字段(AES-GCM 256 位):邮箱/手机/身份证/法人证件
- 静态加密 + 传输加密(TLS)
- 密钥管理:MVP 用环境变量,生产用 KMS

### 访问控制
- Supabase RLS:行级安全策略
- 多 persona RBAC:求职者/老板/HR/部门负责人/管理员
- 一人多 persona(同一用户可在求职者和 HR 间切换)

### 合规
- GDPR / 个保法:被遗忘权(`forget_user` RPC)+ 数据可携权(`export_user_data`)
- 数据保留期:730 天
- 审计:所有用户操作写入 `signals` 表

---

## 📈 性能与扩展

### 性能目标
- API P95 延迟: < 500ms (不含 LLM 调用)
- LLM 调用 P95: < 3s
- WebSocket 并发: 1000+ 连接/实例
- 数据库: pgvector 10k 候选人 < 100ms

### 扩展性
- **水平扩展**:FastAPI 无状态,可任意加 worker
- **LLM 缓存**:`llm_cache.py` 相同 prompt 复用结果
- **LLM 配额**:`llm_budget.py` per-user token 限制
- **压测**:`tests/load/locustfile.py` 1000 并发场景

### 监控
- Prometheus:Agent 调用量 / LLM tokens / 匹配延迟
- Grafana 仪表板:`infra/grafana-dashboard.json`
- 告警:钉钉/飞书 webhook(`infra/alertmanager.yml`)

---

## 🔧 配置矩阵

| 环境 | LLM | Database | Realtime |
|---|---|---|---|
| 开发 | OpenAI / 本地 | 本地 Supabase / Docker | WebSocket |
| 预发布 | OpenAI GPT-4o | 云 Supabase | WebSocket |
| 生产 | OpenAI GPT-4o + Anthropic 备份 | 多区域 Supabase | WebSocket + CDN |

---

## 📚 相关文档

- [AGENTS.md](./AGENTS.md) — 16 智能体详解
- [API.md](./API.md) — API 端点清单
- [DEPLOYMENT.md](./DEPLOYMENT.md) — 部署与运维
- [ROADMAP.md](./ROADMAP.md) — 未来路线图
- [PROVIDERS.md](./PROVIDERS.md) — v3.0 供应商 + i18n + Webhook + Rule DSL
- [I18N_GUIDE.md](./I18N_GUIDE.md) — i18n 三语翻译指南

---

## 🆕 v3.0 横切能力

### 🌍 i18n 三语 (zh-CN / en-US / ja-JP)
- **前端**:`next-intl` 全栈支持,`frontend/messages/{locale}.json` 维护译文
- **后端**:Agent prompt 模板接受 `locale` 参数,生成对应语言的解释/反馈
- **语言切换**:`middleware/proxy.ts` 根据 `Accept-Language` + cookie 自动分流
- **CI 守门**:`npm run i18n:check` 强制三语键一致(缺失立即失败)
- **AI 翻译**:用 LLM 自动生成新 key 的初版译文,人工 review

### 📡 Webhook 出口 (T804 衍生)
- **签名**:HMAC-SHA256,header `X-Waibao-Signature`
- **重试**:指数退避,最多 5 次,失败入 `webhook_dead_letter`
- **事件类型**:`match.created` / `ticket.escalated` / `rule.triggered` / `bias.detected` / `audit.recorded`
- **订阅管理**:HR 在 admin UI 配置 endpoint URL + 事件过滤
- **路由**:`/api/webhooks/subscriptions`、`/api/webhooks/deliveries`

### 🔑 公开 API Key (T902)
- **scope**:`read:roles` / `read:candidates` / `read:matches` / `write:notes`
- **rate limit**:per-key, sliding window (默认 60 req/min)
- **管理**:Admin 在 `admin_api_keys.py` 创建/吊销;Key 一次性展示后仅存哈希
- **路由**:`/api/public/*`(无需 Supabase JWT, 用 API Key header 鉴权)

### ⚙️ 规则引擎 (T804)
- **DSL**:JSON 形式 `{when: {field, op, value}, then: [{action, args}]}`
- **内置触发器**:12+ 种(简历到达、SLA 逾期、偏见告警、关键词命中…)
- **Action 类型**:建工单 / 通知 / Webhook / 自动调整权重
- **调度**:`rule_scheduler.py` 每分钟扫描待评估事件
- **路由**:`/api/rules/*`、`admin/rules/*`

### 🧪 A/B 实验 (T901)
- **分桶**:基于用户 ID + experiment salt 的稳定哈希
- **指标**:`record_metric(experiment, variant, metric, value)`
- **显著性**:内置 Welch's t-test,给出 p-value
- **UI**:`/admin/ab` 看分布 + 显著性,自动停掉明显劣势变体
- **路由**:`/api/admin/ab/*`

### 📊 可观测性 (T1001/T1003)
- **OpenTelemetry**:初始化在 `services.telemetry.init_telemetry()`,挂载 FastAPI/HTTPX/Redis
- **Span 助手**:`with span("llm_call", provider=..., model=...)` 自动埋点
- **采样率**:默认 10%(可经 `OTEL_SAMPLER_ARG` 调整)
- **OTLP 导出**:可选 endpoint(生产环境走 OTel Collector)
- **Prometheus**:`/metrics` 暴露,`services.metrics` 封装
- **Sentry**:仅生产 + 配置 DSN 时启用,`beforeSend` 过滤 PII
- **审计**:`@audit` 装饰器记录所有写入操作,落 `audit_log` 表(append-only)

---

## 🔌 Providers 抽象层

v2.0 引入统一的外部供应商抽象层,把"调用哪家 LLM/OCR/通知"从业务代码里彻底剥离。

### 设计原则

1. **零业务侵入**: 切换供应商只改 `LLM_PROVIDER=anthropic`,不动任何 `.py`
2. **能力维度隔离**: 7 个 capability 维度各自独立(LLM / Embedding / Vision / OCR / STT / Notify / CompanyLookup)
3. **共享韧性中间件**: 所有 provider 统一接入重试 / 熔断 / 限流 / 成本追踪 / Prometheus 指标
4. **Mock 优先**: 默认全 mock,接入新供应商时不影响测试
5. **可观测**: 每次调用都打 metric,失败自动降级到下一个 provider

### 架构

```
business (agents/services/pipelines)
        │ 调用 registry.get_xxx_provider()
        ▼
providers/registry.py  (单例 + 懒加载 + 按 ENV 路由)
        │ name = os.getenv("LLM_PROVIDER")  →  class lookup
        ▼
providers/<capability>/<vendor>_provider.py  (每个 vendor 一个类)
        │ 每个对外方法都用 @with_resilience(...) 装饰
        ▼
providers/base.py  (RetryPolicy / CircuitBreaker / TokenBucket / CostTracker / Metrics)
        │
        ▼
外部 API (OpenAI / Anthropic / DeepSeek / 钉钉 / ...)
```

### 7 个 Capability 维度

| 维度 | 支持的供应商 | 默认 |
|---|---|---|
| LLM | OpenAI / Anthropic / DeepSeek / Zhipu / Tongyi / Moonshot | mock |
| Embedding | OpenAI / Zhipu / Tongyi | mock |
| Vision (多模态) | GPT-4V / Qwen-VL | mock |
| OCR | 腾讯云 / 百度 / 阿里云读光 / GPT-4V | mock |
| STT | Whisper / 阿里云 ASR | mock |
| Notify | SMTP / 钉钉 / 飞书 / 企业微信 / Webhook | mock |
| CompanyLookup | 天眼查 / 启信宝 | mock |

### 切换示例

```bash
# 默认 (开发)
LLM_PROVIDER=mock
EMBEDDING_PROVIDER=mock

# 生产 (用 GPT-4o + 智谱 embedding)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxx
EMBEDDING_PROVIDER=zhipu
ZHIPU_API_KEY=xxx

# 国内合规 (全栈国产)
LLM_PROVIDER=tongyi
EMBEDDING_PROVIDER=tongyi
VISION_PROVIDER=qwen_vl
OCR_PROVIDER=tencent
TENCENT_SECRET_ID=xxx
TENCENT_SECRET_KEY=xxx
NOTIFY_DINGTALK_ENABLED=true
```

### 共享中间件 (`base.py::with_resilience`)

每个 provider 方法被装饰器统一加上:

1. **熔断器** (CircuitBreaker): 连续 5 次失败 → 熔断 60s → 探测一个请求
2. **重试** (RetryPolicy): 指数退避 (1s → 2s → 4s),最大 3 次,带 20% jitter
3. **限流** (TokenBucket): 每 provider 独立桶,可配 rate_per_sec / burst
4. **成本** (CostTracker): per-tenant 日预算,超限抛 `BudgetExceeded`
5. **指标** (ProviderMetrics): Prometheus `provider_calls_total` + `provider_latency_seconds`

### Mock & 测试

```python
# 业务测试不需要任何外部 key
os.environ["LLM_PROVIDER"] = "mock"
os.environ["EMBEDDING_PROVIDER"] = "mock"
os.environ["NOTIFY_DINGTALK_ENABLED"] = "false"  # 走 mock 通道

# 单测覆盖
pytest providers/tests/test_registry.py -v
pytest providers/tests/test_base.py -v
pytest tests/test_llm_providers.py -v
```

### 新增供应商流程

详见 [`backend/providers/README.md`](../talent-tool-mvp/backend/providers/README.md),5 步上手:

1. 创建 `providers/<capability>/<vendor>_provider.py`
2. 继承对应基类 (`LLMProvider` / `EmbeddingProvider` / ...)
3. 在 `registry.py` mapping 中加入
4. 写至少 3 个单元测试
5. 更新 `config.example.env` + 本文档