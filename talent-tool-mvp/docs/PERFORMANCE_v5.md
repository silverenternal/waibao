# PERFORMANCE_v5.md — v5.0 真实业务压测报告 (T1703)

> Owner: waibao 实施工程师 / SRE
> Status: 🟡 压测脚本就绪 (locustfile.py v5 + scripts/run_real_loadtest.sh + 12 persona)
> 测试目标: **P95 < 2s / 错误率 < 0.5% / 1000 HTTP 并发 / 5000 WebSocket 并发 / P95 消息延迟 < 200ms**

---

## 1. 测试方法

### 1.1 压测对象
- **后端服务**: FastAPI + Uvicorn (Gunicorn 多 worker, 默认 4 × 2 CPU)
- **依赖**: Supabase PostgreSQL + pgvector / Redis 7 / OpenTelemetry / Prometheus
- **真实业务路径**: 走 12 个 persona 覆盖 6 大业务域 (求职 / 用人 / 匹配 / 订阅 / 协同 / 测评)
- **测试数据**: mock JWT + Faker, 不污染真实库

### 1.2 工具
| 工具 | 版本 | 用途 |
| --- | --- | --- |
| Locust | 2.x | HTTP 压测主控 |
| Locust plugins | ≥ 0.1.0 | WebSocket 用户支持 |
| websockets | ≥ 12 | asyncio 5000+ WS 并发 |
| Faker | ≥ 24 | 假数据生成 |
| Prometheus + Grafana | 实时 | 切片对照 (persona × region × endpoint) |

安装:
```bash
pip install locust locust-plugins faker websockets redis
```

### 1.3 12 个 Persona (v5.0 升级)

| Persona | weight | 主路径 API | 业务价值 |
| --- | --- | --- | --- |
| **JobseekerUser** | 8 | realtime/invoke, uploads/resume, journal, emotion, clarifier, offer/compare, career-plan | 求职者主链路 |
| **EmployerUser** | 10 | organisations, roles, vision, talent-brief, job-spec, tickets CRUD, clarifications, collections, subscriptions | 用人方主链路 |
| **MatchingUser** | 4 | two-way-match compute/explain/batch/feedback | 核心匹配业务 |
| **SubscriptionUser** | 3 | subscriptions CRUD + match (主动推送) | 主动推送链路 |
| **CollabRoomUser** | 3 | rooms + messages (模拟 WS 业务量) | 协同房间 |
| **VideoInterviewUser** | 2 | video-interviews CRUD | 视频面试 |
| **AssessmentUser** | 2 | assessments/invite, background-check | 测评 + 背调 |
| **AnalyticsUser** | 2 | analytics/funnel-events + funnel + channel-attribution | 漏斗埋点 |
| **PartnerUser** | 1 | pilot dashboard / nps / feedback | 合作方视角 |
| **AdminUser** | 1 | emotion/alerts, admin/audit, cost, matching-quality | 管理后台 |
| **AnonymousHealthUser** | 1 | /health, /metrics, /ready | 探针 |
| **AIInterviewUser** | 1 | ai-interview/sessions + answer | AI 面试 |

合计 12 类 / **45+ task** / 覆盖所有 v5.0 真实业务 API。

---

## 2. 执行方式

### 2.1 一键脚本 (推荐)

```bash
cd /home/hugo/codes/waibao/talent-tool-mvp

# 默认: HTTP 1000 + WS 5000
bash scripts/run_real_loadtest.sh

# 仅 HTTP 1000 / 10 分钟
bash scripts/run_real_loadtest.sh http

# 仅 WebSocket 5000 / 60 秒
bash scripts/run_real_loadtest.sh ws

# 100 并发烟囱
bash scripts/run_real_loadtest.sh smoke

# 100 → 500 → 1000 三档完整
bash scripts/run_real_loadtest.sh full

# 阶梯爬升 (100 → 1000)
bash scripts/run_real_loadtest.sh ramp 100 1000
```

