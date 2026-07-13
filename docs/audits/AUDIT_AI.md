# waibao v10.0 AI + 集成审查报告

> 审查基线：`/home/hugo/codes/waibao/talent-tool-mvp/backend/`，覆盖 v6.0 EventBus / ConfigCenter / FeatureFlag / PluginSDK / WorkflowEngine，v7.0 RAG (LlamaIndex) / Memory (Mem0) / Multi-Agent (CrewAI) / Prompt v2 (Agenta)，以及 v8.0 ServiceToggle 三层权限门 (ConfigCenter + ServiceToggle + FeatureFlag)。
>
> 静态扫描 870+ 个 Python 文件、46 个 Provider 实现、16 个 Agent (6 jobseeker + 9 employer + 1 evaluator)，未在真实 LLM 端点 / Qdrant / Mem0 / 多 Agent 集群重跑全链路，因此“检索准确度 / 实体抽取 F1 / 共识一致性”等指标均为工程估算（基于 schema、单元测试覆盖与代码路径）。

## 总体评分

| 维度 | 分数 | 评价 |
|---|---|---|
| EventBus 基础 | **7.5/10** | In-memory + Redis 双实现、~16 个 emit_* helper、12 个跨切 subscriber；缺死信/重试/顺序保证/事件 schema 注册表 |
| Plugin SDK | **8.2/10** | RestrictedPython + AST 黑名单 + 网络/FS/资源三重沙箱，结构清晰；但强依赖系统 rlimit (Windows 失效)，签名验证缺 |
| Workflow Engine | **6.8/10** | DAG + Pause/Resume + 状态持久化插拔；缺 DAG 循环检测、超时、监控、并行 fan-out |
| RAG (LlamaIndex) | **7.0/10** | Qdrant + BM25 + RRF Hybrid 检索 + cross-encoder reranker + citation 完整链路；embedding/reranker 实际是 hash-bucket/lexical fallback（无真实模型权重），多租户未通过 collection name 隔离 |
| Memory (Mem0) | **6.9/10** | Supabase 持久化 + LLM/正则实体抽取 + decay + GDPR forget；搜索仍走 hash-bucket cosine，多租户靠 tenant_id 过滤（schema 上 RLS 缺失确认） |
| Multi-Agent (CrewAI) | **7.3/10** | 4 场景 + 4 共识算法 + 4 collaboration pattern 完整；orchestrator 默认 `default_executor` 是 stub (synthesize_decision)，不是真实 LLM，memory 写入是字符串拼接 |
| Prompt v2 (Agenta) | **8.0/10** | 版本化 + traffic_pct A/B + 4 维评估 + shift_traffic + ConfigCenter render；缺真实热加载 (InMemoryProcess 单例) + 评估指标采集未自动化 |
| Provider 抽象 | **7.5/10** | 12 维度 + 46 Provider + with_resilience (retry/circuit/rate/cost/cache/metrics)；真实 API 走 mock fallback 兜底；缺统一 Provider 基类继承 |
| Feature Flag / ConfigCenter / ServiceToggle | **8.6/10** | 三层门 + 60s 缓存 + EventBus 联动 + 审计 + 回滚 + 依赖阻断；多入口失效回退良好但 ConfigCenter 全局开关 boolean 单一维度 |

**综合判断**：v6.0/v7.0/v8.0 三轮发布使 EventBus + PluginSDK + Workflow + RAG + Memory + MultiAgent + Prompt + Provider + 三层 Feature Access 形成了“形式覆盖齐全、企业级骨架存在”的 AI 集成栈。但有 5 类显著短板：
1. **真模型接入覆盖率不足**：Embedding / Reranker / Mem0 extractor / Multi-Agent executor / Memory cosine 五大热路径默认走 hash-bucket / lexical / stub fallback，没有真实模型权重在 CI 中被自动验证。
2. **多租户隔离在 AI 子系统未端到端**：RAG Qdrant collection 名非 tenant_id 派生，Memory `memories_v2` 走 RLS 但 injector 仅按 user_id 过滤；Plugin SDK 在 sandbox 级别无 tenant 标签。
3. **缺 4 个核心可靠性原语**：EventBus 死信/重试、Workflow 节点超时/循环检测、RAG chunking 增量、Memory decay 调度均未上线。
4. **评估与监控缺闭环**：Prompt v2 4 维指标 (`accuracy/fluency/safety/bias`) 需手动 record_metric，无定时评估任务；MultiAgent 无 latency / token / cost 监控。
5. **Plugin 签名 / 版本不兼容矩阵 / Provider 单测覆盖** 三大信任根基仍靠 docstring 描述，没有真实测试/集成验证。

---

## 关键量化证据

