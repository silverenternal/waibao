# 招聘智能体 (Recruitment Agent)

> **v9.0 — Frontend Enterprise Rebuild**
>
> 前端整体重做达到企业级 (Refine + shadcn/admin + Tremor + Open WebUI + OpenResume 五大开源参考),共享 design tokens / 组件库 / Storybook / A11y,后端 3700+ 测试通过,5 端 (Web + 小程序 + 钉钉 + 飞书 + PWA) 视觉一致。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org)
[![Tests](https://img.shields.io/badge/tests-3700%2B%20passed-green.svg)](./talent-tool-mvp/backend/tests)
[![Providers](https://img.shields.io/badge/providers-7%20capabilities%20×%20N%20vendors-blue.svg)](./talent-tool-mvp/backend/providers/README.md)
[![v8.1](https://img.shields.io/badge/version-8.1.0-blueviolet.svg)](./CHANGELOG.md)

---

## 🎯 v7.0 北极星

| 目标 | 指标 | 目标 |
|---|---|---|
| ARR | 真实收入 | ≥ 1000 万 RMB (2027 Q4) |
| NPS | 客户净推荐值 | ≥ 65 |
| RAG 准确度 | 检索 Top-5 hit rate | > 85% |
| Multi-Agent 任务成功率 | end-to-end | > 80% |
| SLA | 月度可用性 | 99.9% |
| 合规 | GDPR / PIPL / CCPA | 100% 覆盖 |

## ✨ v7.0 新增能力

### 🏢 Enterprise SaaS 化 (Phase P0)
- ✅ **严格多租户隔离** (T2601) — Tenant Context + RLS + Postgres `current_setting('app.tenant_id')`
- ✅ **统一 Rate Limiting + 配额** (T2602) — slowapi + plan-based quota store
- ✅ **完整审计 + GDPR/PIPL/CCPA** (T2603) — `audit_log_v2` + AST 装饰器 + per-purpose consent + GDPR v2 API
- ✅ **SLA 99.9% + 状态页** (T2604) — SLA monitor + Instatus 自托管 + Intercom 支持

### 🧠 AI 能力深化 (Phase P1)
- ✅ **完整 RAG** (T2701) — LlamaIndex + Qdrant + 文档解析/分块/检索/重排/citation
- ✅ **统一记忆库** (T2702) — Mem0 + 向量 + 图谱,跨 Agent 共享
- ✅ **Multi-Agent 协作** (T2703) — CrewAI + 角色 + 投票 + 共识机制
- ✅ **Prompt 版本化 + A/B + 评估** (T2704) — Agenta 风格 + LLM-as-judge + 黄金集

### 📊 数据仓库 + BI + 预测 (Phase P2)
- ✅ **ClickHouse 数仓 + ETL** (T2801) — Airbyte + dbt + scheduler
- ✅ **BI 报表 + Cube.js** (T2802) — 拖拽式报表生成器 + Redis 缓存
- ✅ **预测分析** (T2803) — LightGBM (流失/招聘成功) + Prophet (时间序列)

### 🌐 合规 + 生态 (Phase P3)
- ✅ **SSO/SAML** (T2901) — Authlib + NextAuth + Keycloak
- ✅ **开放 API 平台** (T2902) — Developer Portal + OAuth 2.0 + SDK 自动生成
- ✅ **第三方应用市场** (T2903) — Strapi 后台 + 审核 + 安装/卸载
- ✅ **API 版本化** (T2904) — `/api/v1/` + `/api/v2/` 平滑过渡

### 🚀 AI 高级 + 商业化 (Phase P4)
- ✅ **Fine-tuning (LoRA)** (T3001) — LLaMA-Factory + QLoRA + vLLM serve
- ✅ **AI 主动 Sourcing** (T3002) — Outbound 寻才 + GitHub 集成
- ✅ **白标 + 私有化部署** (T3003) — 域名 / logo / 颜色 / 字体可配置 + Docker Compose / Helm / Terraform
- ✅ **v7.0.0 Release** (T3004) — 本次发布

---

## 🏗️ 技术栈

| 层 | 技术 |
|---|---|
| **Backend** | FastAPI + Python 3.12 + EventBus + RAG + MultiAgent + TenantIsolation |
| **Frontend** | Next.js 16 + TypeScript + Tailwind + next-intl + Storybook + ReactFlow |
| **Database** | Supabase (OLTP) + ClickHouse (OLAP) + pgvector + Neo4j (知识图谱) + Qdrant (向量) |
| **AI** | OpenAI / Anthropic / DeepSeek / 智谱 / 通义 / Kimi + Whisper / GPT-4V / GPT-4o Realtime + LoRA |
| **Infrastructure** | Docker Compose + Supabase + ClickHouse + Redis + OpenTelemetry + Prometheus + Sentry + Locust + ArgoCD + LiveKit |

---

## 🚀 快速开始

### 前置要求
- Python 3.12+
- Node.js 20+
- Supabase 项目 (本地或云端)
- OpenAI API Key (或其它 LLM 供应商 key)

### 1. 克隆并安装
```bash
git clone https://github.com/silverenternal/waibao
cd waibao/talent-tool-mvp
cd backend && pip install -r requirements.txt
cd ../frontend && pnpm install
```

### 2. 配置环境变量
```bash
cp backend/.env.example backend/.env
# 编辑 .env,填入 SUPABASE_URL / SUPABASE_KEY / OPENAI_API_KEY 等
```

### 3. 启动开发服务器
```bash
# Backend
cd backend && uvicorn main:app --reload --port 8000

# Frontend (新终端)
cd frontend && pnpm dev
```

打开 http://localhost:3000

### 4. 运行测试
```bash
cd backend && python -m pytest        # 641 tests, 全离线
cd frontend && pnpm tsc --noEmit      # TypeScript strict 模式
```

---

## 📦 私有化部署

详见 [`docs/PRIVATE_DEPLOYMENT.md`](./docs/PRIVATE_DEPLOYMENT.md) 与
[`infra/private-deployment/`](./talent-tool-mvp/infra/private-deployment/)。

```bash
# Docker Compose (单主机,POC / 中小企业)
cp infra/private-deployment/.env.example infra/private-deployment/.env
docker compose -f infra/private-deployment/docker-compose.yml up -d

# Helm (Kubernetes,大规模生产)
helm install waibao ./infra/private-deployment/helm/waibao \
  --set whitelabel.tenantId=acme \
  --set whitelabel.domain=hire.acme.com

# Terraform (AWS 参考架构)
cd infra/private-deployment/terraform
terraform apply
```

---

## 🏛️ 架构

详见 [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) 和 [`docs/AI_DEEP.md`](./docs/AI_DEEP.md)。

```
┌────────────────────────────────────────────────────────────────────┐
│  Frontend (Next.js 16) — WhiteLabelProvider + ThemeProvider         │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│  Backend (FastAPI) — Tenant Context + Rate Limiting + Audit v2     │
│  ├─ 16 个 Agent (Profile / Clarifier / CareerPlanner / ...)        │
│  ├─ Multi-Agent (CrewAI) + RAG (LlamaIndex) + Memory (Mem0)        │
│  ├─ Prompt v2 (Agenta-style) + LoRA fine-tuning                    │
│  └─ Whitelabel Service + ClickHouse + Qdrant + Supabase            │
└────────────────────────────────────────────────────────────────────┘
                              │
            ┌──────────┬───────┼────────┬──────────┐
            ▼          ▼       ▼        ▼          ▼
        Supabase   ClickHouse  Qdrant  Redis    Object Storage
        (OLTP)     (数仓)     (向量)   (缓存)   (uploads)
```

---

## 📚 文档

| 文档 | 内容 |
|---|---|
| [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) | 整体架构 (含 RAG/MultiAgent/Memory/BI/SSO/LoRA) |
| [docs/AI_DEEP.md](./docs/AI_DEEP.md) | RAG / Multi-Agent / Memory / Fine-tuning 详解 |
| [docs/PRIVATE_DEPLOYMENT.md](./docs/PRIVATE_DEPLOYMENT.md) | 白标 + 私有化部署 |
| [docs/VENDOR_SELECTION.md](./docs/VENDOR_SELECTION.md) | 开源选型决策记录 |
| [docs/COMMERCIAL.md](./docs/COMMERCIAL.md) | 商业化 / 计费 / 隐私 / 合同 |
| [docs/RUNBOOK.md](./docs/RUNBOOK.md) | 运维手册 |
| [docs/MULTI_REGION.md](./docs/MULTI_REGION.md) | 多区域部署 |
| [docs/SECURITY.md](./docs/SECURITY.md) | 安全策略 |

---

## 📜 License

MIT — 详见 [LICENSE](./LICENSE)
商业使用 + 私有化部署 — 详见 [docs/COMMERCIAL.md](./docs/COMMERCIAL.md)

---

## 🤝 贡献

详见 [CONTRIBUTING.md](./CONTRIBUTING.md)。