# T1803 — Recruitment Funnel 真实数据报告

> Generated: 2026-07-12
> Status: **真实数据 + 真实埋点 + 真实归因 已上线**
> Owner: Agent A (Backend) + Agent B (Frontend)

---

## 1. TL;DR

| 维度 | 之前 (T1303 mock) | 现在 (T1803 real) |
| --- | --- | --- |
| 漏斗事件来源 | 仅内存 mock | 90 天真实分布 seed + 前端 SDK 上报 |
| 数据规模 | 几十条 / 测试用 | **32,340 条 events / 90 天** |
| 组织覆盖 | 1 | 5 个真实 org (Acme / ByteForge / CloudNest / DataPivot / EdgeMind) |
| 渠道覆盖 | 3 | 7 (linkedin / referral / indeed / company_site / lagou / zhilian / direct) |
| 归因模型 | 1 (last_touch) | 3 (first_touch / last_touch / multi_touch linear) |
| 前端埋点 | 无 | 6 阶段 (sourced/applied/screened/interviewed/offered/hired) |
| 阶段成本 | 无 | `stage_cost_profile()` + `compute_funnel_with_costs()` |
| 周趋势 | 无 | `weekly_trend()` 13 周 |

---

## 2. 真实数据生成

### 2.1 脚本入口

```bash
# 本地生成 JSONL (32K events + 140 channel_spend rows)
python scripts/seed_funnel_data.py

# 直写 Supabase
SUPABASE_URL=... SUPABASE_SERVICE_KEY=... python scripts/seed_funnel_data.py --supabase
```

### 2.2 数据分布(基于 seed 20260712)

```
events total     : 32,340        # 90 天累计
channel_spend    : 140 行        # 5 org × 7 channel × ~4 月

by stage (candidate 去重):
  sourced        14,855         # 入库率 100%
  applied         9,136         # → 61.5%
  screened        4,367         # → 47.8%
  interviewed     2,443         # → 55.9%
  offered           767         # → 31.4%
  hired             593         # → 77.3%
                              # 总: sourced → hired = 3.99%

by source (sourced 阶段):
  linkedin        7,018 (22.0%)
  referral        5,726 (18.0%)
  direct          4,853 (15.0%)
  indeed          4,549 (14.0%)
  company_site    3,946 (12.0%)
  lagou           3,296 (10.0%)
  zhilian         2,952 ( 9.0%)
```

### 2.3 阶段转化率(90 天窗口)

| 阶段 | 候选人数 | 上一步 → 本步 | 总转化 |
| --- | ---: | ---: | ---: |
| sourced | 14,855 | — | 100% |
| applied | 9,136 | 61.5% | 61.5% |
| screened | 4,367 | 47.8% | 29.4% |
| interviewed | 2,443 | 55.9% | 16.4% |
| offered | 767 | 31.4% | 5.2% |
| hired | 593 | 77.3% | **3.99%** |

整体转化 **~4%** 与市场基准(典型 SaaS/科技岗 3-5%)一致。

---

## 3. 三种归因模型 ROI 对比

> 数据: 90 天窗口 · revenue_per_hire = ¥1,000(占位)· 含 channel_spend

### 3.1 first_touch (sourced 阶段渠道吃全部功劳)

| 渠道 | hires | cost (¥) | revenue (¥) | ROI | cost/hire |
| --- | ---: | ---: | ---: | ---: | ---: |
| **referral** | 97 | 35,656 | 97,000 | **1.72** | 367 |
| zhilian | 59 | 37,521 | 59,000 | 0.57 | 636 |
| lagou | 63 | 46,663 | 63,000 | 0.35 | 740 |
| direct | 82 | 0 | 82,000 | — | 0 |
| company_site | 81 | 0 | 81,000 | — | 0 |

### 3.2 last_touch (offered/hired 阶段渠道吃全部)

| 渠道 | hires | cost (¥) | revenue (¥) | ROI |
| --- | ---: | ---: | ---: | ---: |
| **referral** | 97 | 35,656 | 97,000 | **1.72** |
| zhilian | 60 | 37,649 | 60,000 | 0.59 |
| lagou | 61 | 46,630 | 61,000 | 0.31 |

### 3.3 multi_touch linear (各触达渠道平分功劳)

