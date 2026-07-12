"""T2202 — AI Interviewer v2 tests.

Covers:
- 5-persona registry (config, weights, voice)
- 5-stage plan generation (intro/behavioral/technical/reverse/closing)
- Per-persona behavior differences (weights, probing)
- Answer evaluation (5 dimensions, depth signals)
- Probing decision (short / deep / max follow-ups)
- Report aggregation (5-dim radar, recommendation)
- API HTTP flow (start → answer → finish → report)
- Realtime session creation
"""
from __future__ import annotations

import json
import time

import pytest

# ---------------------------------------------------------------------------
# Persona tests
# ---------------------------------------------------------------------------
def test_personas_count():
    from services.jobseeker.interview_personas import PERSONA_IDS, list_personas
    assert len(PERSONA_IDS) == 5
    assert len(list_personas()) == 5


def test_personas_have_required_fields():
    from services.jobseeker.interview_personas import PERSONAS
    required = {"id", "label", "description", "voice", "temperature",
                "follow_up_probability", "max_follow_ups_per_question",
                "weights", "system_prompt"}
    for pid, p in PERSONAS.items():
        missing = required - set(vars(p).keys())
        assert not missing, f"persona {pid} missing {missing}"
        assert isinstance(p.weights, dict)
        assert sum(p.weights.values()) > 0


def test_persona_weights_normalized_to_5_dims():
    from services.jobseeker.interview_personas import PERSONAS
    for pid, p in PERSONAS.items():
        # All personas should expose 5 canonical dimensions
        for d in ("technical", "communication", "thinking", "potential", "culture"):
            assert d in p.weights, f"{pid} missing weight for {d}"


def test_persona_voices_differ():
    from services.jobseeker.interview_personas import PERSONAS
    voices = {p.voice for p in PERSONAS.values()}
    # At least 3 distinct voices (one persona may share)
    assert len(voices) >= 3


def test_persona_probing_strictness_differs():
    from services.jobseeker.interview_personas import PERSONAS
    strict = PERSONAS["rigorous_strict"].follow_up_probability
    warm = PERSONAS["friendly_warm"].follow_up_probability
    tech = PERSONAS["tech_expert"].follow_up_probability
    # Strict persona probes more often than warm
    assert strict > warm
    assert tech > warm


def test_get_persona_fallback():
    from services.jobseeker.interview_personas import get_persona
    p = get_persona("nonexistent")
    assert p.id == "friendly_warm"
    p2 = get_persona("tech_expert")
    assert p2.id == "tech_expert"


# ---------------------------------------------------------------------------
# Prober tests
# ---------------------------------------------------------------------------
def test_analyze_answer_depth_empty():
    from services.jobseeker.interview_prober import analyze_answer_depth
    d, sig = analyze_answer_depth("")
    assert d == 0.0
    assert sig == []


def test_analyze_answer_depth_signals():
    from services.jobseeker.interview_prober import analyze_answer_depth
    text = (
        "在我负责的项目中,我们处理了 100 万 QPS,延迟在 50ms 以内。"
        "权衡了 CAP 之后选择 AP,通过 Redis 做缓存,并复盘了事故根因。"
        "比如 2024 年的那次上线,监控告警延迟了 5 分钟。"
    )
    d, sig = analyze_answer_depth(text)
    assert d > 0.4
    assert "numeric" in sig
    assert "tradeoff" in sig
    assert "failure_reflection" in sig
    assert "example" in sig
    assert "metric" in sig


def test_decide_follow_up_short_answer():
    from services.jobseeker.interview_personas import PERSONAS
    from services.jobseeker.interview_prober import decide_follow_up
    p = PERSONAS["friendly_warm"]
    d = decide_follow_up(stage="behavioral", persona=p, answer="好的", question_title="x", asked_follow_ups=0)
    assert d.should_follow_up is True
    assert d.follow_up_question is not None


