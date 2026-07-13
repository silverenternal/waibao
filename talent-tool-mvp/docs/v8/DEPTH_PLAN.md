# v8.0 "16 项需求做透" 方案 (DEPTH_PLAN)

> **作者**: waibao v8.0 架构师
> **日期**: 2026-07-13
> **基础**: v7.0 已完成 16 Agent + 12 维度 Provider + 2300+ tests
> **目标**: 把 16 项需求从"能用"做到"透"
> **不包含**: LoRA 训练 (用户明确排除)

---

## 0. 总体策略

### 0.1 "做透" 的 4 个维度

| 维度 | 含义 | 衡量指标 |
|---|---|---|
| **深度 (Depth)** | 模型/算法层超越第一版 | 准确率 +10pp, 召回 +15pp |
| **闭环 (Loop)** | 每个需求有反馈回路, 越用越好 | A/B 指标环比提升 |
| **个性化 (Persona)** | 不再千篇一律, 因人而异 | 用户留存 +20% |
| **可运营 (Operable)** | PM/QA 可配置, 不靠研发 | 运营自助率 > 80% |

### 0.2 16 项需求清单 (按客户视角)

**求职者侧 (6)**
1.1 知心朋友
1.2 评价
1.3 频繁/主动服务
1.4 情绪关怀
1.5 画像确认
1.6 规划追踪

**用人单位侧 (9)**
2.1 个性化 HR
2.2 假资质检测
2.3 战略传达
2.4 偏见纠正
2.5 JD 营销
2.6 制度 AI 解释
2.7 多方协同
2.8 共识度
2.9 主动 HR

**匹配 (1)**
3 命中率提升

---

## 1. 求职者侧 (6 项)

### 1.1 知心朋友 (Phase 2: Relationship Engine)

**做透目标**: 不是"AI 工具",是"记得住你的朋友"。

#### 1.1.1 关系系统 (Relationship State Machine)

```python
# backend/services/jobseeker/relationship_state.py
from enum import Enum
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List

class RelationshipPhase(str, Enum):
    STRANGER    = "stranger"      # 0-3 天, 礼貌但谨慎
    ACQUAINTANCE = "acquaintance" # 3-30 天, 主动但不越界
    FRIEND      = "friend"        # 30+ 天 + 5+ 深度对话
    BUDDY       = "buddy"         # 60+ 天 + 关键事件纪念
    COLD        = "cold"          # 沉默 30 天, 重启后回到 ACQUAINTANCE

@dataclass
class RelationshipContext:
    user_id: str
    phase: RelationshipPhase
    last_deep_talk_at: Optional[datetime]
    last_interaction_at: datetime
    cumulative_deep_talks: int  # 触发 FRIEND 的关键对话数
    notable_moments: List["Moment"] = field(default_factory=list)
    dry_period_started_at: Optional[datetime] = None

    def recalculate(self):
        """每次交互后调用"""
        now = datetime.utcnow()
        days_silent = (now - self.last_interaction_at).days

        # 关系升级
        if days_silent > 30:
            self.phase = RelationshipPhase.COLD
            self.dry_period_started_at = now
        elif self.cumulative_deep_talks >= 10 and (now - self.last_deep_talk_at).days >= 14:
            self.phase = RelationshipPhase.BUDDY
        elif self.cumulative_deep_talks >= 5 and (now - self.last_interaction_at).days >= 7:
            self.phase = RelationshipPhase.FRIEND
        elif (now - self.created_at).days >= 3:
            self.phase = RelationshipPhase.ACQUAINTANCE


@dataclass
class Moment:
    """关键时刻 - 服务于此人"""
    user_id: str
    type: str  # "promotion" | "breakup" | "first_offer" | "interview_pass" | ...
    date: datetime
    summary: str           # "收到某厂 offer, 年包 35w"
    sentiment: str         # "positive" | "neutral" | "negative"
    stored_in_mem0: bool = False
```

#### 1.1.2 主动 push (Proactive Scheduler)

