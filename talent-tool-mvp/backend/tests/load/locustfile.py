"""Locust 压测主入口 (T1703 — v5.0 真实业务压测).

v5.0 升级要点 (相对 v3.0 T1104):
  - Persona 从 5 扩到 **12 个**, 覆盖 P0/P1/P2 全部真实业务
  - 真实业务 API:
      * agent invoke (高频)
      * matches compute + explain + batch + feedback
      * tickets CRUD + comments + assign + resolve
      * clarifications send + reply + resolve
      * subscriptions create + list + match + delete
      * collections 列表 + 报价 / quote
      * assessments 邀请 + 提交
      * collaboration rooms 创建 + 发消息
      * realtime invoke + skill score
      * voice / video interview 创建 + 列表
      * background check 启动 + 状态
      * analytics funnel events 写入
  - 自动 SLA 检查 (p95 < 2000ms / 错误率 < 0.5%)
  - 与 Prometheus metrics 联动 (标签透传 region / persona)

默认通过 ``-u`` / ``-r`` 控制并发;目标 1000 并发 / 10 分钟稳态。

Usage:
    locust -f locustfile.py --host http://localhost:8000 \\
        -u 1000 -r 50 --run-time 10m --headless \\
        --html reports/locust_v5_1000.html --csv reports/locust_v5_1000
"""
from __future__ import annotations

import logging
import os
import random
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from locust import HttpUser, between, events, task

# Allow `python locustfile.py` from any cwd
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from scenarios import (  # noqa: E402  (import after path tweak)
    DEMO_CANDIDATE_ID,
    DEMO_ORG_ID,
    DEMO_ROLE_ID,
    fake_brief_payload,
    fake_clarifier_text,
    fake_emotion_text,
    fake_jd_payload,
    fake_journal_payload,
    fake_org_payload,
    fake_resume_text,
    fake_resume_upload_payload,
    fake_role_payload,
    fake_room_id,
    fake_room_message,
    fake_short_code,
    fake_ticket_payload,
    fake_two_way_match_payload,
    fake_user_id,
    fake_user_payload,
    fake_vision_payload,
)

logger = logging.getLogger("recruittech.load.v5")

# ---------------------------------------------------------------------------
# 通用配置
# ---------------------------------------------------------------------------

MOCK_JWT_JOBSEEKER = os.getenv("LOAD_JWT_JOBSEEKER", "mock-jwt-jobseeker")
MOCK_JWT_EMPLOYER = os.getenv("LOAD_JWT_EMPLOYER", "mock-jwt-employer")
MOCK_JWT_ADMIN = os.getenv("LOAD_JWT_ADMIN", "mock-jwt-admin")
MOCK_JWT_PARTNER = os.getenv("LOAD_JWT_PARTNER", "mock-jwt-partner")
LOCALE = os.getenv("LOAD_LOCALE", random.choice(["zh", "en"]))

# SLA 阈值 (T1703 目标)
SLA_P95_MS = int(os.getenv("SLA_P95_MS", "2000"))
SLA_ERROR_RATE = float(os.getenv("SLA_ERROR_RATE", "0.005"))


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _common_headers(token: str, persona: str) -> dict[str, str]:
    """压测专用头部 — 携带 persona 与 region 标签便于 Prometheus 切片."""
    h = _auth_headers(token)
    h["X-Load-Test"] = "1"
    h["X-Persona"] = persona
    h["X-Region"] = os.getenv("LOAD_REGION", random.choice(["cn", "sg", "us"]))
    return h


# ---------------------------------------------------------------------------
# 基类
# ---------------------------------------------------------------------------