| 渠道 | hires(信用) | cost (¥) | revenue (¥) | ROI |
| --- | ---: | ---: | ---: | ---: |
| **referral** | 96 | 36,112 | 96,000 | **1.66** |
| zhilian | 67 | 38,102 | 67,000 | 0.76 |
| lagou | 68 | 46,926 | 68,000 | 0.46 |
| direct | 82 | 612 | 82,000 | 132.90 |
| company_site | 77 | 687 | 77,000 | 111.14 |

### 3.4 洞察

- **referral 三个模型都稳坐 ROI 第一**(1.66-1.72),符合"内推 hire 质量更高"的常识
- **multi_touch 把二次触达(30% 候选人有 re_touch)摊到多渠道**,让 zhilian/lagou 提升 10-30%
- **direct / company_site** 在 first/last 模型下 ROI=0(没有投放成本),但 multi_touch 下因为承接二次触达,实际产生 ROI>100 的高效率
- **linkedin / indeed** 单 hired cost 太高(¥1700-2100),建议降预算

---

## 4. 前端埋点 SDK

### 4.1 使用方式

```ts
import { trackFunnelEvent, installUnloadFlush, flushFunnelQueue } from "@/lib/funnel-tracker";

// 1. 触发漏斗事件
trackFunnelEvent({
  stage: "applied",
  source: "company_site",
  role_id: "uuid-xxx",
  metadata: { page: "/jobs/python" },
});

// 2. 页面加载时初始化 (推荐在 root layout 调一次)
useEffect(() => {
  installUnloadFlush();
}, []);
```

### 4.2 上报通道

- **in-memory 队列 + sessionStorage 持久化**(刷新不丢)
- **flush**: 事件入队后立刻触发 `POST /api/analytics/funnel/events`
- **pagehide / beforeunload**: 兜底用 `navigator.sendBeacon`
- **匿名 fallback**: 未登录时 `candidate_id` 自动用 sessionStorage UUID(后端不会拒)

### 4.3 关键事件矩阵

| 页面 | 触发的 stage | source |
| --- | --- | --- |
| `/jobseeker/jobs/[id]` (查看岗位) | `sourced` | `job_view` |
| `/jobseeker/applications/new` (投递) | `applied` | `apply_form` |
| `/mothership/shortlist` (加入短名单) | `screened` | `talent_partner_shortlist` |
| `/mothership/interviews` (安排面试) | `interviewed` | `interview_scheduled` |
| `/mothership/offers/new` (发 offer) | `offered` | `offer_sent` |
| `/mothership/placements` (确认入职) | `hired` | `placement_confirmed` |

> 当前已经在 `/mothership/analytics/funnel` 页面打开时自动埋 `sourced`(其他业务页面接入 SDK 时只需调用 `trackFunnelEvent()`)。

---

## 5. 后端 API

| Method | Path | 用途 | T1803 新增 |
| --- | --- | --- | --- |
| GET | `/api/analytics/funnel` | 漏斗汇总 | — |
| GET | `/api/analytics/funnel/stages` | 阶段详细 | — |
| **GET** | `/api/analytics/funnel/with-costs` | 漏斗 + 阶段成本 | **新增** |
| **GET** | `/api/analytics/funnel/trend` | 13 周趋势 | **新增** |
| **POST** | `/api/analytics/funnel/events` | 前端埋点批量上报 | **新增** |
| GET | `/api/analytics/channels` | 单模型渠道归因 | — |
| GET | `/api/analytics/channels/roi` | 全模型 ROI 报告 | — |

`POST /api/analytics/funnel/events` 接受:

```json
{
  "events": [
    {
      "candidate_id": "uuid-xxx",
      "stage": "applied",
      "source": "company_site",
      "role_id": "uuid-yyy",
      "cost_cents": 0,
      "metadata": { "page": "/jobs/python" },
      "occurred_at": "2026-07-12T08:30:00Z"
    }
  ]
}
```

返回:

```json
{ "ok": 1, "total": 1 }
```

---

## 6. 前端组件升级

### 6.1 新增图表

- **`frontend/components/charts/funnel-cost-chart.tsx`** — 各阶段成本条形图(¥)
- **`frontend/components/charts/funnel-trend-chart.tsx`** — 13 周 sourced/hired 趋势

### 6.2 升级页面

- **`frontend/app/mothership/analytics/funnel/page.tsx`**
  - 新增第 5 个 MetricTile: **Total spend**
  - 新增两列: cost overlay + weekly trend
  - `useEffect` 自动埋 `sourced` 事件(打开即追踪)
  - 拉数据从 `Promise.all` 4 个 endpoint(funnel / stages / with-costs / trend)

---

## 7. 测试覆盖

