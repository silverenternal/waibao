from contracts.shared import (
    ConfidenceLevel,
    ExtractedSkill,
    RequiredSkill,
    SeniorityLevel,
    SkillMatch,
)

# Scoring weights (T805 + T1306): 三因子 + 测评加权 (0.15)
# 测评分数为 None 时,自动回退到三因子(总分归一不变).
WEIGHT_SKILL_OVERLAP = 0.40
WEIGHT_SEMANTIC_SIMILARITY = 0.35
WEIGHT_EXPERIENCE_FIT = 0.25
# T1306: 测评权重,当候选人存在 assessment_score 时启用
WEIGHT_ASSESSMENT = 0.15

# A/B 实验动态权重 (T805): variant -> {skill, semantic, experience}
AB_WEIGHT_VARIANTS: dict[str, dict[str, float]] = {
    "control": {
        "skill": 0.40,
        "semantic": 0.35,
        "experience": 0.25,
    },
    "semantic_heavy": {
        "skill": 0.30,
        "semantic": 0.50,
        "experience": 0.20,
    },
    "experience_focused": {
        "skill": 0.35,
        "semantic": 0.30,
        "experience": 0.35,
    },
}

EXPERIMENT_MATCH_WEIGHTS = "match_weights_v2"

SENIORITY_ORDER = {
    SeniorityLevel.junior: 1,
    SeniorityLevel.mid: 2,
    SeniorityLevel.senior: 3,
    SeniorityLevel.lead: 4,
    SeniorityLevel.principal: 5,
}