class BaseUser(HttpUser):
    abstract = True
    wait_time = between(0.2, 1.5)
    timeout = 30.0

    def _post_json(self, path: str, payload: dict[str, Any], name: str | None = None) -> None:
        with self.client.post(
            path,
            json=payload,
            headers=_common_headers(self.token, self.persona),
            name=name or path,
            catch_response=True,
        ) as resp:
            self._classify(resp, name or path)

    def _patch_json(self, path: str, payload: dict[str, Any], name: str | None = None) -> None:
        with self.client.patch(
            path,
            json=payload,
            headers=_common_headers(self.token, self.persona),
            name=name or path,
            catch_response=True,
        ) as resp:
            self._classify(resp, name or path)

    def _get(self, path: str, name: str | None = None) -> None:
        with self.client.get(
            path,
            headers=_common_headers(self.token, self.persona),
            name=name or path,
            catch_response=True,
        ) as resp:
            self._classify(resp, name or path)

    def _delete(self, path: str, name: str | None = None) -> None:
        with self.client.delete(
            path,
            headers=_common_headers(self.token, self.persona),
            name=name or path,
            catch_response=True,
        ) as resp:
            self._classify(resp, name or path)

    def _classify(self, resp, name: str) -> None:
        if resp.status_code >= 500:
            resp.failure(f"5xx {resp.status_code}: {resp.text[:200]}")
        elif resp.status_code in (401, 403):
            resp.failure(f"auth {resp.status_code}: {resp.text[:200]}")
        else:
            # 4xx 业务校验预期 (如重复注册), 不算 SLA 失败
            resp.success()


# ---------------------------------------------------------------------------
# Persona 1: Jobseeker — 求职者主路径 (weight 8)
# ---------------------------------------------------------------------------

class JobseekerUser(BaseUser):
    weight = 8
    token = MOCK_JWT_JOBSEEKER
    persona = "jobseeker"

    def on_start(self) -> None:
        self._post_json(
            "/api/auth/register",
            fake_user_payload(role="jobseeker", locale=LOCALE),
            name="/api/auth/register [jobseeker]",
        )

    @task(5)
    def invoke_agent(self) -> None:
        self._post_json(
            "/api/realtime/invoke",
            {
                "text": fake_emotion_text(LOCALE),
                "context": {"persona": "jobseeker"},
                "stream": False,
            },
            name="/api/realtime/invoke",
        )

    @task(2)
    def upload_resume(self) -> None:
        self._post_json(
            "/api/uploads/resume",
            fake_resume_upload_payload(LOCALE),
            name="/api/uploads/resume",
        )

    @task(2)
    def submit_journal(self) -> None:
        self._post_json(
            "/api/journal",
            fake_journal_payload(LOCALE),
            name="/api/journal",
        )

    @task(1)
    def trigger_emotion(self) -> None:
        self._post_json(
            "/api/emotion/analyze",
            {"text": fake_emotion_text(LOCALE)},
            name="/api/emotion/analyze",
        )

    @task(1)
    def trigger_clarifier(self) -> None:
        self._post_json(
            "/api/realtime/invoke",
            {
                "text": fake_clarifier_text(LOCALE),
                "context": {"force_agent": "clarifier_agent"},
                "stream": False,
            },
            name="/api/realtime/invoke [clarifier]",
        )

    @task(1)
    def list_today_journal(self) -> None:
        self._get("/api/journal/today", name="/api/journal/today")

    @task(2)
    def career_plan(self) -> None:
        """T1801 — 真实业务: 职业规划 / 行动项."""
        self._get("/api/career-plan", name="/api/career-plan")

    @task(1)
    def offer_calculator(self) -> None:
        """T1802 — 真实业务: Offer 比较."""
        self._post_json(
            "/api/offer/compare",
            {
                "offers": [
                    {
                        "company": "Acme",
                        "base": random.randint(30, 80) * 1000,
                        "equity": random.randint(50, 300) * 1000,
                        "bonus": random.randint(0, 12) * 1000,
                    },
                    {
                        "company": "Beta",
                        "base": random.randint(30, 80) * 1000,
                        "equity": random.randint(50, 300) * 1000,
                        "bonus": random.randint(0, 12) * 1000,
                    },
                ],
            },
            name="/api/offer/compare",
        )

    @task(1)
    def list_matches_for_candidate(self) -> None:
        self._get(
            f"/api/two-way-match/for-candidate/{DEMO_CANDIDATE_ID}",
            name="/api/two-way-match/for-candidate",
        )


# ---------------------------------------------------------------------------
# Persona 2: Employer — 用人方 (weight 5)
# ---------------------------------------------------------------------------

