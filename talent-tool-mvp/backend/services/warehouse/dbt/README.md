# T2801 — dbt 数据转换项目

## 模型分层

| 层 | 作用 | 物化 |
|---|---|---|
| `staging` | 1:1 映射 `raw_*`, 改类型, 加 audit | view |
| `intermediate` | join / 简单 enrich | view |
| `marts` | 维度 + 事实表, 给 API / BI 用 | table |

## 关键表

- `dim_candidates` — ReplacingMergeTree, 慢变维 (SCD type 1)
- `dim_jobs`       — ReplacingMergeTree
- `fct_matches`    — MergeTree, 按天分区
- `fct_applications` — MergeTree, 按天分区
- `fct_sla_metrics` — **AggregatingMergeTree** (State 合并), 实时 SLA 监控

## 自定义宏 (`macros/`)

| 宏 | 用途 |
|---|---|
| `time_bucket(col, 'day' / 'week' / 'month' / 'hour' / 'quarter' / 'year')` | 时间截断 |
| `time_buckets(col, [...])` | 多粒度展开 |
| `funnel(stages, partition, distinct_key)` | 漏斗 |
| `funnel_conversion(stages)` | 漏斗 + 转化率 |
| `retention_query(first_at, repeat_at, periods=(1,7,14,30,60,90))` | cohort 留存 |
| `tenant_filter()` | 多租户隔离 (--vars 注入) |
| `retention_ttl()` | TTL 生成 |

## 运行

```bash
# 安装
pip install dbt-core dbt-clickhouse

# 验证连接
dbt debug --profiles-dir .

# 全量
dbt run --profiles-dir . --target prod

# 增量 (改 model 时)
dbt run --profiles-dir . --select state:modified+ --target prod

# 测试
dbt test --profiles-dir . --target prod

# 全链路 (run + test + snapshot)
dbt build --profiles-dir . --target prod
```

## 调度

- Airbyte: 每小时 (raw_*) — 见 `infra/airbyte/bootstrap/connection.json`
- dbt:   同步后 5 分钟 (marts) — 见 `etl_scheduler.py` (`DbtRunner`)