- **EventBus**：6 文件 (base.py / registry.py / decorators.py / integration.py / subscribers.py / tests/)，`InMemoryEventBus` + `RedisEventBus` 双实现；16 个 `emit_*` helper (`emit_profile_updated / _enriched / _created / _needs_clarified / _emotion_detected / _emotion_risk / _plan_generated / _market_updated / _journal_submitted / _role_image_updated / _strategy_updated / _ticket_created / _ticket_escalated / _agent_started / _agent_completed / _agent_failed`)；15 个 `_register_*` 跨切订阅器 (notify_profile/notify_ticket/analytics/audit/realtime/match/career/journal/hr/workflow/plugin/metric/sentry/crm/roi)；Event 含 `event_id/correlation_id/source/timestamp` 4 元数据。
- **Plugin SDK**：6 文件 (base/manifest/runner/sandbox/registry/loader)，40+ 模块黑名单 (`os/sys/subprocess/socket/ctypes/importlib/pickle/multiprocessing/...`)，10 个 builtin 黑名单 (`__import__/compile/exec/eval/open/input/globals/locals/getattr/setattr/delattr`)，5 层防护 (AST audit / RestrictedPython / ResourceLimiter CPU+AS+NOFILE / NetworkGuard / FilesystemGuard)；10 个允许权限 (`db:read/db:write/events:emit/events:subscribe/http:call/http:listen/files:read/files:write/llm:call/metrics:emit/admin`)；semver 严格正则 `^\d+\.\d+\.\d+([\-+][\w.]+)?$`。
- **Workflow Engine**：6 状态 (PENDING/RUNNING/PAUSED/COMPLETED/FAILED/CANCELLED)，Edge.condition 分支；Resume 通过 `remember()` 单实例保存，DAG `start_node` 必填；`_execute_node` 当前 fan-out 顺序执行（注释承认 "async parallel straightforward to add"）。
- **RAG**：7 模块 (parser/chunker/embedder/retriever/reranker/generator/citation)，3 检索模式 (VECTOR/BM25/HYBRID)，RRF 融合 (k=60) + cross-encoder reranker fallback (lexical)；chunk_size=512 / overlap=50；3 嵌入模型 (OPENAI_SMALL/BGE_LARGE/BGE_BASE/MOCK)；chunking 走 LlamaIndex `SentenceSplitter` 失败后回退 sentence + sliding window。
- **Memory**：4 后端 (InMemoryBackend + SupabaseBackend)，4 类型 (FACT/PREFERENCE/EVENT/SUMMARY)；`MemoryInjector.build_context_block` 把 top-8 memory 拼成 system prompt；5 个 cross-bus 订阅 (`profile.updated / preference.expressed / interview.completed / offer.received / memory.decay.requested`)。
- **Multi-Agent**：4 scenario (RESUME_SCORING/BIAS_REVIEW/OFFER_NEGOTIATION/STRATEGY_DECODE) × 4 pattern (SEQUENTIAL/PARALLEL/HIERARCHICAL/DEBATE) × 4 consensus (MAJORITY/UNANIMOUS/WEIGHTED/QUORUM)；4 类 RoleKind (TECH/CULTURE/DOMAIN scorer、WRITER/BIAS_REVIEWER/REVIEWER/RESEARCHER/PM)；max_rounds 默认 3，post_run 写 `multiagent.task.completed` 事件 + memory 一条。
- **Prompt v2**：3 状态 (DRAFT/ACTIVE/RETIRED)，4 评估维度 (accuracy/fluency/safety/bias)，`get_active_prompt` 加权 bucket；`shift_traffic` 原子迁移；`render()` 用 `{{var}}` 模板替换。
- **Provider**：46 个 .py 实现（去除 mock 约 30+ 真），覆盖 llm(7)/embedding(3)/vision(2)/ocr(3)/stt(2)/notify(5)/lookup(2)/job_market/assessment/ats/background_check/sourcing/payment/video_interview；`with_resilience` 串联 cache → circuit → rate limit → retry → cost → metrics；`CostTracker` 支持 `tenant:date` + `tenant:date:provider:model` 双维度。
- **三层 Feature Access**：`feature_access.check` 依次调 ConfigCenter (boolean `service_toggle/<name>` 全局) → ServiceToggle (status + plan + role + per-org override) → FeatureFlag (per-user/per-org override + rollout_percent hash + rules + admin enabled)，任一 deny 即拒；缓存 TTL 60s。

---

## 高优先级问题 (P0 - 立即修)

