# 16 个智能体详解

## 📋 总览

本系统共有 **16 个智能体**,分布在 3 个领域:

| 领域 | 数量 | 名称 |
|---|---|---|
| 求职者侧 | 6 | Profile / Intake / DailyJournal / Emotion / Clarifier / CareerPlanner |
| 用人单位侧 | 9 | Persona / Compliance / Vision / TalentBrief / JobSpec / Policy / MultiParty / EmployerClarifier / HRService |
| 双向匹配 | 1 | MutualEvaluator |

所有智能体继承 `BaseAgent`,运行在统一底座上(`backend/agents/runtime.py`)。

---

## 🟦 求职者侧 (6 个)

### 1. Profile Agent — 画像采集 (1.1)

**文件**: `backend/agents/jobseeker/profile_agent.py`

**职责**: 通过对话采集求职者画像(姓名/学历/技能/经验)

**Prompt**:
```
你是温暖、专业的职业规划师,与求职者一对一交流。
目标: 了解基本信息和职业兴趣。
风格: 像朋友,一次只问 1-2 个问题。
```

**输出**:
```json
{
  "updated_profile": {...},
  "next_questions": ["能说说你的工作经历吗?"],
  "completion": 0.4,
  "warm_response": "好的,我记下了。"
}
```

**Memory**: 长期记忆 (`agent_memory.profile`)

---

### 2. Intake Agent — 建档引导 (1.1)

**文件**: `backend/agents/jobseeker/intake_agent.py`

**职责**: 引导式建档,文件上传,完成度跟踪

**阶段**:
- < 30%: 邀请上传简历
- 30-70%: 询问工作年限/技能
- 70-90%: 询问兴趣方向
- > 90%: 询问期望薪资/地点

**核心能力**:
- 文件 OCR (CV/证书/作品集)
- 邮箱/手机/技能自动抽取
- 完成度自动推进

---

### 3. DailyJournal Agent — 日记 + 评价 (1.2)

**文件**: `backend/agents/jobseeker/daily_journal_agent.py`

**职责**: 摄取日记,生成评价

**输入**: 当日工作内容/困惑/心得

**输出**:
```json
{
  "rating": "good | excellent | needs_improvement",
  "advice": "2-3 句建议",
  "warnings": ["风险点"],
  "action_items": ["明天的事"],
  "mood_score": -1.0~1.0,
  "topics": ["关键词"]
}
```

**持久化**: `daily_journals` 表

**前端显示**: `frontend/app/(jobseeker)/journal/page.tsx`

---

### 4. Emotion Agent — 情感接收 (1.4)

**文件**: `backend/agents/jobseeker/emotion_agent.py`

**职责**: LLM 情绪识别 + 共情回应

**核心能力**:
- 识别讽刺、复合情绪、隐含情绪
- 评估心理风险等级 (none/mild/moderate/severe)
- severe 时:推送钉钉 HR 群 + 建议专业咨询

**输出**:
```json
{
  "primary_emotion": "anxiety",
  "emotions": [
    {"name": "anxiety", "intensity": 0.7, "evidence": "项目延期"}
  ],
  "complexity": "mixed",
  "underlying_need": "需要被倾听",
  "risk_level": "moderate",
  "recommended_response_tone": "warm",
  "response": "听起来你今天不太好受..."
}
```

**持久化**: `emotion_timeline` 表

---

### 5. Clarifier Agent — 多步澄清 (1.5)

**文件**: `backend/agents/jobseeker/clarifier_agent.py`

**职责**: 多源画像综合 + 反思

**两阶段推理**:
1. **综合**: 聚合所有数据源(画像/日记/对话/情绪)→ profile_synthesis + real_needs
2. **反思**: LLM 审视自己输出,纠正过度解读

**输出**:
```json
{
  "profile_synthesis": {
    "summary": {"value": "...", "reasoning": "..."},
    "explicit_skills": [{"value": "Python", "reasoning": "..."}],
    "implicit_traits": [{"value": "学习能力强", "reasoning": "..."}]
  },
  "real_needs": {
    "explicit": [...],
    "implicit": [...],
    "must_haves": [...],
    "nice_to_haves": [...],
    "deal_breakers": [...]
  },
  "contradictions": [...],
  "follow_up_questions": [...],
  "reasoning_chain": ["synthesize", "reflect"]
}
```