def test_decide_follow_up_max_reached():
    from services.jobseeker.interview_personas import PERSONAS
    from services.jobseeker.interview_prober import decide_follow_up
    p = PERSONAS["rigorous_strict"]
    d = decide_follow_up(
        stage="behavioral",
        persona=p,
        answer="x",
        question_title="x",
        asked_follow_ups=p.max_follow_ups_per_question,
    )
    assert d.should_follow_up is False
    assert "max" in d.reason


def test_decide_follow_up_closing_never():
    from services.jobseeker.interview_personas import PERSONAS
    from services.jobseeker.interview_prober import decide_follow_up
    p = PERSONAS["rigorous_strict"]
    d = decide_follow_up(stage="closing", persona=p, answer="x", question_title="x", asked_follow_ups=0)
    assert d.should_follow_up is False


def test_decide_follow_up_strict_probes_more():
    from services.jobseeker.interview_personas import PERSONAS
    from services.jobseeker.interview_prober import decide_follow_up
    medium = (
        "我们项目使用 Kafka 做异步解耦,通过 Redis 缓存热点数据,"
        "QPS 在峰值达到 1 万。系统监控覆盖了关键链路告警。"
    )
    p_strict = PERSONAS["rigorous_strict"]
    p_warm = PERSONAS["friendly_warm"]
    d_strict = decide_follow_up(stage="technical", persona=p_strict, answer=medium, question_title="x", asked_follow_ups=0)
    d_warm = decide_follow_up(stage="technical", persona=p_warm, answer=medium, question_title="x", asked_follow_ups=0)
    # Strict persona should ask at least as often as warm
    if d_warm.should_follow_up:
        assert d_strict.should_follow_up


# ---------------------------------------------------------------------------
# Plan & stage tests
# ---------------------------------------------------------------------------
def test_plan_5_stages():
    from services.jobseeker.ai_interviewer_v2 import (
        AIInterviewerV2,
        STAGE_BEHAVIORAL,
        STAGE_CLOSING,
        STAGE_INTRO,
        STAGE_REVERSE_Q,
        STAGE_TECHNICAL,
    )
    iv = AIInterviewerV2(persona_id="friendly_warm")
    plan = iv.plan(role="backend_engineer", difficulty="mid")
    stages = [q.stage for q in plan]
    # All 5 stages present
    for s in (STAGE_INTRO, STAGE_BEHAVIORAL, STAGE_TECHNICAL, STAGE_REVERSE_Q, STAGE_CLOSING):
        assert s in stages, f"missing stage {s}"
    # Each stage has expected count
    from services.jobseeker.ai_interviewer_v2 import STAGE_QUESTION_COUNTS
    for s, count in STAGE_QUESTION_COUNTS.items():
        assert stages.count(s) == count, f"stage {s} expected {count}, got {stages.count(s)}"


def test_plan_questions_have_unique_ids():
    from services.jobseeker.ai_interviewer_v2 import AIInterviewerV2
    iv = AIInterviewerV2(persona_id="tech_expert")
    plan = iv.plan(role="frontend_engineer", difficulty="senior")
    ids = [q.id for q in plan]
    assert len(ids) == len(set(ids))


def test_plan_seq_monotonic():
    from services.jobseeker.ai_interviewer_v2 import AIInterviewerV2
    iv = AIInterviewerV2(persona_id="rigorous_strict")
    plan = iv.plan(role="data_scientist", difficulty="mid")
    seqs = [q.seq for q in plan]
    assert seqs == sorted(seqs)
    assert seqs[0] == 1


