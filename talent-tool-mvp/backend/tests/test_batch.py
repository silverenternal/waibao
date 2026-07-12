"""T2302 — 批量操作服务测试.

覆盖:
- 6 种 batch action
- 进度跟踪
- 失败重试
- 取消任务
- 100 个候选人批量 < 30s
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.platform.batch_processor import (  # noqa: E402
    BatchAction,
    BatchProcessor,
    BatchProgress,
    NEXT_STAGE_MAP,
    ProgressStore,
    TaskStatus,
    handle_bulk_archive,
    handle_bulk_email,
    handle_bulk_move_stage,
    handle_bulk_offer,
    handle_bulk_tag,
    handle_bulk_update,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mock_supabase(table_data: dict[str, list[dict]] | None = None):
    """构建 mock supabase,表 mock 通过 .table_name_attr 访问."""
    supabase = MagicMock()
    tables: dict[str, MagicMock] = {}
    data_map = table_data or {}

    def table(name):
        if name not in tables:
            t = MagicMock()
            rows = data_map.get(name, [])

            # 链式方法 — 默认返回 self
            for method in ("select", "eq", "in_", "order", "range",
                           "insert", "update", "delete", "gte", "lte", "neq"):
                getattr(t, method).return_value = t

            # .single().execute() 返回第一行 (dict)
            single_t = MagicMock()

            def single_execute():
                r = MagicMock()
                r.data = rows[0] if rows else None
                r.count = 1 if rows else 0
                return r

            single_t.execute = single_execute
            t.single.return_value = single_t

            # .execute() 默认返回 list 结果
            def execute():
                r = MagicMock()
                r.data = rows
                r.count = len(rows)
                return r

            t.execute = execute
            tables[name] = t
        return tables[name]

    supabase.table.side_effect = table
    supabase.tables = tables
    return supabase


@pytest.fixture
def mock_supabase():
    return _mock_supabase({"candidates": [{"id": "c1", "tags": ["existing"]}]})


@pytest.fixture
def processor(mock_supabase):
    return BatchProcessor(mock_supabase, max_concurrency=5, max_retries=2)


# ---------------------------------------------------------------------------
# 1. BatchProgress
# ---------------------------------------------------------------------------


def test_progress_percent():
    p = BatchProgress(task_id="t1", action="bulk_email", total=10, processed=3)
    assert p.percent == 30.0


def test_progress_percent_zero_total():
    p = BatchProgress(task_id="t1", action="x", total=0)
    assert p.percent == 100.0


def test_progress_to_dict():
    p = BatchProgress(task_id="t1", action="bulk_email", total=5)
    p.succeeded = 3
    p.failed = 1
    p.processed = 4
    d = p.to_dict()
    assert d["percent"] == 80.0
    assert d["status"] == TaskStatus.PENDING.value


# ---------------------------------------------------------------------------
# 2. ProgressStore
# ---------------------------------------------------------------------------


def test_store_save_and_get():
    store = ProgressStore()
    p = BatchProgress(task_id="t1", action="x", total=10)
    store.save(p)
    got = store.get("t1")
    assert got is not None
    assert got.task_id == "t1"
    assert got.total == 10


def test_store_get_missing_returns_none():
    store = ProgressStore()
    assert store.get("missing") is None


def test_store_cancel_running_task():
    store = ProgressStore()
    p = BatchProgress(task_id="t1", action="x", total=10)
    p.status = TaskStatus.RUNNING
    store.save(p)
    assert store.cancel("t1")
    got = store.get("t1")
    assert got.status == TaskStatus.CANCELLED


def test_store_cancel_completed_returns_false():
    store = ProgressStore()
    p = BatchProgress(task_id="t1", action="x", total=10)
    p.status = TaskStatus.COMPLETED
    store.save(p)
    assert not store.cancel("t1")


def test_store_with_redis():
    """带 redis backend (mock) 时也能正常保存."""
    fake_redis = MagicMock()
    fake_redis.setex = MagicMock()
    store = ProgressStore(redis_client=fake_redis)
    p = BatchProgress(task_id="t1", action="x", total=10)
    store.save(p)
    fake_redis.setex.assert_called_once()
    # Get falls through to memory first
    assert store.get("t1").task_id == "t1"


# ---------------------------------------------------------------------------
# 3. 单个处理器
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_bulk_update():
    sb = _mock_supabase()
    await handle_bulk_update("c1", {"stage": "interviewed"}, sb)
    sb.table.assert_called_with("candidates")


@pytest.mark.asyncio
async def test_handle_bulk_update_skips_candidate_ids():
    sb = _mock_supabase()
    # payload 含 candidate_ids 时应跳过
    await handle_bulk_update("c1", {"candidate_ids": ["x"], "stage": "y"}, sb)
    sb.table.assert_called_with("candidates")


@pytest.mark.asyncio
async def test_handle_bulk_email():
    sb = _mock_supabase()
    await handle_bulk_email("c1", {"template": "intro", "subject": "Hi"}, sb)
    sb.table.assert_called_with("signals")


@pytest.mark.asyncio
async def test_handle_bulk_offer():
    sb = _mock_supabase()
    await handle_bulk_offer("c1", {"role_id": "r1", "salary": 100000, "currency": "USD"}, sb)
    sb.table.assert_called_with("offers")


@pytest.mark.asyncio
async def test_handle_bulk_move_stage():
    sb = _mock_supabase({"candidates": [{"id": "c1", "stage": "sourced"}]})
    await handle_bulk_move_stage("c1", {}, sb)
    # 应 update stage=screened
    upd = sb.tables["candidates"].update
    upd.assert_called_with({"stage": "screened"})


@pytest.mark.asyncio
async def test_handle_bulk_move_stage_no_mapping_uses_payload():
    sb = _mock_supabase({"candidates": [{"id": "c1", "stage": "unknown"}]})
    await handle_bulk_move_stage("c1", {"target_stage": "manual"}, sb)
    sb.tables["candidates"].update.assert_called_with({"stage": "manual"})


@pytest.mark.asyncio
async def test_handle_bulk_tag_merges():
    sb = _mock_supabase({"candidates": [{"id": "c1", "tags": ["a", "b"]}]})
    await handle_bulk_tag("c1", {"tags": ["c", "b"]}, sb)
    call_args = sb.tables["candidates"].update.call_args[0][0]
    assert set(call_args["tags"]) == {"a", "b", "c"}
    assert len(call_args["tags"]) == 3


@pytest.mark.asyncio
async def test_handle_bulk_tag_empty():
    sb = _mock_supabase()
    await handle_bulk_tag("c1", {"tags": []}, sb)
    # 不应调用 update (handler 提前 return)
    # 因为 candidates 表未创建,直接检查 table 没被调用
    sb.table.assert_not_called()


@pytest.mark.asyncio
async def test_handle_bulk_archive():
    sb = _mock_supabase()
    await handle_bulk_archive("c1", {}, sb)
    sb.tables["candidates"].update.assert_called()
    call_args = sb.tables["candidates"].update.call_args[0][0]
    assert "archived_at" in call_args


# ---------------------------------------------------------------------------
# 4. BatchProcessor.run 基础
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_unknown_action_returns_failed():
    sb = _mock_supabase()
    p = BatchProcessor(sb)
    result = await p.run(
        action="unknown",
        candidate_ids=["c1"],
        payload={},
    )
    assert result.status == TaskStatus.FAILED
    assert result.errors[0]["id"] == "_global"


@pytest.mark.asyncio
async def test_run_bulk_email_succeeds():
    sb = _mock_supabase()
    p = BatchProcessor(sb, max_concurrency=5)
    result = await p.run(
        action=BatchAction.BULK_EMAIL.value,
        candidate_ids=["c1", "c2", "c3"],
        payload={"template": "intro"},
    )
    assert result.status == TaskStatus.COMPLETED
    assert result.total == 3
    assert result.succeeded == 3
    assert result.failed == 0


@pytest.mark.asyncio
async def test_run_bulk_update_with_payload():
    sb = _mock_supabase()
    p = BatchProcessor(sb)
    result = await p.run(
        action=BatchAction.BULK_UPDATE.value,
        candidate_ids=["c1", "c2"],
        payload={"stage": "screened"},
    )
    assert result.status == TaskStatus.COMPLETED
    assert result.succeeded == 2


@pytest.mark.asyncio
async def test_run_bulk_tag():
    sb = _mock_supabase({
        "candidates": [
            {"id": "c1", "tags": ["a"]},
            {"id": "c2", "tags": []},
        ]
    })
    p = BatchProcessor(sb)
    result = await p.run(
        action=BatchAction.BULK_TAG.value,
        candidate_ids=["c1", "c2"],
        payload={"tags": ["vip"]},
    )
    assert result.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_run_progress_persisted():
    sb = _mock_supabase()
    p = BatchProcessor(sb)
    result = await p.run(
        action=BatchAction.BULK_EMAIL.value,
        candidate_ids=["c1", "c2"],
        payload={},
        task_id="custom-task-1",
    )
    # 应能从 store 取回
    got = p.get_progress("custom-task-1")
    assert got is not None
    assert got.succeeded == 2


# ---------------------------------------------------------------------------
# 5. 进度跟踪
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_progress_updates_during_run():
    sb = _mock_supabase()
    p = BatchProcessor(sb, max_concurrency=2)
    snapshots = []

    # monkey-patch save to capture snapshots
    original_save = p.store.save

    def capture_save(prog):
        snapshots.append((prog.processed, prog.succeeded))
        original_save(prog)

    p.store.save = capture_save
    await p.run(
        action=BatchAction.BULK_EMAIL.value,
        candidate_ids=["c1", "c2", "c3"],
        payload={},
    )
    # 至少 3 次 save (每项 + 1 收尾)
    assert len(snapshots) >= 3
    # 最后应为 (3, 3)
    final_processed, final_succeeded = snapshots[-1]
    assert final_processed == 3
    assert final_succeeded == 3


# ---------------------------------------------------------------------------
# 6. 失败重试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_on_failure_then_success():
    """第一次失败,第二次成功."""
    call_count = [0]

    async def flaky_handler(cid, payload, sb):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("transient")

    sb = _mock_supabase()
    p = BatchProcessor(sb, max_retries=2, retry_base_delay=0.01)
    # 替换 handler
    from services.platform.batch_processor import HANDLERS
    HANDLERS["bulk_email"] = flaky_handler

    result = await p.run(
        action="bulk_email",
        candidate_ids=["c1"],
        payload={},
    )
    assert result.succeeded == 1
    assert call_count[0] == 2
    HANDLERS["bulk_email"] = handle_bulk_email  # 恢复


@pytest.mark.asyncio
async def test_retry_exhausted_marks_failed():
    async def always_fail(cid, payload, sb):
        raise RuntimeError("permanent")

    sb = _mock_supabase()
    p = BatchProcessor(sb, max_retries=2, retry_base_delay=0.01)
    from services.platform.batch_processor import HANDLERS
    HANDLERS["bulk_email"] = always_fail

    result = await p.run(
        action="bulk_email",
        candidate_ids=["c1", "c2"],
        payload={},
    )
    assert result.failed == 2
    assert result.status in (TaskStatus.FAILED, TaskStatus.PARTIAL)
    assert len(result.errors) == 2
    HANDLERS["bulk_email"] = handle_bulk_email


@pytest.mark.asyncio
async def test_partial_success_status():
    """部分成功 → status=partial."""
    async def fail_for_c2(cid, payload, sb):
        if cid == "c2":
            raise RuntimeError("c2 always fails")

    sb = _mock_supabase()
    p = BatchProcessor(sb, max_retries=0)
    from services.platform.batch_processor import HANDLERS
    HANDLERS["bulk_email"] = fail_for_c2

    result = await p.run(
        action="bulk_email",
        candidate_ids=["c1", "c2", "c3"],
        payload={},
    )
    assert result.succeeded == 2
    assert result.failed == 1
    assert result.status == TaskStatus.PARTIAL
    HANDLERS["bulk_email"] = handle_bulk_email


# ---------------------------------------------------------------------------
# 7. 取消
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_running_task():
    sb = _mock_supabase()
    p = BatchProcessor(sb, max_concurrency=1)

    # 用一个慢 handler 来保证可取消
    async def slow_handler(cid, payload, sb):
        await asyncio.sleep(0.1)

    from services.platform.batch_processor import HANDLERS
    HANDLERS["bulk_email"] = slow_handler

    # 启动后台运行
    task = asyncio.create_task(
        p.run(
            action="bulk_email",
            candidate_ids=["c1", "c2", "c3", "c4"],
            payload={},
            task_id="cancel-test",
        )
    )
    await asyncio.sleep(0.02)
    # 取消
    assert p.cancel("cancel-test")
    await task

    result = p.get_progress("cancel-test")
    assert result is not None
    assert result.status == TaskStatus.CANCELLED
    HANDLERS["bulk_email"] = handle_bulk_email


def test_cancel_unknown_task_returns_false():
    sb = _mock_supabase()
    p = BatchProcessor(sb)
    assert not p.cancel("nonexistent")


# ---------------------------------------------------------------------------
# 8. 性能测试 — 100 个候选人 < 30s
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_100_candidates_under_30s():
    sb = _mock_supabase()
    p = BatchProcessor(sb, max_concurrency=20, max_retries=1)

    cids = [f"c{i}" for i in range(100)]
    start = time.time()
    result = await p.run(
        action=BatchAction.BULK_EMAIL.value,
        candidate_ids=cids,
        payload={"template": "intro"},
    )
    elapsed = time.time() - start
    assert result.status == TaskStatus.COMPLETED
    assert result.succeeded == 100
    assert elapsed < 30, f"耗时 {elapsed:.2f}s 超过 30s 限制"


@pytest.mark.asyncio
async def test_concurrency_limit_respected():
    """semaphore 限制并发数."""
    sb = _mock_supabase()
    p = BatchProcessor(sb, max_concurrency=3, max_retries=0)
    active = 0
    max_active = 0

    async def tracking_handler(cid, payload, sb):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        active -= 1

    from services.platform.batch_processor import HANDLERS
    HANDLERS["bulk_email"] = tracking_handler

    await p.run(
        action="bulk_email",
        candidate_ids=[f"c{i}" for i in range(20)],
        payload={},
    )
    assert max_active <= 3
    HANDLERS["bulk_email"] = handle_bulk_email


# ---------------------------------------------------------------------------
# 9. Stage progression
# ---------------------------------------------------------------------------


def test_next_stage_map():
    assert NEXT_STAGE_MAP["sourced"] == "screened"
    assert NEXT_STAGE_MAP["screened"] == "interviewed"
    assert NEXT_STAGE_MAP["offered"] == "hired"


def test_next_stage_map_partial():
    assert "applied" in NEXT_STAGE_MAP
    assert "new" in NEXT_STAGE_MAP


# ---------------------------------------------------------------------------
# 10. API 端点
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.auth import CurrentUser, get_current_user
    from api.batch import router, _processors
    from api.deps import get_supabase

    # 清空 processor 缓存,避免测试间状态污染
    _processors.clear()

    fake_user = CurrentUser(
        id=UUID("00000000-0000-0000-0000-000000000099"),
        email="t@example.com",
        role="talent_partner",
        organisation_id=None,
    )

    async def override_user():
        return fake_user

    sb_instance = _mock_supabase()

    def override_supabase():
        return sb_instance

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_supabase] = override_supabase
    return TestClient(app)


def test_api_bulk_email_returns_task_id(api_client):
    r = api_client.post(
        "/api/batch/candidates/bulk_email",
        json={"candidate_ids": ["c1", "c2"], "payload": {"template": "x"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert "task_id" in body
    assert body["action"] == "bulk_email"
    assert body["total"] == 2


def test_api_bulk_unknown_action_400(api_client):
    r = api_client.post(
        "/api/batch/candidates/bulk_invalid",
        json={"candidate_ids": ["c1"]},
    )
    assert r.status_code == 400


def test_api_bulk_validates_candidate_ids(api_client):
    r = api_client.post(
        "/api/batch/candidates/bulk_email",
        json={"candidate_ids": [], "payload": {}},
    )
    assert r.status_code == 422  # pydantic min_length


def test_api_get_task(api_client):
    # 启动一个任务 (BackgroundTasks 在 TestClient 关闭时执行)
    r = api_client.post(
        "/api/batch/candidates/bulk_email",
        json={"candidate_ids": ["c1"]},
    )
    task_id = r.json()["task_id"]
    # 任务进入 store 后即使未完成也可查
    g = api_client.get(f"/api/batch/tasks/{task_id}")
    assert g.status_code == 200
    body = g.json()
    assert body["task_id"] == task_id
    # status 至少是 pending/running/completed 之一
    assert body["status"] in ("pending", "running", "completed", "partial", "failed")


def test_api_get_unknown_task_404(api_client):
    r = api_client.get("/api/batch/tasks/nonexistent-xyz")
    assert r.status_code == 404


def test_api_cancel_task(api_client):
    r = api_client.post(
        "/api/batch/candidates/bulk_email",
        json={"candidate_ids": ["c1"]},
    )
    task_id = r.json()["task_id"]
    c = api_client.post(f"/api/batch/tasks/{task_id}/cancel")
    assert c.status_code in (200, 400)


def test_api_cancel_unknown_400(api_client):
    r = api_client.post("/api/batch/tasks/nonexistent-xyz/cancel")
    assert r.status_code == 400


def test_api_list_tasks(api_client):
    # 至少创建一个任务
    api_client.post(
        "/api/batch/candidates/bulk_email",
        json={"candidate_ids": ["c1"]},
    )
    r = api_client.get("/api/batch/tasks")
    assert r.status_code == 200
    body = r.json()
    assert "tasks" in body
    assert body["count"] >= 1


# ---------------------------------------------------------------------------
# 11. 边界
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_candidate_ids_allowed():
    """边界: 0 个候选人 (允许空跑)."""
    sb = _mock_supabase()
    p = BatchProcessor(sb)
    result = await p.run(
        action=BatchAction.BULK_EMAIL.value,
        candidate_ids=[],
        payload={},
    )
    assert result.status == TaskStatus.COMPLETED
    assert result.succeeded == 0


@pytest.mark.asyncio
async def test_handler_exception_caught():
    """单条 handler 抛错不应中断整个 batch."""
    async def mixed_handler(cid, payload, sb):
        if cid == "c2":
            raise RuntimeError("boom")

    sb = _mock_supabase()
    p = BatchProcessor(sb, max_retries=0)
    from services.platform.batch_processor import HANDLERS
    HANDLERS["bulk_email"] = mixed_handler

    result = await p.run(
        action="bulk_email",
        candidate_ids=["c1", "c2", "c3"],
        payload={},
    )
    assert result.succeeded == 2
    assert result.failed == 1
    HANDLERS["bulk_email"] = handle_bulk_email


def test_all_handlers_registered():
    from services.platform.batch_processor import HANDLERS
    expected = {
        "bulk_update",
        "bulk_email",
        "bulk_offer",
        "bulk_move_stage",
        "bulk_tag",
        "bulk_archive",
    }
    assert expected.issubset(HANDLERS.keys())