```python
# backend/services/jobseeker/proactive_scheduler.py

class ProactiveScheduler:
    """基于关系状态 + 时间窗 + 触发规则的主动 push"""

    # 每 30 分钟扫一轮 (cron)
    async def tick(self):
        candidates = await db.fetch("""
            SELECT user_id FROM relationship_context
            WHERE phase IN ('friend', 'buddy')
              AND can_push = TRUE
              AND next_push_at <= now()
            LIMIT 1000
        """)
        for row in candidates:
            await self.consider_push(row.user_id)

    async def consider_push(self, user_id: str):
        ctx = await self.load_ctx(user_id)
        rules = self.rules_for_phase(ctx.phase)  # 不同阶段不同规则

        for rule in rules:
            if not rule.matches(ctx):
                continue
            if await self.recently_pushed(user_id, cooldown=rule.cooldown):
                continue

            msg = await self.compose_message(rule, ctx)
            if await channel_router.send(user_id, msg):
                await self.mark_pushed(user_id, rule)
                ctx.last_interaction_at = datetime.utcnow()
                await self.save_ctx(ctx)

    # 触发规则 (按 phase 区分)
    def rules_for_phase(self, phase):
        return {
            RelationshipPhase.STRANGER: [
                TriggerRule("weekly_summary", weekday="monday", hour=9, cooldown="7d"),
            ],
            RelationshipPhase.ACQUAINTANCE: [
                TriggerRule("weekly_summary", weekday="monday", hour=9, cooldown="7d"),
                TriggerRule("interview_followup", event="interview_pass", cooldown="0d"),
            ],
            RelationshipPhase.FRIEND: [
                TriggerRule("weekly_summary", weekday="monday", hour=9, cooldown="7d"),
                TriggerRule("industry_insight", weekday="wednesday", hour=14, cooldown="7d"),
                TriggerRule("check_in", weekday="friday", hour=18, cooldown="7d"),
                TriggerRule("milestone_celebrate", event="any_milestone", cooldown="0d"),
            ],
            RelationshipPhase.BUDDY: [
                TriggerRule("daily_mood", hour=20, cooldown="1d", opt_in=True),
                TriggerRule("birthday", event="birthday", cooldown="365d"),
                TriggerRule("holiday", event="chinese_new_year", cooldown="365d"),
                TriggerRule("anniversary", event="work_anniversary", cooldown="365d"),
                TriggerRule("proactive_unstuck", condition="search_stuck_30d", cooldown="14d"),
            ],
        }[phase]
```

#### 1.1.3 关怀空白期 + 节日/生日

```python
# backend/services/jobseeker/seasonal_care.py

class SeasonalCare:
    async def on_user_event(self, event: UserEvent):
        if event.type == "birthday":
            await self.send_birthday_wishes(event.user_id)
        elif event.type == "chinese_new_year":
            await self.send_ny_greeting(event.user_id)
        elif event.type == "job_search_started":
            # 主动询问状态, 1 周后回访
            await scheduler.schedule("check_in", user_id=event.user_id, delay="7d")

    async def detect_dry_period(self, user_id: str):
        """候选期空窗 14 天, 主动关心"""
        ctx = await db.fetchrow("""
            SELECT * FROM job_search_status WHERE user_id = $1
        """, user_id)
        if ctx and ctx.last_apply_days > 14:
            await channel_router.send(user_id, Message(
                template="gentle_check_in",
                tone="warm",  # 用 BUDDY 语气
                attachments=[
                    ResumeSuggestionCard(...),  # 主动给简历优化建议
                    IndustryNewsCard(top=3),    # 行业要闻 3 条
                ],
            ))
```

#### 1.1.4 关键代码示例 - 上下文组装器

```python
# backend/services/jobseeker/context_weaver.py

@dataclass
class UserStory:
    """AI 看到的'关于此人的所有'"""
    user: User
    current_phase: RelationshipPhase
    notable_moments: List[Moment]
    recent_conversations: List[Conversation]
    pending_actions: List[str]
    mood_signal: Optional[str]

    def to_prompt(self) -> str:
        return f"""
[关于此人的故事]
- 关系阶段: {self.current_phase.value} ({"朋友" if self.current_phase in (FRIEND, BUDDY) else "熟人"})
- 关键时刻 ({len(self.notable_moments)} 个):
{chr(10).join(f"  - {m.date.date()}: {m.summary} ({m.sentiment})" for m in self.notable_moments[:5])}
- 最近 3 次对话主题:
{chr(10).join(f"  - {c.summary}" for c in self.recent_conversations[-3:])}
- 待办事项: {self.pending_actions}
- 最近心境: {self.mood_signal or "未知"}

[回复指引]
- 称呼: {"昵称" if self.current_phase in (FRIEND, BUDDY) else "同学"}
- 不要重复已说过的
- 引用过去的承诺 (例如 "上次你说想冲 X 厂...")
- 如果是 BUDDY 阶段, 可以主动问"最近顺不顺"
"""
```

---

### 1.2 评价 (Phase 2: Industry-Vertical Review + Action State Machine)

**做透目标**: 不是"打分",是"给得出行动项"。

#### 1.2.1 行业垂直评价 prompt

```python
# backend/services/jobseeker/review_engine.py

REVIEW_PROMPT_BY_INDUSTRY = {
    "互联网": """
        针对互联网行业的简历, 按以下维度评分 (0-100):
        - 技术深度 (项目含金量 / 解决了什么难题)
        - 业务影响 (DAU/GMV/留存/转化)
        - 系统设计能力
        - 代码质量证据 (开源 / 技术博客 / 论文)
        - 学习成长曲线 (晋升 / 跳槽路径)

        每个维度给分 + 1 句证据 + 3 条具体改进行动。
    """,
    "金融": """
        针对金融行业的简历, 按:
        - 牌照 / 资质 (CPA/CFA/FRM)
        - 合规意识
        - 模型 / 风控经验
        - 项目复杂度
        - 业绩可量化度
    """,
    # ... 12 个行业
}

class ReviewEngine:
    async def review(self, user_id: str, resume: Resume):
        industry = self.classify_industry(resume)
        prompt = REVIEW_PROMPT_BY_INDUSTRY[industry]
        raw_review = await llm.invoke(prompt + "\n\n[简历]\n" + resume.text)

        # 结构化
        parsed = self.parse_review(raw_review)
        action_items = await self.generate_actions(parsed)

        return ComprehensiveReview(
            industry=industry,
            dimensions=parsed.dimensions,
            overall=parsed.overall,
            action_items=action_items,
        )
```

