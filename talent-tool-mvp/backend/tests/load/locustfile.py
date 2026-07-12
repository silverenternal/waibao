"""Locust 压测主入口 (T1104).

覆盖 10+ 任务场景:
  - JobseekerUser: 注册 → 上传简历 → 写日记 → 触发 emotion → 触发 clarifier
  - EmployerUser: 创建 org → 创建 role → 提交 vision → 提交 brief → 提交 JD → 创建工单
  - MatchingUser: 请求双向匹配
  - AdminUser: 查看告警 / 审计
  - AnonymousHealthUser: 健康检查压测

默认通过 ``-u`` / ``-r`` 控制并发;支持 100 / 500 / 1000 三档,详见 run_locust.sh。

Usage:
    locust -f locustfile.py --host http://localhost:8000 \\
        -u 1000 -r 50 --run-time 5m --headless \\
        --html reports/locust_report.html --csv reports/locust_report
"""
from __future__ import annotations

import logging
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

from locust import HttpUser, between, events, task

# Allow `python locustfile.py` from any cwd
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from scenarios import (  # noqa: E402  (import after path tweak)
    DEMO_CANDIDATE_ID,
    DEMO_ROLE_ID,
    fake_brief_payload,
    fake_clarifier_text,
    fake_emotion_text,
    fake_jd_payload,
    fake_journal_payload,
    fake_org_payload,
    fake_resume_upload_payload,
    fake_role_payload,
    fake_room_message,
    fake_short_code,
    fake_ticket_payload,
    fake_two_way_match_payload,
    fake_user_id,
    fake_user_payload,
    fake_vision_payload,
)

logger = logging.getLogger("recruittech.load")


# ---------------------------------------------------------------------------
# 通用头: 加载测试 fake JWT, 真实环境请改用真实登录.
# ---------------------------------------------------------------------------

MOCK_JWT_JOBSEEKER = os.getenv("LOAD_JWT_JOBSEEKER", "mock-jwt-jobseeker")
MOCK_JWT_EMPLOYER = os.getenv("LOAD_JWT_EMPLOYER", "mock-jwt-employer")
MOCK_JWT_ADMIN = os.getenv("LOAD_JWT_ADMIN", "mock-jwt-admin")
LOCALE = os.getenv("LOAD_LOCALE", random.choice(["zh", "en"]))


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# 基类: 共享超时/异常处理
# ---------------------------------------------------------------------------

class BaseUser(HttpUser):
    abstract = True
    wait_time = between(0.2, 1.5)
    timeout = 30.0

    def _post_json(self, path: str, payload: dict[str, Any], name: str | None = None) -> None:
        with self.client.post(
            path,
            json=payload,
            headers=_auth_headers(self.token),
            name=name or path,
            catch_response=True,
        ) as resp:
            if resp.status_code >= 500:
                resp.failure(f"5xx {resp.status_code}: {resp.text[:200]}")
            elif resp.status_code >= 400:
                # 4xx 在负载测试里允许(校验错误);只标记非预期码
                if resp.status_code in (401, 403):
                    resp.failure(f"auth {resp.status_code}: {resp.text[:200]}")
                else:
                    resp.success()  # client errors expected for some scenarios

    def _get(self, path: str, name: str | None = None) -> None:
        with self.client.get(
            path,
            headers=_auth_headers(self.token),
            name=name or path,
            catch_response=True,
        ) as resp:
            if resp.status_code >= 500:
                resp.failure(f"5xx {resp.status_code}")
            elif resp.status_code in (401, 403):
                resp.failure(f"auth {resp.status_code}")
            else:
                resp.success()


# ---------------------------------------------------------------------------
# 1) Jobseeker — weight 5
# ---------------------------------------------------------------------------

class JobseekerUser(BaseUser):
    weight = 5
    token = MOCK_JWT_JOBSEEKER
    persona_id = DEMO_CANDIDATE_ID

    def on_start(self) -> None:
        # 注册 (幂等: 重名时 4xx 但不应 5xx)
        self._post_json(
            "/api/auth/register",
            fake_user_payload(role="jobseeker", locale=LOCALE),
            name="/api/auth/register [jobseeker]",
        )

    @task(4)
    def invoke_agent(self) -> None:
        """主路径: 召唤 agent (高频)."""
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
        """上传简历元数据."""
        self._post_json(
            "/api/uploads/resume",
            fake_resume_upload_payload(LOCALE),
            name="/api/uploads/resume",
        )

    @task(2)
    def submit_journal(self) -> None:
        """写日记."""
        self._post_json(
            "/api/journal",
            fake_journal_payload(LOCALE),
            name="/api/journal",
        )

    @task(1)
    def trigger_emotion(self) -> None:
        """触发 emotion 显式 agent."""
        self._post_json(
            "/api/emotion/analyze",
            {"text": fake_emotion_text(LOCALE)},
            name="/api/emotion/analyze",
        )

    @task(1)
    def trigger_clarifier(self) -> None:
        """触发 clarifier 整合画像."""
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