环境变量:
```bash
HOST=http://localhost:8000 \
LOAD_USERS=1000 SPAWN_RATE=50 RUN_TIME=10m \
bash scripts/run_real_loadtest.sh http
```

### 2.2 直接 Locust (高级)

```bash
cd backend
LOAD_USERS=1000 SPAWN_RATE=50 RUN_TIME=10m \
locust -f tests/load/locustfile.py \
    --host http://localhost:8000 \
    --users 1000 --spawn-rate 50 --run-time 10m \
    --headless --html reports/locust_v5_1000.html \
    --csv reports/locust_v5_1000
```

### 2.3 WebSocket 高并发 (asyncio 模式)

```bash
cd backend
CONCURRENCY=5000 DURATION_SEC=60 PUBLISH_INTERVAL_MS=200 \
WS_URL_TEMPLATE='ws://localhost:8000/api/realtime/ws/rooms/{room_id}?token=mock-jwt-ws' \
python -m tests.load.ws_concurrent
```

### 2.4 Redis Pub/Sub 瓶颈

```bash
cd backend
REDIS_URL=redis://localhost:6379/0 \
CHANNELS=16 SUBSCRIBERS=500 MSGS_PER_PUB=1000 \
python -m tests.load.redis_pubsub_test
```

---

## 3. 结果模板 (执行后回填)

### 3.1 HTTP — 100 / 500 / 1000 三档汇总

| 并发 | 持续 | 总请求 | RPS | p50 (ms) | p95 (ms) | p99 (ms) | 错误率 | SLA P95<2s | SLA 错<0.5% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 100  | 2m  | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| 500  | 5m  | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| 1000 | 10m | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

> 回填脚本: `cat reports/locust_*_summary.txt`

### 3.2 HTTP — 单接口 TOP 15 (按 P95 倒序, 1000 并发档)

| Endpoint | p50 | p95 | p99 | 错误率 | 调用次数 |
| --- | --- | --- | --- | --- | --- |
| /api/two-way-match/explain        | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| /api/ai-interview/sessions        | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| /api/realtime/invoke              | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| /api/two-way-match/compute        | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| /api/vision/submit                | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| /api/talent-brief                 | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| /api/job-spec                     | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| /api/uploads/resume               | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| /api/emotion/analyze              | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| /api/rooms/messages               | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| /api/tickets                      | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| /api/clarifications               | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| /api/two-way-match/batch          | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| /api/journal                      | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| /api/subscriptions/match          | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

### 3.3 WebSocket — 5000 并发连接

| 指标 | 目标 | 实测 | 是否达标 |
| --- | --- | --- | --- |
| 连接成功率 | ≥ 99% | _TBD_ | _TBD_ |
| 连接延迟 p95 | < 500 ms | _TBD_ | _TBD_ |
| Ack 消息延迟 p50 | < 50 ms | _TBD_ | _TBD_ |
| Ack 消息延迟 p95 | < 200 ms | _TBD_ | _TBD_ |
| Ack 消息延迟 p99 | < 500 ms | _TBD_ | _TBD_ |
| 总吞吐 (msg/s) | ≥ 5000 | _TBD_ | _TBD_ |
| 错误率 | < 0.5% | _TBD_ | _TBD_ |

### 3.4 Redis Pub/Sub 瓶颈

| 指标 | 实测 | 结论 |
| --- | --- | --- |
| Publish 吞吐 (msg/s) | _TBD_ | 16 channel 并发 publish |
| Publish p95 延迟 | _TBD_ | |
| 端到端 p95 延迟 | _TBD_ | < 200ms 视为通过 |
| 投递成功率 | _TBD_ | > 99% 视为通过 |
| 瓶颈点 | _TBD_ | fd 上限? CPU? 网络? |

### 3.5 Persona 切片 (Grafana 查询 PromQL)

