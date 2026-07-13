# T2801 — Airbyte OSS ETL

## 链路

```
Supabase Postgres (CDC)  --[Airbyte]-->  ClickHouse warehouse.raw_*
```

## 启动

```bash
cd infra/airbyte
cp .env.example .env  # 改密码
docker compose up -d
# 等 60s 启动, 访问 http://localhost:8000
```

## 一键注册 (推荐)

```bash
# 先去 Airbyte UI 拿 API token
export AIRBYTE_API_TOKEN=eyJhbGciOi...
export AIRBYTE_URL=http://localhost:8001
./bootstrap/apply.sh
```

脚本会自动:
1. 拿到 workspaceId
2. 创建 Postgres CDC source
3. 创建 ClickHouse destination
4. 创建每小时的 Connection
5. 立即触发一次同步

## 手动配置 (UI)

按 `bootstrap/connection.json` 的 5 张表 (candidates / jobs / matches / applications / tickets) 配即可。

## 同步后表

Airbyte 会自动在 ClickHouse 建:
- `warehouse.raw_candidates`
- `warehouse.raw_jobs`
- `warehouse.raw_matches`
- `warehouse.raw_applications`
- `warehouse.raw_tickets`

dbt 接下来会基于这些 raw 表做维度建模。
