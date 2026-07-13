# CHANGELOG

## v7.0.0 — 2026-07-13

> **Enterprise SaaS 化 + AI 能力深化** — 让产品能卖钱,让 AI 护城河更深。

### Highlights

- **白标 + 私有化部署** — 域名 / Logo / 颜色 / 字体可配置;Docker Compose / Helm / Terraform 全套交付
- **完整 RAG** — LlamaIndex + Qdrant + 文档解析/分块/重排/强制 citation
- **Multi-Agent 协作** — CrewAI + 角色 + 投票 + 共识机制
- **统一记忆库** — Mem0 + 向量 + 图谱,跨 Agent 共享
- **Prompt v2** — Agenta 风格 + 版本化 + A/B + LLM-as-judge 自动评估
- **ClickHouse 数仓 + BI** — dbt + Cube.js 拖拽式报表
- **预测分析** — LightGBM (流失 / 招聘成功) + Prophet (时间序列)
- **SSO/SAML** — Authlib + NextAuth + Keycloak
- **开放 API 平台** — Developer Portal + OAuth 2.0 + SDK 自动生成
- **第三方应用市场** — Strapi 后台 + 审核 + 安装/卸载
- **API 版本化** — `/api/v1/` + `/api/v2/` 平滑过渡
- **LoRA Fine-tuning** — LLaMA-Factory + QLoRA + vLLM serve 多适配器热挂载
- **AI 主动 Sourcing** — Outbound 寻才 + GitHub 集成
- **严格多租户** — Tenant Context + RLS + Postgres `current_setting('app.tenant_id')`
- **Rate Limiting + 配额** — slowapi + plan-based quota store
- **完整审计** — `audit_log_v2` 不可变 + AST 自动打点 + PII 检测
- **GDPR/PIPL/CCPA** — per-purpose consent + forget/export/rectify API
- **SLA 99.9%** — SLA monitor + Instatus 状态页 + Intercom 支持

### Phase P0 — Enterprise SaaS 化

| Task | 标题 | 状态 |
|---|---|---|
| T2601 | 严格多租户隔离 (RLS + Tenant 上下文) | ✅ |
| T2602 | 统一 Rate Limiting + 配额管理 | ✅ |
| T2603 | 完整审计日志 + GDPR/PIPL/CCPA | ✅ |
| T2604 | SLA 99.9% + 状态页 + 客户支持 | ✅ |

### Phase P1 — AI 能力深化

| Task | 标题 | 状态 |
|---|---|---|
| T2701 | 完整 RAG (文档解析/分块/检索/重排/citation) | ✅ |
| T2702 | Agent 统一记忆库 (Mem0 + 向量 + 图谱) | ✅ |
| T2703 | Multi-Agent 协作框架 (CrewAI) | ✅ |
| T2704 | Prompt 版本化 + A/B + LLM-as-judge | ✅ |

### Phase P2 — 数据仓库 + BI + 预测

| Task | 标题 | 状态 |
|---|---|---|
| T2801 | ClickHouse 数据仓库 + Airbyte ETL + dbt | ✅ |
| T2802 | BI 报表 (Cube.js) + 拖拽生成器 | ✅ |
| T2803 | 预测分析 (LightGBM + Prophet) | ✅ |

### Phase P3 — 合规 + 生态

| Task | 标题 | 状态 |
|---|---|---|
| T2901 | SSO/SAML 企业级登录 (Authlib + Keycloak) | ✅ |
| T2902 | 开放 API 平台 (Developer Portal + OAuth 2.0) | ✅ |
| T2903 | 第三方应用市场 (Strapi + 审核) | ✅ |
| T2904 | API 版本化 (`/api/v1/` + `/api/v2/`) | ✅ |

### Phase P4 — AI 高级 + 商业化

| Task | 标题 | 状态 |
|---|---|---|
| T3001 | LoRA Fine-tuning (LLaMA-Factory) | ✅ |
| T3002 | AI 主动 Sourcing (Outbound + GitHub) | ✅ |
| T3003 | 白标 + 私有化部署 (域名 / Logo / 颜色 / 字体) | ✅ |
| T3004 | v7.0.0 Release | ✅ |

### Metrics

| 指标 | v6.0 | v7.0 |
|---|---|---|
| 测试总数 | 2273 | 644 (核心) + 配套 |
| 子系统数 | 8 | 19 |
| 数据库表 | 47 | 56 (新增 9 张) |
| API 端点 | 145 | 220+ |
| Agent 数 | 16 | 16 + Multi-Agent 编排 |
| 部署形态 | 1 (公有云 SaaS) | 4 (SaaS + Docker + K8s + 白标) |

### New Files (主要)

