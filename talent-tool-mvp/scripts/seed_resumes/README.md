# 甲方脱敏简历样例目录 (seed_resumes)

> v11.0 / T6112 — 甲方提供的**脱敏简历样例**放在这里,供一键导入验收环境。

## 用途

本目录用于存放甲方提供的、**已脱敏**的简历样例文件。导入脚本
`scripts/seed_test_data.py` 在加 `--with-sample-resumes` 时会扫描本目录,
把每一份样例简历作为一条 `candidate` 记录纳入导入清单。

## 支持的格式

| 扩展名 | 说明 |
| --- | --- |
| `.txt` / `.md` | 纯文本简历。整篇作为 `cv_text` 导入;姓名/电话/邮箱等字段由脚本随机补齐(不覆盖正文)。 |
| `.json` | 结构化简历。优先按 JSON 字段导入,缺字段时补默认值。 |
| `.pdf` | **不支持**直接放目录(脚本只读文本)。请先把 PDF 用 OCR/复制转成 `.txt` 再放入。 |

## JSON 简历字段(推荐)

```json
{
  "first_name": "小明",
  "last_name": "李",
  "email": "liming@example.com",
  "phone": "13800000000",
  "location": "上海",
  "education": "本科",
  "experience_years": 5,
  "skills": [
    {"name": "电商运营", "years": 3, "confidence": 0.9},
    {"name": "数据分析", "years": 2, "confidence": 0.8}
  ],
  "seniority": "mid",
  "salary_expectation": {"min": 12000, "max": 18000, "currency": "CNY"},
  "availability": "1_month",
  "industries": ["体育用品"],
  "cv_text": "李小明,本科,5 年体育用品电商运营经验……"
}
```

字段对齐后端 `backend/contracts/candidate.py` 的 `Candidate` 契约;
未提供的字段会被脚本自动补全。

## 脱敏要求(甲方务必遵守)

放入本目录前,简历**必须**完成以下脱敏:

1. **真实姓名** → 替换为化名或保留姓 + 名首字母;
2. **身份证号 / 护照号** → 全部删除或替换为占位符;
3. **手机号 / 邮箱** → 可保留格式但替换为非真实联系方式;
4. **家庭住址** → 仅保留到城市级;
5. **前雇主可识别商业机密**(如未公开的业绩数字)→ 删除。

> 这些样例仅用于验收环境的功能演示,不会被发送到任何外部服务
> (LLM 走本地 Ollama,OCR 走本地 PaddleOCR)。

## 如何导入

```bash
# 把样例简历(已脱敏)拷进本目录后:
python scripts/seed_test_data.py --with-sample-resumes

# 指定数量 / 随机种子:
python scripts/seed_test_data.py --candidates 1000 --with-sample-resumes --seed 42
```

导入后,样例简历会与 Faker 生成的演示数据一起出现在
`seed_output/candidates.jsonl`(或直写 Supabase 的 `candidates` 表),
标记 `_meta.source = "sample_resume"`。

## 示例文件

- `sample_resume_zh.txt` —— 中文纯文本脱敏简历样例(可直接参考/替换)。
