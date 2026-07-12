"""Interview Question Bank — T1301.

设计:
    - 静态题库 100 题,覆盖 10 大类岗位 (每类 10 题)
    - 每题含 category / role / difficulty / question / expected_points / weights
    - LLM 动态生成 (按 role + 维度) 仅做增量补充,失败降级到静态
    - 与 AIInterviewer 协作,导出 10 道题目用于一场面试

Usage:
    from services.question_bank import question_bank
    qs = question_bank.select_questions(role="backend_engineer", count=10)
"""
from __future__ import annotations

import hashlib
import logging
import random
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("recruittech.services.question_bank")


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Question:
    """一道面试题."""

    id: str
    category: str            # 岗位类别, e.g. backend_engineer / product_manager
    title: str               # 题目(短)
    prompt: str              # 给候选人的完整问题
    expected_points: list[str]  # 期望的回答要点
    skills: list[str] = field(default_factory=list)  # 考察的技能标签
    difficulty: str = "mid"   # junior / mid / senior / lead
    duration_sec: int = 120  # 建议答题时长
    type: str = "behavioral"  # behavioral / technical / situational / case
    weights: dict[str, float] = field(default_factory=dict)
    # 上面 weights 示例: {"communication": 0.3, "depth": 0.4, "creativity": 0.3}


# ---------------------------------------------------------------------------
# 10 大类岗位 (与 role taxonomy 对齐)
# ---------------------------------------------------------------------------
ROLE_CATEGORIES = [
    "backend_engineer",
    "frontend_engineer",
    "fullstack_engineer",
    "mobile_engineer",
    "data_engineer",
    "data_scientist",
    "product_manager",
    "designer",
    "marketing",
    "sales",
]