```
backend/services/platform/whitelabel.py       (NEW — 白标服务)
backend/api/whitelabel.py                    (NEW — 白标 API)
supabase/migrations/052_whitelabel.sql       (NEW — 白标 DB 迁移)
frontend/lib/theme.ts                        (NEW — 主题系统)
frontend/components/WhiteLabelProvider.tsx   (NEW — React Provider)
frontend/components/WhiteLabelProvider.stories.tsx (NEW)
frontend/styles/whitelabel.css               (NEW — CSS 变量)
frontend/app/admin/whitelabel/page.tsx       (NEW — 管理界面)
infra/private-deployment/docker-compose.yml  (NEW — 一键启动)
infra/private-deployment/helm/waibao/        (NEW — Helm chart)
infra/private-deployment/terraform/          (NEW — AWS 参考架构)
infra/private-deployment/OPERATIONS_MANUAL.md (NEW — 客户运维手册)
infra/private-deployment/.env.example        (NEW — 环境变量模板)
docs/PRIVATE_DEPLOYMENT.md                   (NEW)
docs/AI_DEEP.md                              (NEW)
docs/COMMERCIAL.md                           (NEW)
tests/test_whitelabel.py                     (NEW — 76 tests)
```

### Migration Guide from v6.0 → v7.0

1. **DB migration**:
   ```bash
   python -m alembic upgrade head   # 包含 046-052 全部迁移
   ```
2. **环境变量新增**:
   ```bash
   WHITELABEL_ENABLED=true
   WHITELABEL_TENANT_ID=default
   WHITELABEL_PRODUCT_NAME=Waibao Recruitment
   WHITELABEL_PRIMARY_COLOR=#2563EB
   ```
3. **前端集成**:
   ```tsx
   // app/layout.tsx
   import WhiteLabelProvider from "@/components/WhiteLabelProvider";
   <WhiteLabelProvider>{children}</WhiteLabelProvider>
   ```
4. **私有化 (可选)**:
   ```bash
   cd infra/private-deployment
   docker compose up -d
   # 或 helm install waibao ./helm/waibao
   ```
5. **SSO (可选)**: 在 admin / SSO 配置 SAML metadata
6. **API 版本**: 旧 `/api/*` 仍可用,推荐逐步迁移到 `/api/v1/*`

### Breaking Changes

- `auth_sso.py` 中 Pydantic `class Config` → `ConfigDict` (Pydantic v2 必需)
- 旧的 `/api/gdpr` 端点移到 `/api/gdpr/v2` (旧路径保留 6 个月)
- Prompt 字符串模板统一使用 `services.platform.prompt_v2.PromptService`,旧 hard-coded prompt 将在 v7.1 移除

### Deprecations (将在 v7.1 移除)

- `api/compliance.py` 旧路径 → 改用 `api/compliance_api.py`
- `signals/` ad-hoc 事件 → 统一用 EventBus
- 旧的 copilot dashboard → 改用 Mothership UI

### Security

- Tenant Context 在每个 SQL 之前强制注入,无法绕过
- Audit log 不可变 (数据库 trigger 阻止 UPDATE/DELETE)
- 所有白标 mutation 走 RBAC + 审计
- LLM 输出强制 citation (RAG) 或 confidence score

### Contributors

- 16 工程师 × 5 个月
- 详见 [docs/COVERAGE-AUDIT-v7.md](./docs/COVERAGE-AUDIT-v7.md)

---

## v6.0.0 — 2026-04-01

v6.0 — 可扩展架构 + 差异化能力

### Highlights

- Event Bus (16 agents)
- Config Center + Feature Flag + Plugin SDK + Workflow Engine
- GPT-4o Realtime + AI 模拟面试官 + 视频简历 + LiveKit
- 16/16 甲方需求 100% 覆盖,2273 tests

详见 [RELEASE_NOTES_v6.0.0.md](./docs/RELEASE_NOTES_v6.0.0.md)。

---

## v5.0.0 — 2026-01-15

v5.0 — 多区域 + 灾备 + CDN

- 3 区域部署 (cn / sg / us)
- Q3 + Q4 灾备演练
- CDN + 灰度发布
- 商业化 (Sales Deck + Pricing + CSM Playbook)

---

## v4.0 — 2025-09-30

v4.0 — 多区域 + 合规 + 多端

- 多区域拓扑
- 合规模块 (PIPL / GDPR / CCPA / SOC 2)
- 多端覆盖 (Web / 小程序 / 钉钉 / 飞书 / PWA)

---

## v3.0 — 2025-06-30

v3.0 — AI-Native 重构

- SemanticRouter / LLM 抽取器 / ReAct 框架
- 16 个智能体协同
- 完整双向匹配
- Providers 抽象层

---

## v2.0 — 2025-03-31

v2.0 — 业务能力扩展

- 协同 / 漏斗 / 知识库 / 通知
- 多区域
- 真实数据接入 (Zoom / Beisen / Checkr)

---

## v1.0 — 2025-01-15

v1.0 — 首个公开版本

- 基础 Mind + Mothership UI
- 候选人 / 岗位 / 匹配 / 面试核心流程