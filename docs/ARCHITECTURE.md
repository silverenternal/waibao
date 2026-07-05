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