class EmployerUser(BaseUser):
    weight = 5
    token = MOCK_JWT_EMPLOYER
    persona = "employer"

    def on_start(self) -> None:
        org = fake_org_payload(LOCALE)
        self._post_json("/api/organisations", org, name="/api/organisations [create]")
        self.org_id = org.get("id") or DEMO_ORG_ID
        role = fake_role_payload(org_id=self.org_id, locale=LOCALE)
        self._post_json("/api/roles", role, name="/api/roles [create]")
        self.role_id = role.get("id") or DEMO_ROLE_ID

    @task(2)
    def submit_vision(self) -> None:
        self._post_json(
            "/api/vision/submit",
            fake_vision_payload(LOCALE),
            name="/api/vision/submit",
        )

    @task(2)
    def submit_brief(self) -> None:
        self._post_json(
            "/api/talent-brief",
            fake_brief_payload(role_id=self.role_id, locale=LOCALE),
            name="/api/talent-brief",
        )

    @task(2)
    def submit_jd(self) -> None:
        self._post_json(
            "/api/job-spec",
            fake_jd_payload(role_id=self.role_id, locale=LOCALE),
            name="/api/job-spec",
        )

    @task(2)
    def create_ticket(self) -> None:
        """T1703 主路径之一: 工单创建."""
        self._post_json(
            "/api/tickets",
            fake_ticket_payload(role_id=self.role_id, locale=LOCALE),
            name="/api/tickets [create]",
        )

    @task(2)
    def list_tickets(self) -> None:
        self._get("/api/tickets?limit=20", name="/api/tickets [list]")

    @task(1)
    def assign_ticket(self) -> None:
        """工单分派 (PATCH) — 真实路径."""
        self._patch_json(
            f"/api/tickets/{fake_user_id()}",
            {"assignee_id": fake_user_id(), "status": "in_progress"},
            name="/api/tickets [assign]",
        )

    @task(1)
    def list_roles(self) -> None:
        self._get("/api/roles?limit=20", name="/api/roles [list]")

    @task(1)
    def request_two_way_match(self) -> None:
        self._post_json(
            "/api/two-way-match/compute",
            fake_two_way_match_payload(),
            name="/api/two-way-match/compute [employer]",
        )

    @task(1)
    def send_clarification(self) -> None:
        """T1703 主路径之一: clarifications."""
        self._post_json(
            "/api/clarifications",
            {
                "role_id": self.role_id,
                "candidate_id": DEMO_CANDIDATE_ID,
                "question": fake_clarifier_text(LOCALE),
            },
            name="/api/clarifications [send]",
        )

    @task(1)
    def list_clarifications(self) -> None:
        self._get("/api/clarifications?limit=20", name="/api/clarifications [list]")

    @task(1)
    def create_collection(self) -> None:
        """T1703 主路径之一: collections (候选人列表)."""
        self._post_json(
            "/api/collections",
            {"name": f"col-{fake_short_code()}", "role_id": self.role_id},
            name="/api/collections [create]",
        )

    @task(1)
    def list_collections(self) -> None:
        self._get("/api/collections?limit=20", name="/api/collections [list]")

    @task(1)
    def list_subscriptions(self) -> None:
        self._get("/api/subscriptions?limit=20", name="/api/subscriptions [list]")


# ---------------------------------------------------------------------------
# Persona 3: Matching — 匹配业务 (weight 4)
# ---------------------------------------------------------------------------

class MatchingUser(BaseUser):
    weight = 4
    token = MOCK_JWT_EMPLOYER
    persona = "matching"

    @task(5)
    def request_two_way_match(self) -> None:
        self._post_json(
            "/api/two-way-match/compute",
            fake_two_way_match_payload(),
            name="/api/two-way-match/compute",
        )

    @task(2)
    def explain_match(self) -> None:
        """T1703 主路径之一: 匹配解释 (走 LLM, 最贵的端点)."""
        self._post_json(
            "/api/two-way-match/explain",
            fake_two_way_match_payload(),
            name="/api/two-way-match/explain",
        )

    @task(2)
    def list_candidate_matches(self) -> None:
        self._get(
            f"/api/two-way-match/for-candidate/{DEMO_CANDIDATE_ID}",
            name="/api/two-way-match/for-candidate",
        )

    @task(2)
    def list_role_matches(self) -> None:
        self._get(
            f"/api/two-way-match/for-role/{DEMO_ROLE_ID}",
            name="/api/two-way-match/for-role",
        )

    @task(1)
    def batch_match(self) -> None:
        self._post_json(
            "/api/two-way-match/batch",
            {
                "pairs": [
                    fake_two_way_match_payload(),
                    fake_two_way_match_payload(),
                    fake_two_way_match_payload(),
                ]
            },
            name="/api/two-way-match/batch",
        )

    @task(1)
    def feedback_loop(self) -> None:
        """T1703 — 反馈闭环: HR 评分 → 校正算法."""
        self._post_json(
            "/api/matches/feedback",
            {
                "candidate_id": DEMO_CANDIDATE_ID,
                "role_id": DEMO_ROLE_ID,
                "rating": random.randint(1, 5),
                "hired": random.random() < 0.2,
            },
            name="/api/matches/feedback",
        )


