# T2801 — ClickHouse 数据仓库

## 拓扑

- **3 副本 × 1 shard** (生产可扩到 2+ shard, 改 `config.xml` `<remote_servers>` 即可)
- **3 节点 Zookeeper** 协调副本同步
- **altinity/clickhouse-backup** sidecar 每天 03:00 UTC 全量备份到 S3
- **1 年保留**: 用 TTL `event_date + INTERVAL 365 DAY`
- **2 层存储**: 最近 30 天 hot SSD, 30 天-1 年 cold S3

## 启动

```bash
cd infra/clickhouse
cp .env.example .env  # 改密码 + S3 key
docker compose up -d
docker compose exec clickhouse-shard1-replica1 \
  clickhouse-client --query "SELECT version()"
```

## 创建表 (T2801)

```bash
docker compose exec clickhouse-shard1-replica1 \
  clickhouse-client --multiquery < schema/warehouse.sql
```

## 健康检查

| Endpoint | 用途 |
|---|---|
| `http://localhost:8123/ping` | 健康 (返回 `Ok.`) |
| `http://localhost:8123/?query=SELECT...` | HTTP 查询 |
| `tcp://localhost:9000` | Native 协议 (clickhouse-driver / dbt-clickhouse) |
| `http://localhost:9116/metrics` | Prometheus 指标 |
