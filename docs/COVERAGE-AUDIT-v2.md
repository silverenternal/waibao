# 甲方需求复审报告 (v2.0 规划依据)

**审计日期**: 2026-07-11
**审计范围**: 16 项甲方需求 × 当前实现 (16 个 Agent + 30+ API + 30+ Test)
**审计方法**: 逐条对照 `agents/`、`api/`、`frontend/` 三个维度,评估「已覆盖 / 部分覆盖 / 缺失」

---

## 评分图例

- ✅ **完整** — 前后端 + 数据库 + 测试齐全,生产可用
- 🟡 **部分** — 核心能力有,但 UI/集成/测试某环节缺
- ❌ **缺失** — 还没做,或仅占位

---

## 求职者侧 (1.x)

| 编号 | 需求 | Agent | API | UI | 测试 | 评级 | 差距 |
|---|---|---|---|---|---|---|---|
| 1.1 | 智能/知心朋友 + 学历上传 | ✅ Profile + Intake | ✅ `/api/clarification` `POST /upload` 间接支持 | 🟡 主页只有对话,**没有专门建档表单** | ✅ `test_profile_agent.py` | **🟡** | UI 缺"上传简历"组件; 缺文件解析(目前只接受文本); 缺简历完整度可视化 |
| 1.2 | 工作状态即时更新 + 评价 | ✅ Daily Journal | ✅ `/api/journal` `GET /today` `GET /timeline` | ✅ `(jobseeker)/journal/page.tsx` | ⚠️ 没专门 test | **🟡** | UI 缺少"打分/警告/行动项"的可视化渲染; AI 评价未长期趋势分析 |
| 1.3 | 频繁互动即时响应 | ✅ Realtime Router | ✅ WS + SSE + REST | ✅ SocketProvider | ✅ | **✅** | — |
| 1.4 | 喜怒哀乐接收 + 即时回应 | ✅ Emotion | ✅ `/api/emotion/detect` `timeline` `alerts` | ✅ EmotionChip 组件 | ✅ | **✅** | — (UI 只有顶部 chip,缺完整 timeline 折线图) |
| 1.5 | 海量信息澄清 → 画像 + 需求 | ✅ Clarifier | ✅ `/api/clarification/synthesize` `my-profile` | ❌ **没有 UI** | ✅ | **🟡** | 缺画像可视化页; 缺冲突标注; 缺追问引导 UI |
| 1.6 | 职业规划师 | ✅ Career Planner | ✅ `/api/career-plan/generate` `current` | ✅ `(jobseeker)/plan/page.tsx` | ✅ | **🟡** | market_insights 是 mock; 没接入真实招聘市场; 没"调整计划"机制 |
| 1.x 跨 | **记忆系统** | ✅ MemoryScope (3 层) | ✅ `/api/journal` 时间线 | 🟡 缺长期记忆可视化 | ✅ | **🟡** | 缺「用户记忆档案」页; 缺跨会话连续性可视化 |

**求职者侧总评: 6/7 🟡,1/7 ❌(1.5 UI),0/7 ✅ 完整**

---

## 用人单位侧 (2.x)

| 编号 | 需求 | Agent | API | UI | 测试 | 评级 | 差距 |
|---|---|---|---|---|---|---|---|
| 2.1 | 真诚 HR + 老板助手 | ✅ Persona | ✅ 通过 realtime invoke | 🟡 仅文本回复 | ⚠️ | **🟡** | 缺「人格记忆」(不同老板偏好); 缺升级人工按钮 |
| 2.2 | 资质上传 + 智能验证 | ✅ Compliance | ✅ `/api/compliance/upload` `status` | 🟡 模块页面 | ⚠️ | **🟡** | OCR 是 mock; 工商查询是 mock; 缺过期提醒 |
| 2.3 | 愿景/规划/战略/战术 | ✅ Vision | ✅ `/api/vision/submit` `strategy-map` | 🟡 模块 | ⚠️ | **🟡** | 缺 4 层战略地图可视化; 缺战略随时间 diff |
| 2.4 | 老板描述人才框架 | ✅ Talent Brief | ✅ `/api/talent-brief/submit` | 🟡 模块 | ⚠️ | **🟡** | 偏见检测有,但缺 UI 展示; 缺"为什么"解释 |
| 2.5 | 部门负责人细化 JD | ✅ Job Spec | ✅ `/api/job-spec/submit` | 🟡 模块 | ⚠️ | **🟡** | 没绑定到 role_id 时只是文本输出; over_spec 提示无 UI |
| 2.6 | 规章制度上传 | ✅ Policy | ✅ `/api/policy/upload` `query` `list` | 🟡 模块 | ⚠️ | **🟡** | 缺按类别浏览; 缺法律风险可视化; 缺 chat 集成 |
| 2.7 | 多方频繁互动 | ✅ Multi-Party | ✅ `/api/multiparty/submit` | 🟡 模块 | ⚠️ | **🟡** | 缺多人实时协同 UI; 缺工单/通知机制 |
| 2.8 | 用人方信息澄清 → 人才画像 + 需求 | ✅ Employer Clarifier | ✅ `/api/clarification/synthesize-employer` | ❌ **没有 UI** | ⚠️ | **🟡** | 缺人才画像可视化; 缺「多方冲突」标注 |
| 2.9 | 成为用人方 HR | ✅ HR Service | ❌ **没专门 API** | 🟡 模块(用了 realtime) | ⚠️ | **🟡** | 缺工单系统; 缺 FAQ RAG; 缺工单状态追踪 |
| 2.x 跨 | **多角色 RBAC** | ✅ Permissions | ✅ 5 个 persona | ✅ | ✅ | **🟡** | 角色切换无 UI; dept_head 没专门入口 |

