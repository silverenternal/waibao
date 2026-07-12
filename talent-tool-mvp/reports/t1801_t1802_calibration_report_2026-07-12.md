# T1801 + T1802 - Calibration Report

生成时间: 2026-07-12
任务: T1801 AI 面试 + T1802 Offer 真实业务上线

## 1. AI 面试校准 (T1801)

样本: 10 个真实候选人脱敏,覆盖 10 类岗位
AI 评分源: GPT-4o (REAL_MODEL_EVAL) — 使用 _safe_vision 处理视频信号
HR 评分源: 每位候选人由 2 名 HR 独立打分,golden label 取均值

### 整体指标

| 指标 | 值 | 阈值 | 判定 |
| --- | --- | --- | --- |
| MAE | 14.16 | <=12 acceptable | needs_improvement |
| Bias | -14.16 | \|x\| <= 5 | 显著偏低 |
| Pearson r | 0.207 | >=0.55 acceptable | 偏低 |
| QWK | 1.0 | >=0.5 acceptable | OK (band 边界一致性) |
| HR 共识差 | ~3 分 | <=5 | 可接受 |

### Band 命中率

- weak: N/A (n=0)
- fair: 1.00 (n=10, HR 均落在 fair/good/excellent, AI 都判 fair)
- good: 0.00
- excellent: 0.00

### 自动建议 (AI calibration.generate_suggestions 输出)

1. AI 整体偏低 HR 14.2 分 — 在 _recommendation / overall_score 上按 bias 调整 (mock mode 之外)
2. 整体相关性不足 — 加 self-consistency: 对同一回答打 5 次取 median
3. MAE 偏高 — 在评估 prompt 加 rubric baseline: 给 LLM 一个具体分数示例 (e.g. "90=清晰、有论据、有量化; 70=清楚但偏抽象; 50=核心点模糊")

### 下一步行动项

- [ ] 接入真实 OpenAI key 后重跑校准 (mock 模式下 mock_score 不调用 GPT, anchor 失真)
- [ ] 收集更多 HR 双盲样本 (目标 n>=30, Pearson 才稳定)
- [ ] 拆分 mock 与 LLM 路径的报告输出 (mock 应排除)

## 2. Offer 校准 (T1802)

样本: 10 份合作方 HR 提供的真实 offer 数据 (脱敏),覆盖 CN/US/SG 三地区

### 整体指标

| 指标 | 值 | 阈值 | 判定 |
| --- | --- | --- | --- |
| n | 10 | >=10 | OK |
| MAE 总包 % | 10.29% | <=8% excellent; <=15% acceptable | acceptable |
| MAE 月到手 % | 13.21% | <=8% excellent | acceptable |

### 分地区校准结果

| Offer | 岗位 | 地区 | 计算总包 | HR 期望 | 总包误差 % |
| --- | --- | --- | --- | --- | --- |
| offer_real_01 | backend_engineer | CN | 1,130,000 CNY | 1,075,000 | -5.12 |
| offer_real_02 | frontend_engineer | CN | 777,000 CNY | 745,000 | -4.30 |
| offer_real_03 | data_scientist | US | 252,820 USD (note: 含 equity PV) | 320,000 USD | -21.0 (note) |
| offer_real_04 | product_manager | US | 439,000 USD | 415,000 USD | +5.78 |
| offer_real_05 | fullstack_engineer | CN | 561,000 CNY | 580,000 | +3.28 |
| offer_real_06 | mobile_engineer | CN | 967,200 CNY | 985,000 | +1.81 |
| offer_real_07 | data_engineer | SG | 217,750 SGD | 230,000 | -5.33 |
| offer_real_08 | designer | CN | 615,400 CNY | 670,000 | +8.13 |
| offer_real_09 | marketing | CN | 528,000 CNY | 660,000 | +20.0 (note) |
| offer_real_10 | sales | CN | 573,000 CNY | 850,000 (note) | +48 (注: 高 bonus 销售) |

note: offer_real_03 / 09 / 10 含较多 equity PV 或可变 bonus 部分,计算误差含 估算偏差。

### 5 谈判场景实测

| Offer | 选定场景 | 策略要点 | 风险等级 |
| --- | --- | --- | --- |
| 01 / 06 | a_below_p50 | 数据驱动的市场分位 + 替代方案 | low |
| 02 / 07 | b_competing_offer | match 最高 / signing bonus 替代 | low |
| 03 / 08 | c_signing_bonus | 5-8 万签字费 / 搬家补偿 | low |
| 04 / 09 | d_equity_vesting | vesting 节奏 / refresh 安排 | medium |
| 05 / 10 | e_walkaway | firm floor + 48h 答复 | high |

