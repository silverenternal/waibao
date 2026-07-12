"""Tests for probation service (T2404)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest

from services.employer.probation_service import (
    DIMENSIONS,
    ProbationService,
    ProbationStatus,
    TaskType,
    get_probation_service,
)


@pytest.fixture
def svc():
    return get_probation_service()


# ---------------------------------------------------------------------------
# 1. on-boarding 自动任务
# ---------------------------------------------------------------------------

class TestOnboarding:
    def test_creates_five_tasks(self, svc):
        hire = datetime(2026, 6, 1, tzinfo=timezone.utc)
        tasks = svc.create_onboarding_tasks("emp-1", "org-A", hire)
        assert len(tasks) == 5

    def test_task_types_cover_all_stages(self, svc):
        hire = datetime(2026, 6, 1, tzinfo=timezone.utc)
        tasks = svc.create_onboarding_tasks("emp-1", "org-A", hire)
        types = {t["type"] for t in tasks}
        assert TaskType.ORIENTATION.value in types
        assert TaskType.REVIEW_30.value in types
        assert TaskType.REVIEW_90.value in types
        assert TaskType.REVIEW_180.value in types

    def test_due_dates_correct(self, svc):
        hire = datetime(2026, 6, 1, tzinfo=timezone.utc)
        tasks = svc.create_onboarding_tasks("emp-1", "org-A", hire)
        by_type = {t["type"]: t for t in tasks}
        assert by_type["orientation"]["due_at"].startswith("2026-06-01")
        assert by_type["review_30"]["due_at"].startswith("2026-07-01")
        assert by_type["review_90"]["due_at"].startswith("2026-08-30")
        assert by_type["review_180"]["due_at"].startswith("2026-11-28")

    def test_org_id_propagates(self, svc):
        hire = datetime(2026, 6, 1, tzinfo=timezone.utc)
        tasks = svc.create_onboarding_tasks("emp-1", "org-XYZ", hire)
        assert all(t["org_id"] == "org-XYZ" for t in tasks)


# ---------------------------------------------------------------------------
# 2. 评估提交
# ---------------------------------------------------------------------------

class TestReview:
    def test_submit_pass(self, svc):
        review = svc.submit_review(
            employee_id="emp-1",
            manager_id="mgr-1",
            org_id="org-A",
            review_stage="90",
            scores={
                "performance": 4,
                "learning": 5,
                "integration": 4,
                "attitude": 5,
                "potential": 4,
            },
            comments="表现优秀",
        )
        assert review["status"] == ProbationStatus.PASSED.value
        assert review["review_stage"] == "90"
        avg = sum(review["scores"].values()) / 5
        assert avg == pytest.approx(4.4)

    def test_submit_fail(self, svc):
        review = svc.submit_review(
            employee_id="emp-2",
            manager_id="mgr-1",
            org_id="org-A",
            review_stage="90",
            scores={
                "performance": 2,
                "learning": 2,
                "integration": 2,
                "attitude": 2,
                "potential": 2,
            },
            comments="需要改进",
        )
        assert review["status"] == ProbationStatus.FAILED.value

    def test_missing_dimension_raises(self, svc):
        with pytest.raises(ValueError, match="missing dimensions"):
            svc.submit_review(
                employee_id="emp-3",
                manager_id="mgr-1",
                org_id="org-A",
                review_stage="30",
                scores={"performance": 3, "learning": 3},
            )

    def test_out_of_range_raises(self, svc):
        with pytest.raises(ValueError, match="out of range"):
            svc.submit_review(
                employee_id="emp-3",
                manager_id="mgr-1",
                org_id="org-A",
                review_stage="30",
                scores={
                    "performance": 6,  # out of range
                    "learning": 3,
                    "integration": 3,
                    "attitude": 3,
                    "potential": 3,
                },
            )

    def test_average_score(self, svc):
        review = svc.submit_review(
            employee_id="emp-x",
            manager_id="mgr-1",
            org_id="org-A",
            review_stage="30",
            scores={
                "performance": 5,
                "learning": 5,
                "integration": 5,
                "attitude": 5,
                "potential": 5,
            },
        )
        # every dim 5 → avg 5
        assert review["status"] == ProbationStatus.PASSED.value


# ---------------------------------------------------------------------------
# 3. 提醒
# ---------------------------------------------------------------------------

class TestReminder:
    def test_needs_reminder_within_3_days(self, svc):
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        tasks = [
            {
                "id": "t1",
                "type": "review_30",
                "due_at": (now + timedelta(days=2)).isoformat(),
            },
            {
                "id": "t2",
                "type": "review_90",
                "due_at": (now + timedelta(days=10)).isoformat(),
            },
        ]
        result = svc.tasks_needing_reminder(tasks, lead_days=3, now=now)
        assert len(result) == 1
        assert result[0]["id"] == "t1"

    def test_already_reminded_excluded(self, svc):
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        tasks = [
            {
                "id": "t1",
                "due_at": (now + timedelta(days=1)).isoformat(),
                "reminded_at": now.isoformat(),
            }
        ]
        result = svc.tasks_needing_reminder(tasks, lead_days=3, now=now)
        assert result == []

    def test_completed_excluded(self, svc):
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        tasks = [
            {
                "id": "t1",
                "due_at": (now + timedelta(days=1)).isoformat(),
                "completed_at": now.isoformat(),
            }
        ]
        result = svc.tasks_needing_reminder(tasks, lead_days=3, now=now)
        assert result == []


# ---------------------------------------------------------------------------
# 4. 转正 / 延期
# ---------------------------------------------------------------------------

class TestCompletion:
    def test_complete(self, svc):
        result = svc.complete_probation("review-1", "转正通过")
        assert result["status"] == "passed"
        assert result["confirmation_notes"] == "转正通过"
        assert "confirmed_at" in result

    def test_extend_valid(self, svc):
        result = svc.extend_probation("review-1", 30, "再观察一个月")
        assert result["extension_days"] == 30
        assert result["status"] == "extended"

    def test_extend_too_long_raises(self, svc):
        with pytest.raises(ValueError, match="1-90"):
            svc.extend_probation("review-1", 200, "test")

    def test_extend_zero_raises(self, svc):
        with pytest.raises(ValueError):
            svc.extend_probation("review-1", 0, "test")


# ---------------------------------------------------------------------------
# 5. 团队视图
# ---------------------------------------------------------------------------

class TestSummary:
    def test_summarize_employee(self, svc):
        reviews = [
            {
                "id": "r1",
                "review_stage": "30",
                "review_date": "2026-05-01",
                "scores": {
                    "performance": 4, "learning": 4, "integration": 4, "attitude": 4, "potential": 4
                },
                "status": "passed",
            }
        ]
        tasks = [
            {"id": "t1", "due_at": "2099-01-01T00:00:00+00:00"},
            {"id": "t2", "due_at": "2026-01-01T00:00:00+00:00", "completed_at": "2026-01-01T10:00:00+00:00"},
        ]
        s = svc.summarize_employee("emp-1", reviews, tasks)
        assert s["employee_id"] == "emp-1"
        assert s["latest_review"]["id"] == "r1"
        assert s["task_summary"]["total"] == 2
        assert s["task_summary"]["completed"] == 1
        assert s["is_confirmed"] is False

    def test_summarize_team_stats(self, svc):
        emps = [
            {"id": "e1", "tags": ["on_track"]},
            {"id": "e2", "tags": ["on_track"]},
            {"id": "e3", "tags": ["pending_review"]},
            {"id": "e4", "tags": ["at_risk"]},
            {"id": "e5", "tags": ["confirmed"]},
        ]
        s = svc.summarize_team("org-A", emps)
        assert s["stats"]["total"] == 5
        assert s["stats"]["on_track"] == 2
        assert s["stats"]["pending_review"] == 1
        assert s["stats"]["at_risk"] == 1
        assert s["stats"]["confirmed"] == 1


# ---------------------------------------------------------------------------
# 6. Scheduler
# ---------------------------------------------------------------------------

class TestScheduler:
    def test_daily_check(self):
        from services.employer.probation_scheduler import daily_check_tasks
        now = datetime.now(timezone.utc)
        tasks = [
            {"id": "t1", "due_at": now.isoformat()},
            {"id": "t2", "due_at": (now + timedelta(days=10)).isoformat()},
        ]
        result = daily_check_tasks(tasks)
        assert "checked_at" in result
        assert "due_today" in result
        assert "needs_reminder" in result

    def test_weekly_summary(self):
        from services.employer.probation_scheduler import weekly_summary
        reviews = [
            {"id": "r1", "status": "passed"},
            {"id": "r2", "status": "passed"},
            {"id": "r3", "status": "failed"},
            {"id": "r4", "status": "pending"},
        ]
        tasks = [
            {"id": "t1"},
            {"id": "t2", "completed_at": "2026-06-01"},
        ]
        s = weekly_summary(reviews, tasks)
        assert s["passed"] == 2
        assert s["failed"] == 1
        assert s["pending_reviews"] == 1
        assert s["pass_rate"] == pytest.approx(2 / 3, abs=1e-3)

    def test_stale_review_detection(self):
        from services.employer.probation_scheduler import auto_complete_check
        reviews = [
            {"id": "r1", "status": "pending", "review_date": "2020-01-01"},
            {"id": "r2", "status": "pending", "review_date": "2026-06-01"},
        ]
        stale = auto_complete_check(reviews)
        assert "r1" in stale
        assert "r2" not in stale
