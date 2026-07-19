"""T6105 — tests for the hard-condition matching engine.

甲方合同版匹配因素分级:
  * 技能 / 学历 / 证书 → 硬条件 (必须满足, 但不淘汰)
  * 薪资 / 城市 / 工作时间 / 到岗 / 意愿 → 高优先级打分
  * 工作 / 行业经历 → 不使用
甲方要求: 不淘汰, 只排序.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest

from matching.hard_filter import (
    EDUCATION_ORDER,
    HardConditionFilter,
    HardConditionResult,
    MatchResult,
    W_AVAILABILITY,
    W_BENEFITS_TRAVEL,
    W_CERTIFICATE,
    W_EDUCATION,
    W_SALARY_CITY,
    W_SKILL,
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def flt() -> HardConditionFilter:
    return HardConditionFilter()


def _role(**kw) -> dict:
    base = {
        "required_skills": ["python", "django"],
        "education": "本科",
        "certificates_required": [],
        "salary_min_k": 30,
        "salary_max_k": 50,
        "city": "北京",
        "remote_policy": "onsite",
        "availability_required": "1月",
    }
    base.update(kw)
    return base


def _candidate(**kw) -> dict:
    base = {
        "skills": ["python", "django", "flask"],
        "education": "硕士",
        "certificates": [],
        "salary_min_k": 35,
        "salary_max_k": 45,
        "city": "北京",
        "availability": "立即上岗",
        "job_intent": "积极",
    }
    base.update(kw)
    return base


# ===========================================================================
# 1. 基础结构 / 输出形状
# ===========================================================================

class TestOutputShape:
    def test_returns_match_result(self, flt):
        res = flt.filter(_candidate(), _role())
        assert isinstance(res, MatchResult)

    def test_match_score_in_0_100(self, flt):
        res = flt.filter(_candidate(), _role())
        assert 0 <= res.match_score <= 100

    def test_has_four_sections(self, flt):
        res = flt.filter(_candidate(), _role())
        # match_reasons / skill_gaps / risks + hard_conditions + high_priority
        assert isinstance(res.match_reasons, list)
        assert isinstance(res.skill_gaps, list)
        assert isinstance(res.risks, list)
        assert "skill" in res.hard_conditions
        assert "education" in res.hard_conditions
        assert "certificate" in res.hard_conditions
        assert "salary_city" in res.high_priority
        assert "availability" in res.high_priority
        assert "benefits_travel" in res.high_priority

    def test_to_dict_serializable(self, flt):
        res = flt.filter(_candidate(), _role())
        d = res.to_dict()
        assert d["match_score"] == res.match_score
        assert d["passed_hard"] is True
        assert "candidate_id" in d
        assert "hard_conditions" in d
        # 全可 JSON 化 (无 dataclass 残留)
        import json
        json.dumps(d)


# ===========================================================================
# 2. 硬条件 — 技能
# ===========================================================================

class TestSkillHardCondition:
    def test_all_skills_match_passes(self, flt):
        res = flt.filter(_candidate(), _role())
        assert res.hard_conditions["skill"].satisfied is True
        assert res.skill_gaps == []

    def test_missing_skill_recorded_in_gaps(self, flt):
        res = flt.filter(
            _candidate(skills=["python"]),  # 缺 django
            _role(required_skills=["python", "django"]),
        )
        assert res.hard_conditions["skill"].satisfied is False
        assert any("django" in g for g in res.skill_gaps)

    def test_skill_count_in_reasons(self, flt):
        res = flt.filter(
            _candidate(skills=["python"]),
            _role(required_skills=["python", "django", "redis"]),
        )
        joined = " ".join(res.match_reasons)
        assert "1/3" in joined

    def test_skill_alias_python_py(self, flt):
        res = flt.filter(
            _candidate(skills=["py"]),
            _role(required_skills=["python"]),
        )
        assert res.hard_conditions["skill"].satisfied is True

    def test_skill_alias_k8s(self, flt):
        res = flt.filter(
            _candidate(skills=["k8s"]),
            _role(required_skills=["kubernetes"]),
        )
        assert res.hard_conditions["skill"].satisfied is True

    def test_skill_case_insensitive(self, flt):
        res = flt.filter(
            _candidate(skills=["Python", "DJANGO"]),
            _role(required_skills=["python", "django"]),
        )
        assert res.hard_conditions["skill"].satisfied is True

    def test_no_required_skills_passes(self, flt):
        res = flt.filter(_candidate(), _role(required_skills=[]))
        assert res.hard_conditions["skill"].satisfied is True

    def test_skill_ratio_partial(self, flt):
        res = flt.filter(
            _candidate(skills=["python"]),
            _role(required_skills=["python", "django", "redis", "go"]),
        )
        detail = res.hard_conditions["skill"].detail
        assert detail["ratio"] == 0.25


# ===========================================================================
# 3. 硬条件 — 学历
# ===========================================================================

class TestEducationHardCondition:
    def test_meets_requirement(self, flt):
        res = flt.filter(_candidate(education="硕士"), _role(education="本科"))
        assert res.hard_conditions["education"].satisfied is True
        assert any("学历满足" in r for r in res.match_reasons)

    def test_below_requirement(self, flt):
        res = flt.filter(_candidate(education="大专"), _role(education="本科"))
        assert res.hard_conditions["education"].satisfied is False
        assert any("学历要求" in g for g in res.skill_gaps)

    def test_exact_meets(self, flt):
        res = flt.filter(_candidate(education="本科"), _role(education="本科"))
        assert res.hard_conditions["education"].satisfied is True

    def test_no_requirement_passes(self, flt):
        res = flt.filter(_candidate(education="大专"), _role(education=None))
        assert res.hard_conditions["education"].satisfied is True

    def test_education_order_known(self):
        assert EDUCATION_ORDER["博士"] > EDUCATION_ORDER["硕士"]
        assert EDUCATION_ORDER["硕士"] > EDUCATION_ORDER["本科"]
        assert EDUCATION_ORDER["本科"] > EDUCATION_ORDER["大专"]

    def test_education_substring_match(self, flt):
        # "计算机本科" 应命中 "本科"
        res = flt.filter(_candidate(education="计算机本科"), _role(education="本科"))
        assert res.hard_conditions["education"].satisfied is True


# ===========================================================================
# 4. 硬条件 — 证书
# ===========================================================================

class TestCertificateHardCondition:
    def test_no_required_passes(self, flt):
        res = flt.filter(_candidate(), _role())
        assert res.hard_conditions["certificate"].satisfied is True

    def test_all_certs_present(self, flt):
        res = flt.filter(
            _candidate(certificates=["pmp", "cissp"]),
            _role(certificates_required=["pmp", "cissp"]),
        )
        assert res.hard_conditions["certificate"].satisfied is True

    def test_missing_cert_in_gaps(self, flt):
        res = flt.filter(
            _candidate(certificates=["pmp"]),
            _role(certificates_required=["pmp", "cissp"]),
        )
        assert res.hard_conditions["certificate"].satisfied is False
        assert any("cissp" in g for g in res.skill_gaps)

    def test_cert_case_insensitive(self, flt):
        res = flt.filter(
            _candidate(certificates=["PMP"]),
            _role(certificates_required=["pmp"]),
        )
        assert res.hard_conditions["certificate"].satisfied is True


# ===========================================================================
# 5. 高优先级 — 薪资 / 城市 / 工作时间
# ===========================================================================

class TestSalaryCity:
    def test_salary_in_range(self, flt):
        res = flt.filter(
            _candidate(salary_min_k=35, salary_max_k=40),
            _role(salary_min_k=30, salary_max_k=50),
        )
        assert any("薪资符合" in r for r in res.match_reasons)
        assert res.high_priority["salary_city"] > 0.5

    def test_salary_expectation_too_high_risk(self, flt):
        res = flt.filter(
            _candidate(salary_min_k=80),  # 期望 80K, 岗位上限 50
            _role(salary_min_k=30, salary_max_k=50),
        )
        assert any("薪资期望偏高" in r for r in res.risks)

    def test_salary_expectation_high_lowers_score(self, flt):
        high = flt.filter(_candidate(salary_min_k=80), _role(salary_min_k=30, salary_max_k=50))
        ok = flt.filter(_candidate(salary_min_k=35), _role(salary_min_k=30, salary_max_k=50))
        assert high.high_priority["salary_city"] < ok.high_priority["salary_city"]

    def test_same_city_reason(self, flt):
        res = flt.filter(
            _candidate(city="上海"), _role(city="上海"),
        )
        assert any("同城" in r for r in res.match_reasons)

    def test_city_mismatch_risk(self, flt):
        res = flt.filter(
            _candidate(city="广州"), _role(city="北京"),
        )
        assert any("城市不符" in r for r in res.risks)

    def test_remote_city_ok(self, flt):
        res = flt.filter(
            _candidate(city="远程"), _role(city="北京"),
        )
        # 远程 → 不算严重不符
        assert not any("城市不符" in r for r in res.risks)

    def test_no_salary_constraint_defaults_high(self, flt):
        # 岗位无薪资约束 → 满分
        res = flt.filter(_candidate(), _role(salary_min_k=None, salary_max_k=None))
        assert res.high_priority["salary_city"] >= 0.9


# ===========================================================================
# 6. 高优先级 — 到岗 / 求职意愿
# ===========================================================================

class TestAvailability:
    def test_immediate_meets_one_month(self, flt):
        res = flt.filter(
            _candidate(availability="立即上岗"),
            _role(availability_required="1月"),
        )
        assert res.high_priority["availability"] >= 0.9

    def test_too_late_risk(self, flt):
        res = flt.filter(
            _candidate(availability="三个月"),
            _role(availability_required="立即"),
        )
        assert any("到岗" in r for r in res.risks)

    def test_strong_intent_reason(self, flt):
        res = flt.filter(_candidate(job_intent="积极"), _role())
        assert any("求职意愿" in r for r in res.match_reasons)

    def test_passive_intent_risk(self, flt):
        res = flt.filter(_candidate(job_intent="观望"), _role())
        assert any("求职意愿" in r for r in res.risks)

    def test_uncertain_availability_risk(self, flt):
        res = flt.filter(
            _candidate(availability="未知状态"),
            _role(availability_required="1月"),
        )
        assert any("到岗时间不确定" in r for r in res.risks)


# ===========================================================================
# 6b. 高优先级 — 五险一金 + 出差 (v11.2 新增维度)
# ===========================================================================

class TestBenefitsTravel:
    """五险一金 + 出差 高优先级维度 (软评分, 永不淘汰)."""

    def test_social_insurance_match(self, flt):
        # 期望五险一金 + 岗位提供 → 满
        res = flt.filter(
            _candidate(social_insurance_expectation=True),
            _role(offers_social_insurance=True),
        )
        assert res.high_priority["benefits_travel"] >= 0.5
        assert any("五险一金齐全" in r for r in res.match_reasons)

    def test_social_insurance_mismatch_risk(self, flt):
        # 期望五险一金 但岗位不提供 → 低分 + 风险
        res = flt.filter(
            _candidate(social_insurance_expectation=True),
            _role(offers_social_insurance=False),
        )
        assert res.high_priority["benefits_travel"] <= 0.6
        assert any("岗位未提供五险一金" in r for r in res.risks)

    def test_social_insurance_expectation_none_neutral(self, flt):
        # 候选人未表态 → 中性 1.0, 不扣分
        res = flt.filter(
            _candidate(social_insurance_expectation=None),
            _role(offers_social_insurance=False),
        )
        # 社保子分 = 1.0, 出差默认中性 1.0 → 0.5*... 整体该维度 1.0
        # 注意: offers_social_insurance=False 但候选人不期望 → 不惩罚
        sc = self._social_subscore(res)
        assert sc >= 0.9
        assert not any("岗位未提供五险一金" in r for r in res.risks)

    def test_housing_fund_bonus_reason(self, flt):
        res = flt.filter(
            _candidate(),
            _role(offers_housing_fund=True),
        )
        assert any("含住房公积金" in r for r in res.match_reasons)

    def test_travel_tolerant(self, flt):
        # 频繁出差 + 候选人 willing → 可接受
        res = flt.filter(
            _candidate(travel_tolerance="willing"),
            _role(travel_required="frequent"),
        )
        assert res.high_priority["benefits_travel"] >= 0.9
        assert any("出差要求可接受" in r for r in res.match_reasons)

    def test_travel_intolerant_risk(self, flt):
        # 频繁出差 + 候选人 unwilling → 低分 + 风险
        res = flt.filter(
            _candidate(travel_tolerance="unwilling"),
            _role(travel_required="frequent"),
        )
        assert res.high_priority["benefits_travel"] <= 0.7
        assert any("出差频繁超出预期" in r for r in res.risks)

    def test_travel_slightly_higher_risk(self, flt):
        # role_level == tol_level + 1 → 0.6 + 略高风险
        res = flt.filter(
            _candidate(travel_tolerance="occasional"),  # tol=2
            _role(travel_required="frequent"),          # role=3 == tol+1
        )
        assert any("出差频率略高于预期" in r for r in res.risks)

    def test_travel_tolerance_none_neutral(self, flt):
        # 候选人出差容忍度未填 → 中性, 不扣分
        res = flt.filter(
            _candidate(travel_tolerance=None),
            _role(travel_required="frequent"),
        )
        # 出差子分 = 1.0, 社保默认 → 维度 ≈ 1.0
        assert res.high_priority["benefits_travel"] >= 0.9
        assert not any("出差" in r for r in res.risks)

    def test_combined_benefits_travel_in_overall(self, flt):
        # benefits_travel 维度应纳入综合分
        good = flt.filter(
            _candidate(social_insurance_expectation=True, travel_tolerance="willing"),
            _role(offers_social_insurance=True, travel_required="occasional"),
        )
        bad = flt.filter(
            _candidate(social_insurance_expectation=True, travel_tolerance="unwilling"),
            _role(offers_social_insurance=False, travel_required="frequent"),
        )
        assert good.high_priority["benefits_travel"] > bad.high_priority["benefits_travel"]
        assert good.match_score > bad.match_score

    def test_default_role_offers_social_insurance_true(self, flt):
        # role 未填 offers_social_insurance → 默认 True
        res = flt.filter(
            _candidate(social_insurance_expectation=True),
            _role(),  # 不显式提供 offers_social_insurance
        )
        assert any("五险一金齐全" in r for r in res.match_reasons)

    def test_no_elimination_low_benefits_still_scored(self, flt):
        # 即使五险一金/出差全不匹配, 仍是软评分, 综合分不会被清零
        res = flt.filter(
            _candidate(social_insurance_expectation=True, travel_tolerance="unwilling"),
            _role(offers_social_insurance=False, travel_required="frequent"),
        )
        assert res.match_score > 0  # 不淘汰
        assert res.high_priority["benefits_travel"] > 0  # 软评分仍 > 0

    def test_threshold_not_eliminating_low_salary_stays_positive(self, flt):
        # 薪资期望极高 + 城市不符 + 出差不接受 → 分数低但仍 > 0 (不淘汰)
        res = flt.filter(
            _candidate(
                salary_min_k=500, city="广州",
                travel_tolerance="unwilling",
                social_insurance_expectation=True,
            ),
            _role(
                salary_min_k=10, salary_max_k=20, city="北京",
                travel_required="frequent", offers_social_insurance=False,
            ),
        )
        assert res.match_score > 0
        assert res.high_priority["benefits_travel"] > 0

    # -- 辅助: 从 risks/reasons 推断五险一金子分 (黑盒) --
    @staticmethod
    def _social_subscore(res) -> float:
        # 当无 "岗位未提供五险一金" risk 时, 社保子分 = 1.0
        if any("岗位未提供五险一金" in r for r in res.risks):
            return 0.2
        return 1.0


# ===========================================================================
# 7. 不淘汰, 只排序 (核心甲方要求)
# ===========================================================================

class TestNoElimination:
    def test_candidate_with_gaps_still_has_score(self, flt):
        res = flt.filter(
            _candidate(skills=["cobol"], education="高中"),
            _role(required_skills=["python", "django"], education="硕士"),
        )
        # 不淘汰: 仍有分数 (只是低)
        assert res.match_score > 0
        assert len(res.skill_gaps) >= 2

    def test_perfect_match_high_score(self, flt):
        res = flt.filter(_candidate(), _role())
        assert res.match_score >= 75

    def test_weak_match_lower_score(self, flt):
        perfect = flt.filter(_candidate(), _role())
        weak = flt.filter(
            _candidate(skills=["cobol"], education="高中",
                       salary_min_k=200, city="广州", job_intent="不考虑"),
            _role(),
        )
        assert weak.match_score < perfect.match_score

    def test_passed_hard_flag(self, flt):
        ok = flt.filter(_candidate(), _role())
        bad = flt.filter(
            _candidate(skills=["cobol"]),
            _role(required_skills=["python"]),
        )
        assert ok.passed_hard is True
        assert bad.passed_hard is False


# ===========================================================================
# 8. 工作 / 行业经历不使用
# ===========================================================================

class TestExperienceNotUsed:
    def test_experience_fields_ignored(self, flt):
        # 候选人有大量经验 vs 无经验, 但技能/学历相同 → 分数应一致
        # (经历不参与打分)
        with_exp = _candidate(experience=[{"duration_months": 120}])
        no_exp = _candidate(experience=[])
        r1 = flt.filter(with_exp, _role())
        r2 = flt.filter(no_exp, _role())
        assert r1.match_score == r2.match_score


# ===========================================================================
# 9. dict / 对象 双兼容
# ===========================================================================

@dataclass
class _CandidateObj:
    skills: list = field(default_factory=lambda: ["python", "django"])
    education: str = "本科"
    certificates: list = field(default_factory=list)
    salary_min_k: int = 35
    city: str = "北京"
    availability: str = "立即上岗"


@dataclass
class _RoleObj:
    required_skills: list = field(default_factory=lambda: ["python", "django"])
    education: str = "本科"
    certificates_required: list = field(default_factory=list)
    salary_min_k: int = 30
    salary_max_k: int = 50
    city: str = "北京"


class TestObjectCompat:
    def test_accepts_dataclass_objects(self, flt):
        res = flt.filter(_CandidateObj(), _RoleObj())
        assert res.hard_conditions["skill"].satisfied is True
        assert res.match_score >= 70


# ===========================================================================
# 10. 引擎集成 (MatchingEngine.run_hard_filter_matching)
# ===========================================================================

def _mock_supabase(role_row: dict, cand_rows: list[dict]) -> MagicMock:
    sb = MagicMock()
    # role lookup
    sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=role_row)
    # candidate lookup (limit path)
    sb.table.return_value.select.return_value.limit.return_value.execute.return_value = MagicMock(data=cand_rows)
    return sb


class TestEngineIntegration:
    def test_engine_has_hard_filter(self):
        from matching.engine import MatchingEngine
        eng = MatchingEngine(MagicMock())
        assert hasattr(eng, "hard_filter")
        assert hasattr(eng, "run_hard_filter_matching")

    @pytest.mark.asyncio
    async def test_engine_sorts_by_score_desc(self):
        from matching.engine import MatchingEngine
        role = _role()
        cands = [
            {"id": "weak", **_candidate(skills=["cobol"], education="高中")},
            {"id": "strong", **_candidate()},
        ]
        sb = _mock_supabase(role, cands)
        eng = MatchingEngine(sb)
        results = await eng.run_hard_filter_matching("role-1", top_k=10)
        assert len(results) == 2
        # strong (全达标) 排前
        assert results[0].candidate_id == "strong"
        assert results[0].match_score >= results[1].match_score
        # 所有人保留 (不淘汰)
        assert {r.candidate_id for r in results} == {"strong", "weak"}

    @pytest.mark.asyncio
    async def test_engine_explicit_candidate_ids(self):
        from matching.engine import MatchingEngine
        role = _role()
        cands = [{"id": "c1", **_candidate()}]
        sb = MagicMock()
        sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data=role)
        sb.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(data=cands)
        eng = MatchingEngine(sb)
        import uuid
        results = await eng.run_hard_filter_matching(
            uuid.uuid4(), candidate_ids=[uuid.uuid4()]
        )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_engine_passed_hard_priority(self):
        """passed_hard=True 的整体排在 passed_hard=False 前面, 即使分数接近."""
        from matching.engine import MatchingEngine
        role = _role(required_skills=["python", "django"])
        cands = [
            # 不达标但软分高
            {"id": "gap", **_candidate(skills=["python"], salary_min_k=35, job_intent="积极")},
            # 全达标
            {"id": "ok", **_candidate()},
        ]
        sb = _mock_supabase(role, cands)
        eng = MatchingEngine(sb)
        results = await eng.run_hard_filter_matching("r", top_k=10)
        assert results[0].passed_hard is True
        assert results[0].candidate_id == "ok"


# ===========================================================================
# 11. 权重边界
# ===========================================================================

class TestWeights:
    def test_weights_normalized(self):
        total = W_SKILL + W_EDUCATION + W_CERTIFICATE
        # 加上软权重应当 = 1.0 (在模块里断言过)
        assert abs(total - 0.65) < 1e-9

    def test_skill_dominant(self):
        # 技能权重最大
        assert W_SKILL > W_EDUCATION
        assert W_SKILL > W_CERTIFICATE

    def test_soft_total_three_dims(self):
        # v11.2: 三个软维度总和仍为 0.35
        soft = W_SALARY_CITY + W_AVAILABILITY + W_BENEFITS_TRAVEL
        assert abs(soft - 0.35) < 1e-9

    def test_all_four_weights_sum_to_one(self):
        total = (
            W_SKILL + W_EDUCATION + W_CERTIFICATE
            + W_SALARY_CITY + W_AVAILABILITY + W_BENEFITS_TRAVEL
        )
        assert abs(total - 1.0) < 1e-9

    def test_benefits_travel_weight_value(self):
        assert W_BENEFITS_TRAVEL == 0.11
        assert W_SALARY_CITY == 0.14
        assert W_AVAILABILITY == 0.10


# ===========================================================================
# 12. 空输入健壮性
# ===========================================================================

class TestRobustness:
    def test_empty_dicts(self, flt):
        res = flt.filter({}, {})
        # 不崩, 仍给分
        assert 0 <= res.match_score <= 100
        assert res.passed_hard is True  # 无约束 = 全达标

    def test_none_fields(self, flt):
        res = flt.filter(
            {"skills": None, "education": None, "certificates": None},
            {"required_skills": None, "education": None},
        )
        assert res.passed_hard is True

    def test_risks_dedup(self, flt):
        # 重复触发相同风险 → 去重
        res = flt.filter(
            _candidate(salary_min_k=200, city="广州"),
            _role(salary_min_k=30, salary_max_k=50, city="北京"),
        )
        # 每条风险只出现一次
        assert len(res.risks) == len(set(res.risks))


# ===========================================================================
# 13. T6107 — 岗位卡 4 部分 (职责/硬条件/加分项/边界) 后端 schema
# ===========================================================================

class TestJobCardFourParts:
    """岗位卡 4 部分在 JobDetail dataclass + JobDetailOut schema 上落地."""

    def test_job_detail_has_four_part_fields(self):
        from services.marketplace.talent_market import JobDetail
        jd = JobDetail(
            id="j1", company="c", company_industry="i", title="t", city="x",
            salary_min_k=None, salary_max_k=None, skills_required=[],
            skills_preferred=[], seniority=None, education=None,
            experience_years=None, remote_policy="onsite",
            match_score=0, posted_at="2026-07-01",
        )
        # 加分项 + 边界 + 工作时间 + 出差 + 证书
        assert hasattr(jd, "nice_to_have")
        assert hasattr(jd, "boundaries")
        assert hasattr(jd, "work_schedule")
        assert hasattr(jd, "travel_required")
        assert hasattr(jd, "certificates_required")

    def test_enriched_job_populates_boundaries(self):
        from services.marketplace.talent_market import get_service
        svc = get_service()
        jobs, _, _ = svc.list_jobs(page=1, page_size=1)
        job = svc.get_job(jobs[0].id)
        # 边界 4 类: 工作时间 / 工作地点 / 出差 / 不做什么
        assert len(job.boundaries) >= 3
        assert any("工作时间" in b for b in job.boundaries)
        assert any("工作地点" in b for b in job.boundaries)
        assert any("出差" in b for b in job.boundaries)
        # 加分项非空
        assert len(job.nice_to_have) >= 1

    def test_job_detail_out_schema_includes_new_fields(self):
        from api.talent_market import JobDetailOut
        fields = set(JobDetailOut.model_fields.keys())
        assert "nice_to_have" in fields
        assert "boundaries" in fields
        assert "work_schedule" in fields
        assert "travel_required" in fields
        assert "certificates_required" in fields

    def test_job_detail_out_serializes_four_parts(self):
        from api.talent_market import _job_detail_out
        from services.marketplace.talent_market import get_service
        svc = get_service()
        jobs, _, _ = svc.list_jobs(page=1, page_size=1)
        out = _job_detail_out(svc.get_job(jobs[0].id))
        d = out.model_dump()
        # 甲方 4 部分: 职责 / 硬条件 / 加分项 / 边界 全可序列化
        import json
        json.dumps(d)
        assert isinstance(d["responsibilities"], list)
        assert isinstance(d["nice_to_have"], list)
        assert isinstance(d["boundaries"], list)
        assert isinstance(d["certificates_required"], list)

    def test_hard_filter_endpoint_registered(self):
        from api.matches import router
        paths = [r.path for r in router.routes]
        assert "/hard-filter/{role_id}" in paths