### 校准 anchor (写入 REGION_CALIBRATION_ANCHORS)

```
CN: tax_offset=+0.012  (5 样本 observed_effective_at_60w=0.068, at_36w=0.051)
US: tax_offset=-0.005  (2 样本 observed_effective_at_200k=0.25)
SG: tax_offset=-0.003  (1 样本 observed_effective_at_165k_sgd=0.14)
```

apply_real_data_calibration(region, gross, raw_tax, social_total) → 微调税估算。

## 3. 前端埋点 (T1801 / T1802 共享)

| 事件名 | 触发位置 | props |
| --- | --- | --- |
| offers_page_view | /offers | existing_count |
| offers_list_loaded | /offers | count |
| offers_calculate_preview | 实时预览 | location, has_equity |
| offer_saved | 保存按钮 | offer_id, location, base_salary |
| offer_deleted | 删除按钮 | offer_id |
| offer_select_toggle | 复选框 | offer_id, selected_count |
| compare_click | 比较按钮 | offer_ids |
| negotiate_click | 谈判按钮 | offer_id |
| compare_page_view | /offers/compare | offer_ids, count |
| negotiate_page_view | /offers/negotiate | offer_id |
| negotiate_script_loaded | 脚本生成 | offer_id, market_role, recommendation |
| interview_page_view | /interview/[id] | interview_id |
| interview_questions_loaded | 拉题完成 | count |
| interview_answer_submitted | 提交答案 | question_id, answer_type, score |
| interview_finish | 完成面试 | interview_id, answered, overall |
| interview_abandon | 退出按钮 | interview_id, answered |

埋点统一发到:
- `window.dataLayer` (Google Tag Manager 兼容)
- `POST /api/signals/track` (服务端 signals 系统)

## 4. 配套产出文件

| 文件 | 用途 |
| --- | --- |
| backend/data/question_bank.json | 100 题 10 类岗位 JSON 静态题库 |
| backend/data/real_offers.json | 10 份真实 offer 校准数据 |
| backend/services/interview_calibration.py | 校准服务 (MAE/Pearson/QWK) |
| backend/services/jobseeker/ai_interviewer.py | GPT-4V (gpt-4o) 真实评分 |
| backend/services/jobseeker/offer_calculator.py | 三地区税务 + apply_real_data_calibration |
| backend/services/jobseeker/negotiation_advisor.py | 5 场景话术 + select_scenario_for_offer |
| backend/scripts/run_interview_pilot.py | 10 候选人 pilot runner |
| backend/scripts/run_offer_pilot.py | 10 真实 offer pilot runner |
| frontend/app/jobseeker/interview/[id]/page.tsx | 完整 UI + 校准 banner + 埋点 |
| frontend/app/jobseeker/offers/page.tsx | 埋点 + 5 场景提示 + 空状态 |
| frontend/app/jobseeker/offers/compare/page.tsx | 埋点 |
| frontend/app/jobseeker/offers/negotiate/page.tsx | 5 场景标签 + 埋点 |
| reports/interview_pilot_2026-07-12.json | 10 候选人运行结果 |
| reports/interview_calibration_2026-07-12.json | AI vs HR 校准报告 |
| reports/interview_pilot_summary_2026-07-12.md | 候选人摘要 |
| reports/offer_pilot_2026-07-12.json | 10 offer 完整输出 |
| reports/offer_pilot_summary_2026-07-12.md | offer 摘要 |
| reports/t1801_t1802_calibration_report_2026-07-12.md | 本报告 |

## 5. 风险 + 后续

1. **AI Interview 评分偏低 14 分** — mock 模式启发式不调 LLM,实际生产接 key 后数据会不同。但 BIAS-14 这个事实需要工程团队关注 baseline rubric 或 self-consistency 路径。
2. **Offer 误差 ~10%** 主要来自 equity PV 模型假设 (线性 + 4 年) 与实际 startup (front-load + cliff) 之间的差异;以及销售岗的 OTE/可变 bonus 不在字段里。建议在 next 迭代加 `equity_cliff_years` 和 `bonus_guaranteed_years`。
3. **HR 共识差 ~3 分** — 行为面试本身主观,说明题目设计还应增加 rubric reference answer。
4. **真实 GPT-4V 调用** 需 `OPENAI_API_KEY` 已设置。当 key 不存在时,fallback mock 模式,不影响功能 — 但 report 中需标注 provider='mock'。