#### 1.2.2 行动项状态机

```python
# backend/services/jobseeker/action_state.py

class ActionStatus(str, Enum):
    PROPOSED   = "proposed"    # AI 提出
    ACCEPTED   = "accepted"    # 用户接受
    IN_PROGRESS = "in_progress"
    BLOCKED    = "blocked"     # 卡住了, 提示 "需要 X 资源"
    DONE       = "done"
    EXPIRED    = "expired"     # 30 天未完成, 转推荐
    ABANDONED  = "abandoned"

ACTION_TRANSITIONS = {
    PROPOSED:   {ACCEPTED, EXPIRED},
    ACCEPTED:   {IN_PROGRESS, BLOCKED, ABANDONED},
    IN_PROGRESS: {DONE, BLOCKED, ABANDONED},
    BLOCKED:    {IN_PROGRESS, ABANDONED},
    DONE:       set(),
    EXPIRED:    set(),
    ABANDONED:  set(),
}

@dataclass
class ReviewAction:
    id: UUID
    user_id: str
    title: str                # "在简历第 3 段加量化结果"
    category: str             # "content" | "format" | "skill" | "narrative"
    priority: int             # 1-5
    status: ActionStatus
    proposed_at: datetime
    due_date: Optional[datetime]   # PROPOSED 时设定 = propose + 30 天
    accepted_at: Optional[datetime]
    completed_at: Optional[datetime]
    evidence: Optional[str]        # 用户提交"已修改", 附对比
    impact_score: Optional[int]    # 完成 7 天后回评影响 (面试通过率)

class ActionTracker:
    """行动项追踪 + 影响回评"""
    async def mark_done(self, action_id: UUID, evidence: str):
        action = await self.get(action_id)
        action.status = ActionStatus.DONE
        action.completed_at = datetime.utcnow()
        action.evidence = evidence
        await self.save(action)
        # 7 天后回评影响
        await scheduler.schedule("evaluate_action_impact", action_id, delay="7d")

    async def evaluate_action_impact(self, action_id: UUID):
        """比较完成前后, 用户的面试率/简历浏览数"""
        before = await self.metric_before(action.user_id, days=30)
        after = await self.metric_after(action.user_id, days=30)
        delta = (after.interview_rate - before.interview_rate) / before.interview_rate
        action.impact_score = int(delta * 100)
        await self.save(action)
        # 用作后续 prompt 调优
```

---

### 1.3 频繁/主动服务 (Proactive Engine)

**做透目标**: AI 比用户更早发现"该做点什么的信号"。

```python
# backend/services/jobseeker/proactive_engine.py

class Signal(Enum):
    LAST_INTERVIEW_WAS_2_DAYS_AGO = "interview_recency"
    OPENED_APP_3_TIMES_TODAY = "high_engagement"
    SEARCH_STUCK_14_DAYS = "search_stuck"
    RESUME_VIEWED_BY_RECRUITER = "external_interest"
    PROFILE_COMPLETE_70_PERCENT = "profile_momentum"

PROACTIVE_RULES = [
    {
        "signal": Signal.SEARCH_STUCK_14_DAYS,
        "action": "建议重写自我介绍",
        "channel": "in_app_banner",
        "prompt_template": "感觉我们好像没找到合适的岗位, 要不试着调整简历方向?",
        "cooldown": "7d",
        "track_conversion": "applied_within_7d",
    },
    {
        "signal": Signal.LAST_INTERVIEW_WAS_2_DAYS_AGO,
        "action": "鼓励复盘 + 主动提供录音转写复盘",
        "channel": "push",
        "prompt_template": "两天前那场面试感觉怎么样? 要不要一起看看?",
        "cooldown": "1d",
    },
]

class ProactiveEngine:
    async def eval_signals(self):
        for user in active_users:
            signals = await self.detect_signals(user.id)
            for sig in signals:
                rule = next((r for r in PROACTIVE_RULES if r["signal"] == sig), None)
                if not rule: continue
                if await self.cooldown_active(user.id, rule): continue

                msg = await self.compose_message(user, rule)
                await channel_router.send(user.id, msg)

                await self.log_proactive(user.id, rule, sig)
```

---

### 1.4 情绪关怀 (Emotion Workflow + Resource Library)

#### 1.4.1 情绪识别 → 工作流