# ---------------------------------------------------------------------------
# 2) Employer — weight 3
# ---------------------------------------------------------------------------

class EmployerUser(BaseUser):
    weight = 3
    token = MOCK_JWT_EMPLOYER
    org_id = DEMO_ROLE_ID  # reuse demo id slot — only used as fake uuid

    def on_start(self) -> None:
        # 1) 创建 org
        org = fake_org_payload(LOCALE)
        self._post_json("/api/organisations", org, name="/api/organisations [create]")
        self.org_id = org.get("id") or self.org_id

        # 2) 创建 role
        role = fake_role_payload(org_id=self.org_id, locale=LOCALE)
        self._post_json("/api/roles", role, name="/api/roles [create]")
        self.role_id = role.get("id") or DEMO_ROLE_ID

    @task(2)
    def submit_vision(self) -> None:
        """提交公司愿景."""
        self._post_json(
            "/api/vision/submit",
            fake_vision_payload(LOCALE),
            name="/api/vision/submit",
        )

    @task(2)
    def submit_brief(self) -> None:
        """提交 talent brief."""
        self._post_json(
            "/api/talent-brief",
            fake_brief_payload(role_id=self.role_id, locale=LOCALE),
            name="/api/talent-brief",
        )

    @task(2)
    def submit_jd(self) -> None:
        """生成 JD."""
        self._post_json(
            "/api/job-spec",
            fake_jd_payload(role_id=self.role_id, locale=LOCALE),
            name="/api/job-spec",
        )

    @task(1)
    def create_ticket(self) -> None:
        """创建工单."""
        self._post_json(
            "/api/tickets",
            fake_ticket_payload(role_id=self.role_id, locale=LOCALE),
            name="/api/tickets",
        )

    @task(1)
    def list_roles(self) -> None:
        self._get("/api/roles?limit=20", name="/api/roles [list]")


# ---------------------------------------------------------------------------
# 3) Matching — weight 2
# ---------------------------------------------------------------------------

class MatchingUser(BaseUser):
    weight = 2
    token = MOCK_JWT_JOBSEEKER

    @task(4)
    def request_two_way_match(self) -> None:
        """请求双向匹配."""
        self._post_json(
            "/api/two-way-match/compute",
            fake_two_way_match_payload(),
            name="/api/two-way-match/compute",
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
        """批量匹配."""
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


# ---------------------------------------------------------------------------
# 4) Admin — weight 1
# ---------------------------------------------------------------------------

class AdminUser(BaseUser):
    weight = 1
    token = MOCK_JWT_ADMIN
    wait_time = between(2.0, 5.0)

    @task(3)
    def emotion_alerts(self) -> None:
        self._get("/api/emotion/alerts", name="/api/emotion/alerts")

    @task(2)
    def audit_logs(self) -> None:
        self._get("/api/admin/audit?limit=50", name="/api/admin/audit")

    @task(1)
    def cost_overview(self) -> None:
        self._get("/api/admin/cost/overview", name="/api/admin/cost/overview")


# ---------------------------------------------------------------------------
# 5) Anonymous — health check, weight 1
# ---------------------------------------------------------------------------

class AnonymousHealthUser(HttpUser):
    weight = 1
    wait_time = between(0.1, 0.5)

    @task
    def health(self) -> None:
        self.client.get("/health", name="/health")

    @task
    def metrics(self) -> None:
        # Prometheus scrape endpoint — 不期望 401
        self.client.get("/metrics", name="/metrics")


# ---------------------------------------------------------------------------
# Locust 事件钩子: 报告扩展 / 启动日志
# ---------------------------------------------------------------------------

@events.test_start.add_listener
def _on_test_start(environment, **kwargs) -> None:  # pragma: no cover
    logger.info(
        "Load test starting | users=%s spawn_rate=%s host=%s",
        environment.runner.user_count if environment.runner else "?",
        environment.runner.spawn_rate if environment.runner else "?",
        environment.host,
    )


@events.test_stop.add_listener
def _on_test_stop(environment, **kwargs) -> None:  # pragma: no cover
    stats = environment.stats
    total = stats.total
    logger.info(
        "Load test done | requests=%s failures=%(num_failures)s "
        "p50=%(median_response_time)sms p95=%(p95_response_time)sms "
        "p99=%(p99_response_time)sms rps=%(total_rps)s",
        total.num_requests,
        extra={},
    ) if False else None  # avoid formatting confusion

    print("\n=== Load Test Summary ===")
    print(f"  Total requests : {total.num_requests}")
    print(f"  Failures       : {total.num_failures}")
    print(f"  Median (p50)   : {total.median_response_time} ms")
    print(f"  p95            : {total.get_response_time_percentile(0.95)} ms")
    print(f"  p99            : {total.get_response_time_percentile(0.99)} ms")
    print(f"  RPS            : {total.total_rps:.2f}")
    print(f"  Max response   : {total.max_response_time} ms")