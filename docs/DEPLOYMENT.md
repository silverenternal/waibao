# 部署指南

## 🚀 部署架构

```
                    ┌─────────────────────┐
                    │   CDN / Cloudflare   │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                                  │
    ┌─────────▼─────────┐             ┌─────────▼─────────┐
    │   Frontend (Vercel)│            │  Backend (Railway) │
    │   Next.js 16      │  HTTPS/WS   │  FastAPI + 16     │
    │                   │ ◄─────────► │  Agents            │
    └───────────────────┘             └─────────┬──────────┘
                                                │
                                ┌───────────────┼───────────────┐
                                │                               │
                      ┌─────────▼─────────┐         ┌──────────▼─────────┐
                      │ Supabase (Cloud)   │         │ OpenAI/Anthropic   │
                      │ PostgreSQL+pgvector│         │ (LLM Provider)     │
                      └───────────────────┘         └─────────────────────┘
```

## 📦 依赖服务

| 服务 | 用途 | 推荐供应商 |
|---|---|---|
| PostgreSQL + pgvector | 主数据库 | Supabase |
| Realtime | WebSocket 订阅 | Supabase Realtime |
| Auth | JWT 鉴权 | Supabase Auth |
| Storage | CV/资质文件 | Supabase Storage |
| LLM | GPT-4o | OpenAI |
| Embedding | text-embedding-3 | OpenAI |
| Container | 部署运行时 | Railway / Fly.io / AWS ECS |
| CDN | 前端分发 | Vercel / Cloudflare |

---

## 🛠️ 部署步骤

### 1. Supabase 初始化

```bash
# 创建 Supabase 项目 https://supabase.com

# 在 SQL 编辑器依次执行迁移:
psql -h db.xxx.supabase.co -U postgres -d postgres \
  -f supabase/migrations/002_agent_memory.sql \
  -f supabase/migrations/003_conversations.sql \
  -f supabase/migrations/004_emotion_timeline.sql \
  -f supabase/migrations/005_company_knowledge.sql \
  -f supabase/migrations/006_clarification_artifacts.sql \
  -f supabase/migrations/007_multi_persona.sql \
  -f supabase/migrations/008_pii_encryption.sql

# 创建 storage bucket: 'credentials' (private)
# 创建 storage bucket: 'resumes' (private)
```

### 2. 后端部署

#### 选项 A: Docker Compose(自托管)

```bash
# 1. 克隆
git clone https://github.com/silverenternal/waibao.git
cd waibao/talent-tool-mvp

# 2. 配置 .env
cat > backend/.env <<EOF
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJhbGc...
SUPABASE_SERVICE_KEY=eyJhbGc...
SUPABASE_JWT_SECRET=your-jwt-secret
OPENAI_API_KEY=sk-xxx
PII_ENCRYPTION_KEY=$(openssl rand -base64 32)
CORS_ORIGINS=https://your-frontend.com
DEFAULT_LOCALE=zh
EOF

# 3. 生产部署
docker-compose -f docker-compose.prod.yml up -d

# 4. 验证
curl http://localhost:8000/health
```

#### 选项 B: Railway / Fly.io

```bash
# Railway
railway init
railway add
railway variables set SUPABASE_URL=...
railway variables set OPENAI_API_KEY=...
railway up

# Fly.io
fly launch
fly secrets set SUPABASE_URL=...
fly secrets set OPENAI_API_KEY=...
fly deploy
```

### 3. 前端部署

#### 选项 A: Vercel(推荐)

```bash
cd frontend
vercel

# 环境变量
vercel env add NEXT_PUBLIC_API_URL https://api.your-domain.com
vercel env add NEXT_PUBLIC_SUPABASE_URL https://xxx.supabase.co
vercel env add NEXT_PUBLIC_SUPABASE_ANON_KEY eyJhbGc...
```

#### 选项 B: 自托管

```bash
cd frontend
npm install
npm run build
# 静态文件输出到 .next/, 用 nginx / caddy 反向代理
```

### 4. 域名 + HTTPS

```bash
# Cloudflare / Let's Encrypt
# API: api.your-domain.com → 后端服务
# Web: your-domain.com → 前端静态
```

---

## 🔐 安全配置

### 环境变量

