"""T6304 (v11.2) — 阈值可见性 (threshold-visibility) service tests.

甲方合同: 联系前企业可见的求职者信息由平台按匹配度评判; 只有匹配度 ≥ 阀值
(默认 70%) 才能发起沟通; 低于阀值双方根本无法知道彼此. AI 不淘汰, 只排序/
增量.

These tests drive the SERVICE layer (TalentMarketService) directly so they
do not depend on auth/DB wiring. They cover:

  * employer sees ONLY >= threshold talents (+ best_role_id attached)
  * below-threshold talent is hidden (get_talent -> None / 404)
  * anonymous gets masked cards (can_contact=False, score hidden)
  * initiate_contact below threshold -> ValueError('below threshold')
  * initiate_contact above threshold -> channel created + mutually visible
  * best_role_id attached to employer cards
  * resilience: in-memory fallback used when Supabase unreachable
"""
from __future__ import annotations

import pytest

from matching.threshold import MATCH_THRESHOLD
from services.marketplace.talent_market import (
    CommunicationChannel,
    TalentCard,
    TalentMarketService,
    ViewerContext,
)


# ---------------------------------------------------------------------------
# fixtures / builders
# ---------------------------------------------------------------------------

def _talent_card(**kw) -> TalentCard:
    base = dict(
        id="t1",
        name="张*",
        title="后端工程师",
        city="北京",
        skills=["python", "django"],
        seniority="高级",
        education="硕士",
        salary_min_k=35,
        salary_max_k=45,
        experience_years=5,
        availability="立即上岗",
        match_score=0,
        online=True,
        avatar_color="hsl(0 0% 0%)",
    )
    base.update(kw)
    return TalentCard(**base)


def _employer_viewer(roles: list[dict]) -> ViewerContext:
    return ViewerContext(kind="employer", employer_roles=roles)


def _matching_role(role_id: str = "r1") -> dict:
    """A role that scores >= threshold against the default talent."""
    return {
        "id": role_id,
        "required_skills": ["python", "django"],
        "education": "本科",
        "certificates_required": [],
        "salary_min_k": 30,
        "salary_max_k": 50,
        "city": "北京",
        "remote_policy": "onsite",
        "availability_required": "1月",
    }


def _mismatch_role(role_id: str = "r_bad") -> dict:
    """A role that scores well below threshold against the default talent."""
    return {
        "id": role_id,
        "required_skills": ["cobol", "fortran", "rpg"],
        "education": "博士",
        "certificates_required": ["稀有证书"],
        "salary_min_k": 5,
        "salary_max_k": 10,
        "city": "广州",
        "remote_policy": "onsite",
    }


@pytest.fixture
def svc(monkeypatch) -> TalentMarketService:
    """A service forced onto the in-memory fallback (no DB)."""
    s = TalentMarketService()

    # Force fallback data + in-memory channels by stubbing the Supabase probe.
    monkeypatch.setattr(s, "_channels_client", lambda: None)
    monkeypatch.setattr(s, "_channels_probed", True, raising=False)

    # Inject a deterministic talent pool (matching + non-matching talents).
    matching = _talent_card(id="t_match", skills=["python", "django"])
    weak = _talent_card(
        id="t_weak",
        skills=["cobol"],
        education="高中",
        salary_min_k=500,
        salary_max_k=600,
        city="广州",
    )
    s._talents = [matching, weak]
    return s


# ===========================================================================
# 1. employer sees only >= threshold talents
# ===========================================================================

class TestEmployerThresholdFilter:
    def test_employer_keeps_only_above_threshold(self, svc):
        viewer = _employer_viewer([_matching_role()])
        cards, total, _ = svc.list_talents(viewer=viewer)
        ids = {c.id for c in cards}
        assert "t_match" in ids
        assert "t_weak" not in ids
        assert total == 1

    def test_employer_card_has_real_score_and_best_role(self, svc):
        viewer = _employer_viewer([_matching_role("rA"), _matching_role("rB")])
        cards, _, _ = svc.list_talents(viewer=viewer)
        card = next(c for c in cards if c.id == "t_match")
        assert card.match_score >= MATCH_THRESHOLD
        # best_role_id is one of the employer's roles and can_contact is on
        assert getattr(card, "best_role_id") in {"rA", "rB"}
        assert getattr(card, "can_contact") is True

    def test_employer_with_no_roles_returns_empty(self, svc):
        viewer = ViewerContext(kind="employer", employer_roles=[])
        cards, total, meta = svc.list_talents(viewer=viewer)
        assert cards == []
        assert total == 0
        # helpful empty-state hint surfaced (not an error)
        assert meta.get("empty_hint")

    def test_employer_listing_sorted_descending_by_score(self, svc):
        # two matching talents with different scores
        svc._talents = [
            _talent_card(id="t_low", skills=["python"]),       # partial match
            _talent_card(id="t_high", skills=["python", "django"]),  # full match
        ]
        viewer = _employer_viewer([_matching_role()])
        cards, _, _ = svc.list_talents(viewer=viewer)
        scores = [c.match_score for c in cards]
        assert scores == sorted(scores, reverse=True)