```python
# backend/services/jobseeker/emotion_workflow.py

EMOTION_TRIGGERS = {
    "frustrated":   "被拒 / 面试连环挂",
    "anxious":      "长期未面试 + 高频刷 app",
    "celebratory":  "拿到 offer / 通过面试",
    "grieving":     "被裁员 / 项目失败",
    "burned_out":   "搜索 > 60 天 + 情绪词频高",
    "confident":    "offer 比较中 / 谈判期",
}

class EmotionWorkflow:
    async def detect_emotion(self, msg: str) -> str:
        # 用 emotion_agent (v7.0) + 多模态信号
        ...

    async def handle(self, user_id: str, msg: str):
        emo = await self.detect_emotion(msg)
        workflow = EMOTION_WORKFLOWS.get(emo, default_workflow)
        await workflow.run(user_id, msg, emo)


EMOTION_WORKFLOWS = {
    "frustrated": Workflow([
        Step("acknowledge", emotion_agent, "完全理解, 这种事真的让人崩溃..."),
        Step("recall_history", mem0, query="用户过去战胜挫折的时刻", max_results=3),
        Step("micro_action", jtbd, "今天能不能就投 3 家? 我帮你筛"),
        Step("schedule", scheduler, "48h 后再问一次进展"),
    ]),
    "anxious": Workflow([
        Step("grounding", emotion_agent, "深呼吸 3 次, 我们慢慢来"),
        Step("normalization", emotion_agent, "求职焦虑是非常普遍的情绪, 数据显示平均 4.8 个月找到合适岗"),
        Step("offer_resources", resource_lib, filter="焦虑/睡眠/正念"),
    ]),
}
```

#### 1.4.2 减压资源库

```python
# backend/services/jobseeker/resource_library.py

@dataclass
class Resource:
    id: str
    category: str         # "焦虑", "失眠", "自信", "面试怯场"
    format: str           # "audio" | "video" | "article" | "exercise"
    duration_sec: int
    title: str
    url: str
    language: str
    curator: str
    rating: float

class ResourceLibrary:
    def __init__(self):
        self.items = load_from_supabase("resource_library")

    async def recommend(self, emotion: str, user_ctx) -> List[Resource]:
        """上下文相关: 通勤场景推荐音频, 深夜推荐文章"""
        candidates = [r for r in self.items if emotion in r.category]
        return self.rank(candidates, user_ctx)[:3]

    async def track_effect(self, user_id: str, resource_id: str):
        """3 天后回访: 看了资源后情绪分数"""
        before = await emotion_score(user_id, days=-1)
        await scheduler.schedule("recheck_emotion", user_id, resource_id, delay="3d", before=before)
```

---

### 1.5 画像确认 (ProfileConfirmCard + Mem0 Loop)

```python
# backend/services/jobseeker/profile_confirmation.py

class ProfileConfirmCard:
    """主动展示 AI 从对话中抽取的画像条目, 求用户确认"""

    async def build_pending_cards(self, user_id: str) -> List[PendingFact]:
        # 抽取来自最近 7 天的对话
        recent_facts = await mem0.search(user_id, query="用户自述偏好/经历", limit=20)
        confirmed_set = await db.fetch_confirmed_facts(user_id)

        pending = []
        for fact in recent_facts:
            if not self.is_confirmed(fact, confirmed_set):
                pending.append(PendingFact(
                    content=fact.value,
                    confidence=fact.confidence,
                    source="conversation",
                    extracted_at=fact.created_at,
                    suggested_actions=["确认", "编辑", "删除"],
                ))
        return pending[:5]

    async def confirm(self, user_id: str, fact_id: str, edited_value: Optional[str]):
        """确认 → 写入 Mem0, 编辑 → 更新 + 重新 embedding"""
        if edited_value:
            await mem0.update(fact_id, edited_value, reason="user_edit")
            await self.feedback_loop("user_correction", before=fact.value, after=edited_value)
        else:
            await mem0.confirm(fact_id)
        await self.feedback_loop("user_confirm", fact=fact_id)

    async def feedback_loop(self, event_type: str, **payload):
        """每次确认/编辑都进入精排模型的负采样, 反哺 AI 抽取"""
        await ml_collector.collect(category="profile_fact", label=event_type, payload=payload)
```

---

### 1.6 规划追踪 (甘特图 + Smart Adjustment)

```python
# backend/services/jobseeker/career_planner_v2.py

@dataclass
class CareerPlan:
    user_id: str
    goals: List[Goal]                  # 长中短期
    milestones: List[Milestone]
    gantt: GanttChart
    last_reviewed_at: datetime
    velocity_score: float              # 完成率 × 时间

    def to_gantt_json(self) -> dict:
        """前端甘特图组件直接消费"""
        return {
            "tasks": [m.to_task() for m in self.milestones],
            "dependencies": self.edges(),
            "progress": self.progress_pct,
            "delayed": self.delayed_tasks(),
        }


class SmartAdjuster:
    """根据完成情况自动调整后续计划"""

    async def adjust(self, plan: CareerPlan):
        if plan.velocity_score < 0.6:
            # 拖延严重: 砍非关键路径, 拉长截止日
            await self.prune_non_critical(plan)
            await self.extend_deadlines(plan, by_days=14)
            # 推一条消息
            await notify.send(plan.user_id, "原计划似乎有点赶, 我重新排了一下...")
        elif plan.velocity_score > 1.2:
            # 超前: 可以加码
            await self.add_challenge_task(plan)
            await notify.send(plan.user_id, "你进展超出预期! 要不要再挑战 X?")
        # 写回
        await self.save_plan(plan)
        # emit event for visual diff
        await event_bus.emit("career_plan.adjusted", plan.user_id, plan.to_gantt_json())
```

---

## 2. 用人单位侧 (9 项)

### 2.1 个性化 HR (Tone Learning + Template Demolding)