**持久化**: `candidate_clarifications` 表

---

### 6. CareerPlanner Agent — 职业规划 (1.6)

**文件**: `backend/agents/jobseeker/career_planner_agent.py`

**职责**: 多层次职业规划

**输入**: 画像 + 真实需求 + 市场行情

**输出**:
```json
{
  "short_term": [{"title": "...", "duration": "2 周", "priority": "high"}],
  "mid_term": [{"title": "...", "duration": "3 个月", "milestone": "..."}],
  "long_term": [{"title": "...", "duration": "3 年", "outcome": "..."}],
  "learning_paths": [{"topic": "...", "resources": [...]}],
  "recommended_roles": [...],
  "skill_gaps": [...],
  "market_insights": {"salary_trends": {...}, "hot_skills": [...]}
}
```

**市场行情源**: MVP mock,生产接招聘网站 API

**持久化**: `career_plans` 表

---

## 🟧 用人单位侧 (9 个)

### 7. Persona Agent — 真诚 HR 人格 (2.1 / 2.9)

**文件**: `backend/agents/employer/persona_agent.py`

**职责**: HR 通用问答,边界感

**Prompt**:
```
你是用人单位的"真诚HR"人格化身。
性格: 专业、有同理心、不卑不亢。
边界: 涉及工资/个税/解雇 → 建议联系直线 HR。
```

---

### 8. Compliance Agent — 资质审核 (2.2)

**文件**: `backend/agents/employer/compliance_agent.py`

**职责**: OCR + 工商查询 + trust_score

**流程**:
1. OCR 提取字段
2. 调用 `company_lookup` 工商查询
3. LLM 综合判定
4. 计算 `trust_score` (0~1)
5. 标记缺失材料

**持久化**: `company_credentials` 表

---

### 9. Vision Agent — 战略解码 (2.3)

**文件**: `backend/agents/employer/vision_agent.py`

**职责**: 把老板口述解构为 4 层

**4 层**:
- Vision (3-5 年想成为什么)
- Planning (1 年方向)
- Strategy (年度重点)
- Tactic (季度动作)

**持久化**: `company_strategy` 表 (含 parent_id 层级)

---

### 10. TalentBrief Agent — 人才框架 (2.4)

**文件**: `backend/agents/employer/talent_brief_agent.py`

**职责**: 提取老板描述 + LLM 偏见检测

**调用** `detect_biases` 让 LLM 自己发现:
- demographic_bias (年龄/性别/学历/婚育/地域)
- cognitive_bias (光环/锚定/确认偏误)
- implicit_requirements
- fairness_score

**委婉提醒示例**:
> 我注意到几个可能值得重新考虑的地方:
> - 性别: "只要男的"可能扩大 50% 候选人池
> - 学历: 985/211 限制可能错过同等能力人才
> 我不是指责,而是想帮您扩大候选人池...

---

### 11. JobSpec Agent — JD 细化 (2.5)

**文件**: `backend/agents/employer/job_spec_agent.py`

**输入**: 部门负责人口语化描述

**输出**: 结构化 JD + 过度要求检测

**支持的 over_spec_flags**:
- 5 年经验 + 985 学历 + 35 岁以下 → 过于严苛
- 10 项必备技能 → 实际可能 5 项就够
- 加分项数量过多 → 反映部门认知模糊

**持久化**: `roles.required_skills` + `preferred_skills`

---

### 12. Policy Agent — 规章制度 (2.6)

**文件**: `backend/agents/employer/policy_agent.py`

**双模式**:
- **upload**: 解析制度,分类(考勤/请假/报销/晋升等),入库 + 检测法律风险
- **query**: 求职者/HR 查询,从 DB 检索并生成 FAQ 风格回答

**持久化**: `company_policies` (含 pgvector embedding,准备 RAG)

---

### 13. MultiParty Agent — 多方协调 (2.7)

**文件**: `backend/agents/employer/multi_party_agent.py`

**输入**: 老板/HR/部门负责人/财务各方意见

**输出**:
- 各方立场摘要
- 立场冲突识别
- 折中方案
- 决策汇总

---

### 14. EmployerClarifier Agent — 用人方澄清 (2.8)

**文件**: `backend/agents/employer/employer_clarifier_agent.py`