# ===========================================================================
# 2. below-threshold talent is hidden (get_talent -> None)
# ===========================================================================

class TestBelowThresholdHidden:
    def test_get_talent_below_threshold_returns_none(self, svc):
        viewer = _employer_viewer([_mismatch_role()])
        assert svc.get_talent("t_match", full=True, viewer=viewer) is None

    def test_get_talent_above_threshold_returns_card(self, svc):
        viewer = _employer_viewer([_matching_role()])
        card = svc.get_talent("t_match", full=True, viewer=viewer)
        assert card is not None
        assert card.id == "t_match"
        assert card.match_score >= MATCH_THRESHOLD

    def test_get_talent_employer_no_roles_returns_none(self, svc):
        viewer = ViewerContext(kind="employer", employer_roles=[])
        assert svc.get_talent("t_match", viewer=viewer) is None


# ===========================================================================
# 3. anonymous gets masked cards (no contact, no real score)
# ===========================================================================

class TestAnonymousMasking:
    def test_anonymous_cards_have_no_contact(self, svc):
        viewer = ViewerContext(kind="anonymous")
        cards, _, _ = svc.list_talents(viewer=viewer)
        assert cards  # browse still allowed (marketplace feel)
        for c in cards:
            assert getattr(c, "can_contact") is False
            assert getattr(c, "comm_channel_open") is False

    def test_anonymous_score_hidden(self, svc):
        viewer = ViewerContext(kind="anonymous")
        cards, _, _ = svc.list_talents(viewer=viewer)
        for c in cards:
            # real score masked to 0 (frontend shows 登录查看匹配度)
            assert c.match_score == 0

    def test_anonymous_get_talent_no_full(self, svc):
        viewer = ViewerContext(kind="anonymous")
        card = svc.get_talent("t_match", full=True, viewer=viewer)
        # anonymous never gets the full resume
        assert card is not None
        assert getattr(card, "can_contact") is False


# ===========================================================================
# 4 & 5. initiate_contact below / above threshold
# ===========================================================================

class TestInitiateContact:
    def test_below_threshold_raises(self, svc):
        with pytest.raises(ValueError, match="below threshold"):
            svc.initiate_contact(
                candidate_id="t_weak",
                role_id="r_bad",
                org_id="org1",
                initiated_by="employer",
                employer_roles=[_mismatch_role()],
            )

    def test_above_threshold_creates_channel(self, svc):
        ch = svc.initiate_contact(
            candidate_id="t_match",
            role_id="r1",
            org_id="org1",
            initiated_by="employer",
            employer_roles=[_matching_role()],
        )
        assert isinstance(ch, CommunicationChannel)
        assert ch.candidate_id == "t_match"
        assert ch.role_id == "r1"
        assert ch.org_id == "org1"
        assert ch.status == "open"
        assert ch.match_score >= MATCH_THRESHOLD

    def test_channel_idempotent_on_repeat(self, svc):
        ch1 = svc.initiate_contact(
            candidate_id="t_match", role_id="r1", org_id="org1",
            initiated_by="employer", employer_roles=[_matching_role()],
        )
        ch2 = svc.initiate_contact(
            candidate_id="t_match", role_id="r1", org_id="org1",
            initiated_by="employer", employer_roles=[_matching_role()],
        )
        # UNIQUE(candidate_id, role_id) — same pair → same channel id
        assert ch1.id == ch2.id


# ===========================================================================
# 6. mutual visibility after channel opened
# ===========================================================================

