# waibao v8.0 开源选型清单 (Vendor Selection)

> 文档版本: v8.0
> 创建日期: 2026-07-13
> 维护者: waibao 架构组
> 选型原则: 严禁造轮子,所有功能从 GitHub 找成熟开源项目集成/二次开发
> 优先级: 生产级 > 大 star 数 > 社区活跃 > 文档完整 > 二次开发友好

## v8.0 新增选型 (T35xx / T39xx)

### T3501 服务开关
- **FastAPI Depends** — 官方守卫 (无新依赖)
- **Redis 5.0+** — 已有依赖 (T2602 已引入 slowapi)
- **Python 3.12 match-case** — 标准库
- **Supabase + RLS** — 已有依赖 (T2601)
- 自研 `services/platform/service_toggle.py` + `service_catalog.py` + `service_audit.py`

### T3506 前端 FeatureGate
- **React 18 hooks** — 已有
- 自研 `<FeatureGate>` + `useServiceAccess()`

### T3901 数据驱动
- **reportlab** — PDF 渲染 (T2303 文档生成已引入, fallback TXT)
- **python-docx** — DOCX 渲染 (T2303 已引入, fallback TXT)
- **APScheduler** — 可选, 调度入口由 main.py scheduler 拉起
- 自研 `auto_report.py` + `anomaly_detector.py`

### T3902 反馈统一入口
- **React 18 + lucide-react** — 已有
- **FastAPI Form** — 官方
- 自研 `FeedbackWidget` + `feedback_v2` API

### 端到端 Smoke Test
- **playwright** (可选) — 已有 v5.0 引入
- **httpx** — 已有 (T2604 SLA 监控引入)
- 自研 `tests/smoke/v8_smoke.py` 22+ 场景

### 评估效果
- reportlab / python-docx 已经存在依赖列表 (T2303)
- FastAPI Depends / Redis / Supabase 均已有
- v8.0 **未引入任何新外部依赖**

---

---

## 目录