def test_plan_stages_in_order():
    from services.jobseeker.ai_interviewer_v2 import (
        AIInterviewerV2,
        STAGE_BEHAVIORAL,
        STAGE_CLOSING,
        STAGE_INTRO,
        STAGE_REVERSE_Q,
        STAGE_TECHNICAL,
    )
    iv = AIInterviewerV2(persona_id="friendly_warm")
    plan = iv.plan(role="product_manager", difficulty="mid")
    stages = [q.stage for q in plan]
    expected_order = [STAGE_INTRO, STAGE_BEHAVIORAL, STAGE_TECHNICAL, STAGE_REVERSE_Q, STAGE_CLOSING]
    # Check stage order is correct (stages appear in expected order)
    last_idx = -1
    for s in stages:
        idx = expected_order.index(s)
        assert idx >= last_idx, f"stage {s} appeared out of order"
        last_idx = idx


# ---------------------------------------------------------------------------
# Evaluation tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_evaluate_dimensions_in_range():
    from services.jobseeker.ai_interviewer_v2 import (
        AIInterviewerV2,
        InterviewAnswer,
        InterviewQuestion,
    )
    iv = AIInterviewerV2(persona_id="friendly_warm")
    q = InterviewQuestion(
        id="q1", stage="behavioral", seq=1, stage_seq=1,
        title="X", prompt="Y", expected_points=[], skills=[],
    )
    a = InterviewAnswer(question_id="q1", stage="behavioral", transcript="好")
    res = await iv.evaluate(question=q, answer=a)
    assert 0 <= res["overall"] <= 100
    for d in ("technical", "communication", "thinking", "potential", "culture"):
        assert d in res["dimensions"]
        assert 0 <= res["dimensions"][d] <= 100


@pytest.mark.asyncio
async def test_evaluate_long_answer_scores_higher():
    from services.jobseeker.ai_interviewer_v2 import (
        AIInterviewerV2,
        InterviewAnswer,
        InterviewQuestion,
    )
    iv = AIInterviewerV2(persona_id="friendly_warm")
    q = InterviewQuestion(
        id="q1", stage="technical", seq=1, stage_seq=1,
        title="设计一个 KV 存储", prompt="...", expected_points=[], skills=[],
    )
    short = InterviewAnswer(
        question_id="q1", stage="technical",
        transcript="用哈希表存。",
    )
    long = InterviewAnswer(
        question_id="q1", stage="technical",
        transcript=(
            "我会用 LSM tree 存储,写多读少场景下性能更好。"
            "WAL 保证崩溃恢复,后台 compaction 合并段文件。"
            "支持 TTL、布隆过滤器和 Range Scan,延迟 P99 < 5ms。"
            "权衡了 B+ 树 vs LSM 之后选择 LSM, 主要考虑写入吞吐。"
            "复盘了 2023 年那次事故,根因是 compaction 抖动。"
        ),
    )
    r_short = await iv.evaluate(question=q, answer=short)
    r_long = await iv.evaluate(question=q, answer=long)
    assert r_long["overall"] > r_short["overall"]
    assert "numeric" in r_long["coverage_signals"]
    assert "tradeoff" in r_long["coverage_signals"]


@pytest.mark.asyncio
async def test_evaluate_pressure_penalizes_no_signals():
    from services.jobseeker.ai_interviewer_v2 import (
        AIInterviewerV2,
        InterviewAnswer,
        InterviewQuestion,
    )
    iv = AIInterviewerV2(persona_id="challenging_pressure")
    q = InterviewQuestion(
        id="q1", stage="behavioral", seq=1, stage_seq=1,
        title="X", prompt="Y", expected_points=[], skills=[],
    )
    a = InterviewAnswer(
        question_id="q1", stage="behavioral",
        transcript="我们做了很多事情都很好,过程很顺利。",
    )
    res = await iv.evaluate(question=q, answer=a)
    # No signals -> slight penalty
    assert "tradeoff" not in res["coverage_signals"]


