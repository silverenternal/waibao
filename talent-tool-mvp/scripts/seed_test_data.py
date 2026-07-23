#!/usr/bin/env python3
"""
T6112 — Seed 甲方验收用测试数据 (脱敏 / 演示).

生成 v11.0 验收环境所需的核心演示数据,与后端 ``contracts/`` 形状对齐:

1. **1000 名求职者 (candidates)** — Faker 生成:
   姓名 / 邮箱 / 电话 / 简历文本 / 技能 / 学历 / 城市 / 薪资期望 / 资历 / 可到岗时间.
2. **10 家企业 (organisations)** — 公司名 / 行业 / 规模 / 资质(营业执照等).
3. **5 个岗位 (roles)** — 体育用品行业: 运营 / 电商 / 供应链 / 设计 / 销售.
4. **匹配结果 (matches)** — 每个岗位自动生成 Top-N 候选人匹配 (技能重叠评分).

两种落地方式 (同 seed_funnel_data.py 约定):

* **本地 JSONL (默认)** — 写到 ``./seed_output/`` 下的 jsonl 文件,
  供后续通过 admin 批量导入 UI 或后端 API 灌入. 无任何外部依赖.
* **直写 Supabase** — 当 ``SUPABASE_URL`` + ``SUPABASE_SERVICE_KEY`` 在环境变量中时,
  脚本会直接 ``insert`` 进对应表 (candidates / organisations / roles / matches).

数据脱敏说明:
* 所有姓名 / 邮箱 / 电话均为 Faker 随机生成, 不对应任何真实自然人.
* 甲方提供的真实脱敏简历样例请放到 ``scripts/seed_resumes/``,
  本脚本会**同时**扫描该目录并纳入导入清单 (见 ``--with-sample-resumes``).

用法::

    # 默认: 本地 JSONL, 1000 求职者
    python scripts/seed_test_data.py

    # 自定义规模 + 随机种子
    python scripts/seed_test_data.py --candidates 200 --orgs 5 --seed 42

    # 直写 Supabase
    SUPABASE_URL=xxx SUPABASE_SERVICE_KEY=yyy python scripts/seed_test_data.py --supabase

    # 同时把 scripts/seed_resumes/ 下的脱敏样例简历纳入导入清单
    python scripts/seed_test_data.py --with-sample-resumes
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("seed_test_data")

# --------------------------------------------------------------------- Faker
# Faker 是可选依赖:甲方离线环境可能没装。装了就用,没装用内置随机生成器,
# 保证脚本在纯离线 / 最小依赖下也能跑。
try:
    from faker import Faker  # type: ignore

    _FAKE = Faker("zh_CN")
    Faker.seed(0)
    HAS_FAKER = True
except Exception:  # pragma: no cover - 离线 fallback
    HAS_FAKER = False
    _FAKE = None

# ------------------------------------------------------------------ 常量池
# 体育用品行业为甲方主场景,技能 / 城市 / 学历 / 资质围绕它构造.
ROLE_DEFS = [
    {
        "title": "电商运营专员",
        "industry": "体育用品",
        "required_skills": [
            {"name": "电商运营", "min_years": 2, "importance": "required"},
            {"name": "数据分析", "min_years": 1, "importance": "required"},
            {"name": "活动策划", "min_years": 1, "importance": "preferred"},
        ],
        "seniority": "mid",
        "salary": (8000, 14000),
    },
    {
        "title": "跨境电商经理",
        "industry": "体育用品",
        "required_skills": [
            {"name": "跨境电商", "min_years": 3, "importance": "required"},
            {"name": "团队管理", "min_years": 2, "importance": "required"},
            {"name": "英语", "min_years": 5, "importance": "preferred"},
        ],
        "seniority": "senior",
        "salary": (15000, 28000),
    },
    {
        "title": "供应链主管",
        "industry": "体育用品",
        "required_skills": [
            {"name": "供应链管理", "min_years": 3, "importance": "required"},
            {"name": "仓储物流", "min_years": 2, "importance": "required"},
            {"name": "ERP", "min_years": 2, "importance": "preferred"},
        ],
        "seniority": "senior",
        "salary": (13000, 22000),
    },
    {
        "title": "工业设计师",
        "industry": "体育用品",
        "required_skills": [
            {"name": "产品设计", "min_years": 2, "importance": "required"},
            {"name": "Rhino", "min_years": 1, "importance": "required"},
            {"name": "材料工艺", "min_years": 1, "importance": "preferred"},
        ],
        "seniority": "mid",
        "salary": (10000, 18000),
    },
    {
        "title": "区域销售经理",
        "industry": "体育用品",
        "required_skills": [
            {"name": "渠道销售", "min_years": 3, "importance": "required"},
            {"name": "客户管理", "min_years": 2, "importance": "required"},
            {"name": "经销商拓展", "min_years": 1, "importance": "preferred"},
        ],
        "seniority": "senior",
        "salary": (12000, 25000),
    },
]

SKILL_POOL = [
    "电商运营", "跨境电商", "数据分析", "活动策划", "供应链管理", "仓储物流",
    "ERP", "产品设计", "Rhino", "SolidWorks", "材料工艺", "渠道销售",
    "客户管理", "经销商拓展", "团队管理", "英语", "日语", "直播运营",
    "小红书运营", "抖音运营", "采购", "质量管理", "项目管理", "Excel",
    "Python", "SQL", "市场调研", "品牌策划", "视觉设计", "UI设计",
]

CITY_POOL = ["上海", "北京", "深圳", "广州", "杭州", "苏州", "南京", "成都", "武汉", "厦门"]
EDU_POOL = ["大专", "本科", "硕士"]
COMPANY_PREFIX = ["飞跃", "劲跑", "极地", "潮动", "竞速", "锋尚", "跃动", "体能", "驰跃", "动界"]
COMPANY_SUFFIX = ["体育用品", "运动科技", "体育产业", "运动器材", "户外装备"]
INDUSTRY_POOL = ["体育用品", "运动科技", "户外装备", "跨境电商", "运动器材"]
SCALE_POOL = ["1-50人", "51-200人", "201-500人", "500-1000人", "1000人以上"]
QUALIFICATION_POOL = [
    "营业执照(三证合一)",
    "体育用品生产许可证",
    "ISO9001 质量管理体系认证",
    "进出口经营权",
    "一般纳税人资格",
]
AVAILABILITY_POOL = ["immediate", "1_month", "3_months", "not_looking"]

# v11.2 T6302 — identity verification + 五险一金/出差 dimension pools.
# identity lifecycle per document + rolled-up identity_status.
IDENTITY_STATUS_POOL = ["pending", "submitted", "verified"]
DOC_STATUS_POOL = ["pending", "submitted", "verified"]
TRAVEL_TOLERANCE_POOL = ["willing", "occasional", "unwilling", None]
TRAVEL_REQUIRED_POOL = ["none", "occasional", "frequent"]


# ----------------------------------------------------------------- 生成器
def _zh_name() -> tuple[str, str]:
    """返回 (姓, 名)."""
    if HAS_FAKER:
        full = _FAKE.name()  # zh_CN Faker 给中文名
        # 简单拆:第一个字为姓,其余为名
        return full[:1], full[1:]
    surnames = ["王", "李", "张", "刘", "陈", "杨", "黄", "赵", "周", "吴", "徐", "孙", "马", "朱", "胡"]
    given = ["伟", "芳", "娜", "敏", "静", "丽", "强", "磊", "军", "洋", "勇", "艳", "杰", "娟", "涛", "明", "超", "霞", "平", "刚"]
    return random.choice(surnames), random.choice(given) + random.choice(given)


def _phone() -> str:
    if HAS_FAKER:
        return _FAKE.phone_number()
    prefixes = ["138", "139", "150", "151", "158", "188", "199", "136", "186", "177"]
    return random.choice(prefixes) + "".join(random.choice("0123456789") for _ in range(8))


def _email(last_name: str) -> str:
    if HAS_FAKER:
        return _FAKE.email()
    pinyin_stub = f"user{random.randint(1000, 9999)}"
    domains = ["example.com", "test.cn", "demo.org", "mail.com"]
    return f"{pinyin_stub}@{random.choice(domains)}"


def _salary_range(low: int, high: int) -> dict:
    """构造 SalaryRange 形状 (canonical: min_amount/max_amount).

    v11.6 R3 — 与 contracts.shared.SalaryRange 对齐. 旧版用 ``{min,max}``
    裸键, 但所有消费方 (api/roles.py, api/candidates.py, matching/structured.py,
    talent_market.py 卡片, frontend extraction-viewer.tsx) 都读 ``min_amount``/
    ``max_amount``; 裸键导致薪资维度恒显示为空 / 硬过滤失效. 统一到 canonical.
    """
    lo = random.randint(low, high - 1000)
    hi = random.randint(lo + 1000, high)
    return {"min_amount": lo, "max_amount": hi, "currency": "CNY"}


def _salary_range_biased(low: int, high: int) -> dict:
    """构造 SalaryRange, 期望值大概率落在给定区间内 (帮助薪资维度达标).

    约 70% 期望下限落在 [low, high], 另 30% 略高于上限 (真实求职者也会略高期望),
    但不会高得离谱. 用于让候选人薪资期望与岗位区间自然重叠.

    v11.6 R3 — 键名对齐到 canonical ``min_amount``/``max_amount`` (见
    ``_salary_range`` 注释). 随机区间逻辑不变, 仅改键名.
    """
    if random.random() < 0.7:
        lo = random.randint(low, max(low + 1, high - 1000))
        hi = random.randint(lo + 1000, high + 2000)
    else:
        # 期望偏高 (真实存在), 但受控
        lo = random.randint(high, high + 3000)
        hi = random.randint(lo + 1000, lo + 5000)
    return {"min_amount": lo, "max_amount": hi, "currency": "CNY"}


def _required_skill_names(role_def: dict) -> list[str]:
    """从 ROLE_DEFS 形状里取出 required skill 名称 (用于候选人技能引导)."""
    return [s["name"] for s in role_def.get("required_skills", []) if isinstance(s, dict) and s.get("name")]


# 候选人技能城市对齐: 选一组"热门城市"作为岗位主要所在地, 让一部分候选人自然同城.
# 这只是把分布往现实靠拢 (一线城市机会多), 不是强制对齐.
HOT_CITIES = ["上海", "深圳", "杭州", "广州", "北京"]
# 每个候选人有多大比例"技能被岗位需求引导" (让其成为真实可匹配的求职者).
# 其余仍纯随机, 保留背景噪声 / 跨行业人才, 避免数据失真 (不会全员 100 分).
_SKILL_GUIDED_RATIO = 0.55


def gen_candidate(idx: int, created_by: str) -> dict:
    last, first = _zh_name()

    # v11.4 R2 — 让一部分候选人的技能围绕某个岗位的 required_skills 构造,
    # 使"技能硬条件"成为真实可达的信号, 而不是纯靠基础分蹭过阀值.
    # 不改 MATCH_THRESHOLD / 不动 hard_filter — 只调数据让真实匹配自然达标.
    guided_role = random.choice(ROLE_DEFS) if random.random() < _SKILL_GUIDED_RATIO else None
    if guided_role is not None:
        required_names = _required_skill_names(guided_role)
        # 必含该岗位全部 required_skills (且年限满足 min_years), 再补几个随机背景技能
        guided = list(required_names)
        extra_k = random.randint(1, 4)
        pool = [s for s in SKILL_POOL if s not in guided]
        guided += random.sample(pool, k=min(extra_k, len(pool)))
        skills = guided
    else:
        skills = random.sample(SKILL_POOL, k=random.randint(3, 8))

    skill_objs: list[dict] = []
    if guided_role is not None:
        req_map = {s["name"]: (s.get("min_years") or 0) for s in guided_role["required_skills"] if isinstance(s, dict)}
    else:
        req_map = {}
    for s in skills:
        min_y = req_map.get(s)
        if min_y is not None:
            # 引导技能: 年限满足该岗位 min_years (可能略高), 保证"全部满足"达标
            years = round(random.uniform(max(0.5, float(min_y)), float(min_y) + 4.0), 1)
        else:
            years = round(random.uniform(0.5, 8.0), 1)
        skill_objs.append({"name": s, "years": years, "confidence": round(random.uniform(0.7, 1.0), 2)})

    edu = random.choices(EDU_POOL, weights=[2, 6, 2], k=1)[0]
    exp_years = {"大专": random.randint(0, 4), "本科": random.randint(0, 8), "硕士": random.randint(0, 10)}[edu]
    # 城市偏向热门城市 (一线城市岗位多, 自然提升同城命中率, 但不全对齐)
    city = random.choice(HOT_CITIES) if random.random() < 0.6 else random.choice(CITY_POOL)
    if guided_role is not None:
        # 被引导的候选人薪资期望落在该岗位区间附近 (70% 命中), 其余略高
        lo, hi = guided_role["salary"]
        expectation = _salary_range_biased(lo, hi)
    else:
        expectation = _salary_range(6000, 30000)
    cv_lines = [
        f"{last}{first} | {edu} | {city}",
        f"工作年限:{exp_years} 年",
        "核心技能:" + "、".join(skills[:5]),
        f"期望薪资:{expectation['min_amount']}-{expectation['max_amount']} 元/月",
        "求职意向:体育用品行业相关岗位,期望稳定发展与专业成长。",
    ]
    # v11.2 T6302 — identity verification lifecycle. The rolled-up
    # identity_status is derived to honour the invariant: 'verified' ONLY
    # when id_card_status AND education_doc_status AND resume_status are all
    # 'verified' (the DB trigger also enforces this).
    id_card_status = random.choice(DOC_STATUS_POOL)
    education_doc_status = random.choice(DOC_STATUS_POOL)
    resume_status = random.choice(DOC_STATUS_POOL)
    if id_card_status == "verified" and education_doc_status == "verified" and resume_status == "verified":
        identity_status = "verified"
    else:
        # any document pending → overall pending; else submitted
        if "pending" in (id_card_status, education_doc_status, resume_status):
            identity_status = random.choice(["pending", "submitted"])
        else:
            identity_status = "submitted"
    return {
        "id": str(uuid.uuid4()),
        "first_name": first,
        "last_name": last,
        "email": _email(last),
        "phone": _phone(),
        "location": city,
        "education": edu,
        "experience_years": exp_years,
        "skills": skill_objs,
        "seniority": random.choice(["junior", "mid", "senior", "lead"]),
        "salary_expectation": expectation,
        "availability": random.choice(AVAILABILITY_POOL),
        "industries": random.sample(INDUSTRY_POOL, k=random.randint(1, 3)),
        "cv_text": "\n".join(cv_lines),
        "profile_text": None,
        "created_by": created_by,
        # v11.2 T6302 — identity verification + 五险一金/出差 expectations
        "identity_status": identity_status,
        "id_card_status": id_card_status,
        "education_doc_status": education_doc_status,
        "resume_status": resume_status,
        "identity_verified_at": (
            datetime.now(timezone.utc).isoformat() if identity_status == "verified" else None
        ),
        "social_insurance_expectation": random.random() < 0.8,  # 五险一金 (mostly True)
        "travel_tolerance": random.choice(TRAVEL_TOLERANCE_POOL),  # willing|occasional|unwilling|None
        # 标记:测试数据,便于验收后清理
        "_meta": {"source": "seed_test_data", "seq": idx},
    }


def gen_organisation(idx: int, created_by: str) -> dict:
    name = f"{random.choice(COMPANY_PREFIX)}{random.choice(COMPANY_SUFFIX)}({chr(65 + idx)})"
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "industry": random.choice(INDUSTRY_POOL),
        "scale": random.choice(SCALE_POOL),
        "qualifications": random.sample(QUALIFICATION_POOL, k=random.randint(2, 4)),
        "location": random.choice(CITY_POOL),
        "website": f"https://www.example-{idx}.com",
        "created_by": created_by,
        "_meta": {"source": "seed_test_data", "seq": idx},
    }


def gen_role(defn: dict, org_id: str, created_by: str) -> dict:
    lo, hi = defn["salary"]
    return {
        "id": str(uuid.uuid4()),
        "title": defn["title"],
        "description": (
            f"{defn['industry']}行业 — {defn['title']}。\n"
            "负责对应业务模块的日常运营 / 管理 / 执行,与团队协同达成业绩目标。\n"
            "公司提供完善培训与晋升通道,欢迎体育用品行业从业者加入。"
        ),
        "organisation_id": org_id,
        "required_skills": defn["required_skills"],
        "preferred_skills": [],
        "seniority": defn["seniority"],
        "salary_band": _salary_range(lo, hi),
        "location": random.choice(CITY_POOL),
        "remote_policy": random.choice(["onsite", "hybrid", "remote"]),
        "industry": defn["industry"],
        "status": "active",
        # v11.2 T6302 — benefits/travel offerings (soft scoring dimensions)
        "offers_social_insurance": random.random() < 0.85,  # 五险一金 (mostly True)
        "offers_housing_fund": random.random() < 0.4,  # 住房公积金 (~40%)
        "travel_required": random.choice(TRAVEL_REQUIRED_POOL),  # none|occasional|frequent
        "created_by": created_by,
        "_meta": {"source": "seed_test_data"},
    }


def _skill_overlap(candidate: dict, role: dict) -> tuple[float, list[dict]]:
    """简单技能重叠评分 (0-1) + SkillMatch 列表 (验收演示用,非生产匹配引擎)."""
    cand_skills = {s["name"].lower(): s for s in candidate["skills"]}
    matches: list[dict] = []
    hit = 0
    total = 0
    for req in role["required_skills"]:
        total += 1
        name = req["name"].lower()
        if name in cand_skills:
            hit += 1
            status = "matched" if (req.get("min_years") or 0) <= (cand_skills[name].get("years") or 0) else "partial"
            matches.append({
                "skill_name": req["name"],
                "status": status,
                "candidate_years": cand_skills[name].get("years"),
                "required_years": req.get("min_years"),
            })
        else:
            matches.append({
                "skill_name": req["name"],
                "status": "missing",
                "candidate_years": None,
                "required_years": req.get("min_years"),
            })
    overlap = (hit / total) if total else 0.0
    return overlap, matches


# v11.4 R2 — 用生产匹配引擎 (与阀值门 threshold.py 同一 HardConditionFilter) 评分,
# 让 seed 生成的 matches.jsonl 与"可见性"判定一致 (避免演示时:可见但详情显示低分).
# 该 import 是可选的: 后端 backend/ 不在 sys.path 时回退到老的轻量公式, 保证离线可跑.
try:  # pragma: no cover - 依赖后端包, 离线 fallback
    from matching.hard_filter import HardConditionFilter as _HCF  # type: ignore

    _hcf = _HCF()
except Exception:  # noqa: BLE001
    _hcf = None


def _engine_score(candidate: dict, role: dict) -> Optional[int]:
    """调用生产引擎评分 (0-100). 引擎不可用时返回 None (调用方回退)."""
    if _hcf is None:
        return None
    try:
        return _hcf.filter(candidate, role).match_score
    except Exception:  # noqa: BLE001 — 单条脏数据不影响整体
        return None


def gen_matches(candidates: list[dict], roles: list[dict], top_n: int = 15) -> list[dict]:
    """为每个岗位生成 Top-N 候选人匹配.

    v11.4 R2: overall_score 优先取生产引擎 (HardConditionFilter) 分数, 与阀值门一致;
    引擎不可用时回退到轻量公式 (技能重叠 70% + 经验 20% + 城市/薪资 10%).
    """
    out: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()
    for role in roles:
        scored = []
        for c in candidates:
            overlap, skill_matches = _skill_overlap(c, role)
            eng = _engine_score(c, role)
            if eng is not None:
                overall = round(eng / 100.0, 3)  # 与阀值门同一口径
            else:
                # 回退轻量公式 (离线 / 后端不可导入时)
                exp_factor = min(1.0, (c.get("experience_years", 0) / 6.0))
                soft = 1.0 if c.get("location") == role.get("location") else 0.5
                overall = round(overlap * 0.7 + exp_factor * 0.2 + soft * 0.1, 3)
            scored.append((overall, overlap, skill_matches, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        for overall, overlap, skill_matches, c in scored[:top_n]:
            confidence = "strong" if overall >= 0.7 else "good" if overall >= 0.45 else "possible"
            out.append({
                "id": str(uuid.uuid4()),
                "candidate_id": c["id"],
                "role_id": role["id"],
                "overall_score": overall,
                "structured_score": round(overlap, 3),
                "semantic_score": round(random.uniform(0.4, 0.9), 3),
                "experience_score": round(min(1.0, c.get("experience_years", 0) / 6.0), 3),
                "skill_overlap": skill_matches,
                "confidence": confidence,
                "explanation": f"技能重叠 {int(overlap * 100)}%,综合匹配度 {int(overall * 100)}%。",
                "strengths": [m["skill_name"] for m in skill_matches if m["status"] == "matched"][:3],
                "gaps": [m["skill_name"] for m in skill_matches if m["status"] == "missing"][:2],
                "recommendation": "推荐进入下一轮" if overall >= 0.6 else "备选",
                "status": "generated",
                "created_at": now,
            })
    return out


# -------------------------------------------------------------- 样例简历扫描
def scan_sample_resumes(resume_dir: Path) -> list[dict]:
    """扫描 scripts/seed_resumes/ 下的脱敏样例简历 (txt / json),转成 candidate 形状."""
    out: list[dict] = []
    if not resume_dir.exists():
        return out
    created_by = str(uuid.uuid4())
    for i, path in enumerate(sorted(resume_dir.glob("*"))):
        if path.suffix.lower() not in {".txt", ".json", ".md"}:
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception as exc:  # pragma: no cover
            log.warning("跳过样例简历 %s: %s", path.name, exc)
            continue
        if path.suffix.lower() == ".json":
            try:
                payload = json.loads(raw)
                payload.setdefault("id", str(uuid.uuid4()))
                payload.setdefault("created_by", created_by)
                payload.setdefault("_meta", {"source": "sample_resume", "file": path.name})
                out.append(payload)
                continue
            except json.JSONDecodeError:
                pass  # 当纯文本处理
        last, first = _zh_name()
        out.append({
            "id": str(uuid.uuid4()),
            "first_name": first,
            "last_name": last,
            "email": _email(last),
            "phone": _phone(),
            "location": random.choice(CITY_POOL),
            "education": random.choice(EDU_POOL),
            "experience_years": random.randint(0, 8),
            "skills": [{"name": s, "years": round(random.uniform(1, 6), 1), "confidence": 0.9}
                       for s in random.sample(SKILL_POOL, k=4)],
            "seniority": "mid",
            "salary_expectation": _salary_range(8000, 25000),
            "availability": "immediate",
            "industries": ["体育用品"],
            "cv_text": raw,
            "profile_text": None,
            "created_by": created_by,
            "_meta": {"source": "sample_resume", "file": path.name},
        })
    return out


# ----------------------------------------------------------------- 输出
def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    log.info("写入 %d 行 -> %s", len(rows), path)


def write_to_supabase(table: str, rows: list[dict]) -> None:
    """直写 Supabase (可选). 需要 supabase-py."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY 未设置")
    try:
        from supabase import create_client  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"未安装 supabase-py: {exc}") from exc
    client = create_client(url, key)
    # 去掉 _meta 字段 (DB 表里没有)
    clean = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    # 分批 insert (Supabase 单次上限 1000 行左右)
    BATCH = 500
    for i in range(0, len(clean), BATCH):
        client.table(table).insert(clean[i:i + BATCH]).execute()
    log.info("Supabase %s 插入 %d 行", table, len(clean))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Seed v11.0 甲方验收测试数据")
    ap.add_argument("--candidates", type=int, default=1000, help="求职者数量 (默认 1000)")
    ap.add_argument("--orgs", type=int, default=10, help="企业数量 (默认 10)")
    ap.add_argument("--top-n", type=int, default=15, help="每个岗位 Top-N 匹配 (默认 15)")
    ap.add_argument("--seed", type=int, default=42, help="随机种子 (默认 42)")
    ap.add_argument("--supabase", action="store_true", help="直写 Supabase (需环境变量)")
    ap.add_argument("--with-sample-resumes", action="store_true",
                    help="扫描 scripts/seed_resumes/ 纳入脱敏样例简历")
    ap.add_argument("--out-dir", default="./seed_output", help="JSONL 输出目录")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    random.seed(args.seed)
    if HAS_FAKER:
        try:
            Faker.seed(args.seed)
        except Exception:
            pass

    log.info("Faker: %s", "已安装" if HAS_FAKER else "未安装,使用内置随机生成器")

    root = Path(__file__).resolve().parent.parent
    out_dir = Path(args.out_dir) if Path(args.out_dir).is_absolute() else root / args.out_dir
    created_by = str(uuid.uuid4())

    # 1. 求职者
    log.info("生成 %d 名求职者 ...", args.candidates)
    candidates = [gen_candidate(i, created_by) for i in range(args.candidates)]

    # 1b. 样例简历
    if args.with_sample_resumes:
        samples = scan_sample_resumes(root / "scripts" / "seed_resumes")
        if samples:
            log.info("纳入 %d 份脱敏样例简历", len(samples))
            candidates.extend(samples)

    # 2. 企业
    log.info("生成 %d 家企业 ...", args.orgs)
    orgs = [gen_organisation(i, created_by) for i in range(args.orgs)]

    # 3. 岗位 (5 个体育用品行业岗位, 分配到前几家企业)
    log.info("生成 %d 个岗位 (体育用品行业) ...", len(ROLE_DEFS))
    roles = [gen_role(defn, orgs[i % len(orgs)]["id"], created_by) for i, defn in enumerate(ROLE_DEFS)]

    # 4. 匹配
    log.info("生成匹配结果 (每岗位 Top-%d) ...", args.top_n)
    matches = gen_matches(candidates, roles, top_n=args.top_n)

    # ---- 输出 ----
    if args.supabase:
        log.info("直写 Supabase ...")
        write_to_supabase("organisations", orgs)
        write_to_supabase("candidates", candidates)
        write_to_supabase("roles", roles)
        write_to_supabase("matches", matches)
    else:
        write_jsonl(out_dir / "candidates.jsonl", candidates)
        write_jsonl(out_dir / "organisations.jsonl", orgs)
        write_jsonl(out_dir / "roles.jsonl", roles)
        write_jsonl(out_dir / "matches.jsonl", matches)

    # 摘要
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidates": len(candidates),
        "organisations": len(orgs),
        "roles": len(roles),
        "matches": len(matches),
        "seed": args.seed,
        "faker": HAS_FAKER,
        "output": "supabase" if args.supabase else str(out_dir),
    }
    (out_dir / "seed_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("完成: %s", json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