```promql
# 按 persona 切 P95
histogram_quantile(0.95, sum by (le, persona) (
  rate(http_request_duration_seconds_bucket[5m])
))

# 按 persona 切 RPS
sum by (persona) (rate(http_requests_total[1m]))

# 按 region 切错误率
sum by (region) (rate(http_requests_total{status=~"5.."}[5m]))
  / sum by (region) (rate(http_requests_total[5m]))
```

---

## 4. 优化建议清单 (按 ROI 排序)

### 4.1 P0 — 立即生效

| 优化项 | 适用 | 预期 | 成本 |
| --- | --- | --- | --- |
| **Redis 缓存热点读** (候选人 / 角色 / 组织) | `GET /api/candidates/{id}`, `GET /api/roles/{id}`, `GET /api/organisations/{id}` | 读接口 p95 -60~80%, DB 负载 -70% | 2-3 天 |
| **LLM 响应缓存** (prompt hash → response) | `/api/realtime/invoke`, `/api/vision/submit`, `/api/job-spec`, `/api/two-way-match/explain` | 重复 prompt 跳过 LLM, RPS ×2, 成本 -50% | 1 天 (复用 `services/observability/llm_cache.py`) |
| **DB 索引补齐** | `roles(organisation_id, status)`, `matches(candidate_id, score DESC)`, `journal(user_id, created_at DESC)`, `tickets(role_id, status)`, `subscriptions(user_id, kind)` | SQL p95 -50%+ | 1 天 |
| **Nginx `worker_processes auto`** + `worker_rlimit_nofile 65535` | 所有 HTTPS 入口 | 文件句柄 +30% | 0.5 天 |
| **压测纳入 CI** (nightly + 阈值门禁) | CI pipeline | regression 立刻发现 | 1 天 |

### 4.2 P1 — 中期 (1-2 周)

| 优化项 | 预期 | 成本 |
| --- | --- | --- |
| **pgbouncer transaction pooling** | DB 连接 -90%, QPS +30% | 2 天 |
| **Celery + Redis 异步队列** (upload OCR / matching compute / notify push) | 接口 p95 < 300ms, 长任务后台 | 5 天 |
| **读副本路由** (Supabase 自动, `SUPABASE_READ_URL`) | 读 QPS ×2 | 1 天 |
| **响应分页 + 限制** (统一 limit ≤ 100) | 大列表响应 500ms → 80ms | 0.5 天 |
| **Embedding 批量 + 缓存** (text_hash key) | 每次匹配省 100ms LLM | 1 天 |

### 4.3 P2 — 架构级 (1 个月+)

| 优化项 | 预期 | 成本 |
| --- | --- | --- |
| **WebSocket 多实例 + Redis pub/sub** (`realtime_router.py`) | WS 容量 50k+ 连接 | 3 天 |
| **Gunicorn `uvicorn.workers.UvicornWorker`** × `2 * CPU` | QPS +100% | 0.5 天 |
| **K8s HPA + prometheus-adapter** (CPU + 自定义 QPS) | 自动扩缩容 | 3 天 |
| **CDN** (Cloudflare / 阿里云) | 出口带宽 -80% | 1 天 |
| **PG 物化视图** (matches) | 复杂 JOIN 1s → 50ms | 2 天 |
| **OpenTelemetry tail sampler** | CPU -20%, 存储 -90% | 1 天 |

### 4.4 P3 — 长期治理

- 容量规划模型 (基于 RPS × p95 反推资源)
- 数据库分区 (journal / audit 按月)
- Cold path 限流 (matching compute 走 token bucket)
- 多区域部署 (海外就近接入, 延迟 -50%)
- LLM 路由按模型分流 (cheap model 走 70% 流量)

---

## 5. SLA & 告警阈值