# ---------------------------------------------------------------------------
# Persona 4: Subscriptions — 主动推送 / 订阅 (weight 3)
# ---------------------------------------------------------------------------

class SubscriptionUser(BaseUser):
    weight = 3
    token = MOCK_JWT_JOBSEEKER
    persona = "subscriptions"

    def on_start(self) -> None:
        # 创建订阅作为基础
        self.sub_id = fake_user_id()

    @task(3)
    def create_subscription(self) -> None:
        self._post_json(
            "/api/subscriptions",
            {
                "kind": "job_match",
                "filters": {
                    "role_titles": ["Senior Backend Engineer", "Staff Engineer"],
                    "locations": ["Shanghai", "Remote"],
                    "min_salary": 30000,
                },
                "channel": random.choice(["email", "web_push", "feishu", "dingtalk"]),
            },
            name="/api/subscriptions [create]",
        )

    @task(2)
    def list_subscriptions(self) -> None:
        self._get("/api/subscriptions?limit=20", name="/api/subscriptions [list]")

    @task(2)
    def match_subscription(self) -> None:
        """主动匹配 — 触发推送链路."""
        self._post_json(
            f"/api/subscriptions/{self.sub_id}/match",
            {"dry_run": True},
            name="/api/subscriptions [match]",
        )

    @task(1)
    def delete_subscription(self) -> None:
        self._delete(
            f"/api/subscriptions/{self.sub_id}",
            name="/api/subscriptions [delete]",
        )


# ---------------------------------------------------------------------------
# Persona 5: Realtime / Collab — 协同房间 (weight 3)
# ---------------------------------------------------------------------------

class CollabRoomUser(BaseUser):
    weight = 3
    token = MOCK_JWT_EMPLOYER
    persona = "collab"

    def on_start(self) -> None:
        # 真实业务: 创建协同房间
        with self.client.post(
            "/api/rooms",
            json={"name": f"room-{fake_short_code()}", "members": [fake_user_id(), fake_user_id()]},
            headers=_common_headers(self.token, self.persona),
            name="/api/rooms [create]",
            catch_response=True,
        ) as resp:
            if resp.status_code >= 500:
                resp.failure(f"5xx {resp.status_code}")
            else:
                resp.success()
                try:
                    data = resp.json()
                    self.room_id = data.get("id") or fake_room_id()
                except Exception:
                    self.room_id = fake_room_id()
        if not hasattr(self, "room_id"):
            self.room_id = fake_room_id()

    @task(4)
    def publish_room_message(self) -> None:
        """协同房间发送消息 — 模拟 WebSocket 业务量."""
        self._post_json(
            f"/api/rooms/{self.room_id}/messages",
            fake_room_message(room_id=self.room_id, locale=LOCALE),
            name="/api/rooms/messages [publish]",
        )

    @task(2)
    def list_room_messages(self) -> None:
        self._get(
            f"/api/rooms/{self.room_id}/messages?limit=20",
            name="/api/rooms/messages [list]",
        )

    @task(1)
    def list_rooms(self) -> None:
        self._get("/api/rooms?limit=20", name="/api/rooms [list]")


# ---------------------------------------------------------------------------
# Persona 6: Video Interview — 视频面试 (weight 2)
# ---------------------------------------------------------------------------

class VideoInterviewUser(BaseUser):
    weight = 2
    token = MOCK_JWT_EMPLOYER
    persona = "video"

    @task(2)
    def create_video_interview(self) -> None:
        self._post_json(
            "/api/video-interviews",
            {
                "candidate_id": DEMO_CANDIDATE_ID,
                "role_id": DEMO_ROLE_ID,
                "scheduled_at": "2026-08-01T10:00:00Z",
                "provider": random.choice(["zoom", "tencent", "mock"]),
            },
            name="/api/video-interviews [create]",
        )

    @task(1)
    def list_video_interviews(self) -> None:
        self._get("/api/video-interviews?limit=20", name="/api/video-interviews [list]")