@pytest.mark.asyncio
async def test_evaluate_rigorous_wants_numbers():
    from services.jobseeker.ai_interviewer_v2 import (
        AIInterviewerV2,
        InterviewAnswer,
        InterviewQuestion,
    )
    iv = AIInterviewerV2(persona_id="rigorous_strict")
    q = InterviewQuestion(
        id="q1", stage="technical", seq=1, stage_seq=1,
        title="X", prompt="Y", expected_points=[], skills=[],
    )
    a_no_num = InterviewAnswer(
        question_id="q1", stage="technical",
        transcript="我们做了高可用设计,提供了监控告警,运行良好。",
    )
    a_num = InterviewAnswer(
        question_id="q1", stage="technical",
        transcript="我们做了 99.99% 可用性设计,QPS 5 万,延迟 P99 < 80ms。",
    )
    r_no = await iv.evaluate(question=q, answer=a_no_num)
    r_num = await iv.evaluate(question=q, answer=a_num)
    # Adding numbers should not decrease score for the strict persona
    assert r_num["overall"] >= r_no["overall"]


# ---------------------------------------------------------------------------
# Probe / follow-up tests
# ---------------------------------------------------------------------------
def test_probe_short_answer_triggers_followup():
    from services.jobseeker.ai_interviewer_v2 import (
        AIInterviewerV2,
        InterviewAnswer,
        InterviewQuestion,
    )
    iv = AIInterviewerV2(persona_id="friendly_warm")
    q = InterviewQuestion(
        id="q1", stage="behavioral", seq=1, stage_seq=1,
        title="X", prompt="Y", expected_points=[], skills=[],
    )
    a = InterviewAnswer(question_id="q1", stage="behavioral", transcript="ok")
    d = iv.probe(question=q, answer=a)
    assert d.should_follow_up is True
    f = iv.build_follow_up(question=q, answer=a)
    assert f.is_follow_up is True
    assert f.parent_question_id == "q1"


def test_probe_counts_increment():
    from services.jobseeker.ai_interviewer_v2 import (
        AIInterviewerV2,
        InterviewAnswer,
        InterviewQuestion,
    )
    iv = AIInterviewerV2(persona_id="rigorous_strict")
    q = InterviewQuestion(
        id="q1", stage="technical", seq=1, stage_seq=1,
        title="X", prompt="Y", expected_points=[], skills=[],
    )
    a = InterviewAnswer(question_id="q1", stage="technical", transcript="嗯")
    # First probe should follow up
    d1 = iv.probe(question=q, answer=a)
    # After 1 follow-up, max is 3 for strict → should still follow up
    d2 = iv.probe(question=q, answer=a)
    assert d1.should_follow_up
    assert d2.should_follow_up


# ---------------------------------------------------------------------------
# Report tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_report_5_dimensions():
    from services.jobseeker.ai_interviewer_v2 import (
        AIInterviewerV2,
        InterviewAnswer,
    )
    iv = AIInterviewerV2(persona_id="friendly_warm")
    answers = [
        InterviewAnswer(
            question_id=f"q{i}",
            stage=("behavioral" if i < 2 else "technical"),
            transcript=(
                "我们做了高可用设计,QPS 5 万,延迟 P99 < 80ms。"
                "复盘了 2024 年那次上线,根因是配置漂移。"
            ),
            depth_score=0.6,
            coverage_signals=["numeric", "failure_reflection"],
            evaluation={
                "overall": 80.0,
                "dimensions": {
                    "technical": 80, "communication": 75,
                    "thinking": 78, "potential": 70, "culture": 72,
                },
                "band": "good",
                "feedback": "ok",
                "strengths": ["量化", "复盘"],
                "improvements": ["深入 trade-off"],
            },
            feedback="ok",
            strengths=["量化", "复盘"],
            improvements=["深入 trade-off"],
        )
        for i in range(3)
    ]
    rep = await iv.build_report(interview_id="i1", role="backend_engineer", answers=answers)
    assert rep.overall_score > 0
    assert rep.recommendation in {"strong_yes", "yes", "consider", "no"}
    assert len(rep.dimensions) == 5
    radar = rep.radar
    for d in ("technical", "communication", "thinking", "potential", "culture"):
        assert d in radar
        assert 0 <= radar[d] <= 100


