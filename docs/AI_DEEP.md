# v7.0 AI 能力深解 — RAG / Multi-Agent / Memory / Fine-tuning

> Audience: 工程师 + AI 应用架构师
>
> 本文档专门讲清 v7.0 引入的四大 AI 子系统的**实现路径 + 关键参数 + 失败模式**。架构总览见 [ARCHITECTURE.md](./ARCHITECTURE.md)。

---

## 1. RAG — 完整检索增强生成 (T2701)

### 1.1 流水线

```
                        ┌────────────────┐
       PDF/Word/MD ──► │ DocumentParser │ ──► sections[]
                        └────────────────┘
                                │
                                ▼
                        ┌────────────────┐
                        │   Chunker      │ ──► chunks[] (300-800 tokens)
                        │ (semantic)     │      + overlap 80
                        └────────────────┘
                                │
                                ▼
                        ┌────────────────┐
                        │  Embedder      │ ──► vectors[] (1024-d)
                        │ (BGE-M3 / 智谱)│
                        └────────────────┘
                                │
                                ▼
                        ┌────────────────┐
                        │  Qdrant        │ ──► indexed
                        │ (per-tenant)   │
                        └────────────────┘

  Query ──► QueryRewrite ──► HybridSearch (BM25 + dense) ──► Reranker ──► Top-K
                                                                          │
                                                                          ▼
                                                                  LLM w/ citations
```

### 1.2 关键参数 (默认)

| 参数 | 值 | 调整建议 |
|---|---|---|
| `chunk_size` | 512 tokens | 长文档增到 1024;短 FAQ 降到 256 |
| `chunk_overlap` | 80 tokens | 维持 15-20% overlap |
| `embedding_dim` | 1024 (BGE-M3) | 多语言场景保持 1024 |
| `top_k` (recall) | 50 | 50 给 reranker 充足候选 |
| `top_k` (final) | 5 | 输出给 LLM 5 段 |
| `reranker` | BGE-reranker-v2-m3 | 中文场景用 BCE |
| `min_relevance` | 0.35 | 低于此分返回"我不知道" |
| `citation_required` | true | 强制每段含 `doc_id` + `page` |

### 1.3 实现位置

- 流水线:`backend/services/rag/` (LlamaIndex 包装)
- 检索:`backend/services/rag/retrieval.py` — hybrid BM25 + dense
- 重排:`backend/services/rag/reranker.py` — BCE / BGE-reranker
- 文档解析:`backend/services/rag/parser.py` — pypdf + python-docx + markdown
- 测试:`tests/test_rag.py` (50+ 测试)

### 1.4 失败模式 & 对策

| 模式 | 症状 | 对策 |
|---|---|---|
| 检索幻觉 | LLM 用错文档 | 强制 `citation_required`,citation 不在检索结果中 → 拒答 |
| 分块切断语义 | 答案残缺 | `SemanticChunker` 按段落/标题切,不用定长 |
| 多语言混淆 | 中英混合回答差 | 多语言 embedding (BGE-M3) + locale-aware reranker |
| 长文档超窗 | LLM 截断 | Map-Reduce:分而治之再合并 |
| 召回过低 | Top-K 全无关 | `min_relevance` 兜底 + 多路召回 |
| Embedding 漂移 | 旧文档命中率低 | 季度重建索引 |

### 1.5 评估指标

```
recall@5  ≥ 0.85
mrr@10    ≥ 0.70
citation_accuracy ≥ 0.95
answer_relevance  ≥ 4.0/5 (LLM-as-judge)
```

黄金测试集:`backend/services/rag/gold_standard.jsonl`,每 PR 跑回归。

---

## 2. Agent Memory — 统一记忆库 (T2702)

### 2.1 三层架构

```
┌─────────────────────────────────────────┐
│  Short-term  (会话上下文,Redis)          │  TTL: 30 min
│  └─ 原始 messages / tool calls           │  < 1ms read
└────────────┬────────────────────────────┘
             │ (memory summarizer)
             ▼
┌─────────────────────────────────────────┐
│  Working  (Mem0 + 向量,Qdrant)           │  TTL: 30 days
│  └─ 摘要 + 实体 + 偏好                   │  ~10ms recall
└────────────┬────────────────────────────┘
             │ (importance scorer)
             ▼
┌─────────────────────────────────────────┐
│  Long-term  (Neo4j 知识图谱 + Postgres)  │  永久
│  └─ 关系 + 时间线 + 偏好趋势             │  ~50ms recall
└─────────────────────────────────────────┘
```