**整合**: 老板 brief + 部门 spec + 合规要求 + 制度约束

**输出**:
- 所需人才清晰画像 (talent_image)
- 岗位真实需求 (real_needs: explicit + implicit + must + nice)
- 多方共识度 (consensus_score)

**持久化**: `employer_clarifications` 表

---

### 15. HRService Agent — 全生命周期 (2.9)

**文件**: `backend/agents/employer/hr_service_agent.py`

**覆盖 6 个阶段**:
- recruiting
- onboarding
- training
- performance
- promotion
- offboarding

**自动检测阶段**: 关键词匹配(`面试`→recruiting, `入职`→onboarding 等)

**边界**: 涉及个人隐私/纪律 → 建议联系直线 HR

---

## 🟩 双向匹配 (1 个)

### 16. MutualEvaluator Agent — 双方互评

**文件**: `backend/agents/evaluator/mutual_evaluator.py`

**输入**: 求职者评分 + 用人方评分(各 4 维度)

**输出**:
```json
{
  "mutual_score": 0.75,
  "strengths": ["共识优势"],
  "concerns": ["共识顾虑"],
  "recommendation": "proceed | hold | reject",
  "next_steps": [...]
}
```

**配套算法**: `backend/matching/two_way.py` (双向打分 + 调和值)

---

## 🧠 共享能力

### Semantic Router
```python
# 启动时: 计算 16 个 agent 的"意图向量"
await semantic_router.warmup()

# 路由: 输入文本 → 最匹配的 agent
results = await semantic_router.route("我今天心情很差", top_k=3)
# [{agent: "emotion_agent", score: 0.92}, ...]
```

### ReAct Framework
```python
class MyAgent(ReActAgent):
    async def _handle(self, input):
        for iteration in range(max_iterations):
            # Thought + Action via LLM
            # Tool call
            # Observation
            # Reflect or FinalAnswer
```

### LLM Extractors
```python
# 删除所有正则/词典,统一走 LLM
await extract_resume(llm, cv_text)
await detect_emotion(llm, text)
await detect_biases(llm, text)
await understand_intent(llm, text, agent_descriptions)
await synthesize_profile(llm, sources)
```

---

## 📊 Agent 调用统计

```
求职者日均调用 (单人)   : 5-10 次
用人单位日均调用 (单组织) : 20-50 次
匹配计算日均调用 (单匹配) : 2-5 次
LLM tokens/天/用户 (估算) : 5k-20k
```

---

## 🔧 扩展 Agent

新加一个 Agent:

1. 在 `backend/agents/{domain}/` 下创建 `xxx_agent.py`
2. 继承 `BaseAgent` 或 `ReActAgent`
3. 实现 `name`/`description`/`required_personas`/`async _handle`
4. 在 `boot.py` 注册
5. 在 `semantic_router.py::AGENT_INTENT_DESCRIPTIONS` 添加意图描述

详细示例见 `backend/agents/jobseeker/emotion_agent.py`。

---

## 🔌 每个 Agent 现在走哪个 Provider

v2.0 引入统一 Provider 抽象层后,所有 Agent 都通过 `agents.runtime.LLMClient` 调用 LLM,
LLMClient 内部再走 `providers.registry.get_llm_provider()`,由 ENV 决定具体供应商。

| Agent | LLM 调用 | Embedding | OCR / Vision | Notify |
|---|---|---|---|---|
| **Profile** (jobseeker) | `LLMClient` → `LLM_PROVIDER` | — | — | — |
| **Intake** (jobseeker) | `LLMClient` → `LLM_PROVIDER` | — | — | — |
| **DailyJournal** (jobseeker) | `LLMClient` → `LLM_PROVIDER` | — | — | — |
| **Emotion** (jobseeker) | `LLMClient` → `LLM_PROVIDER` | — | — | severe 时通过 `notify_dispatcher` 走 `NOTIFY_*` |
| **Clarifier** (jobseeker) | `LLMClient` → `LLM_PROVIDER` | — | — | — |
| **CareerPlanner** (jobseeker) | `LLMClient` → `LLM_PROVIDER` | — | — | — |
| **Persona** (employer) | `LLMClient` → `LLM_PROVIDER` | — | — | — |
| **Compliance** (employer) | `LLMClient` → `LLM_PROVIDER` | — | `OCR_PROVIDER` (主) + `VISION_PROVIDER` (兜底) | — |
| **Vision** (employer) | `LLMClient` → `LLM_PROVIDER` | — | `VISION_PROVIDER` (gpt4v / qwen_vl) | — |
| **TalentBrief** (employer) | `LLMClient` → `LLM_PROVIDER` | — | — | — |
| **JobSpec** (employer) | `LLMClient` → `LLM_PROVIDER` | — | — | — |
| **Policy** (employer) | `LLMClient` → `LLM_PROVIDER` | — | — | — |
| **MultiParty** (employer) | `LLMClient` → `LLM_PROVIDER` | — | — | — |
| **EmployerClarifier** (employer) | `LLMClient` → `LLM_PROVIDER` | — | — | — |
| **HRService** (employer) | `LLMClient` → `LLM_PROVIDER` | — | — | 关键事件走 `notify_dispatcher` |
| **MutualEvaluator** (evaluator) | `LLMClient` → `LLM_PROVIDER` | — | — | — |

