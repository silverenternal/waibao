# 招聘智能体 (Recruitment Agent)

> 一个**真正 AI-native** 的双向招聘智能体,服务求职者 + 用人单位,基于 16 个智能体协同实现"画像澄清 + 双向精准匹配"。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org)
[![Tests](https://img.shields.io/badge/tests-31%20passed-green.svg)](./talent-tool-mvp/backend/tests)

---

## 🎯 项目愿景

传统招聘系统要么是"职位发布 + 简历投递"的撮合平台,要么是"AI 简历筛选"的工具。

我们要做的是:**两个智能体团队**——
- **求职者侧 6 个智能体**作为求职者的知心朋友 + 职业规划师,陪伴整个求职旅程
- **用人单位侧 9 个智能体**作为企业的真诚 HR,帮助老板/HR/部门负责人共同完成招聘
- **匹配侧 1 个智能体 + 3 个模块**实现真正的双向适配,而不是单向筛选

---

## ✨ 核心亮点

### 🧠 AI-Native 而非规则系统
- ✅ **语义路由**(`SemanticRouter`):用 embedding 相似度替代 200+ 硬编码关键词
- ✅ **LLM 抽取器**(`llm_extractor`):删除所有正则/词典,让 LLM 自己理解语义
- ✅ **ReAct 框架**(`ReActAgent`):Thought → Action → Observation 循环,带工具调用
- ✅ **反思机制**:Clarifier 综合后再让 LLM 审视自己输出,纠正过度解读
- ✅ **推理可视化**(`ReasoningTrace`):用户能看到 agent 怎么想,而不是黑盒

### 👥 16 个智能体协同
- **求职者侧(6)**:Profile / Intake / DailyJournal / Emotion / Clarifier / CareerPlanner
- **用人单位侧(9)**:Persona / Compliance / Vision / TalentBrief / JobSpec / Policy / MultiParty / EmployerClarifier / HRService
- **匹配侧(1)**:MutualEvaluator

### 🎯 完整覆盖甲方 16 个需求点
- 1.1~1.6 求职者知心朋友 + 职业规划师
- 2.1~2.9 用人单位真诚 HR + 全生命周期
- 3. 求职者 ↔ 用人单位 双向适配

---

## 🏗️ 技术栈

| 层 | 技术 |
|---|---|
| **Backend** | FastAPI + Python 3.12 + Pydantic |
| **AI** | OpenAI GPT-4o + text-embedding-3-small (可换 Anthropic / 本地 LLM) |
| **Database** | Supabase (PostgreSQL + pgvector + Auth + Realtime + RLS) |
| **Frontend** | Next.js 16 + TypeScript + Tailwind + shadcn/ui |
| **Realtime** | WebSocket + SSE |
| **Infra** | Docker Compose + Prometheus + Grafana + Alertmanager |

---

## 🚀 快速开始

### 前置要求
- Python 3.12+
- Node.js 20+
- Supabase 项目(本地或云端)
- OpenAI API Key

### 1. 克隆并安装
```bash
cd talent-tool-mvp
cd backend && pip install -r requirements.txt
cd ../frontend && npm install
```

### 2. 配置环境变量
```bash
# backend/.env
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJhbGc...
SUPABASE_SERVICE_KEY=eyJhbGc...
SUPABASE_JWT_SECRET=your-jwt-secret
OPENAI_API_KEY=sk-xxx
PII_ENCRYPTION_KEY=<base64-encoded-32-bytes>
```

### 3. 初始化数据库
```bash
# 在 Supabase SQL 编辑器中依次执行 supabase/migrations/ 下的迁移
psql -h db.xxx.supabase.co -U postgres -d postgres \
  -f supabase/migrations/002_agent_memory.sql \
  -f supabase/migrations/003_conversations.sql \
  ...
```

### 4. 启动开发服务器
```bash
# 后端 (端口 8000)
cd backend && uvicorn main:app --reload

# 前端 (端口 3000)
cd frontend && npm run dev
```

### 5. 跑测试
```bash
cd backend && python -m pytest tests/ -v
# ✅ 31 passed
```

---

## 📁 项目结构

```
waibao/                                  # 项目根
├── todo.json                            # 开发规划(23 任务,16 智能体,16 甲方需求)
├── README.md                            # 本文件
├── LICENSE                              # MIT
├── CONTRIBUTING.md                      # 贡献指南
├── docs/                                # 详细文档
│   ├── ARCHITECTURE.md                  # 系统架构
│   ├── AGENTS.md                        # 16 个智能体详解
│   ├── API.md                           # API 端点清单
│   ├── DEPLOYMENT.md                    # 部署指南
│   └── ROADMAP.md                       # 路线图
└── talent-tool-mvp/                     # 主代码库
    ├── backend/                         # FastAPI 后端
    │   ├── agents/                      # 16 个智能体 + 框架
    │   │   ├── runtime.py               # BaseAgent/LLMClient/Memory
    │   │   ├── semantic_router.py       # embedding 路由
    │   │   ├── react.py                 # ReAct 框架
    │   │   ├── llm_extractor.py         # LLM 抽取器
    │   │   ├── boot.py                  # 启动注册
    │   │   ├── jobseeker/               # 6 个求职者 Agent
    │   │   ├── employer/                # 9 个用人单位 Agent
    │   │   └── evaluator/               # 1 个匹配 Agent
    │   ├── api/                         # REST 端点(14 个新增)
    │   ├── services/                    # 业务服务
    │   ├── matching/                    # 双向打分算法
    │   ├── signals/                     # 反馈闭环
    │   ├── prompts/zh/                  # 中文 prompt 库
    │   └── tests/                       # 31 个测试
    ├── frontend/                        # Next.js 前端
    │   ├── app/(jobseeker)/             # 求职者端
    │   ├── app/(employer)/              # 用人单位端 8 模块
    │   ├── app/match/                   # 双向匹配可视化
    │   ├── app/realtime/                # WebSocket Provider
    │   ├── components/                  # UI 组件(含 ReasoningTrace)
    │   └── messages/                    # i18n(zh-CN / en-US)
    ├── supabase/
    │   └── migrations/                  # 7 个新迁移
    └── docker-compose.prod.yml          # 生产部署
```

---

## 🎓 16 个智能体一览

### 求职者侧(对应甲方需求 1.1-1.6)

| 智能体 | 对应需求 | 功能 |
|---|---|---|
| **Profile Agent** | 1.1 | 对话式画像采集,记忆持久化 |
| **Intake Agent** | 1.1 | 引导建档,文件上传,完成度跟踪 |
| **DailyJournal Agent** | 1.2 | 日记摄取,生成评级/建议/注意事项/行动项 |
| **Emotion Agent** | 1.4 | LLM 情绪识别(讽刺/复合情绪)+ 共情回应 |
| **Clarifier Agent** | 1.5 | 多源画像综合 + 反思 + 显隐性需求分离 |
| **CareerPlanner Agent** | 1.6 | 短期/中期/长期规划 + 市场行情 + 学习路径 |

### 用人单位侧(对应甲方需求 2.1-2.9)

| 智能体 | 对应需求 | 功能 |
|---|---|---|
| **Persona Agent** | 2.1/2.9 | 真诚 HR 人格,边界感 |
| **Compliance Agent** | 2.2 | OCR + 工商查询 + trust_score |
| **Vision Agent** | 2.3 | 愿景→规划→战略→战术 4 层解构 |
| **TalentBrief Agent** | 2.4 | 老板口述人才框架 + LLM 偏见检测 |
| **JobSpec Agent** | 2.5 | JD 结构化 + 过度要求检测 |
| **Policy Agent** | 2.6 | 制度解析 + 法律风险 + 求职者查询 |
| **MultiParty Agent** | 2.7 | 多方意见汇总 + 冲突调解 |
| **EmployerClarifier Agent** | 2.8 | 人才画像 + 真实需求 + 共识度 |
| **HRService Agent** | 2.9 | 招聘→入职→培训→绩效→晋升→离职全周期 |

### 双向匹配(对应甲方需求 3)

| 智能体/模块 | 功能 |
|---|---|
| **MutualEvaluator Agent** | 双方互评(proceed/hold/reject) |
| **Two-Way Matcher** | candidate_to_role + role_to_candidate + harmonic |
| **Feedback Loop** | outcomes → 画像更新 + 校准 |

---

## 📊 关键指标

```
✅ 16 个智能体            ✅ 31 个测试通过 (100%)
✅ 14 个新 API 端点       ✅ 7 个数据库迁移
✅ 12 个新数据表          ✅ 5 个前端页面
✅ 16/16 甲方需求覆盖     ✅ 中英文双语
```

---

## 🔒 安全与合规

- ✅ PII 字段级 AES-GCM 加密
- ✅ GDPR / 个保法:被遗忘权 + 数据可携权
- ✅ Supabase RLS 行级安全
- ✅ 情绪告警 → 心理风险评估
- ✅ 偏见检测 → 公平性评分

详见 [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)

---

## 📚 文档导航

| 文档 | 说明 |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统架构、数据流、模块关系 |
| [docs/AGENTS.md](docs/AGENTS.md) | 16 个智能体详解、Prompt、Tool |
| [docs/API.md](docs/API.md) | REST + WebSocket 端点清单 |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | 生产部署、监控、安全 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | 未来路线图 |
| [todo.json](todo.json) | 开发规划与里程碑 |
| [talent-tool-mvp/README.md](talent-tool-mvp/README.md) | 原项目文档 |

---

## 🤝 贡献

欢迎 PR!详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

开发前请阅读 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 理解整体设计。

---

## 📄 License

MIT © 2026 waibao