# ---------------------------------------------------------------------------
# 静态题库 (10 类 × 10 题 = 100 题)
# ---------------------------------------------------------------------------
_STATIC_BANK: dict[str, list[dict[str, Any]]] = {
    "backend_engineer": [
        {"title": "系统设计:短链生成", "prompt": "请设计一个短链生成系统,要求:高可用、海量数据、短码不可枚举。请说明核心组件、数据模型、缓存与降级。",
         "expected_points": ["Base62 编码", "发号器/哈希", "读写分离 + 缓存", "rate limit"], "skills": ["system_design", "redis", "高可用"], "difficulty": "senior",
         "type": "technical", "duration_sec": 240, "weights": {"depth": 0.5, "architecture": 0.3, "communication": 0.2}},
        {"title": "数据库隔离级别", "prompt": "解释 MySQL InnoDB 的四种事务隔离级别,以及每种级别下的幻读现象及解决方案。",
         "expected_points": ["RU/RC/RR/Serializable", "MVCC", "next-key lock", "幻读示例"], "skills": ["mysql", "transaction"], "difficulty": "mid",
         "type": "technical", "weights": {"depth": 0.6, "communication": 0.4}},
        {"title": "REST vs RPC", "prompt": "对比 REST 与 gRPC/Thrift,什么场景选什么?为什么我们这里用混合方案?",
         "expected_points": ["协议差异", "性能 vs 可读性", "流式 vs 请求-响应"], "skills": ["api_design"], "difficulty": "mid",
         "type": "technical", "weights": {"depth": 0.5, "tradeoff": 0.5}},
        {"title": "并发与锁", "prompt": "高并发场景下,如何实现一个幂等接口?给出至少 3 种方案及局限。",
         "expected_points": ["唯一索引", "状态机", "Redis SETNX", "token"], "skills": ["concurrency"], "difficulty": "mid",
         "type": "technical", "weights": {"depth": 0.5, "creativity": 0.3, "communication": 0.2}},
        {"title": "故障排查", "prompt": "线上服务 QPS 突降 50%,你的排查思路?",
         "expected_points": ["metrics/log/trace", "依赖逐级排查", "容量评估", "回滚"], "skills": ["ops", "diagnosis"], "difficulty": "senior",
         "type": "behavioral", "weights": {"depth": 0.4, "communication": 0.4, "calm": 0.2}},
        {"title": "团队协作", "prompt": "讲一次你与产品/前端意见冲突的经历,最后怎么推进的?",
         "expected_points": ["冲突描述", "倾听/数据论证", "决策机制", "复盘"], "skills": ["soft_skill"], "difficulty": "mid",
         "type": "behavioral", "weights": {"communication": 0.5, "empathy": 0.3, "ownership": 0.2}},
        {"title": "技术债务", "prompt": "你们项目里最大的技术债务是什么?你如何权衡重构与业务节奏?",
         "expected_points": ["具体案例", "影响量化", "渐进式方案"], "skills": ["ownership"], "difficulty": "senior",
         "type": "behavioral", "weights": {"ownership": 0.5, "depth": 0.3, "communication": 0.2}},
        {"title": "新同事上手", "prompt": "你是新加入的高级工程师,前 30 天你会怎么熟悉代码并交付第一个 PR?",
         "expected_points": ["读文档/OnCall", "小修复入手", "与 Senior 配对"], "skills": ["learning"], "difficulty": "mid",
         "type": "behavioral", "weights": {"planning": 0.4, "communication": 0.4, "humility": 0.2}},
        {"title": "算法:Top K", "prompt": "在不排序的前提下,如何在 N 个数里找到前 K 大?给出时间复杂度对比。",
         "expected_points": ["堆", "快选", "分治"], "skills": ["algo"], "difficulty": "mid",
         "type": "technical", "weights": {"depth": 0.7, "communication": 0.3}},
        {"title": "安全:越权", "prompt": "如何系统性地防止水平越权和垂直越权?列出代码层面的关键检查点。",
         "expected_points": ["RBAC/ABAC", "数据级权限", "审计"], "skills": ["security"], "difficulty": "senior",
         "type": "technical", "weights": {"depth": 0.6, "security_awareness": 0.4}},
    ],
    "frontend_engineer": [
        {"title": "React 渲染优化", "prompt": "举例说明 React 中不必要的 re-render,以及至少 3 种优化手段。",
         "expected_points": ["memo / useMemo / useCallback", "split components", "key", "Recoil/Zustand 选择"], "skills": ["react"], "difficulty": "mid",
         "type": "technical", "weights": {"depth": 0.5, "tradeoff": 0.3, "communication": 0.2}},
        {"title": "前端架构", "prompt": "怎么设计一个中后台前端工程?包管理、模块、状态、网络层、构建产物。",
         "expected_points": ["monorepo", "权限模型", "微前端"], "skills": ["arch"], "difficulty": "senior",
         "type": "technical", "weights": {"depth": 0.4, "architecture": 0.4, "communication": 0.2}},
        {"title": "CSS 陷阱", "prompt": "解释 BFC、stacking context,以及 z-index 失效的常见原因。",
         "expected_points": ["block formatting context", "isolation", "transform/opacity 引出新 stacking"], "skills": ["css"], "difficulty": "mid",
         "type": "technical", "weights": {"depth": 0.7, "communication": 0.3}},
        {"title": "性能指标", "prompt": "讲出 LCP/FCP/CLS/INP 的含义及目标值,你会怎么监控?",
         "expected_points": ["web vitals", "RUM", "lab/field"], "skills": ["perf"], "difficulty": "senior",
         "type": "technical", "weights": {"depth": 0.4, "metric_aware": 0.4, "communication": 0.2}},
        {"title": "协作故事", "prompt": "你和设计/产品为某个交互细节反复争论,怎么处理?",
         "expected_points": ["用户价值", "实验/数据", "决策机制"], "skills": ["soft_skill"], "difficulty": "mid",
         "type": "behavioral", "weights": {"communication": 0.5, "empathy": 0.3, "ownership": 0.2}},
        {"title": "前端安全", "prompt": "XSS/CSRF 是什么,前端常见的防护手段?",
         "expected_points": ["escape", "CSP", "SameSite cookie"], "skills": ["security"], "difficulty": "mid",
         "type": "technical", "weights": {"depth": 0.5, "security_awareness": 0.5}},
        {"title": "上手一段代码", "prompt": "加入陌生代码库,前 2 周你会如何避免破坏性改动?",
         "expected_points": ["lint/test", "feature flag", "pr review 流程"], "skills": ["learning"], "difficulty": "mid",
         "type": "behavioral", "weights": {"planning": 0.4, "humility": 0.4, "communication": 0.2}},
        {"title": "TS 类型体操", "prompt": "什么时候用 `unknown` vs `any`? 给出真实场景。",
         "expected_points": ["类型推断", "类型守卫", "narrowing"], "skills": ["ts"], "difficulty": "mid",
         "type": "technical", "weights": {"depth": 0.6, "communication": 0.4}},
        {"title": "构建工具选择", "prompt": "对比 Vite / Webpack / Turbopack 在 HMR、tree-shaking、产物体积上的差异。",
         "expected_points": ["esbuild", "RSC", "缓存策略"], "skills": ["build_tool"], "difficulty": "mid",
         "type": "technical", "weights": {"depth": 0.4, "tradeoff": 0.4, "communication": 0.2}},
        {"title": "无障碍 a11y", "prompt": "为什么 a11y 重要? 列出 5 个键盘可达问题及修复方式。",
         "expected_points": ["focus ring", "aria-label", "颜色对比度", "tab order"], "skills": ["a11y"], "difficulty": "senior",
         "type": "technical", "weights": {"empathy": 0.4, "depth": 0.3, "communication": 0.3}},
    ],
    "fullstack_engineer": [
        {"title": "全栈视角", "prompt": "一次需求从产品 idea → 上线,作为全栈你会怎么划分边界?",
         "expected_points": ["前后端契约", "数据所有权", "灰度"], "skills": ["fullstack"], "difficulty": "mid",
         "type": "behavioral", "weights": {"planning": 0.4, "communication": 0.4, "depth": 0.2}},
        {"title": "Auth 设计", "prompt": "请设计一个支持 SSO + MFA + Session 的认证方案,并说明攻击面。",
         "expected_points": ["OIDC", "TOTP / WebAuthn", "Session 安全", "CSRF"], "skills": ["security", "auth"], "difficulty": "senior",
         "type": "technical", "weights": {"depth": 0.4, "security_awareness": 0.4, "communication": 0.2}},
        {"title": "数据库设计", "prompt": "设计一个简单工单系统的表结构,核心字段 + 索引策略。",
         "expected_points": ["ER", "FK", "复合索引", "软删除"], "skills": ["db_design"], "difficulty": "mid",
         "type": "technical", "weights": {"depth": 0.6, "communication": 0.4}},
        {"title": "缓存一致性", "prompt": "DB 与 Redis 的数据一致性怎么做? 说出至少 2 种方案和失效场景。",
         "expected_points": ["Cache-Aside", "延迟双删", "binlog 订阅"], "skills": ["redis"], "difficulty": "senior",
         "type": "technical", "weights": {"depth": 0.5, "tradeoff": 0.5}},
        {"title": "故障演练", "prompt": "API 5xx 比例突增,你的 30 分钟 on-call 步骤?",
         "expected_points": ["看板", "日志", "回滚", "用户沟通"], "skills": ["ops"], "difficulty": "senior",
         "type": "behavioral", "weights": {"calm": 0.4, "communication": 0.4, "depth": 0.2}},
        {"title": "代码评审", "prompt": "你做 code review 时最关注哪三件事?给出反例。",
         "expected_points": ["可读性", "边界/错误", "性能"], "skills": ["review"], "difficulty": "mid",
         "type": "behavioral", "weights": {"communication": 0.5, "depth": 0.3, "ownership": 0.2}},
        {"title": "前端 ↔ 后端协议", "prompt": "GraphQL / tRPC / REST 各自适合什么场景?为什么?",
         "expected_points": ["按需 vs 暴露", "契约", "缓存"], "skills": ["api"], "difficulty": "mid",
         "type": "technical", "weights": {"tradeoff": 0.5, "communication": 0.5}},
        {"title": "可观测性", "prompt": "设计一套覆盖前端+后端的可观测性体系。",
         "expected_points": ["trace / metric / log", "OTel", "RUM"], "skills": ["observability"], "difficulty": "senior",
         "type": "technical", "weights": {"depth": 0.4, "metric_aware": 0.4, "communication": 0.2}},
        {"title": "学习新框架", "prompt": "公司要引入 DDD,你怎么判断并落地?",
         "expected_points": ["价值假设", "PoC", "分享"], "skills": ["learning"], "difficulty": "senior",
         "type": "behavioral", "weights": {"planning": 0.4, "communication": 0.3, "depth": 0.3}},
        {"title": "软技能", "prompt": "讲一次推动跨团队变更的经历。",
         "expected_points": ["利益相关方", "MVP", "对齐机制"], "skills": ["soft_skill"], "difficulty": "mid",
         "type": "behavioral", "weights": {"communication": 0.5, "ownership": 0.5}},
    ],
    "mobile_engineer": [
        {"title": "iOS 内存", "prompt": "iOS 上 ARC 与 MRC 的差异? 哪些场景需要注意 retain cycle?",
         "expected_points": ["引用计数", "weak/unowned", "delegate/block"], "skills": ["ios"], "difficulty": "mid",
         "type": "technical", "weights": {"depth": 0.6, "communication": 0.4}},
        {"title": "Android 启动优化", "prompt": "Android App 冷启动优化思路?",
         "expected_points": ["启动器", "懒加载", "Systrace"], "skills": ["android"], "difficulty": "senior",
         "type": "technical", "weights": {"depth": 0.5, "metric_aware": 0.5}},
        {"title": "跨端方案选型", "prompt": "RN / Flutter / Native 各自的边界?选型经验?",
         "expected_points": ["bridge / engine", "性能 / 体验"], "skills": ["cross_platform"], "difficulty": "mid",
         "type": "technical", "weights": {"tradeoff": 0.5, "communication": 0.5}},
        {"title": "离线优先", "prompt": "如何设计一个可离线工作的 App?",
         "expected_points": ["本地存储", "同步队列", "冲突解决"], "skills": ["offline"], "difficulty": "senior",
         "type": "technical", "weights": {"depth": 0.5, "creativity": 0.3, "communication": 0.2}},
        {"title": "性能监控", "prompt": "移动端的卡顿监控怎么做?",
         "expected_points": ["FPS / ANR / Watchdog"], "skills": ["perf"], "difficulty": "senior",
         "type": "technical", "weights": {"depth": 0.5, "metric_aware": 0.5}},
        {"title": "灰度发布", "prompt": "讲一次移动端灰度策略制定的经验。",
         "expected_points": ["指标", "分桶", "回滚"], "skills": ["release"], "difficulty": "senior",
         "type": "behavioral", "weights": {"planning": 0.5, "communication": 0.5}},
        {"title": "崩溃排查", "prompt": "用户反馈某机型必崩,排查思路?",
         "expected_points": ["机型分桶", "日志", "回放"], "skills": ["diag"], "difficulty": "mid",
         "type": "behavioral", "weights": {"calm": 0.4, "communication": 0.3, "depth": 0.3}},
        {"title": "团队协作", "prompt": "你和设计就动画时长争论,如何收尾?",
         "expected_points": ["数据/共识", "妥协"], "skills": ["soft_skill"], "difficulty": "mid",
         "type": "behavioral", "weights": {"communication": 0.5, "empathy": 0.5}},
        {"title": "App 安全", "prompt": "列举 5 种移动端常见安全攻击及防护。",
         "expected_points": ["反编译", "调试", "中间人"], "skills": ["security"], "difficulty": "senior",
         "type": "technical", "weights": {"security_awareness": 0.6, "depth": 0.4}},
        {"title": "架构演进", "prompt": "你们 App 的模块化方案怎么选?",
         "expected_points": ["业务模块", "路由", "解耦"], "skills": ["arch"], "difficulty": "senior",
         "type": "technical", "weights": {"depth": 0.4, "architecture": 0.4, "communication": 0.2}},
    ],
    "data_engineer": [
        {"title": "数仓分层", "prompt": "讲一下常见的数仓分层及边界。",
         "expected_points": ["ODS/DWD/DWS/ADS"], "skills": ["dw"], "difficulty": "mid",
         "type": "technical", "weights": {"depth": 0.6, "communication": 0.4}},
        {"title": "流批一体", "prompt": "Flink / Spark Streaming 在 Exactly-Once 上如何实现?",
         "expected_points": ["checkpoint", "两阶段提交", "幂等"], "skills": ["stream"], "difficulty": "senior",
         "type": "technical", "weights": {"depth": 0.6, "communication": 0.4}},
        {"title": "数据质量", "prompt": "如何设计数据质量监控?",
         "expected_points": ["指标", "告警", "基线"], "skills": ["dq"], "difficulty": "mid",
         "type": "technical", "weights": {"metric_aware": 0.4, "depth": 0.3, "communication": 0.3}},
        {"title": "建模案例", "prompt": "某业务宽表怎么设计?举一个例子。",
         "expected_points": ["维度/度量", "缓慢变化维"], "skills": ["modeling"], "difficulty": "senior",
         "type": "technical", "weights": {"depth": 0.7, "communication": 0.3}},
        {"title": "ETL 排错", "prompt": "任务突然变慢 10 倍,排查思路?",
         "expected_points": ["数据倾斜", "资源", "依赖"], "skills": ["troubleshoot"], "difficulty": "senior",
         "type": "behavioral", "weights": {"depth": 0.4, "calm": 0.3, "communication": 0.3}},
        {"title": "成本优化", "prompt": "大数据任务的成本优化思路?",
         "expected_points": ["压缩", "生命周期", "spot"], "skills": ["cost"], "difficulty": "senior",
         "type": "behavioral", "weights": {"ownership": 0.5, "depth": 0.5}},
        {"title": "软技能", "prompt": "业务方一直要新指标,你如何梳理优先级?",
         "expected_points": ["评估维度", "对齐", "取舍"], "skills": ["soft_skill"], "difficulty": "mid",
         "type": "behavioral", "weights": {"communication": 0.5, "planning": 0.5}},
        {"title": "Schema 演进", "prompt": "Avro / Protobuf 的 schema 演进策略?",
         "expected_points": ["兼容性", "默认值"], "skills": ["schema"], "difficulty": "mid",
         "type": "technical", "weights": {"depth": 0.6, "communication": 0.4}},
        {"title": "湖仓一体", "prompt": "Iceberg/Hudi/Delta 的差异?选哪种?",
         "expected_points": ["ACID", "查询引擎"], "skills": ["lakehouse"], "difficulty": "senior",
         "type": "technical", "weights": {"tradeoff": 0.5, "depth": 0.5}},
        {"title": "指标治理", "prompt": "你们如何避免指标口径不一致?",
         "expected_points": ["OneService", "指标字典"], "skills": ["governance"], "difficulty": "mid",
         "type": "behavioral", "weights": {"communication": 0.5, "ownership": 0.5}},
    ],
    "data_scientist": [
        {"title": "建模流程", "prompt": "讲一个 end-to-end 的建模项目:从问题定义到上线。",
         "expected_points": ["问题定义", "特征/标注", "验证", "上线"], "skills": ["ml"], "difficulty": "senior",
         "type": "behavioral", "weights": {"ownership": 0.4, "depth": 0.3, "communication": 0.3}},
        {"title": "指标与因果", "prompt": "AB 实验不显著可能的原因?",
         "expected_points": ["功效", "SRM", "新奇效应"], "skills": ["ab"], "difficulty": "senior",
         "type": "technical", "weights": {"depth": 0.6, "communication": 0.4}},
        {"title": "推荐冷启动", "prompt": "新用户/新内容冷启动方案?",
         "expected_points": ["规则/Explore", "外部特征"], "skills": ["recsys"], "difficulty": "senior",
         "type": "technical", "weights": {"creativity": 0.4, "depth": 0.4, "communication": 0.2}},
        {"title": "数据偏差", "prompt": "如何识别和处理数据偏差?",
         "expected_points": ["采样", "重加权"], "skills": ["data_quality"], "difficulty": "mid",
         "type": "technical", "weights": {"depth": 0.6, "communication": 0.4}},
        {"title": "特征工程", "prompt": "举例说明你做过的一个有效的特征设计。",
         "expected_points": ["信号", "嵌入", "组合"], "skills": ["fe"], "difficulty": "mid",
         "type": "behavioral", "weights": {"depth": 0.4, "ownership": 0.3, "communication": 0.3}},
        {"title": "评估指标", "prompt": "AUC 提升但业务收益不明显,可能原因?",
         "expected_points": ["阈值", "排序", "反馈"], "skills": ["metric"], "difficulty": "senior",
         "type": "technical", "weights": {"depth": 0.5, "communication": 0.5}},
        {"title": "软技能", "prompt": "产品给的目标模糊,你如何拆解?",
         "expected_points": ["假设", "度量", "对齐"], "skills": ["soft_skill"], "difficulty": "mid",
         "type": "behavioral", "weights": {"communication": 0.5, "planning": 0.5}},
        {"title": "LLM 应用", "prompt": "如何把 LLM 接入到产品中?需要哪些评估?",
         "expected_points": ["RAG", "评测集", "成本/延迟"], "skills": ["llm"], "difficulty": "mid",
         "type": "technical", "weights": {"depth": 0.4, "tradeoff": 0.4, "communication": 0.2}},
        {"title": "数据漂移", "prompt": "如何监控线上模型的输入分布漂移?",
         "expected_points": ["PSI", "样本对比"], "skills": ["monitor"], "difficulty": "mid",
         "type": "technical", "weights": {"metric_aware": 0.5, "depth": 0.5}},
        {"title": "失败案例", "prompt": "讲一次模型上线后效果不好的复盘。",
         "expected_points": ["根因", "行动项"], "skills": ["reflect"], "difficulty": "senior",
         "type": "behavioral", "weights": {"ownership": 0.5, "communication": 0.5}},
    ],
    "product_manager": [
        {"title": "需求评估", "prompt": "如何判断一个需求值不值得做?",
         "expected_points": ["用户价值", "商业价值", "成本", "风险"], "skills": ["judgment"], "difficulty": "mid",
         "type": "behavioral", "weights": {"judgment": 0.4, "communication": 0.4, "planning": 0.2}},
        {"title": "产品决策", "prompt": "讲一次你和研发对优先级分歧的经历。",
         "expected_points": ["数据/用户", "取舍"], "skills": ["soft_skill"], "difficulty": "senior",
         "type": "behavioral", "weights": {"communication": 0.5, "ownership": 0.5}},
        {"title": "指标体系", "prompt": "怎么为一个新业务搭建指标体系?",
         "expected_points": ["北极星", "A1/A2"], "skills": ["metric"], "difficulty": "mid",
         "type": "technical", "weights": {"metric_aware": 0.5, "communication": 0.5}},
        {"title": "用户访谈", "prompt": "用户访谈怎样避免诱导?",
         "expected_points": ["中立问题", "避免建议"], "skills": ["research"], "difficulty": "mid",
         "type": "behavioral", "weights": {"empathy": 0.5, "communication": 0.5}},
        {"title": "MVP 设计", "prompt": "为某场景设计 MVP,并说明放弃哪些功能。",
         "expected_points": ["假设", "范围"], "skills": ["mvp"], "difficulty": "senior",
         "type": "technical", "weights": {"creativity": 0.4, "judgment": 0.4, "communication": 0.2}},
        {"title": "竞品分析", "prompt": "如何快速判断竞品的关键差异?",
         "expected_points": ["定位", "用户旅程"], "skills": ["analysis"], "difficulty": "mid",
         "type": "behavioral", "weights": {"depth": 0.4, "communication": 0.4, "judgment": 0.2}},
        {"title": "数据驱动", "prompt": "DAU 下跌 20% 你的 7 天行动计划?",
         "expected_points": ["定位", "假设", "实验"], "skills": ["ops"], "difficulty": "senior",
         "type": "behavioral", "weights": {"calm": 0.4, "communication": 0.3, "depth": 0.3}},
        {"title": "PRD 写作", "prompt": "请描述一个你写过的 PRD 中最关键的页面。",
         "expected_points": ["目标/范围/流程"], "skills": ["prd"], "difficulty": "mid",
         "type": "behavioral", "weights": {"communication": 0.5, "depth": 0.5}},
        {"title": "商业模式", "prompt": "讲一次你思考商业模式的经历。",
         "expected_points": ["价值链", "Pricing"], "skills": ["biz"], "difficulty": "senior",
         "type": "behavioral", "weights": {"judgment": 0.5, "communication": 0.5}},
        {"title": "团队协作", "prompt": "你带新人 PM 的方法?",
         "expected_points": ["建模", "复盘"], "skills": ["leadership"], "difficulty": "senior",
         "type": "behavioral", "weights": {"communication": 0.5, "empathy": 0.5}},
    ],
    "designer": [
        {"title": "设计取舍", "prompt": "讲一次你最纠结的设计决策与原因。",
         "expected_points": ["用户", "业务", "技术"], "skills": ["judgment"], "difficulty": "mid",
         "type": "behavioral", "weights": {"communication": 0.5, "judgment": 0.5}},
        {"title": "用户旅程", "prompt": "如何为一个新功能梳理用户旅程?",
         "expected_points": ["persona", "任务流", "情绪"], "skills": ["research"], "difficulty": "mid",
         "type": "behavioral", "weights": {"empathy": 0.5, "communication": 0.5}},
        {"title": "设计系统", "prompt": "讲讲你参与的设计系统的搭建经验。",
         "expected_points": ["tokens", "组件", "贡献流程"], "skills": ["design_system"], "difficulty": "senior",
         "type": "technical", "weights": {"depth": 0.4, "architecture": 0.3, "communication": 0.3}},
        {"title": "可用性", "prompt": "什么是 Nielsen 10 条?挑 3 条最常用的解释。",
         "expected_points": ["可见性", "匹配现实", "防错"], "skills": ["ux"], "difficulty": "mid",
         "type": "technical", "weights": {"depth": 0.6, "communication": 0.4}},
        {"title": "评审争议", "prompt": "讲一次你和产品/研发的设计争议和解决方式。",
         "expected_points": ["共识", "数据"], "skills": ["soft_skill"], "difficulty": "mid",
         "type": "behavioral", "weights": {"communication": 0.5, "empathy": 0.5}},
        {"title": "协同效率", "prompt": "设计-研发交付协作如何减少反复?",
         "expected_points": ["约定", "review"], "skills": ["ops"], "difficulty": "senior",
         "type": "behavioral", "weights": {"communication": 0.5, "ownership": 0.5}},
        {"title": "研究方法", "prompt": "举例定量 + 定性结合的研究案例。",
         "expected_points": ["问卷+访谈"], "skills": ["research"], "difficulty": "mid",
         "type": "technical", "weights": {"depth": 0.4, "communication": 0.4, "judgment": 0.2}},
        {"title": "原型与验证", "prompt": "低保真 vs 高保真原型使用时机?",
         "expected_points": ["探索", "验证"], "skills": ["prototype"], "difficulty": "mid",
         "type": "technical", "weights": {"judgment": 0.5, "communication": 0.5}},
        {"title": "品牌一致性", "prompt": "如何让品牌策略落到具体页面?",
         "expected_points": ["guideline", "组件"], "skills": ["brand"], "difficulty": "senior",
         "type": "behavioral", "weights": {"communication": 0.5, "ownership": 0.5}},
        {"title": "可持续学习", "prompt": "你如何保持设计趋势敏感?",
         "expected_points": ["来源", "实践"], "skills": ["learning"], "difficulty": "mid",
         "type": "behavioral", "weights": {"humility": 0.5, "communication": 0.5}},
    ],
    "marketing": [
        {"title": "活动策划", "prompt": "为新产品策划一次发布活动,说明预算、渠道、目标。",
         "expected_points": ["SMART 目标", "渠道组合"], "skills": ["planning"], "difficulty": "mid",
         "type": "behavioral", "weights": {"planning": 0.4, "creativity": 0.3, "communication": 0.3}},
        {"title": "增长案例", "prompt": "讲一次你跑出的增长实验。",
         "expected_points": ["假设", "实验", "数据"], "skills": ["growth"], "difficulty": "senior",
         "type": "behavioral", "weights": {"ownership": 0.4, "depth": 0.3, "communication": 0.3}},
        {"title": "渠道对比", "prompt": "SEM / 信息流 / KOL 三种渠道适合什么场景?",
         "expected_points": ["用户意图", "成本结构"], "skills": ["channel"], "difficulty": "mid",
         "type": "technical", "weights": {"tradeoff": 0.5, "communication": 0.5}},
        {"title": "内容能力", "prompt": "你写过最满意的一份文案?为什么?",
         "expected_points": ["洞察", "改稿"], "skills": ["copy"], "difficulty": "mid",
         "type": "behavioral", "weights": {"creativity": 0.5, "communication": 0.5}},
        {"title": "危机公关", "prompt": "遇到负面舆情,你 24 小时动作?",
         "expected_points": ["响应", "证据"], "skills": ["risk"], "difficulty": "senior",
         "type": "behavioral", "weights": {"calm": 0.4, "communication": 0.4, "judgment": 0.2}},
        {"title": "数据复盘", "prompt": "ROI 不达预期,如何定位?",
         "expected_points": ["漏斗", "归因"], "skills": ["analysis"], "difficulty": "senior",
         "type": "technical", "weights": {"depth": 0.4, "judgment": 0.3, "communication": 0.3}},
        {"title": "跨部门协作", "prompt": "市场+产品+研发三方项目如何推进?",
         "expected_points": ["RACI", "里程碑"], "skills": ["ops"], "difficulty": "mid",
         "type": "behavioral", "weights": {"communication": 0.5, "planning": 0.5}},
        {"title": "品牌 vs 效果", "prompt": "讲讲品牌投入与效果投放的平衡。",
         "expected_points": ["短长期"], "skills": ["strategy"], "difficulty": "senior",
         "type": "behavioral", "weights": {"judgment": 0.5, "communication": 0.5}},
        {"title": "用户洞察", "prompt": "不做调研,如何快速理解一个新行业?",
         "expected_points": ["二手资料", "圈层访谈"], "skills": ["research"], "difficulty": "mid",
         "type": "behavioral", "weights": {"creativity": 0.4, "communication": 0.4, "judgment": 0.2}},
        {"title": "领导力", "prompt": "你如何带小团队完成重要 campaign?",
         "expected_points": ["分工", "复盘"], "skills": ["leadership"], "difficulty": "senior",
         "type": "behavioral", "weights": {"ownership": 0.5, "communication": 0.5}},
    ],
    "sales": [
        {"title": "陌生拜访", "prompt": "第一次 cold call 你会怎么开场?",
         "expected_points": ["价值主张", "提问"], "skills": ["outreach"], "difficulty": "junior",
         "type": "behavioral", "weights": {"communication": 0.5, "creativity": 0.3, "calm": 0.2}},
        {"title": "异议处理", "prompt": "客户说太贵了,你怎么回应?",
         "expected_points": ["价值", "对比", "选择"], "skills": ["objection"], "difficulty": "mid",
         "type": "behavioral", "weights": {"communication": 0.5, "empathy": 0.3, "judgment": 0.2}},
        {"title": "大单案例", "prompt": "讲一次你拿下大客户的全过程。",
         "expected_points": ["决策链", "教练"], "skills": ["case"], "difficulty": "senior",
         "type": "behavioral", "weights": {"ownership": 0.4, "communication": 0.4, "depth": 0.2}},
        {"title": "失单复盘", "prompt": "输掉一单后,你怎么复盘?",
         "expected_points": ["客观原因", "行动"], "skills": ["reflect"], "difficulty": "mid",
         "type": "behavioral", "weights": {"ownership": 0.5, "humility": 0.5}},
        {"title": "销售漏斗", "prompt": "如何管理 pipeline 提高转化?",
         "expected_points": ["阶段定义", "量化"], "skills": ["ops"], "difficulty": "mid",
         "type": "technical", "weights": {"metric_aware": 0.4, "depth": 0.3, "communication": 0.3}},
        {"title": "团队带教", "prompt": "如何辅导一名新人销售?",
         "expected_points": ["陪访", "录音复盘"], "skills": ["leadership"], "difficulty": "senior",
         "type": "behavioral", "weights": {"communication": 0.5, "empathy": 0.5}},
        {"title": "行业洞察", "prompt": "对客户所在行业的洞察怎么积累?",
         "expected_points": ["信息来源", "复用"], "skills": ["research"], "difficulty": "mid",
         "type": "behavioral", "weights": {"humility": 0.5, "communication": 0.5}},
        {"title": "多角色决策", "prompt": "面对采购、技术、财务多角色怎么推进?",
         "expected_points": ["Coach", "RFC"], "skills": ["multi_role"], "difficulty": "senior",
         "type": "behavioral", "weights": {"communication": 0.5, "judgment": 0.5}},
        {"title": "谈判策略", "prompt": "谈判中让步的原则?",
         "expected_points": ["价值交换", "退路"], "skills": ["negotiation"], "difficulty": "senior",
         "type": "behavioral", "weights": {"judgment": 0.5, "communication": 0.5}},
        {"title": "压力时刻", "prompt": "季度末距目标还有 40%,你怎么办?",
         "expected_points": ["优先级", "协调资源"], "skills": ["calm"], "difficulty": "senior",
         "type": "behavioral", "weights": {"calm": 0.5, "communication": 0.3, "judgment": 0.2}},
    ],
}