**做透目标**: AI 不仅懂这家公司的"知识",还学它的"语气"。

#### 2.1.1 Tone Learning

```python
# backend/services/employer/tone_learning.py

@dataclass
class CompanyToneProfile:
    org_id: str
    formality: float           # 0..1, 0=超级随意, 1=全文书面
    warmth: float              # 0..1
    directness: float          # 0..1, 0=委婉, 1=直白
    typical_phrases: List[str] # 高频短语, 例如 "一起看看", "蛮好的"
    forbidden_words: List[str] # 公司明令不要的词
    signature_emoji: Optional[str]  # ":)"
    updated_at: datetime

    def to_system_prompt(self) -> str:
        return f"""
[此公司语气规范]
- 正式度: {self.formality:.1f} ({"超级随意" if self.formality < 0.3 else "中等" if self.formality < 0.7 else "正式"})
- 温度: {self.warmth:.1f}
- 直接度: {self.directness:.1f}
- 惯用语: {", ".join(self.typical_phrases[:10])}
- 禁用词: {", ".join(self.forbidden_words) or "无"}
- 末尾表情: {self.signature_emoji or "无"}

请所有回复都符合此规范。例如, 同样说"通过", 正式场合说"通过本次筛选", 随意场合说"OK 通过 : )"
"""


class ToneLearner:
    """从历史 HR 消息中学语气 - 增量学习"""

    async def refresh(self, org_id: str):
        # 1. 取最近 1000 条 HR 主动发出的消息
        msgs = await db.fetch("""
            SELECT content FROM messages
            WHERE org_id = $1 AND sender_role = 'hr'
              AND created_at > now() - INTERVAL '90 days'
            LIMIT 1000
        """, org_id)

        # 2. LLM 抽取语气特征
        profile = await llm.extract(
            system="你是语气分析专家, 从历史消息中提取这家公司的'味道'",
            user="\n".join(m.content for m in msgs[:200]) +
                 "\n\n请输出 JSON: formality/warmth/directness/typical_phrases/forbidden_words",
        )

        # 3. 比老 profile, diff
        old = await db.get_tone_profile(org_id)
        delta = self.diff(old, profile)
        await db.save_tone_profile(org_id, profile)

        # 4. 通知 PM "x 公司语气变化"
        if delta.significant:
            await notify_admin(f"org={org_id} tone profile 显著变化", delta)
```

#### 2.1.2 Template Demolding

```python
# backend/services/employer/template_demolder.py

class TemplateDemolder:
    """模板去模板化: 每个模板都基于公司上下文重写"""

    async def demold(self, org_id: str, template_text: str, candidate: Candidate) -> str:
        tone = await tone_learner.get(org_id)
        # Prompt 注入: 模板 ≠ 答案, 必须结合候选人具体信息
        prompt = f"""
[模板原文]
{template_text}

[候选人具体信息]
{candidate.summary}

[改写要求]
1. 套用模板骨架, 但所有 "X" 必须替换为候选人具体描述
2. 加入 1 个候选人简历里的细节引用 (如某个项目)
3. 避免任何模板感 (去掉 "恭喜您已通过我司初审")
4. 遵循公司语气: {tone.to_system_prompt()}

[输出] 改写后的真实消息
"""
        return await llm.invoke(prompt, temperature=0.7)  # 高温度去模板化
```

---

### 2.2 假资质检测 (PS Detection + Cross-Source Verification)

#### 2.2.1 PS / 篡改检测 (多模态)

```python
# backend/services/employer/document_forensics.py

class DocumentForensics:
    """检测证书/简历是否被 PS"""
    async def detect(self, doc_url: str, doc_type: str) -> ForensicsResult:
        img = await fetch_image(doc_url)
        return ForensicsResult(
            ela_score=await self.error_level_analysis(img),   # ELA: 检测压缩差异
            noise_inconsistency=await self.noise_analysis(img),  # 噪点一致性
            font_inconsistency=await self.font_analysis(img),     # 字体不一致
            copy_move=await self.copy_move_detection(img),       # 复制粘贴块
            semantic_inconsistency=None,  # 等 cross_source 后填充
        )

    async def error_level_analysis(self, img) -> float:
        """ELA 原理: 重压缩后, 篡改区域的高频分量差异会暴露"""
        from PIL import Image, ImageChops
        reencoded = img.save("/tmp/r.jpg", "JPEG", 95)
        diff = ImageChops.difference(img, Image.open("/tmp/r.jpg"))
        return float(np.std(np.array(diff)))
```

#### 2.2.2 跨源验证

```python
class CrossSourceVerifier:
    """学历 / 工作经历 / 证书的跨源验证"""

    async def verify(self, candidate_id: str):
        results = {}
        candidate = await db.get_candidate(candidate_id)

        # 学校验证 - 学信网
        results["education"] = await self.education_verify(
            candidate.school, candidate.degree,
        )

        # 工作经历 - 社保 / 前雇主背调
        for exp in candidate.experiences:
            results[f"exp_{exp.company}"] = await self.work_verify(exp)

        # 证书 OCR → 颁发机构 API
        for cert in candidate.certifications:
            results[f"cert_{cert.name}"] = await self.cert_verify(cert)

        # 综合判定
        return VerificationReport(
            candidate_id=candidate_id,
            per_item=results,
            overall_score=self.aggregate(results),
            flags=[k for k, v in results.items() if v.red_flag],
        )
```