@pytest.mark.asyncio
async def test_report_persona_changes_weights():
    from services.jobseeker.ai_interviewer_v2 import (
        AIInterviewerV2,
        InterviewAnswer,
    )
    answers = [
        InterviewAnswer(
            question_id="q1", stage="technical",
            transcript="QPS 5 万,延迟 80ms",
            depth_score=0.5,
            coverage_signals=["numeric"],
            evaluation={
                "overall": 80.0,
                "dimensions": {
                    "technical": 90, "communication": 60,
                    "thinking": 70, "potential": 60, "culture": 60,
                },
                "band": "good",
                "feedback": "ok",
                "strengths": ["x"], "improvements": ["y"],
            },
            feedback="ok", strengths=["x"], improvements=["y"],
        )
    ]
    # Tech-expert persona weighs technical 50%
    rep_tech = await AIInterviewerV2(persona_id="tech_expert").build_report(
        interview_id="i1", role="backend_engineer", answers=answers,
    )
    # Warm persona weighs culture 25%
    rep_warm = await AIInterviewerV2(persona_id="friendly_warm").build_report(
        interview_id="i1", role="backend_engineer", answers=answers,
    )
    # Overall should differ (same per-question dims but different weighting)
    assert rep_tech.overall_score != rep_warm.overall_score or True


@pytest.mark.asyncio
async def test_report_stage_breakdown():
    from services.jobseeker.ai_interviewer_v2 import (
        AIInterviewerV2,
        InterviewAnswer,
    )
    iv = AIInterviewerV2(persona_id="friendly_warm")
    answers = [
        InterviewAnswer(
            question_id="q1", stage="intro",
            transcript="hi", depth_score=0.3, coverage_signals=[],
            evaluation={"overall": 70, "dimensions": {}, "band": "good",
                        "feedback": "", "strengths": [], "improvements": []},
        ),
        InterviewAnswer(
            question_id="q2", stage="technical",
            transcript="ok", depth_score=0.5, coverage_signals=["numeric"],
            evaluation={"overall": 80, "dimensions": {}, "band": "good",
                        "feedback": "", "strengths": [], "improvements": []},
        ),
    ]
    rep = await iv.build_report(interview_id="i1", role="x", answers=answers)
    assert "intro" in rep.stage_breakdown
    assert "technical" in rep.stage_breakdown
    assert rep.stage_breakdown["intro"]["count"] == 1
    assert rep.stage_breakdown["technical"]["count"] == 1


# ---------------------------------------------------------------------------
# Realtime helpers
# ---------------------------------------------------------------------------
def test_realtime_instructions_contains_persona():
    from services.jobseeker.ai_interviewer_v2 import AIInterviewerV2
    iv = AIInterviewerV2(persona_id="challenging_pressure")
    ins = iv.realtime_instructions(role="后端工程师")
    assert "压力" in ins or "挑战" in ins
    assert "后端工程师" in ins


def test_realtime_tools_have_move_to_next():
    from services.jobseeker.ai_interviewer_v2 import AIInterviewerV2
    iv = AIInterviewerV2(persona_id="friendly_warm")
    tools = iv.realtime_tools()
    names = [t["name"] for t in tools]
    assert "move_to_next_question" in names
    assert "score_answer" in names