### 共享 service 层 Provider 路由

| Service / Pipeline | 调用的 Provider | ENV 标识 |
|---|---|---|
| `services/notify/dispatcher.py` | `get_notify_provider(channel)` | `NOTIFY_<CHANNEL>_ENABLED` |
| `services/resume_parser.py` | `get_ocr_provider()` + `get_vision_provider()` (兜底) | `OCR_PROVIDER` / `VISION_PROVIDER` |
| `services/compliance_service.py` | `get_lookup_provider()` | `LOOKUP_PROVIDER` |
| `services/credit_code_validator.py` | (纯 Python,无外部依赖) | — |
| `services/file_storage.py` | (Supabase Storage,不走 provider 层) | — |
| `services/ticket_service.py` | (数据库 CRUD,无外部依赖) | — |
| `agents/semantic_router.py` | `get_embedding_provider()` | `EMBEDDING_PROVIDER` |
| `agents/llm_extractor.py` | `LLMClient` → `get_llm_provider()` | `LLM_PROVIDER` |
| `agents/runtime.py::LLMClient` | `get_llm_provider()` | `LLM_PROVIDER` |

### ENV 切换示例

```bash
# 默认 (开发 / 单测)
LLM_PROVIDER=mock
EMBEDDING_PROVIDER=mock
OCR_PROVIDER=mock
VISION_PROVIDER=mock
LOOKUP_PROVIDER=mock
NOTIFY_SMTP_ENABLED=false
NOTIFY_DINGTALK_ENABLED=false
NOTIFY_FEISHU_ENABLED=false
NOTIFY_WECOM_ENABLED=false
NOTIFY_WEBHOOK_ENABLED=false

# 生产 (OpenAI + 钉钉)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxx
EMBEDDING_PROVIDER=openai
NOTIFY_DINGTALK_ENABLED=true
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxx

# 国内合规 (通义 + 腾讯云 OCR + 飞书)
LLM_PROVIDER=tongyi
DASHSCOPE_API_KEY=sk-xxx
EMBEDDING_PROVIDER=tongyi
OCR_PROVIDER=tencent
TENCENT_SECRET_ID=xxx
TENCENT_SECRET_KEY=xxx
LOOKUP_PROVIDER=tianyancha
TIANYANCHA_API_KEY=xxx
NOTIFY_FEISHU_ENABLED=true
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
```

---

## 🆕 v3.0 新增智能体能力

### 👤 Persona Memory (用人方画像记忆)

`PersonaAgent` 在 v3.0 增加**长期偏好记忆**,每次老板/HR 与 Agent 互动时:
- 记录 "老板不喜欢的关键词"(如 "加班文化"、"出差 50%")
- 记录 "老板特别看重的特质"(如 "985 毕业"、"5 年以上管理经验")
- 自动在后续 JD 生成、TalentBrief、面试问题中过滤 / 加权
- "升级人工" 按钮让老板一键把当前对话转给 HRBP,自动建工单

存储:`persona_memory` 表(user_id PK, organization_id, preferences JSONB, last_updated)

### 💬 协同房间 (Multi-Party + 实时协作)