---

### 2.3 战略传达 (Strategy → Recruitment Impact Analysis)

```python
# backend/services/employer/strategy_translator.py

class StrategyTranslator:
    """把公司战略翻译成招聘影响"""

    async def translate(self, org_id: str, strategy_doc_url: str) -> RecruitmentImpactPlan:
        strategy_text = await pdf_extract(strategy_doc_url)
        # 抽取战略目标
        goals = await llm.extract(
            "你是战略分析师, 从以下文档抽取 3-5 个战略目标: " + strategy_text,
            schema=List[StrategicGoal],
        )

        plan = RecruitmentImpactPlan(goals=[])
        for goal in goals:
            # 每个目标 → 招聘影响
            impact = await self.impact_of_goal(goal)
            plan.goals.append(impact)
            # 自动建议岗位
            plan.suggested_roles.extend(impact.roles_to_hire)
            # 自动建议合并 / 裁减
            plan.merge_candidates.extend(impact.teams_to_merge)
            # 自动建议培训
            plan.training_topics.extend(impact.upskill_topics)
        return plan

    async def impact_of_goal(self, goal: StrategicGoal) -> GoalImpact:
        return await llm.extract(
            f"""战略目标: {goal.description}
                请输出:
                - 需要新招什么岗位 (含 HC 估算)
                - 现有团队哪些人需要 re-skill
                - 哪些岗位可能冗余 (评估可能需要 30/60/90 天)
                - 招聘优先级 (1-5)
                """,
            schema=GoalImpact,
        )
```

---

### 2.4 偏见纠正 (Bias Reporting + Forced Substitution)

```python
# backend/services/employer/bias_auditor.py

class BiasAuditor:
    """检测 JD / 简历筛选 / 面试评价中的隐性偏见"""

    # 检测哪些偏见
    BIAS_CATEGORIES = [
        "age", "gender", "ethnicity", "school_tier", "industry_bias",
        "gap_penalty", "language_origin",
    ]

    async def audit_jd(self, jd_text: str) -> BiasReport:
        """JD 中歧视性措辞检测"""
        flagged_terms = await self.detect_terms(jd_text)
        suggestions = self.substitutions(flagged_terms)
        return BiasReport(
            found=flagged_terms,
            score=self.bias_score(jd_text),
            suggestions=suggestions,
            before_after=[(t, suggestions[t]) for t in flagged_terms],
        )

    async def audit_screening_decisions(self, org_id: str):
        """分析历史筛选决策 → 哪些群体被系统低判"""
        decisions = await db.fetch("""
            SELECT
                candidate.attributes->>'school' AS school,
                candidate.attributes->>'gender' AS gender,
                screening_decision.label AS label,
                screening_decision.confidence AS confidence
            FROM screening_decisions
            JOIN candidates ON ...
            WHERE org_id = $1 AND decision_at > now() - INTERVAL '6 months'
        """, org_id)

        # 用因果推断检查: 在控制其他因素后, 某群体是否系统低判
        return await self.causal_bias_check(decisions)

    def substitutions(self, flagged_terms: dict) -> dict:
        """强制替代 - 不允许 AI 跳过"""
        return {
            "年轻": "有活力",
            "35 岁以下": "经验匹配",
            "未婚未育": "时间灵活",
            "985/211": "相关学科背景",
            # ... 100+ 条目
        }
```

---

### 2.5 JD 营销 (Marketing Mode + SEO + A/B)

```python
# backend/services/employer/jd_marketing.py

class JDMarketing:
    """JD 营销化 - 把职位描述从"招聘文档"变成"营销页"""

    async def marketing_mode(
        self, jd: JobDescription, target_persona: Persona
    ) -> MarketingPage:
        page = await llm.generate(
            f"""
            任务: 把以下 JD 改写成面向 {target_persona.name} 的营销页。

            JD 内容: {jd.text}
            目标人群: {target_persona.summary}

            输出结构:
              - Hero: 一句让人想点进来的标题
              - Why Us: 3 条这家公司的独特卖点
              - Day In Life: 一个典型一天场景 (5 段)
              - Growth Path: 30/60/90 天成长路径
              - Team: 团队成员的 1 句话介绍 (基于真名 - 占位)
              - FAQ: 8 个候选人最常问的问题
              - Apply CTA: 引导加微信 / 投递
            """,
        )

        # SEO
        page.seo = await self.seo_optimize(page, jd)

        # AB 测试
        page.variants = await self.gen_variants(page, n=3)

        return page

    async def gen_variants(self, page, n):
        """生成 N 个 hero 标题变体, AB 测试"""
        return [await self.vary_hero(page) for _ in range(n)]

    async def seo_optimize(self, page, jd) -> SEO:
        # 同义词扩展, 长尾 query 覆盖
        ...
```

---

### 2.6 制度 AI 解释 (Policy → Plain Language + FAQ)