- [一、Enterprise SaaS 系列 (T26xx)](#一-enterprise-saas-系列-t26xx)
  - [T2601 多租户 RLS](#t2601-多租户-rls)
  - [T2602 Rate Limiting](#t2602-rate-limiting)
  - [T2603 审计日志 + GDPR](#t2603-审计日志--gdpr)
  - [T2604 SLA 监控 + 状态页](#t2604-sla-监控--状态页)
- [二、AI Deep 系列 (T27xx)](#二-ai-deep-系列-t27xx)
  - [T2701 RAG 系统](#t2701-rag-系统)
  - [T2702 统一记忆库](#t2702-统一记忆库)
  - [T2703 Multi-Agent 协作](#t2703-multi-agent-协作)
  - [T2704 Prompt v2 + A/B + 评估](#t2704-prompt-v2--ab--评估)
- [三、数据仓库 + BI (T28xx)](#三-数据仓库--bi-t28xx)
  - [T2801 ClickHouse 数据仓库](#t2801-clickhouse-数据仓库)
  - [T2802 BI 报表](#t2802-bi-报表)
  - [T2803 预测分析](#t2803-预测分析)
- [四、生态开放 (T29xx)](#四-生态开放-t29xx)
  - [T2901 SSO/SAML](#t2901-ssosaml)
  - [T2902 开放 API 平台](#t2902-开放-api-平台)
  - [T2903 第三方应用市场](#t2903-第三方应用市场)
  - [T2904 API 版本化](#t2904-api-版本化)
- [五、AI 私有化 (T30xx)](#五-ai-私有化-t30xx)
  - [T3001 LoRA Fine-tuning](#t3001-lora-fine-tuning)
  - [T3002 AI 主动 Sourcing](#t3002-ai-主动-sourcing)
  - [T3003 白标 + 私有化](#t3003-白标--私有化)
- [六、整体集成时间估计](#六-整体集成时间估计)
- [七、风险总览](#七-风险总览)

---

## 一、Enterprise SaaS 系列 (T26xx)

### T2601 多租户 RLS

- **首选**: Supabase RLS + Python Context
- **GitHub URL**: https://github.com/supabase/supabase
- **Stars**: 75k+ (Supabase 主项目)
- **原因**: 项目已使用 Supabase PostgreSQL,RLS 策略现成可用,无需引入新依赖。Python 侧通过 `contextvars.ContextVar` 注入 `tenant_id`,FastAPI 中间件自动填充。
- **集成**: 0 成本,直接利用现有 Supabase 客户端
  ```sql
  -- 示例 RLS 策略
  CREATE POLICY tenant_isolation ON resumes
    USING (tenant_id = current_setting('app.tenant_id')::uuid);
  ```
  ```python
  # backend/core/tenant.py
  from contextvars import ContextVar
  tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default="")
  ```
- **使用方式**: 在每个请求进入时由 JWT 解析中间件设置 `tenant_id`,所有 SQL 自动过滤
- **备选**: python3-saml + Casbin (RBAC 补充层)
- **风险**: Supabase RLS 策略写错会全表泄露,必须配合自动化测试 + 审计

### T2602 Rate Limiting

- **首选**: slowapi
- **GitHub URL**: https://github.com/laurentS/slowapi
- **Stars**: 1.5k
- **原因**: FastAPI 官方推荐的限流库,基于 limits 库,支持 Redis/IP/Endpoint 多维度限流,装饰器用法简单
- **集成**:
  ```bash
  pip install slowapi
  ```
  ```python
  from slowapi import Limiter
  limiter = Limiter(key_func=get_remote_address, storage_uri="redis://redis:6379")
  app.state.limiter = limiter
  app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

  @app.get("/api/v1/resumes")
  @limiter.limit("100/minute")
  async def list_resumes(request: Request): ...
  ```
- **使用方式**: 替换 `backend/api/middleware.py` 接入 Redis-backed limiter
- **集成时间**: 1 天
- **备选**: fastapi-limiter (1k stars, 纯 Redis 实现,稍慢但更轻)
- **风险**: 单进程内存限流在多 worker 部署下失效,必须用 Redis backend

### T2603 审计日志 + GDPR

- **首选**: SQLAlchemy Event Hooks + 装饰器 + `audit_log_v2` 表
- **GitHub URL**: https://github.com/sqlalchemy/sqlalchemy (官方事件钩子)
- **Stars**: 10k+ (SQLAlchemy 主体)
- **原因**: 引入 django-auditlog 需拉入 Django 依赖过重;SQLAlchemy-Continuum 维护不活跃。SQLAlchemy 原生 event 系统配合装饰器最干净。
- **集成**:
  ```python
  from sqlalchemy import event

  @event.listens_for(Session, "after_flush")
  def audit_after_flush(session, flush_context):
      for obj in session.new | session.dirty | session.deleted:
          audit_log_v2.insert(
              tenant_id=tenant_id_var.get(),
              actor_id=current_user.id,
              action="INSERT|UPDATE|DELETE",
              table=obj.__tablename__,
              row_id=obj.id,
              before=before_state,
              after=after_state,
              ip=request_ip,
              timestamp=now(),
          )
  ```
- **GDPR 集成**: 单独 `gdpr_delete_requests` 表 + 异步 worker 软删/硬删
- **集成时间**: 3 天
- **备选**: SQLAlchemy-Continuum (1.5k stars, 自动版本化但维护慢)
- **风险**: 高频写表审计会影响性能,建议先写 Redis Stream 再批量入库

### T2604 SLA 监控 + 状态页

- **首选**: Instatus
- **GitHub URL**: https://github.com/instatus
- **Stars**: 自托管版本开源,UI 漂亮,模板丰富
- **原因**: 自托管版本完全开源,UI 现代化,支持多组件维护计划、订阅通知、API 集成
- **集成**:
  ```bash
  docker run -d -p 3000:3000 instatus/instatus
  ```
- **数据源**: 我们的 SLA 监控后端通过 Instatus API 自动推送事件
  ```python
  # infra/sla-monitor/sync.py
  import httpx
  httpx.post("https://status.waibao.com/api/v1/components", json=...)
  ```
- **集成时间**: 2 天
- **备选**: cstate (3k stars, 更简单但 UI 复古)
- **风险**: 自托管版需要自己跑 PostgreSQL + Redis,增加运维成本

---

## 二、AI Deep 系列 (T27xx)

### T2701 RAG 系统

- **首选**: LlamaIndex
- **GitHub URL**: https://github.com/run-llama/llama_index
- **Stars**: 40k+
- **原因**: 文档解析最强,支持 30+ 格式 (PDF/DOCX/PPT/Excel/HTML/Markdown/Notion/CSV);SimpleDirectoryReader + SentenceSplitter + 自动 metadata 抽取;QueryEngine 抽象清晰
- **集成**:
  ```bash
  pip install llama-index llama-index-vector-stores-qdrant
  ```
  ```python
  from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
  documents = SimpleDirectoryReader("./resumes").load_data()
  index = VectorStoreIndex.from_documents(documents, storage_context=qdrant_storage)
  query_engine = index.as_query_engine(similarity_top_k=5)
  ```
- **向量 DB**: Qdrant (https://github.com/qdrant/qdrant, 22k stars) - Rust 写的,性能强,支持 metadata filter 完美契合多租户 RLS
- **集成时间**: 3-5 天
- **使用方式**: 作为独立 backend 服务 `ai-rag-service`,通过 gRPC/HTTP 暴露给 v6.0 backend,不动现有 API
- **备选**: Haystack (18k stars, deepset 出品,生产级,但 Python 抽象偏复杂)
- **风险**: 40k+ stars 但 API 还在演化,锁版本 (建议 v0.10.x 起步)

### T2702 统一记忆库

- **首选**: Mem0
- **GitHub URL**: https://github.com/mem0ai/mem0
- **Stars**: 25k+
- **原因**: 专门做 AI 记忆层,生产级;支持自动 LLM-driven 记忆抽取/合并/遗忘;多 LLM 后端 (OpenAI/Anthropic/Ollama);多 Vector DB 后端 (Qdrant/Pinecone/Chroma);有 self-host 版本
- **集成**:
  ```bash
  pip install mem0ai
  docker run -d -p 8000:8000 mem0ai/mem0-api
  ```
  ```python
  from mem0 import MemoryClient
  memory = MemoryClient(api_key="...")

  # 写入
  memory.add("用户张三在 2026-06 投递了字节跳动算法工程师",
             user_id="zhangsan", metadata={"tenant_id": "tenant-001"})

  # 检索
  memories = memory.search("张三最近面试了什么公司", user_id="zhangsan", limit=5)
  ```
- **集成时间**: 2-3 天
- **使用方式**: 替换 `backend/ai/memory.py`,与 RAG 协同 (RAG 做事实检索,Mem0 做上下文记忆)
- **备选**: Letta (10k stars, 智能体长期记忆 + Reflection,但较重)
- **风险**: 自托管版需要 LLM API 配额,注意成本

### T2703 Multi-Agent 协作

- **首选**: CrewAI
- **GitHub URL**: https://github.com/joaomdmoura/crewAI
- **Stars**: 30k+
- **原因**: 角色化协作最自然 (Agent/Task/Crew/Process 抽象),招聘场景契合度高;支持 sequential/hierarchical 流程
- **集成**:
  ```bash
  pip install crewai
  ```
  ```python
  from crewai import Agent, Crew, Task

  recruiter = Agent(
      role="Senior Tech Recruiter",
      goal="匹配最合适候选人",
      backstory="10 年技术招聘经验",
      tools=[resume_search_tool, github_lookup_tool],
  )

  analyst = Agent(
      role="Resume Analyst",
      goal="评估简历技术深度",
      backstory="前 Google 工程师",
      tools=[llm_tool],
  )

  crew = Crew(agents=[recruiter, analyst], tasks=[sourcing_task, screening_task], process=Process.hierarchical)
  result = crew.kickoff(inputs={"job_description": jd_text})
  ```
- **集成时间**: 3-4 天
- **使用方式**: 新建 `backend/ai/agents/`,每个 agent 独立模块
- **备选**: LangGraph (25k stars, 状态机范式,适合复杂条件分支)
- **风险**: Multi-agent 调试困难,需配套 LangSmith 或自有 trace 系统

### T2704 Prompt v2 + A/B + 评估

- **首选**: Agenta
- **GitHub URL**: https://github.com/agenta-ai/agenta
- **Stars**: 7k+
- **原因**: 专门做 Prompt 管理 + 评估 + A/B Testing + LLM-as-judge,功能最聚焦;支持 Prompt 版本化、Web Playground、Human Feedback
- **集成**:
  ```bash
  pip install agenta
  docker run -d -p 3000:3000 agenta-ai/agenta
  ```
  ```python
  import agenta as ag

  @ag.prompt(name="resume_summarizer", variables=["resume_text"])
  def summarize(resume_text: str):
      return f"请总结以下简历:\n{resume_text}"

  # A/B 测试
  config_a = ag.ConfigManager.get_config("resume_summarizer", variant="A")
  config_b = ag.ConfigManager.get_config("resume_summarizer", variant="B")
  ```
- **集成时间**: 3-4 天
- **使用方式**: 替换 `backend/ai/prompts/` 现有手写 prompt,所有 prompt 走 Agenta Registry
- **备选**: Promptfoo (5k stars, CLI 测试工具,缺管理 UI)
- **风险**: Agenta 部署需要 PostgreSQL + Redis + S3-compatible storage

---

## 三、数据仓库 + BI (T28xx)

### T2801 ClickHouse 数据仓库

- **首选**: ClickHouse + Airbyte (Postgres CDC)
- **GitHub URL**:
  - https://github.com/ClickHouse/ClickHouse
  - https://github.com/airbytehq/airbyte
- **Stars**: 35k (ClickHouse) + 16k (Airbyte)
- **原因**: ClickHouse 列式存储 OLAP 性能顶尖 (10x Postgres);Airbyte CDC 从 Supabase Postgres 实时同步 + 200+ 现成 connector
- **集成**:
  ```bash
  # ClickHouse
  docker run -d -p 8123:8123 clickhouse/clickhouse-server

  # Airbyte
  helm install airbyte airbyte/airbyte
  # 配置 Source: Supabase Postgres (CDC)
  # 配置 Destination: ClickHouse
  ```
- **数据建模**: dbt-clickhouse (https://github.com/ClickHouse/dbt-clickhouse, 200+ stars) 做数据转换层
- **集成时间**: 4-5 天
- **使用方式**: 新建 `infra/data-warehouse/`,独立的 ClickHouse cluster
- **备选**: DuckDB (轻量,单进程,适合小规模分析)
- **风险**: ClickHouse 运维复杂,需要专人维护;数据延迟在分钟级

### T2802 BI 报表

- **首选**: Cube.js
- **GitHub URL**: https://github.com/cube-js/cube.js
- **Stars**: 18k+
- **原因**: Headless BI,可嵌入我们自己前端,无需独立 BI 平台;支持 ClickHouse / Postgres / BigQuery;有现成 React/Angular/Vue SDK
- **集成**:
  ```bash
  npm install @cubejs-client/core @cubejs-client/react
  ```
  ```yaml
  # cube/model/cubes/Resumes.js
  cube(`Resumes`, {
    sql: `SELECT * FROM resumes`,
    measures: { count: { type: `count` } },
    dimensions: { tenant_id: { sql: `tenant_id`, type: `string` } }
  })
  ```
- **集成时间**: 4-5 天
- **使用方式**: Cube Store 在 ClickHouse 之上;前端用 `@cubejs-client/react` 直接嵌
- **备选**: Metabase (40k stars, 完整 BI 平台,但需独立部署用户系统)
- **风险**: Cube.js 文档偏旧,版本升级 breaking change 多

### T2803 预测分析

- **首选**: LightGBM + Prophet
- **GitHub URL**:
  - https://github.com/microsoft/LightGBM
  - https://github.com/facebook/prophet
- **Stars**: 17k (LightGBM) + 19k (Prophet)
- **原因**: LightGBM 处理结构化数据 (候选人特征) 预测录用成功率;Prophet 处理时间序列 (招聘趋势月度预测);Hugging Face transformers 兜底 NLP 任务
- **集成**:
  ```bash
  pip install lightgbm prophet
  ```
  ```python
  import lightgbm as lgb
  train_data = lgb.Dataset(X_train, label=y_train)
  params = {"objective": "binary", "metric": "auc", "num_leaves": 31}
  model = lgb.train(params, train_data, num_boost_round=100)
  ```
- **MLOps**: MLflow (https://github.com/mlflow/mlflow, 19k stars) 做模型版本化 + 实验追踪
- **集成时间**: 2-3 天
- **使用方式**: 新建 `backend/ml/` 服务,batch 训练 + 在线 inference
- **备选**: XGBoost (类似 LightGBM,但训练慢)
- **风险**: 训练数据偏少时模型不稳,需要 A/B 框架配套

---

## 四、生态开放 (T29xx)

### T2901 SSO/SAML

- **首选**: Authlib (Python) + NextAuth.js (前端) + Keycloak (企业 IdP)
- **GitHub URL**:
  - https://github.com/lepture/authlib (5k+ stars)
  - https://github.com/nextauthjs/next-auth (30k+ stars)
  - https://github.com/keycloak/keycloak (25k+ stars)
- **原因**: Authlib Python OAuth/OIDC/SAML 客户端最完整;NextAuth.js 前端 SSO 集成最快;Keycloak 提供完整 IdP 服务供企业自建
- **集成**:
  ```bash
  pip install authlib
  npm install next-auth
  docker run -d -p 8080:8080 -e KEYCLOAK_ADMIN=admin quay.io/keycloak/keycloak
  ```
  ```python
  # backend/auth/sso.py
  from authlib.integrations.starlette_client import OAuth
  oauth = OAuth()
  oauth.register("okta", server_metadata_url="...")
  ```
- **集成时间**: 4-5 天
- **使用方式**: 用户登录路由 `/auth/sso/{provider}` 自动跳转;支持 SAML 2.0 / OIDC / OAuth 2.0
- **备选**: Authentik (12k stars, Python 写的 IdP,比 Keycloak 轻)
- **风险**: SAML metadata 配置复杂,需要测试工具 (samltool.com)

### T2902 开放 API 平台

- **首选**: FastAPI 内置 OpenAPI + Scalar UI
- **GitHub URL**: https://github.com/fastapi/fastapi + https://github.com/scalar/scalar
- **Stars**: 75k (FastAPI) + 8k (Scalar)
- **原因**: FastAPI 原生 OpenAPI 3.1 + JSON Schema;Scalar 比 Swagger UI 现代,支持 API 试调用、暗色主题
- **集成**:
  ```bash
  pip install scalar-fastapi
  ```
  ```python
  from scalar_fastapi import get_scalar_api_reference
  @app.get("/docs/scalar", include_in_schema=False)
  async def scalar_html():
      return get_scalar_api_reference(
          openapi_url=app.openapi_url,
          title="Waibao Public API",
      )
  ```
- **API 文档站**: Mintlify (https://github.com/mintlify/mintlify, 商业 SaaS) 或 Docusaurus (55k stars) 写营销级 API 文档
- **集成时间**: 2-3 天
- **使用方式**: `/docs` 替换为 Scalar UI;`/docs/external` 是 Mintlify 站
- **备选**: Redoc (24k stars, OpenAPI 渲染最强,但 UI 较静态)
- **风险**: OpenAPI schema 太复杂时 Scalar 渲染慢

### T2903 第三方应用市场

- **首选**: Strapi
- **GitHub URL**: https://github.com/strapi/strapi
- **Stars**: 65k+
- **原因**: 轻量 headless CMS,适合应用市场 (应用元数据 + 截图 + 评分);REST + GraphQL API 现成;管理后台开箱即用
- **集成**:
  ```bash
  npx create-strapi-app@latest marketplace --quickstart
  ```
  ```typescript
  // src/api/app/content-types/app/schema.json
  {
    "kind": "collectionType",
    "collectionName": "apps",
    "info": { "singularName": "app", "pluralName": "apps" },
    "options": { "draftAndPublish": true },
    "attributes": {
      "name": { "type": "string", "required": true },
      "developer": { "type": "string" },
      "description": { "type": "richtext" },
      "icon_url": { "type": "string" },
      "rating": { "type": "decimal" },
      "install_count": { "type": "integer" }
    }
  }
  ```
- **集成时间**: 4-5 天
- **使用方式**: 独立 Strapi 实例 `marketplace.waibao.com`,主应用通过 REST API 读取应用列表
- **备选**: Backstage (30k stars, Spotify 开发者门户,重,适合大企业)
- **风险**: Strapi v4 → v5 升级 breaking change 多

### T2904 API 版本化

- **首选**: FastAPI 内置 APIRouter prefix
- **GitHub URL**: https://github.com/fastapi/fastapi
- **Stars**: 75k
- **原因**: FastAPI 原生支持路由分组 + 前缀,无需引入新库
- **集成**:
  ```python
  # backend/api/v1/router.py
  v1_router = APIRouter(prefix="/api/v1")
  v1_router.include_router(resumes.router)

  v2_router = APIRouter(prefix="/api/v2")
  v2_router.include_router(resumes_v2.router)

  app.include_router(v1_router)
  app.include_router(v2_router)
  ```
- **废弃警告**: 自定义 OpenAPI extension + Response header `Deprecation` + `Sunset`
- **集成时间**: 2 天
- **使用方式**: 每个大版本独立 `backend/api/vN/`,共享 `backend/services/`
- **备选**: Starlette versioning 中间件 (侵入性强,不推荐)
- **风险**: 版本并存期间数据模型迁移复杂

---

## 五、AI 私有化 (T30xx)

### T3001 LoRA Fine-tuning

- **首选**: LLaMA-Factory
- **GitHub URL**: https://github.com/hiyouga/LLaMA-Factory
- **Stars**: 45k+
- **原因**: 一站式训练框架,统一 100+ 模型 (LLaMA/Qwen/DeepSeek/Mistral);支持 LoRA / QLoRA / Full FT;Web UI 可视化训练;支持 DeepSpeed / FSDP
- **集成**:
  ```bash
  git clone --depth 1 https://github.com/hiyouga/LLaMA-Factory
  cd LLaMA-Factory
  pip install -e ".[torch,metrics]"
  ```
  ```yaml
  # examples/train_lora/waibao_resume.yaml
  model_name_or_path: Qwen/Qwen2.5-7B-Instruct
  finetuning_type: lora
  lora_rank: 8
  dataset: waibao_resume_sft
  template: qwen
  output_dir: ./output/waibao_lora
  ```
  ```bash
  llamafactory-cli train examples/train_lora/waibao_resume.yaml
  llamafactory-cli export examples/merge_lora/waibao.yaml
  ```
- **集成时间**: 5-6 天
- **使用方式**: 独立训练服务 `infra/llm-trainer/`,训练完成后产出 LoRA adapter 部署到 vLLM
- **备选**: Axolotl (主流训练,Cloud 维护);Unsloth (2x 加速,但 LLaMA 优化最好,其他模型一般)
- **风险**: 单卡 7B 模型全参数微调需要 ≥ 80GB GPU (A100/H100);LoRA 16GB 即可

### T3002 AI 主动 Sourcing

- **首选**: GitHub REST API + 智联 / Boss直聘 / LinkedIn 官方 API
- **GitHub URL**: https://docs.github.com/en/rest
- **Stars**: N/A (官方 API)
- **原因**: GitHub API 现成,无需爬虫;智联 / Boss直聘 / LinkedIn 都有官方招聘 API (需企业认证)
- **集成**:
  ```python
  # backend/sourcing/github.py
  from github import Github
  g = Github(os.getenv("GITHUB_TOKEN"))

  def search_candidates(skills: list[str], location: str = "China"):
      query = f"location:{location} " + " ".join(f"language:{s}" for s in skills)
      return g.search_users(query, sort="followers", order="desc")
  ```
- **数据清洗**: 各平台 schema 标准化 → 推送到 ClickHouse `candidates_raw` 表
- **去重**: SimHash + LSH 在 ClickHouse 上做快速近似去重
- **集成时间**: 4-5 天
- **使用方式**: 新建 `backend/sourcing/` 服务,cron 定时抓取 + 实时 webhook
- **备选**: apify (https://github.com/apify/apify-sdk-python, 1k stars) 提供现成爬虫 actor
- **风险**: LinkedIn API 申请门槛极高;Boss直聘 API 不对外开放,需商务合作

### T3003 白标 + 私有化

- **首选**: CSS Variables 主题系统 + Helm Chart
- **GitHub URL**: https://github.com/twbs/bootstrap (CSS variable 范式)
- **Stars**: 170k (Bootstrap 参考实现)
- **原因**: CSS Variables 浏览器原生支持,主题切换零运行时;Helm Chart 已是 Kubernetes 部署事实标准
- **集成**:
  ```css
  /* frontend/styles/theme.css */
  :root {
    --brand-primary: #1890ff;
    --brand-secondary: #52c41a;
    --brand-bg: #ffffff;
    --brand-text: #262626;
  }
  [data-theme="dark"] {
    --brand-primary: #177ddc;
    --brand-bg: #141414;
  }
  ```
  ```yaml
  # deploy/helm/waibao/values.yaml
  brand:
    name: "CustomerCo"
    primaryColor: "#FF6B35"
    logo: "https://cdn.customco.com/logo.svg"
  tenant:
    subdomain: "customerco"
    database: "customerco_db"
  ```
- **Helm chart 结构**:
  ```
  deploy/helm/waibao/
  ├── Chart.yaml
  ├── values.yaml
  ├── templates/
  │   ├── frontend-deployment.yaml
  │   ├── backend-deployment.yaml
  │   ├── postgres-statefulset.yaml
  │   ├── ingress.yaml
  │   └── configmap.yaml
  ```
- **集成时间**: 3-4 天
- **使用方式**: 部署时通过 `helm install --set brand.name="X"` 一行命令换肤换名
- **备选**: shadcn/ui Themes (前端组件级 theme provider)
- **风险**: 邮件/短信模板需要支持 Liquid 模板替换品牌字段

---

## 六、整体集成时间估计

| 系列 | 任务数 | 总人天 | 关键里程碑 |
|------|--------|--------|----------|
| T26xx Enterprise SaaS | 4 | 6 天 | T2603 审计 3 天是大头 |
| T27xx AI Deep | 4 | 12-16 天 | T2701 RAG 5 天 + T2703 Agent 4 天 |
| T28xx 数据仓库 | 3 | 10-13 天 | T2801 ClickHouse + Airbyte 5 天 |
| T29xx 生态开放 | 4 | 12-15 天 | T2903 Strapi 5 天 + T2901 SSO 5 天 |
| T30xx AI 私有化 | 3 | 12-15 天 | T3001 LLaMA-Factory 6 天是大头 |
| **总计** | **18** | **52-65 人天** | **约 13-16 周 (3 人团队)** |

### 推荐实施顺序

1. **第一波 (基础设施)**: T2601 (0 天) + T2602 (1 天) + T2904 (2 天)
2. **第二波 (AI 核心)**: T2701 RAG (5 天) + T2702 Mem0 (3 天) + T2703 CrewAI (4 天)
3. **第三波 (数据)**: T2801 ClickHouse (5 天) + T2802 Cube.js (5 天) + T2803 ML (3 天)
4. **第四波 (合规 + 监控)**: T2603 审计 (3 天) + T2604 SLA (2 天)
5. **第五波 (开放生态)**: T2901 SSO (5 天) + T2902 API 平台 (3 天) + T2903 Marketplace (5 天)
6. **第六波 (AI 私有化)**: T3001 LoRA (6 天) + T3002 Sourcing (5 天) + T3003 白标 (4 天)
7. **收尾**: T2704 Prompt A/B (4 天)

---

## 七、风险总览

| 风险类别 | 影响任务 | 缓解措施 |
|---------|---------|---------|
| **Supabase RLS 配置错误** | T2601 | 自动化 RLS 测试 + 季度审计 |
| **限流在多 worker 下失效** | T2602 | 必须 Redis backend + 压测验证 |
| **审计日志写入性能** | T2603 | Redis Stream 异步落库 |
| **LLM API 成本** | T2701/2/3/4 | 缓存 + 小模型 + 量化 |
| **Mem0 维护活跃度** | T2702 | 锁版本 + 自托管备份方案 |
| **Multi-agent 调试** | T2703 | 自建 trace + LangSmith 配套 |
| **ClickHouse 运维** | T2801 | 托管服务 (ClickHouse Cloud) |
| **Strapi 版本升级** | T2903 | 锁 v4 LTS,关注 v5 进度 |
| **LinkedIn/Boss API 不可用** | T3002 | 多平台 fallback + 商务合作 |
| **GPU 资源** | T3001 | QLoRA 16GB 卡即可,弹性云 GPU |
| **私有化部署差异** | T3003 | Helm chart 全参数化 + 烟雾测试套件 |

---

## 附录:版本锁定建议

| 项目 | 推荐版本 | 锁定理由 |
|------|---------|---------|
| LlamaIndex | v0.10.x → v0.12.x | API 演化中,锁定 minor |
| Mem0 | v0.1.x | 自托管版本号统一 |
| CrewAI | v0.80+ | API 稳定 |
| Agenta | v0.30+ | 自部署版要求 |
| ClickHouse | 24.x LTS | 生产稳定 |
| Cube.js | v0.34+ | React 18 支持 |
| LLaMA-Factory | main branch | 训练框架跟最新版 |
| Strapi | v4 LTS | v5 升级窗口期观望 |
| Authlib | v1.3+ | Python 3.10+ 支持 |
| Keycloak | v24+ | Quarkus 基础 |

---

**维护说明**: 本文档在每次技术选型变更时同步更新,新引入的开源项目必须填写本表。