# ---------------------------------------------------------------------------
# Persona 7: Assessment / Background — 测评 + 背调 (weight 2)
# ---------------------------------------------------------------------------

class AssessmentUser(BaseUser):
    weight = 2
    token = MOCK_JWT_EMPLOYER
    persona = "assessment"

    @task(2)
    def invite_assessment(self) -> None:
        self._post_json(
            "/api/assessments/invite",
            {
                "candidate_id": DEMO_CANDIDATE_ID,
                "role_id": DEMO_ROLE_ID,
                "provider": random.choice(["beisen", "mock"]),
            },
            name="/api/assessments/invite",
        )

    @task(1)
    def list_assessments(self) -> None:
        self._get("/api/assessments?limit=20", name="/api/assessments [list]")

    @task(1)
    def start_background_check(self) -> None:
        self._post_json(
            "/api/background-check",
            {
                "candidate_id": DEMO_CANDIDATE_ID,
                "provider": random.choice(["checkr", "mock"]),
            },
            name="/api/background-check [start]",
        )


# ---------------------------------------------------------------------------
# Persona 8: Analytics — 漏斗 / 渠道归因 (weight 2)
# ---------------------------------------------------------------------------

class AnalyticsUser(BaseUser):
    weight = 2
    token = MOCK_JWT_EMPLOYER
    persona = "analytics"

    @task(3)
    def write_funnel_event(self) -> None:
        self._post_json(
            "/api/analytics/funnel-events",
            {
                "candidate_id": DEMO_CANDIDATE_ID,
                "role_id": DEMO_ROLE_ID,
                "event": random.choice(
                    ["sourced", "applied", "screened", "interviewed", "offered", "hired"]
                ),
                "channel": random.choice(["boss", "lagou", "referral", "linkedin", "feishu"]),
                "ts": int(time.time() * 1000),
            },
            name="/api/analytics/funnel-events",
        )

    @task(2)
    def get_funnel(self) -> None:
        self._get("/api/analytics/funnel?role_id=" + DEMO_ROLE_ID, name="/api/analytics/funnel")

    @task(1)
    def channel_attribution(self) -> None:
        self._get("/api/analytics/channel-attribution", name="/api/analytics/channel-attribution")


# ---------------------------------------------------------------------------
# Persona 9: Partner / Pilot — Pilot 合作方 (weight 1)
# ---------------------------------------------------------------------------

class PartnerUser(BaseUser):
    weight = 1
    token = MOCK_JWT_PARTNER
    persona = "partner"
    wait_time = between(2.0, 5.0)

    @task(3)
    def pilot_dashboard(self) -> None:
        self._get("/api/pilot/dashboard", name="/api/pilot/dashboard")

    @task(2)
    def pilot_nps(self) -> None:
        self._get("/api/pilot/nps", name="/api/pilot/nps")

    @task(1)
    def submit_pilot_feedback(self) -> None:
        self._post_json(
            "/api/pilot/feedback",
            {
                "rating": random.randint(1, 5),
                "comment": fake_resume_text(LOCALE),
            },
            name="/api/pilot/feedback",
        )


# ---------------------------------------------------------------------------
# Persona 10: Admin — 管理后台 (weight 1)
# ---------------------------------------------------------------------------

class AdminUser(BaseUser):
    weight = 1
    token = MOCK_JWT_ADMIN
    persona = "admin"
    wait_time = between(2.0, 5.0)

    @task(2)
    def emotion_alerts(self) -> None:
        self._get("/api/emotion/alerts", name="/api/emotion/alerts")

    @task(2)
    def audit_logs(self) -> None:
        self._get("/api/admin/audit?limit=50", name="/api/admin/audit")

    @task(1)
    def cost_overview(self) -> None:
        self._get("/api/admin/cost/overview", name="/api/admin/cost/overview")

    @task(1)
    def matching_quality(self) -> None:
        self._get("/api/admin/matching-quality", name="/api/admin/matching-quality")

    @task(1)
    def api_key_list(self) -> None:
        self._get("/api/admin/api-keys", name="/api/admin/api-keys")

    @task(1)
    def admin_notify(self) -> None:
        self._get("/api/admin/notify/templates", name="/api/admin/notify/templates")

    @task(1)
    def admin_ab(self) -> None:
        self._get("/api/admin/ab/experiments", name="/api/admin/ab/experiments")