```python
# backend/services/employer/policy_explainer.py

class PolicyExplainer:
    """把公司制度翻译成候选人能看懂的语言"""

    async def explain(self, org_id: str, policy_text: str, candidate_level: str):
        prompt = f"""
        [原始制度]
        {policy_text}

        [目标读者]
        {candidate_level} (应届/3年/资深/管理层)

        [输出要求]
        1. 用最少的法律/财务术语
        2. 给具体例子 (例如 "年假 = 10 天, 相当于每干 1 个月攒 0.83 天")
        3. 量化所有抽象描述
        4. 对比其他公司 (数据允许时)
        5. 用 5 句话 + 1 个例子 + 1 个例外场景
        """
        explanation = await llm.invoke(prompt)

        # 自动生成 FAQ
        faqs = await self.gen_faq(policy_text, n=10)

        return PolicyExplained(
            summary=explanation,
            faqs=faqs,
            related_policies=await self.find_related(org_id, policy_text),
        )
```

---

### 2.7 多方协同 (Notification Dispatcher + Silence Reactivation)

```python
# backend/services/employer/multi_party_agent.py

class MultiPartyCoordinator:
    """多方协同 - 候选人 + HR + Hiring Manager + Recruiter"""

    async def dispatch(self, thread_id: str, msg: MultiPartyMessage):
        # 沉默检测: 谁超过 24h 没说话
        inactive = await self.detect_silence(thread_id, threshold="24h")
        for participant in inactive:
            await self.gentle_nudge(participant, thread_id)

    async def gentle_nudge(self, user_id: str, thread_id: str):
        """沉默激活: 跨通道推送 + 智能话术"""
        channel = await self.best_channel(user_id)
        await channel_router.send(channel, user_id, Message(
            template="thoughtful_nudge",
            context={"thread_id": thread_id, "summary": "候选人提问..."},
        ))
```

---

### 2.8 共识度 (3-Level Resolution Engine)

```python
# backend/services/employer/consensus_engine.py

@dataclass
class ConsensusLevel:
    STRONG  = "strong"     # 多方 100% 一致 + 高置信
    WEAK    = "weak"       # 多方基本一致, 但有分歧标记
    FUZZY   = "fuzzy"      # 存在反对意见, 需仲裁

class ConsensusEngine:
    async def measure(self, decision: Decision) -> ConsensusReport:
        votes = decision.votes  # 各方评分 + 文本评论

        strong_count = sum(1 for v in votes if v.score >= 4 and v.confidence >= 0.8)
        total = len(votes)
        ratio = strong_count / total

        if ratio >= 0.85:  level = ConsensusLevel.STRONG
        elif ratio >= 0.6: level = ConsensusLevel.WEAK
        else:              level = ConsensusLevel.FUZZY

        return ConsensusReport(
            level=level,
            disagreements=[v for v in votes if v.score <= 2],
            visualization=self.to_chart(votes),  # D3.js 数据
        )

    async def visualize(self, report) -> ConflictMap:
        """冲突可视化: 谁强支持/反对/中立"""
        return ConflictMap(
            nodes=[v.participant for v in report.votes],
            edges=[(a, b, similarity) for a, b, similarity in ...],
        )
```

---

### 2.9 主动 HR (Daily Recommendation Engine)

```python
# backend/services/employer/proactive_hr.py

class ProactiveHR:
    """每天早上 9 点给 HR 主动建议 (前 3)"""

    async def daily_digest(self, hr_id: str):
        candidates = await self.stalled_candidates_for_hr(hr_id)
        if not candidates: return

        top = await self.rank_top3(candidates)
        messages = []
        for c in top:
            msg = await self.compose_proactive(c, hr_id)
            messages.append(msg)

        await channel_router.send(hr_id, Message(
            template="daily_recommendation",
            body={"intro": f"今天有 {len(messages)} 个候选你可能忽略", "items": messages},
        ))

    async def compose_proactive(self, candidate: Candidate, hr_id: str):
        # 用 tone profile 起草建议, 引用候选人具体细节
        tone = await tone_learner.get(hr_id)
        return f"{candidate.name} ({candidate.yrs}年{candidate.role}) - {candidate.notable} - {tone.formal_invite(candidate)}"
```

---

### 3 匹配: 命中率提升 (Metric Loop + HR Feedback)

```python
# backend/services/matching/improvement_loop.py

class MatchImprovementLoop:
    """匹配命中率提升闭环"""

    async def weekly_metrics(self):
        hr_feedback = await db.fetch("""
            SELECT matched_candidate_id, hr_rating, reason_code
            FROM hr_feedback
            WHERE created_at > now() - INTERVAL '7 days'
        """)
        # 命中率
        hit_rate = sum(1 for f in hr_feedback if f.hr_rating >= 4) / len(hr_feedback)

        # 分析: 哪些特征导致低分
        failure_features = await self.feature_contribution(hr_feedback, bad=True)

        # 调整权重
        await self.update_weights(failure_features)

        # 通知研发: "本周命中率 73%, 下降 5pp, 主要因特征 X"
        if hit_rate < self.target:
            await notify_engineering(f"Match hit rate {hit_rate} below target", failure_features)

    async def update_weights(self, failure_features):
        """基于 HR 反馈的权重更新 (无 LoRA, 仅参数调整)
        - 失败的特征权重 ↓
        - 成功的特征权重 ↑
        - 通过 ConfigCenter 热更新, 不重启服务
        """
        await config_center.update("matching.weights", {
            "experience": max(0.1, current - failure_features["experience"] * 0.1),
            "school":    max(0.05, current - failure_features["school"] * 0.1),
            ...
        })
```