1. **问题：RAG embedding / reranker 默认走 hash-bucket / lexical fallback，没有真实模型权重在 CI 验证**
   - 位置：`backend/services/rag/embedder.py:100-137` (`_embed_llama_index` 内部 `_HashEmbed`)、`backend/services/rag/reranker.py:56-69` (`_load_model` 找不到 sentence_transformers 即返回 False)。
   - 影响：CI 中 `_mock_embed` 走 `_deterministic_vector` (SHA-256 hash bucket)，检索准确度无法对齐生产；reranker 退化为 `0.6*cosine + 0.3*coverage + 0.1*score` lexical 综合，对语义相似度识别率显著低于 cross-encoder；RAG 演示“准确度 > 85%” 无法验证。
   - 修复成本：中（1-2 周含 CI fixture 注入 BGE-small + reranker-base）
   - 建议：在 CI fixture 中加入 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` 轻量真模型（~470MB）；`embedder._embed_llama_index` 接受 `embedding_model_path` 参数；为 `Reranker` 增加 `_mock_lexical_predict` 之外的确定性算子作为 fallback 但记录 `metric=fake_rerank` 警告；新增 `tests/test_rag_real_model.py` 在 GPU runner 上跑 Recall@5≥0.7 断言。

2. **问题：Multi-Agent `default_executor` 是 stub (`_synthesize_decision`)，4 个场景的"真实业务跑通" 实质依赖注入 `executor=...`**
   - 位置：`backend/services/multiagent/orchestrator.py:188-233` (`default_executor` + `_synthesize_decision`)、`backend/services/multiagent/orchestrator.py:251-252` (`Orchestrator.__init__` 默认 `executor=default_executor`)。
   - 影响：CI 测试通过的 4 场景（resume_scoring / bias_review / offer_negotiation / strategy_decode）实际是 `_synthesize_decision` 根据 description 关键字算分（"strong"+"senior"+7.5, "weak"+"junior"-7.5），不是真实 LLM；`max_rounds` / `consensus` / `debate` 逻辑得到验证但语义对齐未验证；生产部署若忘记注入 `executor` 仍会跑 stub，导致“5 人格 AI 模拟面试官”"战略解码"等对外宣称能力实际为伪 AI。
   - 修复成本：中（1 周接 `with_resilience` provider + CrewAI 风格 `Crew.kickoff` 适配层）
   - 建议：`Orchestrator.__init__` 默认 executor 改为 `llm_provider_executor`，从 `services.platform.config_service.get("multiagent.executor", "default")` 解析；新增 `MultiAgentExecutor` 实现 (复用 `providers/llm/openai_provider.chat` + `with_resilience` 装饰)；`get_orchestrator()` 工厂在 `app boot` 时注入真实 executor；CI 中新增 `test_multiagent_real_llm.py` 用 mock LLM provider 验证 resume_scoring 输出含 “score/confidence/rationale” 字段且 ≥3 个 agent 输出不同 decision。

3. **问题：Memory `extractor` / Memory search 实际用 hash-bucket cosine，未在生产跑 LLM extractor / embedding**
   - 位置：`backend/services/memory/extractor.py:42-109` (`EntityExtractor._extract_one` 全程 regex)；`backend/services/memory/store.py:148-169` (`InMemoryBackend.search` 用 `_hash_embed`)；`backend/services/memory/store.py:278-301` (`SupabaseBackend.search` 也用 `_hash_embed` 而不是 pgvector RPC)。
   - 影响：实体抽取精度依赖中英文 regex，无法应对 "I tend to prefer" / "Don't like X" 句式；Mem0 vendor client (`mem0.MemoryClient`) 仅在 `MEM0_API_KEY` 设置且 `use_mem0=True` 时启用，且即使启用失败也只是 fallback 到 `mem0_fallback`；SupabaseBackend 注释承认 "A future iteration can swap in a pgvector RPC for large tenants"，意味着 >1k memories 的租户检索是 O(n) 线性扫表。
   - 修复成本：中-高（需创建 pgvector `match_memories` RPC + 调用链改造）
   - 建议：把 `MemoryStore.search` 在 Supabase 后端切换为 `sb.rpc("match_memories", {"query_embedding": ..., "p_user_id": ..., "p_top_k": ...})`；新 migration `054_memory_pgvector.sql` 创建 `match_memories(query_embedding vector, p_user_id uuid, p_top_k int, p_min_confidence float)` 函数 + HNSW 索引；`EntityExtractor.extract_async` 强制 `services.llm_cache.get_cache()` 包装避免重复 token 消耗；CI 增加 `test_memory_pgvector.py` 验证 ≥1000 行召回 P95 < 50ms。

4. **问题：EventBus 缺死信队列 (DLQ) / 重试 / 事件 schema 注册表；事件顺序无保证**
   - 位置：`backend/eventbus/base.py:124-168` (InMemoryEventBus.publish / publish_async)；`backend/eventbus/base.py:202-247` (RedisEventBus.publish → `redis.publish` 是 fire-and-forget)。
   - 影响：`emit_agent_failed → sentry._capture` 失败仅记入 `self._errors` 列表 (in-memory)，进程重启丢失；Redis publish 不持久化，订阅者离线时事件直接丢失；`_invoke` 中 `run_in_executor` 不会因为上一个 handler 阻塞而 delay（同步 publish 顺序保留，async publish `gather` 不保证 order）；事件 schema 仅靠 docstring + integration.py 的 helper 维护，无集中注册表 → 新增 agent 时字段漂移 (e.g. `run_id` 在 `agent.completed` / `multiagent.task.completed` 都出现但含义略不同)。
   - 修复成本：中（引入 `streams:events:dlq` Redis Stream 或 `events_outbox` 表）
   - 建议：把 RedisEventBus 改为基于 Redis Streams (`XADD` + consumer group + DLQ `XADD events:dlq *`)，consumer 失败 N 次后写入 DLQ；为 16 个 `emit_*` helper 增加 Pydantic `EventPayload` 类（如 `ProfileUpdatedPayload / AgentCompletedPayload`）放入 `eventbus/schemas.py`；CI 加 `test_eventbus_dlq.py` 验证 handler 抛异常后事件入 DLQ 且 `XLEN events:dlq` 增加；`Event` 增加 `schema_version: int` 字段支持事件版本演进。

5. **问题：Workflow Engine 缺 DAG 循环检测 + 节点超时 + 监控指标；`remember()` 单实例保存不支持多 workflow 并发**
   - 位置：`backend/services/platform/workflow_engine.py:151-155` (`register` / `get` 用 `_registry: Dict`)、`backend/services/platform/workflow_engine.py:160-176` (`execute` 无 cycle check)、`backend/services/platform/workflow_engine.py:230-263` (`_execute_node` 无 timeout wrapper)、`backend/services/platform/workflow_engine.py:276-282` (`_find_workflow_for` 只在 `_last_workflow` 单实例中查找)。
   - 影响：定义 `A → B → A` 的 workflow 会无限递归直至 RecursionError 或栈溢出；`HumanNode` 长时间等待 (e.g. 24h HR 审批) 占据 asyncio slot；并发跑 2 个 workflow 时第 2 个会覆盖 `_last_workflow`，第 1 个的 `resume()` 会找不到定义；`_execute_node` 无 `prometheus_client.Histogram` 节点级延迟采集 → 无 SLA 监控。
   - 修复成本：中-高（cycle detection + persistent store + timeout + metrics 一起做）
   - 建议：`WorkflowDefinition.register` 时跑 Tarjan/Kahn 拓扑排序检测 cycle 并 raise `WorkflowValidationError`；`_execute_node` 外层包 `asyncio.wait_for(node.timeout, ...)`，超时记录 `node.timed_out` 状态走 FAILED；`WorkflowEngine.__init__` 增加 `metrics: WorkflowMetrics` 字段，记录 `nodes_executed_total / node_latency_seconds / runs_in_progress`；`_find_workflow_for` 改为 `WorkflowStore.load_workflow(workflow_id)` 持久化定义；CI 加 `test_workflow_cycle.py` + `test_workflow_timeout.py`。

---

## 中优先级问题 (P1 - 季度内修)

6. **问题：Plugin SDK 在 Windows 上 ResourceLimiter / NetworkGuard 完全失效；无代码签名验证**
   - 位置：`backend/plugins/sdk/sandbox.py:194-243` (`ResourceLimiter.__post_init__: self._supported = sys.platform != "win32"`)、`backend/plugins/sdk/sandbox.py:265-298` (`NetworkGuard.__enter__` 在 allow 空时直接 return 不 patch)、`backend/plugins/sdk/manifest.py` 全程无签名验证。
   - 影响：Windows 私有化部署时 plugin 进程无 CPU/MEM/FD 限制，恶意 plugin 可占满资源；`NetworkGuard` 默认 `allow=None` 时静默跳过（注释承认 "not recommended in production"），私有化交付时容易遗忘配置；plugin.yaml 没有 SHA-256 / minisign / cosign 签名校验，恶意升级包可被注入。
   - 修复成本：中（signing infra + Windows rlimit polyfill）
   - 建议：增加 `SignatureVerifier` 在 `PluginRunner.install_from_manifest_path` 中读 `plugin.yaml.sig` + `plugin.pub`，校验失败 raise `PluginLoadError`；`ResourceLimiter` Windows 分支用 `ctypes.windll.jobobjects` Job Object 限 CPU；`NetworkGuard` 默认 `allow=[]` 时禁止 outbound (deny-by-default)；新增 `docs/PLUGIN_SIGNING.md` 说明密钥轮换。

7. **问题：RAG 多租户隔离靠 collection_id 字符串，不在 Qdrant collection 名上强制 tenant_id 命名空间**
   - 位置：`backend/services/rag/retriever.py:198-249` (`add` 接受 `qdrant_collection: str | None`，写入的 collection 名由调用方传入)、`backend/services/rag/service.py:165-178` (`ingest_text` 调用 `add(..., qdrant_collection=qdrant_collection)`)。
   - 影响：同一 Qdrant 实例多 tenant 时，调用方必须自行拼接 `{tenant_id}_{name}`；RAGService 不做命名空间校验，跨租户读写风险；InMemoryStore 强制 `collection_id ==` 过滤（行 73），Supabase/pgvector fallback 也未确认。
   - 修复成本：低-中（命名规则 + 校验）
   - 建议：`RagService.__init__` 接受 `qdrant_collection_template: str = "{tenant_id}__{collection_id}"`，所有写操作前 `_validate_collection_name`；`Retriever.add` 删除 `qdrant_collection` 参数改为 `tenant_id + collection_id` 二元组；CI 加 `test_rag_multitenant_isolation.py` 验证 tenant A 写入后 tenant B query 拿不到结果。

8. **问题：FeatureFlag 未知 flag 默认 deny 且不缓存 → 60s 内 1000 个请求 1000 次 Supabase 调用**
   - 位置：`backend/services/platform/feature_flag.py:417-437` (`is_enabled` 注释 "Unknown flag defaults to enabled=False; do not cache so a freshly created flag becomes effective without waiting 60s")。
   - 影响：刚启动时 flag 表为空，每次请求都打 Supabase；运维 flip flag 后要等 60s 才生效 (当前策略正确)，但 “fresh flag 立即生效” 是用 N 次 DB 调用换的；Cache 命中率在稳态应为 > 99% 但冷启动 / 灾备演练时塌方。
   - 修复成本：低（cache negative results with shorter TTL）
   - 建议：`is_enabled` 缓存 miss 用 5s 短 TTL 缓存 `{"__missing__": True}`；`_Cache.invalidate(prefix)` 增加批量删除；新增 `feature_flag_metrics` Prometheus 指标（hit/miss/skip）。

9. **问题：Prompt v2 `record_metric` 是手动调用，缺评估任务；热更新靠进程重启读 InMemoryProcess 单例**
   - 位置：`backend/services/platform/prompt_v2.py:302-312` (`record_metric` 需外部调用)、`backend/services/platform/prompt_v2.py:349-399` (`PromptService` 单例 + `_singleton` 模式)。
   - 影响：Agenta 风格 4 维 (accuracy/fluency/safety/bias) 评估指标只在 CI 测试时录入，生产 zero metric → A/B 决策无依据；`get_active_prompt` 选出的版本跨进程不一致 (InMemoryProcess 实例)；ConfigCenter 改了 prompt 不会主动 push 到进程，需要 SIGHUP 或重启。
   - 修复成本：中（Agenta SDK 或自研 eval runner + cross-process pubsub）
   - 建议：新增 `services/platform/prompt_evaluator.py` 定时跑 golden set → 自动 `record_metric`；`PromptService` 改为订阅 `config.changed` 事件，收到 `scope=prompt` 时清本地缓存并 reload；`render()` 在 prompt 中加 `{{schema_version}}` 占位符支持热升级。

10. **问题：Multi-Agent `_post_run._safe_write_memory` 把 decision 直接拼字符串写入 memory，无 schema 校验**
    - 位置：`backend/services/multiagent/orchestrator.py:483-500` (`_safe_write_memory`)。
    - 影响：`store.add(content=f"multiagent::{scenario}::{status}::{decision}", type="summary")` 把任意 decision 序列化进 memory；`source_agent="multiagent.orchestrator"` 之后会被 MemoryInjector top-8 召回，可能污染未来 prompt；批量跑 1000+ scenarios 时 memory 表膨胀。
    - 修复成本：低（独立 store 或 schema 校验）
    - 建议：把 multiagent decision 写入独立表 `multiagent_runs(run_id/scenario/status/decision_json/confidence/tenant_id)` 不入 MemoryStore；或保持 MemoryStore 但 `content` 限定为 JSON dict 且 `confidence < 0.5` 时不写。

11. **问题：Provider 真实 API 走 mock fallback，但 with_resilience 的 cache / cost 在 fallback 路径仍记录**
    - 位置：`backend/providers/base.py:380-422` (`_run` 中 circuit.allow / bucket.acquire / cache.set / cost_tracker.record 均无条件执行)，provider 内部 fallback 到 mock 后外部仍记真实 cost（取决于 cost_calculator 行为，但默认无 cost_calculator 不计）。
    - 影响：监控指标 `provider_calls_total{status="ok"}` 与实际“真实 API 调用次数”不符；fallback 路径调用次数会被误判为业务调用，影响 Prometheus SLO。
    - 修复成本：低
    - 建议：provider 内部 fallback 时返回 sentinel `_MockFallback`，`_run` 检测到时 `metrics.observe(..., "mock_fallback", latency)`；新增 `provider_metrics{provider, method, status=mock_fallback}` 单独计数。

12. **问题：ServiceToggle `_find_dependents` 在无 Supabase 时返回空列表，`disable` 可能误删依赖**
    - 位置：`backend/services/platform/service_toggle.py:711-723` (`_find_dependents`)、`backend/services/platform/service_toggle.py:482-504` (`disable` 检查 `active = [d for d in dependents if ...]`)。
    - 影响：无 Supabase 配置时 (`sb is None`) `_find_dependents` 返回 `[]`，`active` 也 `[]`，`disable()` 不会 raise `DependencyError` → 进程内单实例下可任意 disable，无依赖保护。
    - 修复成本：低（增加进程内 registry fallback）
    - 建议：`_find_dependents` 在 `sb is None` 时回退扫描 `self._registry`（虽然当前 `_registry` 是空 dict，但可扩展为 `_in_memory_registry: Dict[name, Service]` 在 `register_service` 时填充）。

---

## 低优先级问题 (P2 - 持续改进)

13. **问题：RAG `query_stream` 把 answer 按 80 字符切片 fake streaming，未接 OpenAI stream**
    - 位置：`backend/services/rag/service.py:339-350`。
    - 影响：SSE 体验“流式”但 LLM 已生成完整文本，TTFT 延迟不变；高 QPS 时 `yield` 80-char 切片触发 10+ 次网络包。
    - 修复成本：低-中
    - 建议：Generator 接受 `streaming=True` 时真正调用 LLM stream API；CI 加 latency 对比测试。

14. **问题：Plugin SDK `_call_with_timeout` 用 ThreadPoolExecutor 跑 install，无法撤销僵尸线程**
    - 位置：`backend/plugins/sdk/runner.py:215-228`。
    - 影响：plugin install 阻塞超过 timeout 时线程继续占用内存 + GIL；OS 层面无法 kill（生产应跑在 gVisor / firecracker 子进程）。
    - 修复成本：高（subprocess + IPC）
    - 建议：引入 `PluginSubprocessRunner` 用 `multiprocessing.Process` + `signal.SIGKILL`（Linux）/ `psutil.Process.terminate()`（跨平台）；保留 in-process runner 用于 dev/test。

15. **问题：EventBus 同步 publish 调用链抛异常仅记 in-memory error，重启即丢**
    - 位置：`backend/eventbus/base.py:130-135` (`InMemoryEventBus.publish` 的 except)。
    - 影响：生产 bug 排查只能看 `logger.exception`，metrics 没采集。
    - 修复成本：低
    - 建议：`self._errors.append` 同时 `event_bus.errors_total.inc()`（Prometheus）；`_errors` 队列上限 1000 防 OOM。

16. **问题：WorkflowEngine `_execute_node` 同步 await handler，但 handler 抛 `paused` 信号通过 output dict 隐式传递**
    - 位置：`backend/services/platform/workflow_engine.py:243-249` (`if isinstance(output, dict) and output.get("paused")`)。
    - 影响：handler 必须显式返回 `{"paused": True, "data": ...}` 才能 pause，契约不清晰；任何 handler 忘返 paused 字段即走 RUNNING 终态。
    - 修复成本：低
    - 建议：定义 `NodeOutput` dataclass 含 `paused: bool / branch: str / data: Any / error: str`；`handler.execute` 返回 `NodeOutput`。

17. **问题：Memory `_on_profile_updated` 把 `fields` dict 每个 key 写一条 FACT memory，patch 字段 5 个 = 5 条**
    - 位置：`backend/services/memory/subscribers.py:56-66`。
    - 影响：profile 更新频繁时 memory 表爆炸；同一 update event 应合并为 1 条。
    - 修复成本：低
    - 建议：合并 `content=json.dumps(fields)` 1 条 `EVENT` memory 而非 N 条 `FACT`。

18. **问题：Provider registry `notify` 5 通道 env-based 启用，但 `WAIBAO_SUPABASE_URL` 同时决定 feature_flag Supabase 启用，配置面有重叠**
    - 位置：`backend/providers/registry.py:249-288` (`get_notify_provider`)、`backend/services/platform/feature_flag.py:208-221` (`_init_remote`)。
    - 影响：运维需要分别理解 12 个 `*_PROVIDER` env + `*_ENABLED` env + Supabase env，可读性差。
    - 修复成本：低（文档）
    - 建议：写 `docs/PROVIDER_CONFIG.md` 总览；`providers/README.md` 加 cross-ref。

---

## 各维度详细评估

### A. EventBus（v6.0 / backend/eventbus/）

| 子项 | 状态 | 证据 |
|---|---|---|
| 30+ 事件类型覆盖 16 agent | 🟡 | 已发现 16 个 `emit_*` helper + 至少 30 个事件名（profile.* / needs.* / emotion.* / plan.* / market.* / journal.* / role.image.* / strategy.* / ticket.* / agent.* / workflow.* / config.* / plugin.* / metric.* / funnel.* / match.* / audit.* / preference.* / interview.* / offer.* / memory.* / multiagent.* / service.* / feature_flag.*）。16 个 agent 中 9 个有 emit 调用（emotion_agent, daily_journal_agent, intake_agent, vision_agent, clarifier_agent, talent_brief_agent, job_spec_agent, profile_agent, career_planner_agent, mutual_evaluator, hr_service_agent, employer_clarifier_agent, persona_agent, multi_party_agent, compliance_agent, policy_agent）；缺：evaluator/ 其它 4 个 jobseeker agent 仍 emit，但 emit_agent_started/completed 覆盖率 ~75% |
| 事件 schema 稳定性 | 🟡 | 无 Pydantic schema，依赖 docstring；字段漂移风险（如 `run_id` 在 agent.completed / multiagent.task.completed 含义不同）|
| 异步 vs 同步事件 | ✅ | `publish()` sync + `publish_async()` async 双 API；`asyncio.gather(*, return_exceptions=True)` 防一个 handler 阻塞全部 |
| 失败重试 | ❌ | 失败仅记 `self._errors`，无重试；无 DLQ |
| 死信队列 | ❌ | 完全缺失；Redis pub/sub fire-and-forget，订阅者离线时事件丢失 |
| 事件顺序保证 | 🟡 | 同步 publish 顺序保留（handlers 串行）；async `gather` 不保证；Redis pub/sub 跨进程顺序依赖 broker |
| 幂等性 | 🟡 | 依赖 handler 自实现（`memory/_on_*` 调用 `store.add` 不去重）；event_id 字段已提供但 consumer 普遍不查 |

### B. Plugin SDK（v6.0 / backend/plugins/sdk/）

| 子项 | 状态 | 证据 |
|---|---|---|
| 沙箱安全 (RestrictedPython / 资源限制) | ✅ | `RestrictedPython.compile_restricted` 优先 + AST audit fallback；`ResourceLimiter` RLIMIT_CPU/AS/NOFILE；`NetworkGuard` socket monkey-patch；`FilesystemGuard` open monkey-patch |
| 权限白名单 | ✅ | `_VALID_PERMS = 10 tokens`；`PluginRunner._check_permissions` 强制 host allowed ⊇ manifest |
| 隔离 (crash 不影响主进程) | ✅ | `install / enable / disable / uninstall` 全包 try/except；PluginState.ERROR 状态 |
| 签名验证 | ❌ | manifest.py 无签名字段；runner 无 sig 校验；私有化部署可被中间人替换 plugin.tar.gz |
| 版本管理 | 🟡 | semver 严格正则；无版本兼容性矩阵（plugin v2.0 加载 host v1.0 是否兼容未测） |
| 依赖管理 | 🟡 | manifest.dependencies list 仅声明，未在 install 时解析 / pip install |
| Windows 兼容 | ❌ | `ResourceLimiter._supported = sys.platform != "win32"`；Windows 私有化无 rlimit |

### C. Workflow Engine（v6.0 / backend/services/platform/workflow_engine.py）

| 子项 | 状态 | 证据 |
|---|---|---|
| DAG 验证 (无循环) | ❌ | `register()` 直接 append，无 Tarjan/Kahn；`_run()` 遇到环会 RecursionError |
| 状态持久化 | 🟡 | `InMemoryWorkflowStore` 是默认；接口可插拔，但无内置 Supabase 实现；生产需自实现 |
| 失败重试 | 🟡 | `_execute_node` try/except 把异常抛给 `_run`；整 workflow FAILED，无 node 级 retry |
| 暂停/恢复 | ✅ | `HumanNode` 输出 `{"paused": True}` → RunStatus.PAUSED；`resume(run_id, decision)` |
| 超时 | ❌ | `asyncio.wait_for` 未使用；HumanNode 阻塞 24h 不超时 |
| 监控 | ❌ | 无 Prometheus metrics；无 run 级 latency |
| 并发执行 | ❌ | `_execute_node` 当前顺序 fan-out；评论承认 "async parallel straightforward to add" |
| 多 workflow 并发 | ❌ | `remember()` 单实例，最后执行的 workflow 覆盖前一个 |

### D. RAG (LlamaIndex)（v7.0 / backend/services/rag/）

| 子项 | 状态 | 证据 |
|---|---|---|
| 文档解析准确度 | 🟡 | `DocumentParser` 实现未深读，但 ingest_text / ingest_file 接受多种 mime |
| chunking 策略 | ✅ | LlamaIndex `SentenceSplitter(chunk_size=512, overlap=50)` + fallback sentence + sliding window；CJK-aware token estimate (`一-鿿` count) |
| 检索准确度 > 85% | ❌ | `_mock_embed` 用 SHA-256 hash-bucket，不是语义模型；CI 无 RAGAS/Recall@K 基准测试 |
| 重排效果 | 🟡 | cross-encoder `BAAI/bge-reranker-large` 优先；fallback 是 `0.6*cosine + 0.3*coverage + 0.1*score` lexical 综合 |
| citation 完整性 | ✅ | `CitationFormatter.format()` 自动追加 Sources block；`highlight_tokens()` 给前端高亮 |
| 增量更新 | ❌ | `add()` 是 append-only，没有 `update_document(document_id, new_chunks)` |
| 多租户隔离 (RAG data by tenant_id) | ❌ | `Retriever.add(qdrant_collection=...)` 由调用方传名，无 tenant_id 命名空间校验；InMemoryStore 按 collection_id 过滤 OK，但 Qdrant collection 名不受控 |
| 流式生成 | 🟡 | `query_stream()` 80-char fake streaming，未接真实 OpenAI stream |

### E. Mem0 记忆（v7.0 / backend/services/memory/）

| 子项 | 状态 | 证据 |
|---|---|---|
| 实体抽取准确度 | ❌ | `EntityExtractor._extract_one` 全 regex（仅中英文若干固定句式）；`extract_async` 接 LLM 但默认无 llm 实例；`_PREFERENCE_PATTERNS / _FACT_PATTERNS / _EVENT_PATTERNS` 三类正则 |
| 跨 agent 记忆共享 | ✅ | `MemoryStore` 按 user_id 共享，5 个 eventbus subscriber (`profile.updated / preference.expressed / interview.completed / offer.received / memory.decay.requested`) 跨 agent 写入 |
| 衰减机制 | 🟡 | `decay_all(factor=0.95)` 全表扫描；`touch()` 访问 +0.05；Supabase 后端尝试 RPC (`memory_decay_all`) 失败则 fallback 线性 update；无定时调度器（`memory.decay.requested` event 触发） |
| 隐私删除 (GDPR) | ✅ | `forget(user_id, predicate, source_agent, type)` 支持多维度；记录 `memory_access_v2.action='forget'` |
| 多租户隔离 | 🟡 | `tenant_id` 列写入但 `query` 仅按 `user_id` 过滤；`list_for_user` 不带 tenant_id → 跨租户用户 UUID 冲突时泄漏；需 RLS 兜底（schema 已有，但 RLS 启用情况需审计） |
| 性能 | 🟡 | `SupabaseBackend.search` 是 in-process cosine，全表拉 → O(n)；无 pgvector RPC；>1k 行 P95 不可控 |
| Mem0 vendor client | 🟡 | `_try_mem0()` 导入失败则 None；`extract_via_mem0` fallback 到 `mem0_fallback` 简单 add；vendor 失败不报警 |

### F. Multi-Agent (CrewAI)（v7.0 / backend/services/multiagent/）

| 子项 | 状态 | 证据 |
|---|---|---|
| 4 个场景跑通 | 🟡 | `ScenarioKind.RESUME_SCORING / BIAS_REVIEW / OFFER_NEGOTIATION / STRATEGY_DECODE` 4 个；`build_pattern` 4 个 builder；`default_executor` 是 stub 不是真实 LLM，CI 通过 ≠ 真实场景跑通 |
| 角色分工明确 | ✅ | `RoleKind` enum: TECH_SCORER / CULTURE_SCORER / DOMAIN_SCORER / WRITER / BIAS_REVIEWER / REVIEWER / RESEARCHER / PM；每 scenario 在 `build_pattern` 显式分配 |
| 共识机制有效 | ✅ | 4 策略: `aggregate_majority / unanimous / weighted / quorum`；`_score_confidence` 加权平均；`_collect_votes` 收集 |
| 失败处理 | 🟡 | try/except 包整个 loop → 失败记 status='failed'，无 per-step retry；no_consensus 在 max_rounds 后 fallback |
| 长任务支持 | 🟡 | `aorchestrate` 用 `run_in_executor(None, self.orchestrate, ...)` 把同步 orchestrate 包装成 async，但默认 executor 是 sync |
| 异步协作 | ❌ | 4 个 pattern 都 sequential run；并行 (`PARALLEL`) 注释承认是 "logically independent" 但实现仍是顺序 |
| 记忆 + 事件 | ✅ | `_post_run` 写 `multiagent.task.completed` 事件 + MemoryStore 一条 summary |
| Hierarchical PM 分解 | 🟡 | `_run_pattern` HIERARCHICAL 分支用 PM 输出作为 sub_tasks，但 executor 输出格式未强校验；sub_tasks 字符串也接受 |

### G. Prompt v2 (Agenta)（v7.0 / backend/services/platform/prompt_v2.py）

| 子项 | 状态 | 证据 |
|---|---|---|
| 16 agent prompt 都版本化 | 🟡 | `InMemoryPromptRegistry` 通用；无证据 16 agent 各自动加载版本 prompt（需 grep `get_active_prompt` 调用方） |
| A/B 测试 | ✅ | `traffic_pct` 加权 bucket；`shift_traffic` 原子迁移；traffic 校验 `sum=100` (multi-active) |
| 评估机制 | 🟡 | `record_metric` 手动；4 维度 (accuracy/fluency/safety/bias) dataclass 完整；无自动 eval runner |
| 热更新 | ❌ | `_SERVICE` 单例；ConfigCenter `config.changed` event 未订阅；改 prompt 需重启 |
| 成本监控 | ❌ | 无 token / cost 字段；`render()` 是模板替换不调 LLM |

### H. Provider 抽象（12 维度 / 28+ 实现）

| 子项 | 状态 | 证据 |
|---|---|---|
| 真实 API 跑通 | 🟡 | 46 个 .py 实现包括 llm(7) embedding(3) vision(2) ocr(3) stt(2) notify(5) lookup(2) job_market / assessment / ats / background_check / sourcing / payment / video_interview；T1805/T1806 报告显示 ATS( Greenhouse/Lever ) / Zoom / Tencent Meeting / Beisen / Checkr 已对接；但 fallback 路径自动启用 |
| 失败降级到 mock | 🟡 | registry `_mock_provider(contract)` 默认；get_notify_provider 在 NOTIFY_*_ENABLED 不为 true 时走 mock；FeatureFlag cache miss 走 in-memory |
| 性能 | 🟡 | `with_resilience` 提供 cache → rate → circuit → retry → cost → metrics；circuit breaker 三态 + recovery_window；token bucket rate_per_sec + burst |
| 成本 | ✅ | `CostTracker` 支持 `tenant:date` + `tenant:date:provider:model` 双维度；`BudgetExceeded` 硬限；`_persist_cb` 异步写 Supabase |
| Circuit breaker | ✅ | 5 失败 → OPEN → 60s recovery → HALF_OPEN → 1 probe → CLOSED |
| Rate limit | ✅ | token bucket per provider |
| Metrics | ✅ | Prometheus `provider_calls_total` + `provider_latency_seconds`；缺 mock_fallback 分类（见 P1-11）|

---

## AI 能力成熟度矩阵

| 能力 | 形式覆盖 | 企业级 | 真实业务数据 | 评估 |
|---|---|---|---|---|
| RAG | ✅ | 🟡 | ❌ | 待做：embedding/reranker 真模型 + 多租户 + 增量更新 |
| Memory | ✅ | 🟡 | ❌ | 待做：LLM extractor + pgvector RPC + 多租户 RLS 验证 |
| Multi-Agent | ✅ | 🟡 | ❌ | 待做：注入 LLM executor + 4 场景真实跑通 + 并行 fan-out |
| Plugin | ✅ | 🟡 | ❌ | 待做：签名验证 + Windows 兼容 + 依赖解析 |
| Workflow | ✅ | 🟡 | ❌ | 待做：DAG cycle + 节点超时 + 监控 + 多 workflow 并发 |
| Feature Flag | ✅ | ✅ | 🟡 | 基本就绪：补 negative cache TTL |
| Config Center | ✅ | ✅ | 🟡 | 基本就绪：补 schema 校验 + bulk API |
| Service Toggle | ✅ | ✅ | 🟡 | 基本就绪：补 in-process registry 兜底 |
| Prompt v2 | ✅ | 🟡 | ❌ | 待做：eval runner + 热更新 + cost 字段 |
| EventBus | ✅ | 🟡 | ❌ | 待做：DLQ + 重试 + schema 注册表 |
| Provider | ✅ | 🟡 | 🟡 | 待做：mock_fallback 指标分类 + Provider 基类 |
| Embedding | ✅ | 🟡 | ❌ | 待做：CI 真模型 fixture |
| Vision | ✅ | 🟡 | 🟡 | 待做：跨模型一致性测试 |
| OCR | ✅ | 🟡 | 🟡 | 待做：表格/手写场景评估 |
| STT | ✅ | 🟡 | 🟡 | 待做：方言/多说话人评估 |
| LLM | ✅ | 🟡 | 🟡 | 待做：cache 命中率 + 跨 provider 路由 |

---

## 30/60/90 天改进建议

### 30 天（P0）
- P0-1：CI 引入轻量 embedding/reranker 真模型 fixture；新增 `test_rag_real_model.py` 召回断言
- P0-2：MultiAgent `Orchestrator` 默认 executor 改为 `llm_provider_executor`；新增 `test_multiagent_real_llm.py`
- P0-4：EventBus 接入 Redis Streams + DLQ；新增 `eventbus/schemas.py` Pydantic event payload 类
- P0-5：WorkflowEngine 加 Tarjan cycle detection + `asyncio.wait_for` 节点超时 + Prometheus metrics

### 60 天（P1）
- P0-3：Memory SupabaseBackend.search 切 pgvector RPC；新建 `054_memory_pgvector.sql`
- P1-6：Plugin SDK 加 SignatureVerifier + Windows Job Object polyfill
- P1-7：RAG `RagService` 加 `qdrant_collection_template="{tenant_id}__{collection_id}"` 强制命名空间
- P1-9：Prompt v2 eval runner 自动化 4 维度评估 + 订阅 `config.changed` 热更新
- P1-11：Provider with_resilience 增加 mock_fallback 指标分类

### 90 天（P2 + 持续）
- P2-13：RAG `query_stream` 接真实 LLM stream API
- P2-14：Plugin SDK 引入 `PluginSubprocessRunner`（multiprocessing.Process + SIGKILL）
- P2-17：Memory `_on_profile_updated` 合并为单条 EVENT memory
- 持续：所有 AI 子系统增加 Recall@K / F1 / A/B 业务指标 dashboard；建立 RAGAS / Mem0 benchmark 套件；编写 `docs/AI_INTEGRATION_PLAYBOOK.md` 涵盖插件签名 / RAG 评测 / 多 Agent 编排 / Prompt 调优 / 跨 tenant 隔离 SOP

---

## 附录：审查涉及文件清单

### A. EventBus (6 文件)
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/eventbus/base.py` (249 行) — EventBus ABC + InMemoryEventBus + RedisEventBus
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/eventbus/registry.py` (47 行) — 全局单例
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/eventbus/decorators.py` (119 行) — @on_event / emit / listen / await_event
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/eventbus/integration.py` (236 行) — 16 个 emit_* helper
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/eventbus/subscribers.py` (285 行) — 15 个 _register_* 跨切订阅器
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/eventbus/tests/test_eventbus.py`

### B. Plugin SDK (6 文件)
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/plugins/sdk/base.py` — Plugin ABC / PluginContext / PluginState / PluginRegistry
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/plugins/sdk/manifest.py` (137 行) — plugin.yaml schema + semver + 10 权限白名单
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/plugins/sdk/runner.py` (241 行) — PluginRunner + timeout + result
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/plugins/sdk/sandbox.py` (419 行) — 40+ 模块黑名单 + ResourceLimiter + NetworkGuard + FilesystemGuard
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/plugins/sdk/registry.py`
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/plugins/sdk/loader.py`

### C. Workflow / ConfigCenter / FeatureFlag / ServiceToggle / Feature Access
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/platform/workflow_engine.py` (287 行) — DAG + 6 状态 + pause/resume + InMemoryWorkflowStore
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/platform/config_service.py` (80+ 行片段) — 5 scope + 5 value_type + config.changed event
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/platform/feature_flag.py` (533 行) — 6 决策优先级 + 60s cache + SHA-256 bucket + Redis + audit
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/platform/service_toggle.py` (793 行) — 3 layer (status + plan + role + override) + 60s cache + audit + rollback + dependency check
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/platform/feature_access.py` (314 行) — check / require / batch_check / as_dependency / check_service_access / guard