### 2.2 跨 Agent 共享

任何 Agent 写入记忆时,`memory_id` 命名空间 = `tenant_id + user_id`,
所有同租户同用户 Agent 可读;不同租户硬隔离 (RLS)。

### 2.3 关键参数

| 参数 | 值 | 含义 |
|---|---|---|
| `importance_threshold` | 0.6 | 低于此分不进 long-term |
| `dedup_cosine` | 0.92 | 高于此相似度合并,不新建 |
| `max_chunks_per_recall` | 8 | 每次注入 LLM 的最大块数 |
| `summarize_every_n` | 10 | 每 10 轮消息做一次摘要 |

### 2.4 实现位置

- 写入:`backend/services/memory/writer.py`
- 读取:`backend/services/memory/reader.py`
- 摘要:`backend/services/memory/summarizer.py`
- 实体抽取:`backend/services/memory/entity_extractor.py` (LLM)
- 测试:`tests/test_memory.py`

---

## 3. Multi-Agent 协作 (T2703)

### 3.1 拓扑

v7.0 支持 4 种协作模式,任务自动选择:

```
Sequential ──► A → B → C          (依赖链,简单)
Parallel   ──► A,B,C ──► merge    (独立子任务)
Hierarchical ► Planner → workers (层级,复杂)
Consensus  ──► A,B,C → vote(2/3) (关键决策)
```

### 3.2 角色示例

```python
from crewai import Agent

recruiter = Agent(
    role="Senior Recruiter",
    goal="找到最匹配的候选人",
    backstory="10 年技术招聘经验",
    tools=[search_candidates, score_resume],
    llm="gpt-4o",
)

hiring_manager = Agent(
    role="Hiring Manager",
    goal="评估技术匹配度",
    backstory="前 Google 工程师",
    tools=[score_technical, lookup_skill],
    llm="claude-3.5-sonnet",
)

hrbp = Agent(
    role="HR Business Partner",
    goal="评估文化匹配 + 薪资合理性",
    tools=[salary_benchmark, culture_check],
    llm="deepseek-chat",
)
```

### 3.3 共识机制 (关键决策)

```python
def offer_decision(candidate: Candidate, role: Role):
    verdicts = [
        recruiter.vote(candidate, role),       # hire / no_hire / maybe
        hiring_manager.vote(candidate, role),
        hrbp.vote(candidate, role),
    ]
    counts = Counter(verdicts)
    winner, n = counts.most_common(1)[0]
    if n >= 2:                                 # ≥ 2/3
        return Decision(winner, consensus=True, votes=verdicts)
    return Decision("needs_more_info", consensus=False, votes=verdicts)
```

### 3.4 失败模式

| 模式 | 对策 |
|---|---|
| Agent 死循环 | max_iterations=10 + circuit breaker |
| 投票僵局 | escalate_to: "human_review" |
| 上下文爆炸 | 只传摘要 + top-5 记忆给每个 Agent |
| 成本失控 | per-Agent token budget + early stop |

### 3.5 实现位置

- `backend/services/multiagent/` (CrewAI wrapper)
- `backend/services/multiagent/voting.py` (consensus)
- `backend/services/multiagent/orchestrator.py`
- 前端:`frontend/components/multiagent/` + `/multiagent/*` 页面
- 测试:`tests/test_multiagent.py`

---

## 4. Prompt v2 — 版本化 + A/B + 评估 (T2704)

### 4.1 数据模型

```
PromptRegistry:
  id: "profile_clarifier_v3"
  versions: [
    { v: 1, prompt: "...", traffic: 0%, status: deprecated },
    { v: 2, prompt: "...", traffic: 10%, status: shadow },
    { v: 3, prompt: "...", traffic: 90%, status: active },
  ]
  metrics: { latency_p50, success_rate, llm_judge_score }
```

### 4.2 评估 (LLM-as-judge)

```python
from services.platform.evaluator import judge_output, default_runner

verdict = judge_output(
    prompt_id="profile_clarifier_v3",
    candidate=golden_case,
    output=model_output,
    judge_model="claude-3.5-sonnet",
    runner=default_runner,   # calls LLM with structured rubric
)
# verdict: { score: 4.2, reasoning: "...", dimensions: {...} }
```

### 4.3 自动评估流水线