class TestMutualVisibility:
    def test_comm_channel_open_flag_after_contact(self, svc):
        svc.initiate_contact(
            candidate_id="t_match", role_id="r1", org_id="org1",
            initiated_by="employer", employer_roles=[_matching_role()],
        )
        viewer = _employer_viewer([_matching_role()])
        cards, _, _ = svc.list_talents(viewer=viewer)
        card = next(c for c in cards if c.id == "t_match")
        # channel now open for this pair
        assert getattr(card, "comm_channel_open") is True

    def test_list_channels_returns_opened_channel(self, svc):
        svc.initiate_contact(
            candidate_id="t_match", role_id="r1", org_id="org1",
            initiated_by="employer", employer_roles=[_matching_role()],
        )
        channels = svc.list_channels(org_id="org1")
        assert any(
            c.candidate_id == "t_match" and c.role_id == "r1" for c in channels
        )

    def test_list_channels_scoped_by_org(self, svc):
        svc.initiate_contact(
            candidate_id="t_match", role_id="r1", org_id="orgA",
            initiated_by="employer", employer_roles=[_matching_role()],
        )
        # querying a different org yields nothing
        assert svc.list_channels(org_id="orgB") == []


# ===========================================================================
# 7. talent viewer: jobs scored against profile
# ===========================================================================

class TestTalentViewerJobs:
    def test_talent_sees_only_matching_jobs(self, svc, monkeypatch):
        from services.marketplace.talent_market import JobCard

        svc._jobs = [
            JobCard(
                id="j_good", company="ACME", company_industry="互联网",
                title="后端工程师", city="北京", salary_min_k=30, salary_max_k=50,
                skills_required=["python", "django"], skills_preferred=[],
                seniority="高级", education="本科", experience_years="3-5年",
                remote_policy="onsite", match_score=0, posted_at="2026-07-01",
            ),
            JobCard(
                id="j_bad", company="OldCo", company_industry="金融",
                title="COBOL 维护", city="广州", salary_min_k=5, salary_max_k=10,
                skills_required=["cobol", "fortran"], skills_preferred=[],
                seniority="专家", education="博士", experience_years="10年+",
                remote_policy="onsite", match_score=0, posted_at="2026-07-01",
            ),
        ]
        profile = {
            "id": "t_match",
            "skills": ["python", "django"],
            "education": "硕士",
            "salary_min_k": 35,
            "salary_max_k": 45,
            "city": "北京",
            "availability": "立即上岗",
        }
        viewer = ViewerContext(kind="talent", talent_profile=profile, candidate_id="t_match")
        cards, total, _ = svc.list_jobs(viewer=viewer)
        ids = {c.id for c in cards}
        assert "j_good" in ids
        assert "j_bad" not in ids
        assert total == 1

    def test_talent_get_job_below_threshold_none(self, svc, monkeypatch):
        from services.marketplace.talent_market import JobCard

        svc._jobs = [
            JobCard(
                id="j_bad", company="OldCo", company_industry="金融",
                title="COBOL", city="广州", salary_min_k=5, salary_max_k=10,
                skills_required=["cobol", "fortran"], skills_preferred=[],
                seniority="专家", education="博士", experience_years="10年+",
                remote_policy="onsite", match_score=0, posted_at="2026-07-01",
            ),
        ]
        viewer = ViewerContext(
            kind="talent",
            talent_profile={
                "id": "t_match", "skills": ["python"], "education": "本科",
                "city": "北京", "salary_min_k": 40,
            },
            candidate_id="t_match",
        )
        assert svc.get_job("j_bad", viewer=viewer) is None


# ===========================================================================
# 8. resilience: in-memory fallback never breaks
# ===========================================================================

class TestResilience:
    def test_channels_client_none_uses_memory(self, svc):
        # svc fixture already forces _channels_client -> None
        ch = svc.initiate_contact(
            candidate_id="t_match", role_id="r1", org_id="org1",
            initiated_by="employer", employer_roles=[_matching_role()],
        )
        assert ch.id.startswith("ch_")

    def test_listing_with_no_viewer_defaults_to_anonymous(self, svc):
        # default ViewerContext is anonymous → masked, browse allowed
        cards, total, _ = svc.list_talents()
        assert total == len(svc._all_talents())
        assert all(getattr(c, "can_contact") is False for c in cards)