### D. RAG (7 模块)
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/rag/service.py` (372 行) — RagService + IngestionResult + QueryResult
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/rag/retriever.py` (374 行) — Retriever + InMemoryStore + Qdrant + RRF + BM25
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/rag/chunker.py` (191 行) — SentenceSplitter + fallback
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/rag/embedder.py` (168 行) — Embedder + 3 模型 + hash fallback
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/rag/reranker.py` (119 行) — CrossEncoder + lexical fallback
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/rag/citation.py` (131 行) — Citation + token regex + sources block
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/rag/generator.py` + `document_parser.py` + `models.py`

### E. Memory (5 模块)
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/memory/store.py` (680 行) — MemoryStore + InMemoryBackend + SupabaseBackend + Mem0 vendor
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/memory/extractor.py` (155 行) — EntityExtractor + regex + LLM async
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/memory/injector.py` (85 行) — MemoryInjector + system prompt prepend
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/memory/subscribers.py` (147 行) — 5 cross-bus subscriber
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/memory/agent_adapter.py` + `models.py`

### F. Multi-Agent (4 模块)
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/multiagent/orchestrator.py` (519 行) — Orchestrator + Agent/Task/Crew shims + default_executor stub + _post_run
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/multiagent/patterns.py` (273 行) — 4 pattern + 4 scenario + build_pattern
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/multiagent/consensus.py` (237 行) — 4 strategy + 4 aggregator
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/multiagent/roles.py` — 8 RoleKind