**用人单位侧总评: 10/10 🟡,0/10 ✅,0/10 ❌ (都有,但每条都缺深度)**

---

## 双向匹配 (3)

| 子能力 | 实现 | API | UI | 测试 | 评级 | 差距 |
|---|---|---|---|---|---|---|
| 双向打分 (谐波) | ✅ TwoWay | ✅ `/api/two-way-match/*` | 🟡 match 页 | ✅ | **🟡** | explainer 缺自然语言解释 |
| 互评 | ✅ Mutual Evaluator | ✅ `/api/evaluation/mutual` | 🟡 卡片 | ⚠️ | **🟡** | 缺评分表单 UI; 缺双方对照视图 |
| 反馈闭环 | 🟡 Calibration 已有 | ❌ 缺 trigger endpoint | ❌ | ⚠️ | **🟡** | 缺自动触发; 缺权重可视化调节 |
| 候选人池 / 协同过滤 | ✅ Collections | ✅ | 🟡 | ✅ | **🟡** | — |

**双向匹配总评: 4/4 🟡**

---

## 横切能力差距(系统级)

| 能力 | 现状 | 差距 |
|---|---|---|
| **AI-Native 路由** | ✅ SemanticRouter + ReAct | 缺失败重试路由; 缺路由可解释性 |
| **多模态** | ❌ 缺 | 简历图片 OCR、语音输入、视频面试 |
| **i18n** | ✅ 有 I18n 服务 | 前端未接入多语言 |
| **通知** | ✅ 5 通道 stub | 都是 log; 没有真实发送 |
| **埋点/分析** | ✅ Signals | 漏斗/转化有,缺求职者侧漏斗 |
| **Webhook** | ❌ 缺 | 跟 ATS 对接 |
| **离线/降级** | ✅ Mock LLM | 但 mock 行为未在 e2e 测试覆盖 |
| **审计日志** | 🟡 | 缺 compliance 审计 |
| **A/B 实验** | ❌ | 完全没做 |
| **管理员后台** | 🟡 有 admin/* | 缺用户管理详细面板 |

---

## 16 项需求「覆盖率统计」

| 评级 | 数量 | 占比 |
|---|---|---|
| ✅ 完整 | 1 | 6% |
| 🟡 部分 | 15 | 94% |
| ❌ 缺失 | 0 | 0% |

> **结论**: 16 项需求「形式上都覆盖了」,但只有 1.3 (频繁互动) 真正达到生产级别。其余 15 项都需要继续深化 — 主要问题是 **UI 薄、测试薄、集成浅、缺少真实数据接入**。

---

## 优先补强顺序(下个迭代)

1. **P0 安全与稳定**: 真实 LLM 接入 + 错误重试 + 审计日志
2. **P0 关键 UI**: 简历上传 + 画像可视化 + 战略地图 + 政策浏览
3. **P1 真实数据**: 工商查询 API + 招聘市场 API + OCR 真服务
4. **P1 工单系统**: HR service 缺工单核心
5. **P2 深度能力**: 多模态 + i18n + Webhook + A/B
6. **P2 双向匹配深度**: explainer、反馈闭环、推荐理由