| 指标 | 告警阈值 | 严重度 | 行动 |
| --- | --- | --- | --- |
| **P95 延迟 (HTTP)** | > 1.5s 持续 5 min | P1 | 查 Redis 命中率 + DB 慢查询 |
| **P99 延迟 (HTTP)** | > 3s 持续 5 min | P1 | 升级 P0 + oncall |
| **错误率** | > 1% 持续 2 min | P0 | 查最近部署 / 依赖状态 |
| **错误率 (5xx)** | > 0.5% 持续 5 min | P1 | 检查上游 |
| **WebSocket 连接数** | > 4000 | P2 | 检查 Redis pub/sub 容量 |
| **WS 消息延迟 P95** | > 200ms 持续 5 min | P1 | 扩 WS 实例 |
| **Redis 内存** | > 70% | P2 | 评估 eviction + 扩容 |
| **Postgres 连接数** | > 80% max | P1 | 加 pgbouncer / pool_size |
| **CPU 平均** | > 70% 持续 10 min | P2 | HPA 扩容 |
| **LLM 成本** | > 预算 80% | P1 | 切到便宜模型 |
| **LLM 错误率** | > 5% 持续 5 min | P0 | fallback / 切 provider |

> 详细告警规则: `infra/prometheus/alerts.yml` (30+ 规则, 4 个严重度)
> 告警通道: docs/ALERTING.md (钉钉 / 飞书 / PagerDuty / Webhook)

---

## 6. 复测节奏

| 触发 | 频率 | Owner |
| --- | --- | --- |
| 大版本发布 (v5.x / v6.x) | 必跑 | 实施工程师 |
| 数据库 schema migration | 必跑 | 数据工程师 |
| Redis / PG 配置变更 | 必跑 | SRE |
| 每周一 02:00 | 自动 | CI |
| 每月 | 完整 100/500/1000 + WS | SRE |
| Pilot 接入前 | 必跑 | SRE |

---

## 7. 与 v4.0 对比

| 维度 | v4.0 (T1104) | v5.0 (T1703) | 提升 |
| --- | --- | --- | --- |
| Persona 数 | 5 | 12 | +140% |
| Task 场景 | 16 | 45+ | +180% |
| 真实业务 API | 5 核心 | 20+ | +300% |
| WS 压测 | Locust 500 | asyncio 5000 | +900% |
| SLA 自动校验 | 简单脚本 | locustfile + 汇总器 | 完整 |
| Persona × Region 切片 | 无 | Prometheus 标签透传 | 新增 |

---

## 附录 A — 文件清单

| 路径 | 说明 |
| --- | --- |
| `backend/tests/load/scenarios.py` | Faker 数据生成 + payload 复用 |
| `backend/tests/load/locustfile.py` | v5.0 HTTP 压测主入口 (12 persona / 45+ task) |
| `backend/tests/load/ws_locustfile.py` | WebSocket Locust 入口 (≤ 1000) |
| `backend/tests/load/ws_concurrent.py` | asyncio 高并发 WS 压测 (5000+) |
| `backend/tests/load/redis_pubsub_test.py` | Redis pub/sub 瓶颈识别 |
| `backend/tests/load/run_locust.sh` | 单档 HTTP 压测 |
| `scripts/run_real_loadtest.sh` | v5.0 一键压测 (http/ws/smoke/full/ramp) |
| `docs/PERFORMANCE_v5.md` | 本报告 |
| `infra/prometheus/alerts.yml` | 告警规则 |
| `docs/ALERTING.md` | 告警响应手册 |

## 附录 B — 执行历史

| 日期 | 模式 | 结果 | 操作人 |
| --- | --- | --- | --- |
| _TBD_ | smoke (100 / 2m) | _TBD_ | _TBD_ |
| _TBD_ | full (100+500+1000+WS) | _TBD_ | _TBD_ |
| _TBD_ | 复测 after LLM cache | _TBD_ | _TBD_ |

## 附录 C — Grafana 仪表盘

- **业务总览**: P50/P95/P99 跨 persona + endpoint
- **SLA 雷达**: P95 / 错误率 / 吞吐 / WS 延迟 4 维
- **LLM 成本**: 按 model / provider / user 切片
- **DB 慢查询**: top 20 SQL + 索引建议
- **WS 连接**: 在线数 / 消息速率 / 重连率

仪表盘 ID 详见 `infra/grafana/grafana-dashboard.json`。