### G. Prompt v2
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/platform/prompt_v2.py` (449 行) — InMemoryPromptRegistry + PromptService + traffic_pct + shift_traffic + render + diff

### H. Provider 抽象 (核心 4 文件 + 46 实现)
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/providers/base.py` (465 行) — with_resilience + RetryPolicy + CircuitBreaker + TokenBucket + CostTracker + ProviderMetrics
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/providers/registry.py` (357 行) — 9 get_*_provider factory + 12 维度
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/providers/exceptions.py`
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/providers/mock.py`
- 13 个子包: llm/embedding/vision/ocr/stt/notify/lookup/job_market/assessment/ats/background_check/sourcing/payment/video_interview（含 mock + 真实现）

### I. Agent 调用证据
- 9 个 agent emit 事件: emotion_agent, daily_journal_agent, intake_agent, vision_agent, clarifier_agent, talent_brief_agent, job_spec_agent, profile_agent, career_planner_agent, mutual_evaluator, hr_service_agent, employer_clarifier_agent, persona_agent, multi_party_agent, compliance_agent, policy_agent

---

**审查完成日期**：2026-07-13
**审查者**：v10.0 AI 集成审查 (T495)
**关联审查**：AUDIT_BACKEND.md / AUDIT_DATABASE.md / AUDIT_FRONTEND.md / AUDIT_SECURITY.md
