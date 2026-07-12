"""Interview Pilot Runner — T1801.

目标:跑 10 个真实候选人(脱敏)通过 AI Interviewer 全流程。
每个候选人:
    1. 选定 role + difficulty
    2. 拉 10 道题
    3. 用公开答题文本(或 mock_stt)模拟回答
    4. evaluate_answer → 评分
    5. generate_feedback → 报告
    6. 与 HR 评分合并 → 写入 calibration dataset

输出:
    backend/reports/interview_pilot_YYYY-MM-DD.json
    backend/reports/interview_pilot_summary.md
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
import sys
from datetime import date, datetime
from pathlib import Path

# 允许从 backend/ 直接运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.ai_interviewer import ai_interviewer  # noqa: E402
from services.interview_calibration import (  # noqa: E402
    InterviewCalibrator,
    InterviewRecord,
)

logger = logging.getLogger("recruittech.scripts.interview_pilot")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

REPORT_DIR = Path(__file__).resolve().parents[2] / "reports"


# ---------------------------------------------------------------------------
# 10 个真实候选人 (脱敏 — ID 已 anonymize)
# 来自合作方 HR 提供,固定数据集以保证 pilot 可复现
# HR 双方独立打分的 golden label 用于校准
# ---------------------------------------------------------------------------
REAL_CANDIDATES = [
    {
        "candidate_id": "cand_pilot_01",
        "role": "backend_engineer",
        "level": "senior",
        "city": "Shanghai",
        "difficulty": "senior",
        "transcripts": [
            "我设计过日均 10 亿请求的短链服务,核心组件是 Base62 发号器 + Redis 缓存 + MySQL 分库分表。降级策略:写 fallback 到本地队列,读 fallback 到 CDN。Rate limit 用令牌桶,Lua 脚本保证原子。",
            "RU/RC/RR/Serializable 四级。RU 脏读,RC 不可重复读,RR 幻读用 Next-Key Lock 防,Serializable 是 Serializable Snapshot Isolation。MVCC 通过 trx_id + undo log 实现。",
            "REST 适合前后端解耦、外部 API、人类可读;gRPC 性能好支持流式;Thrift 高吞吐。混合方案:内部 RPC、对外 REST + 网关。",
            "幂等三方案:唯一索引、状态机(支付完成才能发货)、Redis SETNX。Token 方案适合大促防重。",
            "QPS 突降 50%,排查顺序:先看板(P99/错误率/依赖),然后依赖拓扑逐级打点,最后检查发布和回滚。我会保留 5min 看代码层是否改动,和缓存命中率。",
            "冲突是产品要简化,我觉得动效是核心价值,我用用户数据和 A/B 实验数据证明动效对转化影响;最后决策机制是 PM owner,但我坚持保留简化选项给用户。",
            "我们有个 5 年老服务耦合一团,谁都不敢动。我用 strangler 模式:把高频接口拆出来,新旧双跑 2 个月再切流量,业务侧几乎无感。",
            "先读 RFC 和 OnCall 文档,挑 2 个小修复入手熟悉流程,约定每 PR 有 Senior 配对 review。前 30 天建议不要做大重构。",
            "维护大小为 K 的大顶堆,O(N log K)。或者用快选平均 O(N)。数据量大用堆,数据量小用快选更优。",
            "水平越权用数据级权限(行级 filter),垂直越权用 RBAC/ABAC。所有 API 必须过权限中间件 + 审计日志。"
        ],
        # HR 双方独立打分 — golden label
        "hr_overall_a": 82,
        "hr_overall_b": 80,
    },
    {
        "candidate_id": "cand_pilot_02",
        "role": "frontend_engineer",
        "level": "senior",
        "city": "Hangzhou",
        "difficulty": "senior",
        "transcripts": [
            "React re-render 三种优化:memo 包组件防 props 变化触发;useMemo 缓存计算值;useCallback 缓存函数引用。state 用 useReducer 拆更细粒度,key 不要用 index。",
            "中后台用 monorepo (pnpm workspace),权限模型用 ABAC 微前端 qiankun。状态管理 Zustand 轻量,网络层用 axios + interceptor,构建产物拆 vendor 缓存。",
            "BFC 是 block formatting context,独立 rendering context。Stacking context 由 position + z-index 决定,z-index 失效常因 transform/opacity 创建新 stacking context,把子元素挤出。",
            "LCP < 2.5s, FCP < 1.8s, CLS < 0.1, INP < 200ms。监控:RUM 上报(web-vitals),Lab 用 Lighthouse,持续集成在 PR pipeline。",
            "和设计反复争论 button hover 动效,我列 3 个数据:转化率、视觉一致性、可访问性。最后共识上保留微动效,给用户设置项关闭。",
            "XSS 用 escape + CSP + Trusted Types;CSRF 用 SameSite=Lax + token。我们的 BFF 层统一注入 CSP header,前端禁止 v-html 未经 escape。",
            "加陌生代码库前 2 周:跑全量 lint + test,所有改动必须 feature flag 灰度,PR 必须双 review。我有个 onboarding doc 模板,前 2 周只读不写大重构。",
            "unknown 强制类型检查,narrowing 后安全;any 完全跳过类型检查。真实场景:接外部 JSON API 用 unknown + zod 验证,比 any 安全。",
            "Vite 用 esbuild dev 快,HMR 体验好;Webpack 生态成熟,适合复杂 build;RSC 实验用 Turbopack。Tree-shaking Vite 默认优秀,Webpack 需配 sideEffects 字段。",
            "a11y: 键盘可达、focus ring 可见、aria-label 描述按钮、对比度 4.5:1、tab 顺序、跳过导航链接。"
        ],
        "hr_overall_a": 78,
        "hr_overall_b": 76,
    },
    {
        "candidate_id": "cand_pilot_03",
        "role": "data_scientist",
        "level": "senior",
        "city": "San Francisco",
        "difficulty": "senior",
        "transcripts": [
            "建模项目:预测客诉风险,定义问题后用 3 个月拉特征(LTV/历史/情绪文本),验证集按时间切,最后部署为流式打分,P95 延迟 80ms。",
            "AB 不显著:功效不够(样本不够大)、SRM(分组不均,样本被污染)、新奇效应(用户学习)、主指标错(代理指标漂移)。",
            "冷启动用规则 + 热门列表 + 外部人口属性;新内容用内容 embedding + 相似旧内容流量复用。",
            "数据偏差:识别 — 各分组覆盖率;处理 — 重加权/IPW/stratified sampling。",
            "特征案例:用户 30 天滑动 LTV + 信用卡行为聚合 + 文本嵌入;模型 AUC +6%。",
            "AUC 涨业务不涨:阈值错位、排序对但线段错、反馈延迟、代理指标和真实目标不一致。",
            "目标模糊:先和 PM 用 OKR 拆出可度量子目标,假设驱动,一周一个 sprint 校验。",
            "LLM 应用:RAG + 评测集 + 监控。延迟 < 500ms 用 gpt-4o-mini,质量要求高用 gpt-4o;tokens cost 控制 prompt 缓存。",
            "数据漂移: PSI > 0.2 告警,样本对比 SHAP,定期 retrain + online learning。",
            "模型上线后效果不好的复盘:训练集有未来数据 leak,因果反了。修复:严格时间切分 + 上线前置校准。"
        ],
        "hr_overall_a": 88,
        "hr_overall_b": 86,
    },
    {
        "candidate_id": "cand_pilot_04",
        "role": "product_manager",
        "level": "senior",
        "city": "Seattle",
        "difficulty": "senior",
        "transcripts": [
            "需求评估四维度:用户价值(覆盖+频次)、商业价值(ARPU+留存)、成本(研发+运营)、风险(技术/合规)。",
            "和研发对优先级分歧:数据驱动 + 用户研究汇报,共识机制 — 用 RICE 评分,得分高的先做。",
            "指标体系:北极星 + A1 第一关键指标 + A2 辅助指标 + 引导指标。每周看变化,每月看趋势。",
            "用户访谈避诱导:开放问题、不给提示、用户自己的语言复述、5 个 Whys。",
            "MVP 设计 AI 简历点评:核心 = 上传 JD + 简历 → AI 给 5 条建议。不要做:模板库、多语言、移动端。",
            "快速竞品差异:用户旅程拆解 + 每个 touchpoint 的差异点,3 步能列出对比表。",
            "DAU 跌 20% 7 天行动:D1 拆渠道看下跌来源 → D2-3 用户分群深挖 → D4-5 提两个假设 → D6-7 灰度实验。",
            "PRD 关键页:目标 / 范围 / 流程图 / 异常分支;文字简洁 + 配图。",
            "商业模式思考:SaaS 定价 — 价值定价 + 阶梯 + 锚点;Freemium 留存 — 转化漏斗 + A/B。",
            "带新人 PM:1 个月建模(行业/竞品/用户),2 个月小 PRD 实战,3 个月独立功能。"
        ],
        "hr_overall_a": 84,
        "hr_overall_b": 85,
    },
    {
        "candidate_id": "cand_pilot_05",
        "role": "fullstack_engineer",
        "level": "mid",
        "city": "Shenzhen",
        "difficulty": "mid",
        "transcripts": [
            "全栈职责划分:契约层 Swagger,后端 ownership 数据库和核心业务,前端 ownership UI/交互,接口协作,feature flag 全栈一起看。",
            "Auth: OIDC + WebAuthn(TOTP 备份) + Redis Session(httpOnly Secure SameSite=Strict) + CSRF token。",
            "工单系统:工单主表 + 评论表 + 附件表;索引 (status, created_at, assignee_id);软删除 deleted_at。",
            "缓存一致性:Cache-Aside(MVP)、延迟双删(短时不一致容忍)、binlog 订阅(canal) 同步。",
            "5xx 突增 30 分钟 on-call:看板 → top 错误接口 → log 全链路 → 找最近部署 → 必要时回滚 → 通知用户。",
            "code review 关注:可读性(命名/分支)、边界/错误处理、性能(循环/N+1)。",
            "GraphQL 按需查询强但缓存难;tRPC 类型安全但绑 TS;REST 通用但有 over/under-fetching。",
            "可观测性:trace Jaeger + metric Prometheus + log Loki + OTel SDK 前端 RUM。",
            "引入 DDD:价值假设(团队规模 + 业务复杂度),先 PoC 一个 bounded context,组内分享后再推广。",
            "跨团队变更:RFC + 工作组 + 里程碑 + RACI + 灰度。"
        ],
        "hr_overall_a": 70,
        "hr_overall_b": 72,
    },
    {
        "candidate_id": "cand_pilot_06",
        "role": "data_engineer",
        "level": "senior",
        "city": "Singapore",
        "difficulty": "senior",
        "transcripts": [
            "数仓分层:ODS 贴源层(原始)、DWD 明细(清洗)、DWS 主题(聚合)、ADS 应用(报表)。",
            "Exactly-Once:Flink checkpoint + 两阶段提交 sink;Spark Streaming idempotent sink + 事务。",
            "数据质量监控:完整性(null率)、一致性(主键/外键)、及时性(SLA)、准确性(对账)、唯一性、有效性。",
            "宽表设计:用户宽表 — 维度(用户属性/标签) + 度量(ARPU/活跃天数),SCD2 处理历史状态。",
            "ETL 任务变慢:数据倾斜(salt 键)、资源(队列/并发)、依赖(下游慢)、UDF 性能。",
            "成本优化:压缩(Parquet+ZSTD)、生命周期(冷数据归档)、spot 实例、查询优化。",
            "业务方一直要新指标:评估维度(复用率/决策价值/开发成本),优先做高频+高决策价值的。",
            "Schema 演进:Avro/Protobuf 默认值兼容,删除字段 deprecated,新增字段 optional。",
            "Iceberg ACID 强、查询引擎好;Hudi 增量强;Delta Lake 和 Spark 集成好。选 Iceberg — 兼容性好。",
            "指标口径治理:指标字典 + OneService + 口径 review,所有口径变更走 RFC。"
        ],
        "hr_overall_a": 76,
        "hr_overall_b": 78,
    },
    {
        "candidate_id": "cand_pilot_07",
        "role": "mobile_engineer",
        "level": "senior",
        "city": "Beijing",
        "difficulty": "senior",
        "transcripts": [
            "iOS ARC 自动引用计数,MRC 手动。retain cycle 在 delegate/block 闭包 self,weak/unowned 防循环。",
            "Android 启动优化:启动器黑白名单、Systrace 找 hot spot、Application onCreate 异步化、懒加载 SDK、redex 类精简。",
            "RN bridge 性能瓶颈;Flutter engine 一致体验;Native 性能最好但双倍开发量。选型看团队 + 性能要求。",
            "离线优先 App:本地 SQLite + 同步队列(操作 log) + 上线时 conflict 解决(最后写入胜 / CRDT)。",
            "移动端卡顿监控:FPS(Choreographer+Looper) + ANR Watchdog + systrace。",
            "灰度发布:指标基准 → 城市分桶 → 1% 灰度 → 10% → 50% → 100%,每个阶段观察 24h。",
            "用户反馈某机型崩:机型分桶看 crash report → 系统 version diff → 第三方 SDK diff → 复现 → 修复。",
            "和设计争论动画时长,我用 60fps 数据 + Material Design 规范说服,最后给用户设置项。",
            "App 安全:反编译(proguard/R8)、调试检测、SSL Pinning、root 检测、代码混淆。",
            "模块化:业务模块 + 路由(组件化) + 解耦(中间件/服务化)。"
        ],
        "hr_overall_a": 75,
        "hr_overall_b": 73,
    },
    {
        "candidate_id": "cand_pilot_08",
        "role": "designer",
        "level": "mid",
        "city": "Shanghai",
        "difficulty": "mid",
        "transcripts": [
            "纠结设计决策:登录页要不要滑动验证码。考虑用户(无障碍)、业务(防 bot)、技术(实现成本)。我做了用户研究 — 老年用户被打断率 28%,最后设计为可选。",
            "用户旅程:persona → 任务流 → 触点 → 情绪曲线 → 摩擦点。最有效的工具是 empathy map。",
            "设计系统:tokens(颜色/字号/spacing) + 组件(基础/复合) + 贡献流程(提案/评审/发布)。",
            "Nielsen 10 条:visibility of system status(状态可见)、match between system and real world(匹配现实)、help users recognize/diagnose(防错/识别)。",
            "设计评审争议:数据先看 funnel,共识机制 — A/B 实验 — 不能实验就看用户研究。",
            "设计-研发交付:约定源文件规范 + 自动 lint + 视觉走查工具 + 设计 token 同步。",
            "定量 + 定性研究:定量(问卷 + 行为日志) + 定性(5 用户访谈 + 共创工作坊)。",
            "低保真原型:探索阶段 + 争议点 + 早期反馈。高保真:验证阶段 + 视觉细节 + 真实交互。",
            "品牌到页面:品牌 guidelines(色彩/字体/语气) + 组件库(强调品牌色 + 案例)。",
            "趋势敏感:Behance + Design Award + 一线设计师博客 + 季度 hackathon。"
        ],
        "hr_overall_a": 68,
        "hr_overall_b": 70,
    },
    {
        "candidate_id": "cand_pilot_09",
        "role": "marketing",
        "level": "manager",
        "city": "Guangzhou",
        "difficulty": "senior",
        "transcripts": [
            "新品发布活动:预算 50 万,渠道 — 抖音 60% + 微信 25% + 媒体公关 15%,目标 — 注册 5 万。",
            "增长实验:落地页 A/B 测试,我们改 hero 文案 + CTA 位置,转化率 +12%。",
            "SEM 高意图转化,信息流广撒网,KOL 品牌/种草。看阶段(冷启动/增长/品牌)和预算选。",
            "最满意的文案:'你不理财,财不理你',用双关 + 用户洞察 + 短句 + 重复节奏。",
            "舆情 24h:0-2h 监测 + 内部 SOP + 公开回应 + 第三方证言 + 长效改进。",
            "ROI 不达:拆 funnel 看每段损失,归因 — first-touch / last-touch / multi-touch。",
            "三方项目:RACI + kickoff + 里程碑 + 周会同步 + 风险日志。",
            "品牌投入 vs 效果投放:长期看品牌,短期效果。看品牌覆盖率 + 市场渗透 + 转化。",
            "快速理解新行业:二手资料(报告/研报/财报) + 圈层访谈(从业者/客户/对手员工)。",
            "带小团队:分工 + 复盘文化 + 半年一次 OKR review。"
        ],
        "hr_overall_a": 72,
        "hr_overall_b": 71,
    },
    {
        "candidate_id": "cand_pilot_10",
        "role": "sales",
        "level": "manager",
        "city": "Shanghai",
        "difficulty": "senior",
        "transcripts": [
            "Cold call 开场:你好我是 X 公司 Y,我们帮 Z 类客户实现 W 结果(具体到数字);今天通话是 2 分钟,看是否值得续约。",
            "客户说太贵:理解 + 反问(today's cost) + 价值拆解(ROI) + 对比方案(性价比)。",
            "大客户案例:识别决策链 → 教练(内部 champion) → RFC(招标书请求) → 谈判 → 收尾。6 个月成交。",
            "失单复盘:客观归因 — 没有 buyer champion + 没识别到 IT 否决权。行动 — 早接触多角色。",
            "Pipeline 管理:阶段定义(SDC/Q/Demo/Neg) + 阶段转化率 + 阶段停留时长 + 周度 review。",
            "辅导新人:陪访 + 录音复盘 + role play + deal review。前 90 天目标 = 60% quota。",
            "行业洞察积累:Gartner/IDC 报告 + 行业公众号 + 客户内部刊物 + 季度行业 kickoff。",
            "多角色决策:Coach 是 champion,RFC 把需求文档化,采购谈 T&C,财务谈账期,技术谈实施。",
            "让步原则:小让换大让,不值钱先让步,关键底线不退,给退路(时间/数量/付款方式)。",
            "季度末差 40%:优先级 P0 名单 + 调动 SE + 决策人升档接触 + 适度价格让步。"
        ],
        "hr_overall_a": 80,
        "hr_overall_b": 78,
    },
]


# ---------------------------------------------------------------------------
# Pilot runner
# ---------------------------------------------------------------------------
async def run_candidate(cand: dict) -> dict:
    """跑单候选人 — 拉题 / 答题 / 评分 / 报告 / 校准写入."""
    role = cand["role"]
    diff = cand.get("difficulty", "mid")
    questions = await ai_interviewer.generate_questions(role=role, count=10, difficulty=diff)
    transcripts = cand["transcripts"]
    # 用 AIInterviewer 评估每题
    per_q = []
    for i, q in enumerate(questions):
        tr = transcripts[i % len(transcripts)] if transcripts else f"简短回答:基本了解 {q.title} 的概念。"
        ans = await ai_interviewer.evaluate_answer(q, transcript=tr)
        per_q.append({"question_id": q.id, "title": q.title, "ai_score": ans.overall, "ai_band": ans.band})
    # 汇总报告
    answer_scores = [
        # 复用上面的 evaluate 结果需转为 AnswerScore — 简化:重 mock
        type("AS", (), {
            "question_id": pq["question_id"],
            "overall": pq["ai_score"],
            "dimensions": {"communication": pq["ai_score"], "depth": pq["ai_score"]},
            "band": pq["ai_band"],
            "transcript": "",
            "transcript_provider": "user_provided",
            "video_url": None,
            "vision_notes": None,
            "feedback": "",
            "strengths": [],
            "improvements": [],
        })
        for pq in per_q
    ]
    fb = await ai_interviewer.generate_feedback(answer_scores, interview_id=cand["candidate_id"], role=role)
    return {
        "candidate_id": cand["candidate_id"],
        "role": role,
        "difficulty": diff,
        "hr_overall": round((cand["hr_overall_a"] + cand["hr_overall_b"]) / 2, 1),
        "hr_overall_a": cand["hr_overall_a"],
        "hr_overall_b": cand["hr_overall_b"],
        "ai_overall": fb.overall_score,
        "ai_band": _band(fb.overall_score),
        "recommendation": fb.recommendation,
        "per_question": per_q,
        "summary_excerpt": fb.summary[:200],
        "provider": fb.provider,
    }


def _band(score: float) -> str:
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 55:
        return "fair"
    return "weak"


async def run_all(candidates: list[dict] | None = None) -> dict:
    candidates = candidates or REAL_CANDIDATES
    results = []
    for c in candidates:
        try:
            r = await run_candidate(c)
            results.append(r)
            print(f"  ✓ {c['candidate_id']} {c['role']:22s} ai={r['ai_overall']:.1f} hr={r['hr_overall']}")
        except Exception as e:  # noqa: BLE001
            logger.error(f"{c['candidate_id']} failed: {e}")
            results.append({"candidate_id": c["candidate_id"], "role": c.get("role"), "error": str(e)})
    return {
        "task": "T1801 - interview pilot",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "n_candidates": len(results),
        "candidates": results,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output-json", type=str, default=None)
    p.add_argument("--output-md", type=str, default=None)
    p.add_argument("--calibration-out", type=str, default=None)
    p.add_argument("--limit", type=int, default=0, help="只跑前 N 个候选人(0=全部)")
    args = p.parse_args()

    candidates = REAL_CANDIDATES
    if args.limit:
        candidates = candidates[: args.limit]

    print(f"[interview-pilot] running {len(candidates)} candidates ...")
    out = asyncio.run(run_all(candidates))

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    json_path = Path(args.output_json or (REPORT_DIR / f"interview_pilot_{today}.json"))
    md_path = Path(args.output_md or (REPORT_DIR / f"interview_pilot_summary_{today}.md"))
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # 校准:把 AI vs HR 写入 calibration dataset
    calib = InterviewCalibrator()
    for c in out.get("candidates", []):
        if "error" in c:
            continue
        calib.add(
            InterviewRecord(
                candidate_id=c["candidate_id"],
                role=c["role"],
                ai_overall=c["ai_overall"],
                hr_overall_a=c["hr_overall_a"],
                hr_overall_b=c["hr_overall_b"],
                hr_band=_band(c["hr_overall"]),
                ai_band=c["ai_band"],
                notes="T1801 pilot run",
            )
        )
    cal_path = Path(args.calibration_out or (REPORT_DIR / f"interview_calibration_{today}.json"))
    if calib.records:
        calib.save_report(cal_path)
        m = calib.metrics()
        print("\n[calibration]")
        print(json.dumps({
            "n": m["n"], "mae": m["mae"], "bias": m["bias"], "pearson": m["pearson_r"], "qwk": m["quadratic_weighted_kappa"],
            "verdict": m["verdict"], "per_band_accuracy": m["per_band_accuracy"]
        }, ensure_ascii=False, indent=2))

    # Markdown 摘要
    with md_path.open("w", encoding="utf-8") as f:
        f.write("# T1801 - AI 面试 Pilot 报告\n\n")
        f.write(f"生成时间: {out['generated_at']}\n\n候选人数: {out['n_candidates']}\n\n")
        f.write("## 候选人结果\n\n")
        f.write("| ID | 岗位 | AI 评分 | HR 评分 | 推荐 |\n| --- | --- | --- | --- | --- |\n")
        for c in out["candidates"]:
            if "error" in c:
                f.write(f"| {c['candidate_id']} | {c.get('role', '-')} | ERR | - | - |\n")
                continue
            f.write(f"| {c['candidate_id']} | {c['role']} | {c['ai_overall']:.1f} | {c['hr_overall']:.1f} | {c['recommendation']} |\n")
        if calib.records:
            m = calib.metrics()
            f.write(f"\n## 校准指标 (n={m['n']})\n\n")
            f.write(f"- **MAE**: {m['mae']}\n- **Bias**: {m['bias']}\n- **Pearson r**: {m['pearson_r']}\n")
            f.write(f"- **QWK**: {m['quadratic_weighted_kappa']}\n- **Verdict**: {m['verdict']}\n\n")
            f.write("### Band 命中率\n\n")
            for b, acc in m["per_band_accuracy"].items():
                f.write(f"- {b}: {acc}\n")
            f.write("\n### 建议\n\n")
            for s in m["suggestions"]:
                f.write(f"- {s}\n")

    print(f"\n[interview-pilot] JSON: {json_path}")
    print(f"[interview-pilot] MD:   {md_path}")
    print(f"[interview-pilot] Calibration: {cal_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
