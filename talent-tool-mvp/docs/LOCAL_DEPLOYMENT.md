# 本地一键部署指南 (LOCAL_DEPLOYMENT)

> v11.2 / T6307 — 面向甲方验收环境的**一键全离线**本地部署。
> 所有简历 / 资质 / 对话数据**不出甲方环境**:大模型走本地 Ollama,OCR 走本地 PaddleOCR,无任何外部 LLM / OCR API。
>
> **v11.2 新增**:身份验证流程(三证件上传 + AI 提取)、匹配阀值门(`MATCH_THRESHOLD` env)、新增 DB 迁移 `064_identity_compensation.sql`。详见下方 [§10 v11.2 变更](#10-v112-新增变更)。

---

## 1. 环境要求

| 项目 | 最低 | 推荐 | 说明 |
| --- | --- | --- | --- |
| 操作系统 | Linux / macOS / Windows(WSL2) | Linux | Windows 请用 WSL2 + Docker Desktop |
| Docker | 24.0 | 最新稳定版 | 含 `docker compose` v2 插件 |
| Docker Compose | v2.20+ | 最新 | `docker compose version` 能正常输出 |
| 内存 | **16 GB** | 32 GB | Ollama 7B 模型 + PaddleOCR + Postgres + 前端 |
| 磁盘 | **50 GB** 可用 | 100 GB | 镜像 + Ollama 模型(~5GB)+ PaddleOCR 模型 + 业务数据 |
| CPU | 4 核 | 8 核+ | CPU 推理较慢,有 NVIDIA GPU 显著加速 |
| GPU(可选) | — | NVIDIA 8GB+ 显存 | Ollama / PaddleOCR GPU 加速,无则走 CPU |
| 端口 | 3000 / 5432 / 6379 / 8000 / 8500 / 11434 空闲 | 同左 | 见下表 |

### 服务端口

| 服务 | 端口 | 用途 |
| --- | --- | --- |
| frontend | `3000` | 求职者 / HR / 老板 / 部门负责人 四端 UI |
| backend | `8000` | FastAPI 业务 API + Swagger 文档 (`/docs`) |
| postgres | `5432` | 业务数据库 |
| redis | `6379` | 缓存 / 限流 / EventBus |
| ollama | `11434` | 本地大模型推理(OpenAI 兼容 `/v1`) |
| paddleocr | `8500` | 本地 OCR 推理(`/health`) |

> Docker / 内存 / 磁盘不达标的处理:见 [常见问题](#5-常见问题)。

---

## 2. 启动(3 步)

> 全程在仓库根目录 `talent-tool-mvp/` 下执行。

**第 1 步 —— 准备配置(可选)**

```bash
cp .env.local.example .env.local
# 默认值已可用;如需改数据库密码 / 模型,编辑 .env.local
```

**第 2 步 —— 一键启动**

```bash
bash scripts/start_local.sh
```

脚本自动完成:
1. 检查 Docker / docker compose 是否就绪;
2. `docker compose -f docker-compose.local.yml up -d --build` 起 6 个服务(backend + frontend + postgres + redis + ollama + paddleocr);
3. 等待 postgres / redis / ollama 健康;
4. 自动拉取默认大模型 `qwen2.5:7b-instruct`(调用 `scripts/setup_ollama.sh`);
5. 预下载 PaddleOCR 中英文模型(调用 `scripts/setup_paddleocr.sh`);
6. 探测 backend / frontend,就绪后打印访问地址。

**第 3 步 —— 验证**

浏览器打开 **http://localhost:3000** 即可看到前端首页(求职者 / 企业入口)。
后端 Swagger 文档:http://localhost:8000/docs

---

## 3. 停止

```bash
# 停止全部服务,保留数据卷(模型 / 业务数据下次直接复用)
bash scripts/stop_local.sh

# 停止并清空全部数据卷(模型 / 业务数据全部删除,下次重新拉取)
bash scripts/stop_local.sh --purge
```

手动操作(等价):

```bash
docker compose -f docker-compose.local.yml down            # 停 + 删容器,留卷
docker compose -f docker-compose.local.yml down -v         # 停 + 删容器 + 删卷
```

---

## 4. 验证清单

启动后逐项确认:

- [ ] `docker compose -f docker-compose.local.yml ps` 6 个服务均为 `Up (healthy)`;
- [ ] 浏览器访问 http://localhost:3000 能打开前端;
- [ ] `curl http://localhost:8000/api/health` 返回 JSON 健康;
- [ ] `curl http://localhost:8000/docs` 能打开 Swagger;
- [ ] `curl http://localhost:11434/v1/models` 能列出已拉取的 Ollama 模型;
- [ ] `curl http://localhost:8500/health` PaddleOCR 健康(若该镜像暴露 health 路由);
- [ ] 前端注册一个求职者账号,上传简历,触发 OCR + AI 画像(数据全程本地)。

---

## 5. 常见问题

### 5.1 端口冲突(`bind: address already in use`)

某个端口被本机其他进程占用。两种处理:

```bash
# A. 释放占用端口(以 3000 为例)
lsof -i :3000            # macOS/Linux 找到占用进程 PID
kill <PID>

# B. 改映射端口:编辑 docker-compose.local.yml,把 "3000:3000" 改成 "3001:3000"
#    同步把 .env.local 的 NEXT_PUBLIC_API_URL / CORS_ORIGINS 改成新端口后重启。
```

### 5.2 Ollama 模型拉取慢 / 卡住

模型从公网拉取(首次约 4–5 GB)。在甲方内网受限时:

```bash
# 1. 在有网的机器上拉好模型,再离线拷贝 ollama_data 卷
docker run --rm -v ollama_data:/root/.ollama ollama/ollama ollama pull qwen2.5:7b-instruct
# 2. 把卷内容打包拷进甲方环境,放到同名 volume。

# 或换更小的模型
OLLAMA_MODEL=qwen2.5:3b-instruct bash scripts/start_local.sh
```

### 5.3 Ollama 启动 / 健康检查超时

`start_local.sh` 等待 ollama healthy 最多 180s。若超时:

```bash
docker logs waibao-ollama            # 看报错
# 常见:内存不足 → 加内存或换更小模型;GPU 驱动问题 → 注释 GPU 段走 CPU。
docker compose -f docker-compose.local.yml restart ollama
```

### 5.4 PaddleOCR 首次识别慢

首次调用会下载 det / rec / cls 权重(约几百 MB)。`start_local.sh` 已调用 `setup_paddleocr.sh` 预下载;若跳过,首次识别会有延迟,属正常现象,之后走缓存。

### 5.5 内存不足(OOM)

7B 模型 CPU 推理峰值 ~8GB。16GB 机器请:
- 关闭其他占内存程序;
- 换 `qwen2.5:3b-instruct`(约 2GB);
- 或启用 GPU(编辑 compose 取消 GPU 段注释)。

### 5.6 前端构建失败(`next build`)

通常是 Node 内存或依赖问题:

```bash
docker compose -f docker-compose.local.yml build --no-cache frontend
docker compose -f docker-compose.local.yml up -d frontend
```

### 5.7 数据库迁移未生效

compose 启动时通过 `docker-entrypoint-initdb.d` 自动执行 `supabase/migrations/*.sql`,**仅在首次初始化(postgres_data 卷为空)时执行**。改了迁移要重跑:

```bash
bash scripts/stop_local.sh --purge   # 清卷
bash scripts/start_local.sh          # 重新初始化
```

> **v11.2 新增迁移**:`supabase/migrations/064_identity_compensation.sql`(身份验证四状态列 + `profile_versions` + `communication_channels` 表 + RLS + rollup trigger)。若从旧版升级且未 purge 卷,063 不会自动执行 —— 需按上面命令 `--purge` 重跑,或手动在 psql 里执行该 SQL。

### 5.8 查看 / 跟踪日志

```bash
docker compose -f docker-compose.local.yml logs -f           # 全部
docker compose -f docker-compose.local.yml logs -f backend   # 单服务
```

---

## 6. GPU 加速(可选)

有 NVIDIA GPU 时,编辑 `docker-compose.local.yml`,取消 `ollama` 服务的 `deploy.resources` 段注释,并安装 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/),然后:

```bash
docker compose -f docker-compose.local.yml up -d ollama
```

PaddleOCR 启用 GPU:把 `PADDLE_OCR_USE_GPU` 改为 `true`(需 GPU 版 paddlepaddle 镜像)。

---

## 7. 导入测试数据

启动后可一键导入演示数据(1000 求职者 / 10 企业 / 5 岗位 + 匹配结果):

```bash
python scripts/seed_test_data.py
```

详见 [测试数据说明](../scripts/seed_resumes/README.md)。

---

## 8. 数据安全说明

- **大模型**:LLM_PROVIDER=ollama,推理在 `waibao-ollama` 容器内完成,简历 / 对话**不发送到任何外部 API**。
- **OCR**:OCR_PROVIDER=paddle,PaddleOCR 在 `waibao-paddleocr` 容器内识别简历 / 资质,**不上传第三方 OCR**。
- **数据卷**:`postgres_data` / `redis_data` / `ollama_data` / `paddleocr_models` 全部持久化在宿主本地,`stop_local.sh`(不带 `--purge`)不删数据。
- 离线卸载:`bash scripts/stop_local.sh --purge` 即可彻底清除。

---

## 9. 本地验证结果 (v11.1 / T6202 + T6203)

以下检查已在 CI/本地验证机全量通过,部署前可直接复用:

### 9.1 docker-compose 配置 (T6202)

| 检查项 | 命令 | 结果 |
| --- | --- | --- |
| YAML 语法 | `docker compose -f docker-compose.local.yml config` | 通过 (exit 0) |
| 服务齐全 | `docker compose -f docker-compose.local.yml config --services` | 6/6: backend / frontend / postgres / redis / ollama / paddleocr |
| 启动脚本语法 | `bash -n scripts/start_local.sh` | 通过 |
| Ollama 拉模型脚本 | `bash -n scripts/setup_ollama.sh` | 通过 |
| 停止脚本语法 | `bash -n scripts/stop_local.sh` | 通过 |
| PaddleOCR 模型脚本 | `bash -n scripts/setup_paddleocr.sh` | 通过 |
| 配置模板 | `.env.local.example` | 完整 (DB / Redis / CORS / LLM / OCR / mock fallback) |
| Provider 路由 | `backend/providers/registry.py` | `LLM_PROVIDER` 默认 `ollama` → `OllamaProvider`;显式 `mock` 才走本地 fallback |
| base_url 规范化 | `backend/providers/llm/ollama_provider.py` | `_normalize_base_url` 自动补 `/v1` (容器内 `http://ollama:11434` → `/v1`) |
| 构建产物 | `backend/Dockerfile` / `backend/Dockerfile.paddleocr` / `frontend/Dockerfile` | 3 个 Dockerfile 全部存在 |

> `start_local.sh` 6 步流程完整:检查 Docker → `up -d --build` → 等 postgres/redis/ollama healthy → 拉默认模型 `qwen2.5:7b-instruct` → 预下载 PaddleOCR 中英文模型 → 探测 backend/frontend 并打印 URL。

### 9.2 测试数据 Seed + 前端编译 (T6203)

```bash
# 1) 语法验证
python -c "import ast; ast.parse(open('scripts/seed_test_data.py').read())"   # OK

# 2) 实际运行 (本地 JSONL, 无 Supabase 依赖)
python scripts/seed_test_data.py
# → seed_output/ 下生成 9 个 JSONL + seed_summary.json
```

Seed 输出 (`seed_output/`, 全部 JSONL 行通过 `json.loads` 校验):

| 文件 | 行数 |
| --- | --- |
| candidates.jsonl | 1000 |
| funnel_events.jsonl | 32340 |
| channel_spend.jsonl | 140 |
| partner_recommendations.jsonl | 100 |
| job_subscriptions.jsonl | 50 |
| matches.jsonl | 75 |
| organisations.jsonl | 10 |
| roles.jsonl | 5 |
| partner_hrs.jsonl | 1 |

> `candidates` 含 17 字段 (id / first_name / last_name / email / phone / skills / education / experience_years / salary_expectation / seniority / location / availability / cv_text / profile_text / industries / created_by / _meta)。
> `matches` 含完整评分 (structured_score / semantic_score / experience_score / overall_score / skill_overlap) + strengths / gaps / explanation。
> Faker 未安装时自动降级为内置随机生成器 (离线可跑),`faker: false`。

### 9.3 前端编译 (T6203)

```bash
cd frontend && npx next build
```

- `✓ Compiled successfully in 6.8s`
- `✓ Generating static pages (151/151)`
- **招聘市场 (marketplace) 页面全部编译通过**:
  `/marketplace` / `/marketplace/jobs` / `/marketplace/jobs/[id]` / `/marketplace/talents` / `/marketplace/talents/[id]` / `/marketplace/recommendations` / `/marketplace/recruitment` / `/marketplace/compare` / `/admin/marketplace` / `/jobseeker/plan/market-insights`
- exit 0,无编译错误。

---

## 10. v11.2 新增变更 (T6301–T6307)

> v11.2 引入身份验证流程、匹配阀值门、五险一金/出差软匹配维度与画像版本化。详见 `docs/CONTRACT-REVIEW-v12.md` 与 `docs/ACCEPTANCE_CHECKLIST.md` 第八节。

### 10.1 匹配阀值环境变量 `MATCH_THRESHOLD`

双方仅当任一匹配分 ≥ 阀值时才互相可见、可沟通(低于阀值双向不可见)。阀值是**可见性门,非淘汰**(甲方口径:不淘汰、只排序)。

- **默认值**:`70`(百分比)。来源:`backend/matching/threshold.py` → `MATCH_THRESHOLD = int(os.environ.get("MATCH_THRESHOLD", "70"))`。
- **环境变量覆盖**:设置 backend 服务的 `MATCH_THRESHOLD=<int>` 即可。在 `.env.local` 或 `docker-compose.local.yml` 的 backend `environment` 段加:
  ```bash
  MATCH_THRESHOLD=60   # 例:放宽阀值到 60%
  ```
  改后重启 backend(`bash scripts/stop_local.sh && bash scripts/start_local.sh`)生效。
- **门控位置**:`is_above_threshold(score)` 用 `>=`(等于即过线);`GET /api/talent-market/talents` 与 `/jobs` 列表 viewer-aware 过滤;`/talents/{id}`、`/jobs/{id}` 详情未过线 → 404;`POST /api/talent-market/initiate-contact` 与 `/api/recommendations/initiate-contact` 未过线 → **403**。

### 10.2 新增数据库迁移 `064_identity_compensation.sql`

迁移脚本:`supabase/migrations/064_identity_compensation.sql`(经 `docker-entrypoint-initdb.d` 仅在**首次初始化(postgres_data 卷为空)**时执行 —— 见 [§5.7](#57-数据库迁移未生效))。

新增 / 变更:

- **candidates 表**:+ `identity_status` / `id_card_status` / `education_doc_status` / `resume_status`(各 pending|submitted|verified)+ `identity_verified_at` + `social_insurance_expectation`(bool)+ `travel_tolerance`(willing|occasional|unwilling)。
- **roles 表**:+ `offers_social_insurance`(默认 true)+ `offers_housing_fund` + `travel_required`(none|occasional|frequent)。
- **新表 `communication_channels`**:1:1 候选人×岗位沟通线程(`UNIQUE(candidate_id, role_id)`,`initiated_by`,`match_score` 快照,`status`)。RLS:候选人本人 OR 所属 org 可见。
- **新表 `profile_versions`**:append-only 画像快照(`candidate_id + version_no` 升序,`snapshot JSONB`)。RLS:仅候选人本人可见;雇主侧经 `recommendations.resume_snapshot`(061)读推送时刻锁定版本。
- **rollup trigger**:`enforce_candidate_identity_rollup` 保证 `identity_status=verified` 仅当三证件均 verified。

> 从 v11.1(及更早)升级且未 purge 卷时,063 **不会**自动执行。请在 psql 里手动执行该 SQL,或 `bash scripts/stop_local.sh --purge && bash scripts/start_local.sh` 重跑(会清空业务数据)。

### 10.3 身份验证流程 (Identity Flow)

求职者 → 求职者空间 → **身份验证** 页(`/jobseeker/identity`):

1. 上传三类证件:**身份证** / **学历** / **简历**(逐项上传);
2. 后端 `POST /api/identity/upload`(doc_type=id_card|education|resume)→ AI 提取(`services/identity/verification.py` 走 `resume_parser.extract_text_from_url` + 字段抽取);
3. 每个证件状态在「**待上传**(pending) → **待审核**(submitted) → **已认证**(verified)」间流转;前端 `IdentityStatusBadge` 按 `IDENTITY_DISPLAY_MAP` 渲染中文标签;
4. 三证件全部 verified → 汇总 `identity_status` 自动翻为「**已认证**」(DB trigger 强约束);
5. 画像版本化:`GET|PUT /api/identity/profile`(PUT 写新版本)+ `GET /api/identity/profile/versions[/{n}]`(回看历史快照)。

> OCR / 文本提取仍走本地(PaddleOCR / 本地 resume_parser),证件数据**不出甲方环境**(同 AC-02 数据安全前提)。

### 10.4 前端编译(v11.2 实测)

```bash
cd frontend && npx tsc --noEmit   # exit 0,0 类型错误
cd frontend && npx next build     # ✓ Generating static pages (152/152)
```

- v11.2 较 v11.1 新增 1 个静态页:`/jobseeker/identity`(身份验证),总页数 151 → **152**。
- 1 个构建警告为既有的可选 `livekit-client` 依赖 `@ts-expect-error`(非本版引入,非错误)。
