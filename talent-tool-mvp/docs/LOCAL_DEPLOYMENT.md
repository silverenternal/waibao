# 本地一键部署指南 (LOCAL_DEPLOYMENT)

> v11.0 / T6111 — 面向甲方验收环境的**一键全离线**本地部署。
> 所有简历 / 资质 / 对话数据**不出甲方环境**:大模型走本地 Ollama,OCR 走本地 PaddleOCR,无任何外部 LLM / OCR API。

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
