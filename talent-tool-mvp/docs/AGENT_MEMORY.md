# T2702 — Agent 统一记忆库 (Mem0)

> Phase 1: 选型 **Mem0** (https://github.com/mem0ai/mem0)
> Status: ✅ Shipped (v7.0.0 / T2702)

## 1. 目标

解决 v6.0 中暴露的 "Agent Memory 分散" 问题。16 个 agent 各自维护
working / long-term 记忆,跨 agent 上下文不共享,Mem0 选型提供一个
统一的 AI 记忆层:

* 跨 agent 记忆共享:profile agent 写一条 fact,clarifier agent
  立即能在同一次 run() 看到它。
* 自动 entity 抽取:从对话中抽出 `fact / preference / event / task`,
  而不是塞 KV。
* 衰减 / 强化:被反复访问的记忆权重回升,长期不用的权重下降。
* GDPR 友好:用户一键 forget,Audit log 留痕。
* 实体图谱:用 `memory_links_v2` 维护 `related / supports / contradicts`
  关系,支持后续 Neo4j 迁移。

## 2. 组件

```
backend/services/memory/
├── __init__.py
├── models.py          # Memory / MemoryLink / MemoryQuery (Pydantic)
├── store.py           # MemoryStore (vendor Mem0 client + InMemory/Supabase)
├── extractor.py       # EntityExtractor (LLM + 启发式)
├── injector.py        # MemoryInjector (context block 注入)
├── agent_adapter.py   # memory_aware_run / MemoryAwareAgent
└── subscribers.py     # EventBus 桥接 (profile.updated / offer.received ...)

supabase/migrations/049_agent_memory_v2.sql
  memories_v2 (id, tenant_id, user_id, content, embedding[1024], source_agent,
               type, confidence, decay_score, access_count, last_accessed,
               metadata, is_archived, created_at, updated_at)
  memory_links_v2 (memory_id_a, memory_id_b, relation, weight)
  memory_access_v2 (audit trail)
  memory_decay_jobs (background job log)

backend/api/memory.py
  REST endpoints mounted at /api/memory
  CRUD / query / extract / forget / decay / links / health

frontend/app/(jobseeker)/memory/page.tsx
  我的记忆 (看 / 改 / 删 / 批量 forget)

frontend/components/memory/MemoryTimeline.tsx
  时间线组件,带 inline edit / delete / decay 提示

tests/test_memory.py
  60+ test cases
```

## 3. 安装

```bash
pip install mem0ai

# 本地开发 (Docker)
docker run -p 8000:8000 mem0/mem0:latest

# 或用 Mem0 Cloud (免费层)
export MEM0_API_KEY="m0-..."

# Supabase 必须开 pgvector 扩展
psql -f supabase/migrations/049_agent_memory_v2.sql
```

后端启动时,`backend/setup.py: lifespan` 会自动:
1. `get_memory_store()` 拿到全局单例
2. `store.init(supabase_client_factory=...)` 切换到 Supabase 后端
3. `install_memory_subscribers(store)` 挂 EventBus 订阅者

## 4. 数据流

### 写入路径
```
profile_agent
    │ memory_writes
    ▼
BaseAgent.run()
    │ wraps
    ▼
memory_aware_run()
    │ translates legacy memory_writes → Memory
    ▼
MemoryStore.add(user_id, content, source_agent, type)
    │ inserts row + access_log entry
    ▼
memories_v2  (Supabase + RLS)
```

### 读取路径
```
clarifier_agent.run()
    │ memory_aware_run
    ▼
MemoryInjector.build_context_block(user_id, query_text)
    │ queries memories_v2
    ▼
system_prompt = "you are helpful" + "\n[MEMORY CONTEXT]\n- ...\n[END]"
```

### EventBus 桥接
| 事件 | 行为 |
|---|---|
| `profile.updated` | 按 `fields` 写多条 FACT 记忆 |
| `preference.expressed` | 写 1 条 PREFERENCE 记忆 |
| `interview.completed` | 写 1 条 EVENT 记忆 |
| `offer.received` | 写 1 条 conf=1.0 EVENT 记忆 |
| `memory.decay.requested` | 跑一次 decay (cron 调用) |

## 5. 集成 16 Agent

通过 `MemoryAwareAgent(base_agent, store=...)` 包装,所有 agent 的
`run()` 入口都会:

1. 拿 `query_text` 查 top-K 记忆
2. 拼到 system prompt
3. 让 base agent 跑 `_handle()`
4. 把 `memory_writes` 翻译成 `Memory` 持久化(带 `source_agent`)

或显式调用:
```python
from services.memory.agent_adapter import memory_aware_run
output = await memory_aware_run(agent, agent_input)
```

## 6. API

| Method | Path | 说明 |
|---|---|---|
| GET    | `/api/memory/health` | 组件健康 |
| POST   | `/api/memory/memories` | 创建 |
| GET    | `/api/memory/memories` | 列表 |
| GET    | `/api/memory/memories/{id}` | 详情 |
| PATCH  | `/api/memory/memories/{id}` | 编辑 |
| DELETE | `/api/memory/memories/{id}` | 删除 |
| POST   | `/api/memory/memories/query` | 语义查询 |
| POST   | `/api/memory/memories/extract` | 从对话抽取 |
| POST   | `/api/memory/memories/forget` | GDPR 撤回 |
| POST   | `/api/memory/memories/decay` | 手动 decay |
| GET    | `/api/memory/memories/access-log` | 审计日志 |
| POST   | `/api/memory/memories/links` | 创建关系 |
| GET    | `/api/memory/memories/{id}/links` | 查关系 |

## 7. Decay 机制

* 默认 factor=0.95,每次 decay 乘 0.95,衰减趋近 0 但不归零
* 访问时(`touch`):`decay_score = min(1.0, decay_score + 0.05)`,
  `access_count += 1`,`last_accessed = now`
* `min_decay` 查询过滤:低于阈值的记忆不再注入 context
* 可调度任务: `POST /api/memory/memories/decay` 或 `emit("memory.decay.requested")`

## 8. GDPR 撤回

```bash
# 撤回某 agent 写的所有记忆
curl -X POST /api/memory/memories/forget \
  -d '{"source_agent": "clarifier_agent"}'

# 撤回某类型且 decay_score < 0.1
curl -X POST /api/memory/memories/forget \
  -d '{"type": "preference", "decay_below": 0.1}'

# 撤回 90 天前
curl -X POST /api/memory/memories/forget \
  -d '{"older_than_days": 90}'
```

每次 forget 都会在 `memory_access_v2` 留一条 `actor_kind=gdpr_job` 的
审计记录,合规可追溯。

## 9. 验证

```bash
cd backend
python -m pytest tests/test_memory.py -v
```

覆盖:
- 60+ 测试用例
- 跨 agent 共享、decay 逻辑、GDPR、API、EventBus 桥接
- 全程无需 Supabase / Mem0 在线(InMemoryBackend)

## 10. Mem0 集成 (可选)

```python
# store.py
mem0_client = MemoryClient(api_key=MEM0_API_KEY)

# extract_via_mem0 把对话交给 Mem0 抽取高质量事实
result = mem0_client.add(conversation, user_id=str(user_id))
```

注意:即使 Mem0 不可用,EntityExtractor 的启发式正则也会兜底,
保证核心流程不挂。

## 11. 后续路线

| 任务 | 描述 |
|---|---|
| 知识图谱 (Neo4j) | 把 `memory_links_v2` 同步到 Neo4j,支持多跳推理 |
| 主动召回 | Agent 主动问 "你之前说过...",根据 decay_score 触发 |
| 跨用户去重 | Tenant 内共享的"公司评价 / 行业洞察" |
| 隐私分级 | `sensitivity: low/medium/high`,影响注入策略 |
| Fine-tune 训练数据 | 把高 confidence 记忆导出为偏好数据 |