`MultiPartyAgent` v3.0 引入**多人实时协同房间**:
- 老板 + HR + 部门负责人 + 外部猎头可在同一个 room 讨论一个候选人
- WebSocket 实时消息 + 线程回复 + emoji 反应
- `@mention` 触发通知(走 `NotifyDispatcher` 的钉钉/飞书/邮件通道)
- 关键决策(如"约面试")自动生成 Ticket 并关联回房间
- API:`/api/rooms`、`/api/rooms/{id}/messages`(REST + WS 双通道)

实现:`services/collaboration_room.py`(纯函数式 + supabase client)

### ⚖️ 自动权重校准 (Feedback Loop → 权重)

`MutualEvaluator` v3.0 增加**自动权重学习回路**:

1. **每日调度**:`services/feedback_loop.py::daily_scheduler()`
   - 拉过去 7 天所有 `placement_made` / `match_dismissed` 信号
   - 按角色、行业、级别分组,统计每维度的"实际有用度"
2. **权重调整**:对每个分组的 `CompositeScorer` 权重做小幅 +/- 调整
   - 用法:weights × adjustment_factor (clamp 0.5 ~ 2.0)
   - 写回 `weight_settings` 表,带审计 trail
3. **A/B 验证**:调整后的权重先以 10% 流量灰度
4. **人工监督**:Admin 在 `/admin/matching-quality` 看 Precision/Recall 曲线,可一键回滚

风险:每天最多 ±5% 调整,带 cooldown 防抖动。

### 📊 匹配质量 Dashboard (admin/matching-quality)

- Precision / Recall / F1 按周/月趋势
- Bucket 分布(分数段 vs 真实命中率)
- 与人工评分的偏差(BiasMonitor)
- 自动生成 "建议调整维度" 报告

路由:`/api/admin/matching-quality/*`

更多示例见 [`backend/providers/README.md`](../talent-tool-mvp/backend/providers/README.md) 与 [`docs/ARCHITECTURE.md`](./ARCHITECTURE.md) 的 Providers 抽象层章节。
---

## v4.0 — 新增能力 Agent / Service 集成

v4.0 新增的不再是 Agent (智能体数量仍为 16), 而是 **业务 Service / Provider**, 通过 MCP / REST 与现有 Agent 协作:

### 1. AI 自动面试服务 (`services/ai_interviewer.py`)
- 启动会话 → 推题 (按 role/level 匹配) → 答题 (视频 / 文本) → LLM 评分 → 生成报告
- 关联 Agent: HRService Agent (面试流程编排)
- 关联 Provider: Zoom / 腾讯会议 (视频录制)

### 2. Offer 计算 + 谈判 (`services/offer_calculator.py`, `services/negotiation_advisor.py`)
- 多 Offer 总包比较 (汇率 / 税 / 折现统一到 CNY)
- 行业百分位 (market band)
- LLM 谈判脚本生成
- 关联 Agent: CareerPlanner Agent (求职者侧) / HRService Agent (雇主侧)

### 3. 招聘漏斗 + 渠道 ROI (`services/recruitment_funnel.py`, `services/channel_attribution.py`)
- 5 阶段 (applied / screen / onsite / offer / hired) 转化率
- 渠道 ROI: cost / hire × channel
- 关联 Agent: HRService Agent

### 4. 候选人订阅 + 推荐 (`services/job_subscription.py`, `services/candidate_recommender.py`)
- 关键词 + 地点 + 薪资匹配
- embedding-based 推荐
- 实时推送 (push_engine)
- 关联 Agent: Profile Agent / Intake Agent

### 5. 视频面试 (`services/video_interview_service.py`)
- Zoom / 腾讯会议 自动创建
- 录制回传 + 转写
- 关联 Agent: HRService Agent

### 6. 测评 (`services/assessment_service.py`)
- 北森 测评邀请 + 结果回传
- 分数加权到匹配引擎
- 关联 Agent: MutualEvaluator

### 7. 背调 (`services/background_check_service.py`)
- Checkr 触发 (offer 前)
- 状态查询 + webhook
- 关联 Agent: HRService Agent / Compliance Agent

### 8. ATS 双向同步 (`services/ats_sync.py`)
- Greenhouse / Lever 双向候选人 / 职位同步
- 冲突解决 (本地 vs remote)
- 关联 Agent: HRService Agent

### 9. 计费 (`services/billing.py`)
- Stripe / 微信 / 支付宝 订阅
- 配额 + 用量
- 关联: Pilot / 商业化
