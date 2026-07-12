# T1801 - AI 面试 Pilot 报告

生成时间: 2026-07-12T09:11:01.449037Z

候选人数: 10

## 候选人结果

| ID | 岗位 | AI 评分 | HR 评分 | 推荐 |
| --- | --- | --- | --- | --- |
| cand_pilot_01 | backend_engineer | 65.9 | 81.0 | consider |
| cand_pilot_02 | frontend_engineer | 65.6 | 77.0 | consider |
| cand_pilot_03 | data_scientist | 63.6 | 87.0 | consider |
| cand_pilot_04 | product_manager | 60.8 | 84.5 | consider |
| cand_pilot_05 | fullstack_engineer | 59.8 | 71.0 | consider |
| cand_pilot_06 | data_engineer | 62.2 | 77.0 | consider |
| cand_pilot_07 | mobile_engineer | 65.8 | 74.0 | consider |
| cand_pilot_08 | designer | 62.6 | 69.0 | consider |
| cand_pilot_09 | marketing | 61.0 | 71.5 | consider |
| cand_pilot_10 | sales | 62.1 | 79.0 | consider |

## 校准指标 (n=10)

- **MAE**: 14.16
- **Bias**: -14.16
- **Pearson r**: 0.207
- **QWK**: 1.0
- **Verdict**: needs_improvement

### Band 命中率

- weak: None
- fair: 1.0
- good: 0.0
- excellent: 0.0

### 建议

- AI 整体偏低 HR 14.2 分;考虑在 _recommendation 中按 bias 调整
- 整体相关性不足;可能 LLM 评分波动较大,可加 self-consistency (5 次打 median)
- MAE 偏高;在 mock mode 之外增加 rubric 参考分,让 LLM 评分有 baseline