# ---------------------------------------------------------------------------
# Persona 11: AnonymousHealthUser — health/metrics 探针 (weight 1)
# ---------------------------------------------------------------------------

class AnonymousHealthUser(HttpUser):
    weight = 1
    wait_time = between(0.1, 0.5)

    @task
    def health(self) -> None:
        self.client.get("/health", name="/health")

    @task
    def metrics(self) -> None:
        self.client.get("/metrics", name="/metrics")

    @task
    def readiness(self) -> None:
        self.client.get("/ready", name="/ready")


# ---------------------------------------------------------------------------
# Persona 12: AI Interview — 自动面试 (weight 1)
# ---------------------------------------------------------------------------

class AIInterviewUser(BaseUser):
    weight = 1
    token = MOCK_JWT_JOBSEEKER
    persona = "ai_interview"

    @task(3)
    def start_session(self) -> None:
        self._post_json(
            "/api/ai-interview/sessions",
            {"role_id": DEMO_ROLE_ID},
            name="/api/ai-interview/sessions [create]",
        )

    @task(2)
    def list_sessions(self) -> None:
        self._get("/api/ai-interview/sessions?limit=20", name="/api/ai-interview/sessions [list]")

    @task(1)
    def submit_answer(self) -> None:
        self._post_json(
            f"/api/ai-interview/sessions/{fake_user_id()}/answer",
            {"question_id": fake_user_id(), "answer": fake_resume_text(LOCALE)},
            name="/api/ai-interview/answer",
        )


# ---------------------------------------------------------------------------
# Locust 事件钩子: 报告扩展 / 启动日志 / SLA 校验
# ---------------------------------------------------------------------------

@events.test_start.add_listener
def _on_test_start(environment, **kwargs) -> None:  # pragma: no cover
    logger.info(
        "v5 Load test starting | users=%s spawn_rate=%s host=%s p95_sla=%dms err_sla=%.3f",
        environment.runner.user_count if environment.runner else "?",
        environment.runner.spawn_rate if environment.runner else "?",
        environment.host,
        SLA_P95_MS,
        SLA_ERROR_RATE,
    )


@events.test_stop.add_listener
def _on_test_stop(environment, **kwargs) -> None:  # pragma: no cover
    stats = environment.stats
    total = stats.total
    print("\n=== Waibao v5 Load Test Summary ===")
    print(f"  Total requests : {total.num_requests}")
    print(f"  Failures       : {total.num_failures}")
    print(f"  Median (p50)   : {total.median_response_time} ms")
    print(f"  p95            : {total.get_response_time_percentile(0.95)} ms")
    print(f"  p99            : {total.get_response_time_percentile(0.99)} ms")
    print(f"  RPS            : {total.total_rps:.2f}")
    print(f"  Max response   : {total.max_response_time} ms")

    p95 = total.get_response_time_percentile(0.95)
    err = total.num_failures / max(total.num_requests, 1)
    print()
    print(f"  SLA P95 < {SLA_P95_MS}ms      : {'PASS' if p95 < SLA_P95_MS else 'FAIL'} ({p95}ms)")
    print(f"  SLA err < {SLA_ERROR_RATE*100:.2f}% : {'PASS' if err < SLA_ERROR_RATE else 'FAIL'} ({err*100:.3f}%)")

    # 写入额外报告 metrics 给 docs/PERFORMANCE_v5.md 模板填充
    try:
        report_path = Path(os.getenv("LOAD_REPORT_OUT", "reports/locust_v5_summary.txt"))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            (
                f"users={environment.runner.user_count}\n"
                f"total_requests={total.num_requests}\n"
                f"failures={total.num_failures}\n"
                f"p50={total.median_response_time}\n"
                f"p95={p95}\n"
                f"p99={total.get_response_time_percentile(0.99)}\n"
                f"max={total.max_response_time}\n"
                f"rps={total.total_rps}\n"
                f"error_rate={err}\n"
            ),
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("write summary report failed: %s", exc)