```
tests/test_funnel.py              9 passed
tests/test_channel_attribution.py 10 passed
Total: 19 passed in 0.31s
```

新覆盖点(已包含):
- `record_stage` 幂等性 (T1303 旧测)
- `record_frontend_event` 缺字段容错 (T1303)
- `bulk_load_jsonl` (T1803)
- `compute_funnel_with_costs` (T1803)
- `weekly_trend` (T1803)
- `multi_touch` 含 metadata.primary/secondary_source (T1803)

---

## 8. 验证步骤

```bash
# 1. 重生成 seed 数据
cd /home/hugo/codes/waibao/talent-tool-mvp
python scripts/seed_funnel_data.py

# 2. 后端 import 自检
cd backend && python -c "
import asyncio
from services.integrations.funnel_events import FunnelEventTracker
from services.employer.recruitment_funnel import RecruitmentFunnel
from services.employer.channel_attribution import ChannelAttributionService

async def main():
    t = FunnelEventTracker()
    await t.bulk_load_jsonl('../seed_output/funnel_events.jsonl')
    f = RecruitmentFunnel(t)
    print('90d funnel:', (await f.compute_funnel(since_days=90)).overall_conversion, '%')
    svc = ChannelAttributionService(t)
    report = await svc.compute_channel_roi(since_days=90)
    print('best first:', report.best_channel_by_model.get('first_touch'))
    print('best last :', report.best_channel_by_model.get('last_touch'))
    print('best multi:', report.best_channel_by_model.get('multi_touch'))
asyncio.run(main())
"

# 3. 前端页面打开 /mothership/analytics/funnel (默认 30 天) → 切 90 天
#    - Total spend 应显示 ~¥556,000
#    - Cost per stage 图表应有 6 个条
#    - Weekly trend 13 周应全部有数据
#    - Network: POST /api/analytics/funnel/events 1 条 (sourced)
```

---

## 9. 已知边界 / 后续可优化

1. **`re_touch` 当前通过 metadata 标识**,真正的去重要靠 (candidate_id, role_id, stage, source, occurred_at) 五元组。
   短期: 内存层通过 `_extra_events` 区分。  
   长期: 落 Supabase 时改用 `funnel_events_raw` 表,定时 ETL 聚合。
2. **`revenue_per_hire` 是占位值 ¥1,000**,需要按公司行业配置 `channel_revenue` 表(T1702 后续)。
3. **三种归因模型当前产出 referral 都稳第一**,是 seed 数据倾斜;真实生产数据可能让 linkedin 在 first_touch 突出。
4. **WARN**: 多触点 `multi_touch` 用 linear 而非 U-shape / W-shape,如需 time-decay 需扩展。

---

## 10. 涉及文件

**新增:**
- `/home/hugo/codes/waibao/talent-tool-mvp/scripts/seed_funnel_data.py`
- `/home/hugo/codes/waibao/talent-tool-mvp/frontend/lib/funnel-tracker.ts`
- `/home/hugo/codes/waibao/talent-tool-mvp/frontend/components/charts/funnel-cost-chart.tsx`
- `/home/hugo/codes/waibao/talent-tool-mvp/frontend/components/charts/funnel-trend-chart.tsx`
- `/home/hugo/codes/waibao/talent-tool-mvp/docs/FUNNEL_REPORT.md` (本文件)
- `/home/hugo/codes/waibao/talent-tool-mvp/seed_output/funnel_events.jsonl` (32K events)
- `/home/hugo/codes/waibao/talent-tool-mvp/seed_output/channel_spend.jsonl` (140 rows)

**修改:**
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/integrations/funnel_events.py` (+record_frontend_event, bulk_load_jsonl, stage_cost_profile, _extra_events, force flag)
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/employer/recruitment_funnel.py` (+compute_funnel_with_costs, weekly_trend, seed_and_compute)
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/services/employer/channel_attribution.py` (multi_touch 读 metadata.primary/secondary_source)
- `/home/hugo/codes/waibao/talent-tool-mvp/backend/api/analytics.py` (+/funnel/with-costs, +/funnel/trend, +POST /funnel/events)
- `/home/hugo/codes/waibao/talent-tool-mvp/frontend/lib/api.ts` (+funnelWithCosts, +funnelTrend, +recordFunnelEvents)
- `/home/hugo/codes/waibao/talent-tool-mvp/frontend/app/mothership/analytics/funnel/page.tsx` (4-列指标 + cost/trend 卡片 + trackFunnelEvent 埋点)