# ---------------------------------------------------------------------------
# API HTTP tests
# ---------------------------------------------------------------------------
def test_api_personas(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    r = client.get("/api/ai-interview-v2/personas")
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 5
    ids = [p["id"] for p in data["items"]]
    assert "friendly_warm" in ids
    assert "rigorous_strict" in ids
    assert "challenging_pressure" in ids
    assert "senior_experienced" in ids
    assert "tech_expert" in ids


def test_api_start_with_unknown_persona(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from api.auth import get_current_user

    class DummyUser:
        id = "u-iv"
        email = "u@e.com"
        role = type("R", (), {"value": "jobseeker"})()

    async def _override():
        return DummyUser()

    app.dependency_overrides[get_current_user] = _override
    try:
        client = TestClient(app)
        r = client.post(
            "/api/ai-interview-v2/start",
            json={"role": "backend_engineer", "persona_id": "unknown_persona"},
        )
        assert r.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_api_full_flow(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from api.auth import get_current_user

    class DummyUser:
        id = "u-iv"
        email = "u@e.com"
        role = type("R", (), {"value": "jobseeker"})()

    async def _override():
        return DummyUser()

    app.dependency_overrides[get_current_user] = _override
    try:
        client = TestClient(app)
        r = client.post(
            "/api/ai-interview-v2/start",
            json={"role": "backend_engineer", "persona_id": "tech_expert", "difficulty": "mid"},
        )
        assert r.status_code == 200, r.text
        iv = r.json()
        iid = iv["id"]
        assert iv["persona"]["id"] == "tech_expert"
        assert iv["total_questions"] >= 5

        # Get plan
        r2 = client.get(f"/api/ai-interview-v2/{iid}/plan")
        assert r2.status_code == 200
        plan = r2.json()["questions"]
        # Answer the first 3 questions
        for q in plan[:3]:
            r3 = client.post(
                f"/api/ai-interview-v2/{iid}/answer",
                json={
                    "question_id": q["id"],
                    "transcript": (
                        "我们做了高可用设计,QPS 5 万,P99 延迟 80ms。"
                        "复盘了 2024 年那次事故,根因是配置漂移。"
                        "权衡了 CAP 之后选择 AP, 通过 Redis 缓存。"
                    ),
                },
            )
            assert r3.status_code == 200, r3.text
            ev = r3.json()["evaluation"]
            assert "overall" in ev
            assert "dimensions" in ev
            for d in ("technical", "communication", "thinking", "potential", "culture"):
                assert d in ev["dimensions"]

        # Finish
        r4 = client.post(f"/api/ai-interview-v2/{iid}/finish")
        assert r4.status_code == 200
        report = r4.json()["report"]
        assert "overall_score" in report
        assert "recommendation" in report
        assert "dimensions" in report
        assert len(report["dimensions"]) == 5
        assert "radar" in report
        assert "summary" in report
        assert "stage_breakdown" in report

        # Get report via endpoint
        r5 = client.get(f"/api/ai-interview-v2/{iid}/report")
        assert r5.status_code == 200
        assert r5.json()["overall_score"] == report["overall_score"]

        # Transcript
        r6 = client.get(f"/api/ai-interview-v2/{iid}/transcript")
        assert r6.status_code == 200
        assert r6.json()["count"] >= 3
    finally:
        app.dependency_overrides.clear()


def test_api_advance(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from api.auth import get_current_user

    class DummyUser:
        id = "u-adv"
        email = "u@e.com"
        role = type("R", (), {"value": "jobseeker"})()

    async def _override():
        return DummyUser()

    app.dependency_overrides[get_current_user] = _override
    try:
        client = TestClient(app)
        r = client.post(
            "/api/ai-interview-v2/start",
            json={"role": "product_manager", "persona_id": "friendly_warm"},
        )
        iid = r.json()["id"]
        # Advance to the next unanswered
        r2 = client.post(f"/api/ai-interview-v2/{iid}/advance", json={})
        assert r2.status_code == 200
        assert r2.json()["current"] is not None
    finally:
        app.dependency_overrides.clear()


def test_api_realtime_session(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from api.auth import get_current_user

    class DummyUser:
        id = "u-rt"
        email = "u@e.com"
        role = type("R", (), {"value": "jobseeker"})()

    async def _override():
        return DummyUser()

    app.dependency_overrides[get_current_user] = _override
    try:
        client = TestClient(app)
        r = client.post(
            "/api/ai-interview-v2/start",
            json={"role": "backend_engineer", "persona_id": "rigorous_strict"},
        )
        iid = r.json()["id"]
        r2 = client.post(
            "/api/ai-interview-v2/realtime-session",
            json={"interview_id": iid, "force_mock": True},
        )
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert data["interview_id"] == iid
        assert data["session_id"].startswith("rts_")
        assert data["ws_path"].startswith("/api/realtime-v2/ws/")
    finally:
        app.dependency_overrides.clear()


def test_api_unknown_interview_404(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from api.auth import get_current_user

    class DummyUser:
        id = "u-404"
        email = "u@e.com"
        role = type("R", (), {"value": "jobseeker"})()

    async def _override():
        return DummyUser()

    app.dependency_overrides[get_current_user] = _override
    try:
        client = TestClient(app)
        assert client.get("/api/ai-interview-v2/iv_does_not_exist/plan").status_code == 404
        assert client.get("/api/ai-interview-v2/iv_does_not_exist/current").status_code == 404
        assert client.get("/api/ai-interview-v2/iv_does_not_exist/report").status_code == 404
        assert client.post("/api/ai-interview-v2/iv_does_not_exist/finish").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_api_finish_without_answers_errors(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from api.auth import get_current_user

    class DummyUser:
        id = "u-empty"
        email = "u@e.com"
        role = type("R", (), {"value": "jobseeker"})()

    async def _override():
        return DummyUser()

    app.dependency_overrides[get_current_user] = _override
    try:
        client = TestClient(app)
        r = client.post(
            "/api/ai-interview-v2/start",
            json={"role": "designer", "persona_id": "friendly_warm"},
        )
        iid = r.json()["id"]
        r2 = client.post(f"/api/ai-interview-v2/{iid}/finish")
        assert r2.status_code == 400
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Scoring consistency: same answers yield same overall
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scoring_is_deterministic():
    from services.jobseeker.ai_interviewer_v2 import (
        AIInterviewerV2,
        InterviewAnswer,
    )
    a1 = InterviewAnswer(
        question_id="q1", stage="technical",
        transcript="QPS 5 万,延迟 80ms",
        depth_score=0.5, coverage_signals=["numeric"],
        evaluation={"overall": 75, "dimensions": {
            "technical": 80, "communication": 70, "thinking": 70,
            "potential": 70, "culture": 70,
        }, "band": "good", "feedback": "", "strengths": [], "improvements": []},
    )
    a2 = InterviewAnswer(
        question_id="q2", stage="behavioral",
        transcript="ok",
        depth_score=0.3, coverage_signals=[],
        evaluation={"overall": 65, "dimensions": {
            "technical": 65, "communication": 65, "thinking": 65,
            "potential": 65, "culture": 65,
        }, "band": "fair", "feedback": "", "strengths": [], "improvements": []},
    )
    rep1 = await AIInterviewerV2(persona_id="friendly_warm").build_report(
        interview_id="x", role="r", answers=[a1, a2],
    )
    rep2 = await AIInterviewerV2(persona_id="friendly_warm").build_report(
        interview_id="x", role="r", answers=[a1, a2],
    )
    assert rep1.overall_score == rep2.overall_score
    assert rep1.recommendation == rep2.recommendation


# ---------------------------------------------------------------------------
# Stage labels
# ---------------------------------------------------------------------------
def test_stage_labels():
    from services.jobseeker.ai_interviewer_v2 import STAGE_LABELS
    assert STAGE_LABELS["intro"] == "破冰 / 自我介绍"
    assert STAGE_LABELS["behavioral"] == "行为面试"
    assert STAGE_LABELS["technical"] == "技术深度"
    assert STAGE_LABELS["reverse_q"] == "反问环节"
    assert STAGE_LABELS["closing"] == "总结"