```
PR 创建
   │
   ▼
CI 跑 gold_standard_suite (50 cases)
   │
   ▼
LLM-as-judge 评分
   │
   ├─ score ≥ baseline - 5% → merge allowed
   └─ score < baseline - 5% → block merge + comment
```

### 4.4 实现位置

- `backend/services/platform/prompt_v2.py` (registry)
- `backend/services/platform/evaluator.py` (LLM-as-judge)
- 前端:`frontend/app/admin/prompts/` (版本对比 + A/B 流量调节)
- 测试:`tests/test_prompt_v2.py` + `tests/test_evaluator.py`

---

## 5. Fine-tuning (LoRA) (T3001)

### 5.1 流水线

```
历史会话 (脱敏)        黄金标注
       │                  │
       ▼                  ▼
  prepare_all.py    →  data/*.jsonl (Alpaca format)
                            │
                            ▼
                   LLaMA-Factory train  (QLoRA, 4bit)
                            │
                            ▼
                   outputs/{task}/adapter.safetensors
                            │
                            ▼
                   vLLM serve --enable-lora --lora-modules ...
                            │
                            ▼
                   providers/llm/custom_lora.py → OpenAI-compatible
```

### 5.2 关键参数 (默认)

```yaml
# LLaMA-Factory config
model_name_or_path: Qwen2.5-7B-Instruct
quantization_bit: 4        # QLoRA
lora_rank: 16
lora_alpha: 32
learning_rate: 1e-4
num_train_epochs: 3
per_device_train_batch_size: 4
gradient_accumulation_steps: 4
max_seq_length: 4096
bf16: true
```

### 5.3 显存估算

| 模型 | 精度 | 显存 (LoRA 训练) |
|---|---|---|
| Qwen2.5-7B | QLoRA-4bit | ~16 GB |
| Llama-3-8B | QLoRA-4bit | ~16 GB |
| Qwen2.5-14B | QLoRA-4bit | ~24 GB |
| Qwen2.5-32B | QLoRA-4bit | ~48 GB |

### 5.4 何时 Fine-tune

- 高频任务 (>1k 次/月) → 值得 LoRA
- 低频但高精度要求 → 提示工程 / RAG 更划算
- 多语言 / 垂直行业术语 → LoRA 明显有效

### 5.5 实现位置

- `backend/providers/llm/custom_lora.py` (OpenAI 兼容客户端)
- `backend/services/training/` (数据准备 + 训练触发)
- `infra/training/docker-compose.yml`
- 测试:`tests/test_training.py`

---

## 6. AI Sourcing (T3002)

### 6.1 出站寻才

GitHub / LinkedIn (合规抓取) / 内推 / 沉睡库激活 多通道并行,由
SourcingAgent 统一编排:

```
Role.requirements
      │
      ▼
Query Generation (LLM) ──► 多个 keyword + 多语言
      │
      ├──► GitHub Search API
      ├──► 内推系统 (referral graph)
      ├──► 沉睡库 (rediscovery)
      └──► 公司评价 (glassdoor style)
      │
      ▼
   Dedupe + Score
      │
      ▼
   Outreach Draft (LLM, 多语言 + 个性化)
      │
      ▼
   HR Review → Send
```

### 6.2 实现位置

- `backend/providers/sourcing/` (GitHub / 模拟数据源)
- `backend/services/platform/sourcing_agent.py`
- 测试:`tests/test_sourcing.py`

---

## 7. 横向对比:选哪个?

| 需求 | 首选 | 兜底 |
|---|---|---|
| FAQ / 知识库问答 | RAG | 提示工程 |
| 多步决策 (offer / 拒信) | Multi-Agent Consensus | 单 Agent + 人工 |
| 跨会话偏好 | Memory | 单轮 prompt |
| 行业垂直术语 | LoRA + RAG | 提示工程 + 术语表 |
| 主动外联 | Sourcing Agent | 模板邮件 |
| 实时语音 | GPT-4o Realtime | Whisper ASR + TTS |

---

## 8. 监控 + 成本

每个 AI 调用都打点:
- `ai_request_total{agent, model, status}` (Prometheus counter)
- `ai_request_duration_seconds` (histogram)
- `ai_token_cost_usd` (counter, 按 model 单价)
- `ai_rag_citation_rate` (gauge)
- `ai_memory_recall_p95_ms` (gauge)
- `ai_multigent_consensus_rate` (gauge)

成本上限:per-tenant daily budget,超额自动降级 (RAG → 短 prompt → cache hit)。