---

## 4. 整体架构总览

```
┌──────────────────── 求职者侧 ────────────────────┐   ┌──────────────────── 用人单位侧 ─────────────────────┐
│                                                    │   │                                                     │
│  关系引擎   评价引擎   主动引擎   情绪引擎          │   │  HR tone   假资质   战略   偏见    JD 营销          │
│  ↓          ↓          ↓          ↓                 │   │  ↓         ↓        ↓       ↓       ↓              │
│  Scheduler  ActionFSM  Signal    ResourceLib       │   │  ToneLearner DocForensic Trans BiasAud Marketing │
│                                                    │   │                                                     │
│  画像确认                  规划追踪                 │   │  制度解释   多方协同   共识度    主动 HR            │
│  ↓                          ↓                       │   │  ↓          ↓          ↓         ↓                  │
│  ProfileCard+GanttCard      SmartAdjuster            │   │  PolicyExp  MultiParty Consensus ProactiveHR       │
│                                                    │   │                                                     │
│  agent.profile_v2 / agent.emotion / ...             │   │  agent.hr_service / agent.compliance / ...          │
└─────────────────────────────────────────────────────┘   └─────────────────────────────────────────────────────┘
                                          │                                       │
                                          └──────────────┬────────────────────────┘
                                                         │
                                                         ▼
                                                ┌──────────────────┐
                                                │ matching.engine  │ ← 闭环改进
                                                │  ConfigCenter    │
                                                │  FeatureFlag     │
                                                └──────────────────┘
```

---

## 5. 共享基础设施

| 模块 | 来源 | 复用 |
|---|---|---|
| ServiceToggle | v8.0 NEW | 16 项全部经此判断可见性 |
| FeatureAccess.check() | v8.0 NEW | 统一入口 |
| Mem0 | v7.0 | 上下文 / 时刻 / 偏好 |
| ConfigCenter | v6.0 | 调整权重 / 阈值 (无 LoRA) |
| EventBus | v6.0 | trigger 编排 / 失败重试 |
| Audit v2 | v6.0 | GDPR + 审计 |
| Workflow Engine | v6.0 | 多步骤 (情绪工作流、跨源验证) |
| BFF realtime | v7.0 | push / 主动消息 |

---

## 6. 排期

| 周 | 任务 |
|---|---|
| W1 | ServiceToggle + FeatureAccess (并行: 16 项 UI 探索) |
| W2 | 求职者侧 6 项 (关系/评价/主动/情绪/画像/规划) 后端 + 端到端 |
| W3 | 用人单位侧 9 项 (tone/假资质/战略/偏见/JD营销/制度/多方/共识/主动HR) 后端 |
| W4 | 匹配闭环 + 前端集成 + A/B + 监控 (P0 16 个面板) |

---

## 7. 验收标准 (按做透 4 维度)

| 项 | 深度 | 闭环 | 个性化 | 可运营 |
|---|---|---|---|---|
| 1.1 朋友 | 关系状态机 5 阶 | 推送接受率 ≥ 30% | BUDDY 待遇 | PM 可配置触发规则 |
| 1.2 评价 | 12 行业垂直 | 行动影响回评 | 因简历定制 | 行业 prompt 可调 |
| 1.3 主动 | 8 信号触发 | 24h 再 ask | 按 phase 区分 | 规则 JSON 可改 |
| 1.4 情绪 | 6 类工作流 | 72h 复评 | 资源库推荐 | 工作流可视化 |
| 1.5 画像 | Mem0 反馈环 | AI 抽取精度 +5pp | 编辑记忆 | 抽取规则可调 |
| 1.6 规划 | 甘特图组件 | 完成率追踪 | 拖拽改计划 | 模板可编辑 |
| 2.1 HR | tone profile | 90 天滚动 | 1000 家公司 | tone 可手工微调 |
| 2.2 假资质 | ELA + 跨源 | 99% 检测 | 按行业 | 阈值可调 |
| 2.3 战略 | 招聘影响 | 30 天跟踪 | 自动建议 | 战略模板 |
| 2.4 偏见 | 100+ 替代 | 偏见回测 | 因公司 | 词表可编辑 |
| 2.5 JD | 营销模式 | SEO 排名监测 | 3 标题 AB | PM 可改模板 |
| 2.6 制度 | 通俗解释 | FAQ 命中率 | 因读者 | 政策可手工编辑 |
| 2.7 多方 | 沉默激活 | 4h 内激活率 | 按参与方 | 通道可改 |
| 2.8 共识 | 3 级可视化 | 仲裁准确率 | 因 team | 阈值可调 |
| 2.9 主动 | 每日 top3 | HR 接受率 ≥ 35% | 因 HR | 规则可改 |
| 3 匹配 | 命中率 +15pp | HR 反馈闭环 | 因公司 | 权重可调 |

---

**END OF DEPTH_PLAN.md**