# ---------------------------------------------------------------------------
# 题库服务
# ---------------------------------------------------------------------------
class QuestionBank:
    """100 题静态题库 + LLM 动态补充."""

    def __init__(self) -> None:
        self._compiled: list[Question] = []
        self._compile()

    def _compile(self) -> None:
        for role, items in _STATIC_BANK.items():
            for idx, raw in enumerate(items, start=1):
                qid = self._qid(role, idx)
                self._compiled.append(
                    Question(
                        id=qid,
                        category=role,
                        title=raw["title"],
                        prompt=raw["prompt"],
                        expected_points=raw.get("expected_points", []),
                        skills=raw.get("skills", []),
                        difficulty=raw.get("difficulty", "mid"),
                        duration_sec=raw.get("duration_sec", 120),
                        type=raw.get("type", "behavioral"),
                        weights=raw.get("weights", {"depth": 0.5, "communication": 0.5}),
                    )
                )
        logger.info(
            f"QuestionBank compiled: {len(self._compiled)} questions, "
            f"{len(set(q.category for q in self._compiled))} categories"
        )

    @staticmethod
    def _qid(role: str, idx: int) -> str:
        return f"q_{role}_{idx:02d}"

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    def select_questions(
        self, role: str, count: int = 10, *, difficulty: str | None = None
    ) -> list[Question]:
        """按 role + 难度均匀抽取 count 道题.

        Args:
            role: 岗位 category (backend_engineer / ...)
            count: 题目数量
            difficulty: 可选难度过滤 (junior/mid/senior/lead)
        """
        # 找不到 category 时降级为通用题 (用 backend 题,题目足够泛)
        candidates = [q for q in self._compiled if q.category == role]
        if not candidates:
            logger.warning(f"role {role} not in static bank; fallback to backend_engineer")
            candidates = [q for q in self._compiled if q.category == "backend_engineer"]
        if difficulty:
            sub = [q for q in candidates if q.difficulty == difficulty]
            if sub:
                candidates = sub
        # 固定种子 + 角色,保证同一角色尽量稳定 (但仍有一定随机性)
        random.seed(hash(role) & 0xFFFF)
        # 类型分布: 4 技术 + 4 行为 + 2 情景/案例 (允许重复)
        chosen = self._balanced_pick(candidates, count)
        # 重新注入顺序 (稳定)
        chosen = sorted(chosen, key=lambda q: q.id)
        return chosen[:count]

    @staticmethod
    def _balanced_pick(pool: list[Question], n: int) -> list[Question]:
        if not pool:
            return []
        tech = [q for q in pool if q.type == "technical"]
        beh = [q for q in pool if q.type == "behavioral"]
        sit = [q for q in pool if q.type in ("situational", "case")]
        chosen: list[Question] = []
        for bucket, k in ((tech, max(1, n // 2)), (beh, max(1, n // 3)), (sit, n - max(1, n // 2) - max(1, n // 3))):
            random.shuffle(bucket)
            chosen.extend(bucket[:k])
        # 不足补齐
        if len(chosen) < n:
            rest = [q for q in pool if q not in chosen]
            random.shuffle(rest)
            chosen.extend(rest[: n - len(chosen)])
        return chosen

    def get_by_id(self, qid: str) -> Question | None:
        for q in self._compiled:
            if q.id == qid:
                return q
        return None

    def stats(self) -> dict[str, int]:
        """统计,用于管理界面."""
        out: dict[str, int] = {}
        for q in self._compiled:
            out[q.category] = out.get(q.category, 0) + 1
        return out

    # ------------------------------------------------------------------
    # LLM 动态补充 (T1301 占位实现)
    # ------------------------------------------------------------------
    async def generate_extra_questions(
        self,
        role: str,
        count: int = 2,
        *,
        llm_provider: Any | None = None,
    ) -> list[Question]:
        """调用 LLM 补充新题,失败降级到静态。

        在 mock 模式下不会真正调用 LLM,直接返回空 (题库已够用)。
        """
        if count <= 0:
            return []
        try:
            provider = llm_provider
            if provider is None:
                # 不在运行时加载,避免 import side-effects
                return []
            prompt = (
                f"为岗位类别 {role} 生成 {count} 道结构化面试题。"
                "输出 JSON: [{title, prompt, expected_points:[], difficulty, type, weights:{}}]"
            )
            messages = [{"role": "user", "content": prompt}]
            out = await provider.complete(
                messages=messages,
                model="gpt-4o-mini",
                temperature=0.7,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )
            data = out.get("content", "{}")
            import json as _json

            parsed = _json.loads(data) if isinstance(data, str) else data
            items = parsed.get("questions", []) if isinstance(parsed, dict) else []
            extras: list[Question] = []
            for idx, raw in enumerate(items[:count], start=1):
                extras.append(
                    Question(
                        id=f"q_gen_{role}_{idx}_{hashlib.md5(raw.get('prompt','').encode()).hexdigest()[:6]}",
                        category=role,
                        title=str(raw.get("title", f"AI 题目 {idx}"))[:80],
                        prompt=str(raw.get("prompt", ""))[:500],
                        expected_points=list(raw.get("expected_points", []))[:8],
                        skills=list(raw.get("skills", [role])),
                        difficulty=str(raw.get("difficulty", "mid")),
                        duration_sec=int(raw.get("duration_sec", 120)),
                        type=str(raw.get("type", "behavioral")),
                        weights=dict(raw.get("weights", {"depth": 0.5, "communication": 0.5})),
                    )
                )
            return extras
        except Exception as e:  # noqa: BLE001
            logger.warning(f"LLM generate_extra_questions failed: {e}")
            return []


# 单例
question_bank = QuestionBank()