class CompositeScorer:
    """Scores candidates against roles using weighted combination of three factors."""

    def score(
        self,
        candidate_skills: list[ExtractedSkill],
        candidate_seniority: SeniorityLevel | None,
        candidate_experience_months: int,
        role_required_skills: list[RequiredSkill],
        role_preferred_skills: list[RequiredSkill],
        role_seniority: SeniorityLevel | None,
        semantic_similarity: float,
        weights: dict[str, float] | None = None,
        ab_variant: str | None = None,
        assessment_score: float | None = None,
    ) -> dict:
        """Compute composite score and return full breakdown.

        T1306: assessment_score 可选 (0-100); 若存在则折算为 0-1 并按权重
        WEIGHT_ASSESSMENT 加入总分, 三因子权重按比例归一化;
        若为 None 则继续使用三因子权重,总分不受影响(向后兼容).

        weights: 显式权重覆盖;ab_variant: 从 A/B 实验拿 (会查 ab_test.AB_WEIGHT_VARIANTS).
        两者都不传则用全局常量 (生产 control).
        """
        # 1. Skill overlap scoring
        skill_overlap, skill_score = self._compute_skill_overlap(
            candidate_skills, role_required_skills, role_preferred_skills
        )

        # 2. Semantic similarity (already 0-1 from pgvector)
        semantic_score = max(0.0, min(1.0, semantic_similarity))

        # 3. Experience / seniority fit
        experience_score = self._compute_experience_fit(
            candidate_seniority, role_seniority, candidate_experience_months
        )

        # 4. 测评分数 (T1306) 折算为 0-1
        assessment_normalized: float | None = None
        if assessment_score is not None:
            try:
                assessment_normalized = max(
                    0.0,
                    min(1.0, float(assessment_score) / 100.0),
                )
            except (TypeError, ValueError):
                assessment_normalized = None

        # 5. Choose weights (control / 显式 / A/B 决议)
        resolved_weights = self._resolve_weights(
            weights=weights,
            ab_variant=ab_variant,
            assessment_enabled=assessment_normalized is not None,
        )

        # 6. Composite
        overall = (
            resolved_weights["skill"] * skill_score
            + resolved_weights["semantic"] * semantic_score
            + resolved_weights["experience"] * experience_score
            + resolved_weights.get("assessment", 0.0)
            * (assessment_normalized or 0.0)
        )
        overall = round(overall, 4)

        # 7. Confidence bucket
        confidence = self._bucket_confidence(overall)

        return {
            "overall_score": overall,
            "structured_score": round(skill_score, 4),
            "semantic_score": round(semantic_score, 4),
            "experience_score": round(experience_score, 4),
            "assessment_score": (
                round(assessment_normalized, 4)
                if assessment_normalized is not None else None
            ),
            "skill_overlap": skill_overlap,
            "confidence": confidence,
            "ab_variant": ab_variant or "control",
            "scoring_breakdown": {
                "weights": {
                    "skill_overlap": resolved_weights["skill"],
                    "semantic_similarity": resolved_weights["semantic"],
                    "experience_fit": resolved_weights["experience"],
                    "assessment": resolved_weights.get("assessment", 0.0),
                },
                "components": {
                    "skill_overlap_raw": round(skill_score, 4),
                    "semantic_similarity_raw": round(semantic_score, 4),
                    "experience_fit_raw": round(experience_score, 4),
                    "assessment_raw": (
                        round(assessment_normalized, 4)
                        if assessment_normalized is not None else None
                    ),
                },
                "weighted_components": {
                    "skill_overlap_weighted": round(
                        resolved_weights["skill"] * skill_score, 4
                    ),
                    "semantic_similarity_weighted": round(
                        resolved_weights["semantic"] * semantic_score, 4
                    ),
                    "experience_fit_weighted": round(
                        resolved_weights["experience"] * experience_score, 4
                    ),
                    "assessment_weighted": round(
                        resolved_weights.get("assessment", 0.0)
                        * (assessment_normalized or 0.0), 4
                    ),
                },
                "overall_score": overall,
            },
        }

    @staticmethod
    def _resolve_weights(
        weights: dict[str, float] | None,
        ab_variant: str | None,
        assessment_enabled: bool = False,
    ) -> dict[str, float]:
        """Pick the active weight set. 优先级: weights 参数 > ab_variant 查表 > control 常量.

        T1306: assessment_enabled=True 时,把 WEIGHT_ASSESSMENT 加进来,
        并对三因子做 (1 - 0.15) 归一化处理,保证总分归一.
        """
        if weights is not None:
            s = float(weights.get("skill", WEIGHT_SKILL_OVERLAP))
            sem = float(weights.get("semantic", WEIGHT_SEMANTIC_SIMILARITY))
            exp = float(weights.get("experience", WEIGHT_EXPERIENCE_FIT))
            ass = float(weights.get("assessment", 0.0))
            if ass <= 0:
                ass = WEIGHT_ASSESSMENT if assessment_enabled else 0.0
            total = s + sem + exp + ass or 1.0
            return {
                "skill": s / total,
                "semantic": sem / total,
                "experience": exp / total,
                "assessment": ass / total,
            }
        if ab_variant and ab_variant in AB_WEIGHT_VARIANTS:
            base = AB_WEIGHT_VARIANTS[ab_variant]
            if assessment_enabled:
                # 抽成 (1 - 0.15) = 0.85 的份额给三因子
                scale = 1.0 - WEIGHT_ASSESSMENT
                return {
                    "skill": base["skill"] * scale,
                    "semantic": base["semantic"] * scale,
                    "experience": base["experience"] * scale,
                    "assessment": WEIGHT_ASSESSMENT,
                }
            return {**base, "assessment": 0.0}
        if assessment_enabled:
            base_scale = 1.0 - WEIGHT_ASSESSMENT
            return {
                "skill": WEIGHT_SKILL_OVERLAP * base_scale,
                "semantic": WEIGHT_SEMANTIC_SIMILARITY * base_scale,
                "experience": WEIGHT_EXPERIENCE_FIT * base_scale,
                "assessment": WEIGHT_ASSESSMENT,
            }
        return {
            "skill": WEIGHT_SKILL_OVERLAP,
            "semantic": WEIGHT_SEMANTIC_SIMILARITY,
            "experience": WEIGHT_EXPERIENCE_FIT,
            "assessment": 0.0,
        }

    def _compute_skill_overlap(
        self,
        candidate_skills: list[ExtractedSkill],
        required_skills: list[RequiredSkill],
        preferred_skills: list[RequiredSkill],
    ) -> tuple[list[SkillMatch], float]:
        """Compare candidate skills against required + preferred skills."""
        c_skills = {}
        for s in candidate_skills:
            c_skills[s.name.lower().strip()] = s

        overlaps: list[SkillMatch] = []
        total_weight = 0.0
        earned_weight = 0.0

        for skill in required_skills:
            weight = 2.0
            total_weight += weight
            skill_name_lower = skill.name.lower().strip()

            match = self._find_skill_match(skill_name_lower, c_skills)
            if match:
                if skill.min_years and match.years:
                    if match.years >= skill.min_years:
                        status = "matched"
                        earned_weight += weight
                    else:
                        status = "partial"
                        ratio = match.years / skill.min_years
                        earned_weight += weight * min(ratio, 1.0) * 0.7
                else:
                    status = "matched"
                    earned_weight += weight

                overlaps.append(
                    SkillMatch(
                        skill_name=skill.name,
                        status=status,
                        candidate_years=match.years,
                        required_years=skill.min_years,
                    )
                )
            else:
                overlaps.append(
                    SkillMatch(
                        skill_name=skill.name,
                        status="missing",
                        candidate_years=None,
                        required_years=skill.min_years,
                    )
                )

        for skill in preferred_skills:
            weight = 1.0
            total_weight += weight
            skill_name_lower = skill.name.lower().strip()

            match = self._find_skill_match(skill_name_lower, c_skills)
            if match:
                earned_weight += weight
                overlaps.append(
                    SkillMatch(
                        skill_name=skill.name,
                        status="matched",
                        candidate_years=match.years,
                        required_years=skill.min_years,
                    )
                )
            else:
                overlaps.append(
                    SkillMatch(
                        skill_name=skill.name,
                        status="missing",
                        candidate_years=None,
                        required_years=skill.min_years,
                    )
                )

        score = (earned_weight / total_weight) if total_weight > 0 else 0.5
        return overlaps, min(score, 1.0)

    def _find_skill_match(
        self, target: str, candidate_skills: dict[str, ExtractedSkill]
    ) -> ExtractedSkill | None:
        """Find a matching skill with alias support."""
        if target in candidate_skills:
            return candidate_skills[target]

        ALIASES = {
            "javascript": ["js", "ecmascript"],
            "typescript": ["ts"],
            "python": ["py"],
            "react": ["reactjs", "react.js"],
            "node": ["nodejs", "node.js"],
            "postgresql": ["postgres", "psql"],
            "kubernetes": ["k8s"],
            "amazon web services": ["aws"],
            "google cloud platform": ["gcp"],
            "machine learning": ["ml"],
            "artificial intelligence": ["ai"],
            "ci/cd": ["cicd", "continuous integration"],
            "docker": ["containerization"],
        }

        for canonical, aliases in ALIASES.items():
            all_names = [canonical] + aliases
            if target in all_names:
                for name in all_names:
                    if name in candidate_skills:
                        return candidate_skills[name]

        # Substring matching as fallback
        for skill_name, skill in candidate_skills.items():
            if target in skill_name or skill_name in target:
                return skill

        return None

    def _compute_experience_fit(
        self,
        candidate_seniority: SeniorityLevel | None,
        role_seniority: SeniorityLevel | None,
        candidate_experience_months: int,
    ) -> float:
        """Score experience/seniority fit. Perfect=1.0, one level off=0.7."""
        if not role_seniority:
            return 0.7

        if not candidate_seniority:
            years = candidate_experience_months / 12.0
            if years >= 10:
                candidate_seniority = SeniorityLevel.principal
            elif years >= 7:
                candidate_seniority = SeniorityLevel.lead
            elif years >= 4:
                candidate_seniority = SeniorityLevel.senior
            elif years >= 2:
                candidate_seniority = SeniorityLevel.mid
            else:
                candidate_seniority = SeniorityLevel.junior

        c_level = SENIORITY_ORDER.get(candidate_seniority, 2)
        r_level = SENIORITY_ORDER.get(role_seniority, 2)
        diff = abs(c_level - r_level)

        if diff == 0:
            return 1.0
        elif diff == 1:
            return 0.7
        elif diff == 2:
            return 0.3
        else:
            return 0.1

    def _bucket_confidence(self, overall_score: float) -> ConfidenceLevel:
        """Bucket overall score into confidence levels."""
        if overall_score > 0.75:
            return ConfidenceLevel.strong
        elif overall_score >= 0.5:
            return ConfidenceLevel.good
        else:
            return ConfidenceLevel.possible