```bash
# 必填
SUPABASE_URL=...
SUPABASE_KEY=...
SUPABASE_SERVICE_KEY=...         # ⚠️ 严格保密
SUPABASE_JWT_SECRET=...
OPENAI_API_KEY=sk-...            # ⚠️ 严格保密
PII_ENCRYPTION_KEY=<base64-32-bytes>   # ⚠️ 严格保密

# 推荐
ENV=production
CORS_ORIGINS=https://your-domain.com
DEFAULT_LOCALE=zh
RATE_LIMIT_PER_USER=100          # 每分钟请求上限
LLM_BUDGET_PER_USER=100000       # 每日 token 上限
```

### 密钥轮换

每 90 天轮换:
1. 生成新 `PII_ENCRYPTION_KEY`
2. 用旧密钥解密所有 PII 字段
3. 用新密钥重新加密
4. 部署新密钥
5. 废弃旧密钥

---

## 📊 监控

### Prometheus + Grafana

```bash
# 启动监控栈
docker-compose -f docker-compose.prod.yml up -d prometheus grafana

# 访问
# Prometheus: http://localhost:9090
# Grafana:    http://localhost:3001 (admin/<GRAFANA_ADMIN_PASSWORD>)

# 导入仪表板
# infra/grafana-dashboard.json
```

### 关键指标

| 指标 | 类型 | 说明 |
|---|---|---|
| `agent_calls_total` | Counter | 每个 Agent 调用次数 |
| `llm_tokens_total` | Counter | LLM token 消耗 |
| `two_way_match_duration_seconds` | Histogram | 匹配耗时 |
| `emotion_needs_attention_total` | Counter | 高风险情绪数 |
| `daily_journal_logged_total` | Counter | 日记提交数 |
| `two_way_match_status_count` | Gauge | 各状态匹配数 |

### 告警

```yaml
# infra/alertmanager.yml 已配置钉钉/飞书 webhook
# 告警规则:
# - LLM token 超预算
# - 情绪告警(needs_attention)
# - 匹配 P95 > 5s
# - 后端 5xx 错误率 > 1%
```

---

## 🔄 备份与恢复

### 数据库备份
```bash
# Supabase 自动每日备份(Pro 版 7 天保留)
# 手动备份:
pg_dump -h db.xxx.supabase.co -U postgres -d postgres > backup.sql

# 恢复:
psql -h db.xxx.supabase.co -U postgres -d postgres < backup.sql
```

### 密钥备份
- `SUPABASE_SERVICE_KEY`: 1Password / Vault
- `PII_ENCRYPTION_KEY`: 离线冷备份(2 份,不同地理位置)
- 丢失 = 所有加密 PII 不可恢复

---

## 🚨 故障排查

### 后端 500 错误
```bash
docker logs recruittech-api
# 常见: SUPABASE_URL 配错 / OpenAI key 无效 / JWT secret 不匹配
```

### LLM 调用超时
```python
# backend/services/llm_cache.py: 启用缓存减少重复调用
# backend/services/llm_budget.py: 调整 per-user 配额
# 考虑: 切换到更快的模型(4o-mini / Haiku)
```

### WebSocket 断开
```bash
# 检查 nginx/caddy 是否支持 WebSocket 升级
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

### 高风险情绪告警积压
```sql
-- 查看未处理告警
SELECT * FROM emotion_timeline
WHERE needs_attention = true
  AND recorded_at > NOW() - INTERVAL '24 hours'
ORDER BY recorded_at DESC;
```

---

## 📈 扩展性

### 水平扩展

```yaml
# docker-compose.prod.yml
services:
  api:
    deploy:
      replicas: 3  # 多实例
    ports:
      - "8000"
```

配合 nginx upstream 负载均衡。

### 性能优化清单

- [ ] 启用 Supabase 连接池(pgbouncer)
- [ ] LLM 缓存命中率 > 30%
- [ ] pgvector 索引 HNSW 已建
- [ ] Redis 缓存 working memory
- [ ] CDN 加速前端静态资源

---

## 🔧 升级流程

```bash
# 1. 拉新代码
git pull origin main

# 2. 数据库迁移(若有新迁移)
psql ... -f supabase/migrations/00X_xxx.sql

# 3. 重启后端
docker-compose -f docker-compose.prod.yml up -d --build api

# 4. 重启前端(若需要)
vercel --prod

# 5. 验证
curl http://api/health
```

---

## 📞 运维联系

- 文档: [docs/](../)
- Issues: https://github.com/silverenternal/waibao/issues
- 监控: Grafana 仪表板
- 告警: 钉钉 #recruittech-ops