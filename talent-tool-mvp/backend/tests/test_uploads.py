"""Tests for file_storage service + /api/uploads endpoint.

策略:
- 不依赖真实 Supabase, 用 monkeypatch 把 get_supabase_admin 替换成 in-memory mock
- 同时验证 happy path (upload/signed_url/delete) 和错误路径 (empty file / 不支持的 mime)
- 通过 api.uploads.get_current_user 间接引用 auth,避免在测试代码里直接 import jose
"""
from __future__ import annotations

import io
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# --- helpers --------------------------------------------------------------

class _FakeStorageBucket:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def upload(self, *, path, file, file_options=None):
        data = file.read() if hasattr(file, "read") else file
        if isinstance(data, str):
            data = data.encode()
        self.objects[path] = bytes(data)

    def create_signed_url(self, path, ttl):
        if path not in self.objects:
            return {}
        return {"signedURL": f"https://fake.supabase.co/sign/{path}?t={ttl}"}

    def remove(self, paths):
        for p in paths:
            self.objects.pop(p, None)


class _FakeSupabaseStorage:
    def __init__(self):
        self.buckets: dict[str, _FakeStorageBucket] = {}

    def from_(self, name):
        if name not in self.buckets:
            self.buckets[name] = _FakeStorageBucket()
        return self.buckets[name]


class _FakeSupabase:
    def __init__(self):
        self.storage = _FakeSupabaseStorage()


@pytest.fixture(autouse=True)
def _reset_storage(monkeypatch):
    monkeypatch.setenv("STORAGE_DEFAULT_BUCKET", "uploads-test")
    # Patch DEFAULT_BUCKET on the underlying module where upload() actually reads it
    import services.integrations.file_storage as mod

    # DEFAULT_BUCKET 是模块级常量,在 import 时一次性读取 os.getenv;
    # 因此除了 setenv 之外,还要把模块上的常量本身改掉,才能让 svc 看到新值。
    monkeypatch.setattr(mod, "DEFAULT_BUCKET", "uploads-test")
    mod.reset_file_storage()

    fake = _FakeSupabase()

    def _fake_get():
        return fake

    monkeypatch.setattr("api.deps.get_supabase_admin", _fake_get)
    yield


def _reset_clients():
    from services.file_storage import get_file_storage

    svc = get_file_storage()
    svc._client = None
    return svc


def _make_fake_user():
    """Create a CurrentUser without importing api.auth (avoids jose install)."""
    from uuid import uuid4
    from contracts.shared import UserRole

    class _U:
        def __init__(self):
            self.id = uuid4()
            self.email = "t@t.com"
            self.role = UserRole.talent_partner

        def model_dump(self):
            return {"id": str(self.id), "email": self.email, "role": self.role.value}

    return _U()


# --- tests: file_storage service 直接调用 ----------------------------------

@pytest.mark.asyncio
async def test_upload_bytes_with_filename():
    svc = _reset_clients()
    result = await svc.upload(
        b"\x89PNG\r\n\x1a\n" + b"fake-png-bytes",
        filename="avatar.png",
        content_type="image/png",
    )
    assert result["bucket"] == "uploads-test"
    assert result["mime"] == "image/png"
    assert result["size"] > 0
    assert result["path"].startswith("files/")
    assert "file_url" in result


@pytest.mark.asyncio
async def test_upload_rejects_empty():
    svc = _reset_clients()
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await svc.upload(b"", filename="empty.png", content_type="image/png")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_mime():
    svc = _reset_clients()
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await svc.upload(b"x", filename="evil.exe", content_type="application/x-msdownload")
    assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_upload_via_filelike():
    svc = _reset_clients()
    bio = io.BytesIO(b"hello world pdf")
    result = await svc.upload(bio, filename="cv.pdf", content_type="application/pdf")
    assert result["mime"] == "application/pdf"
    assert result["size"] == len(b"hello world pdf")


@pytest.mark.asyncio
async def test_signed_url_then_delete():
    svc = _reset_clients()
    res = await svc.upload(b"abc123", filename="r.txt", content_type="text/plain")
    path = res["path"]
    url = await svc.signed_url(path, ttl=120)
    assert ("https://" in url) or url.startswith("memory://")
    ok = await svc.delete(path)
    assert ok is True
    # 二次删除也应该不抛错 — fake supabase 的 remove 是幂等的
    ok2 = await svc.delete(path)
    assert ok2 is True


@pytest.mark.asyncio
async def test_signed_url_404_when_missing():
    svc = _reset_clients()
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await svc.signed_url("nonexistent/path.png")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_upload_supabase_success_via_fake(monkeypatch):
    """让 FileStorageService 走 fake supabase 并验证存储链路."""
    from services.file_storage import get_file_storage

    fake = _FakeSupabase()
    svc = get_file_storage()
    svc._client = fake

    res = await svc.upload(b"x" * 32, filename="img.png", content_type="image/png")
    bucket = fake.storage.buckets[res["bucket"]]
    assert res["path"] in bucket.objects
    assert bucket.objects[res["path"]] == b"x" * 32


# --- tests: /api/uploads endpoint (with override, no jose needed) ----------

def _build_test_app():
    from fastapi import FastAPI
    from api.uploads import router
    from api.uploads import get_current_user as gcu_export

    app = FastAPI()
    app.include_router(router, prefix="/api/uploads")
    fake_user = _make_fake_user()
    app.dependency_overrides[gcu_export] = lambda: fake_user
    return app, fake_user


@pytest.mark.asyncio
async def test_uploads_endpoint_happy():
    from fastapi.testclient import TestClient

    app, fake_user = _build_test_app()
    client = TestClient(app)
    files = {"file": ("resume.png", b"PNG-BYTES", "image/png")}
    data = {"folder": "candidates"}
    r = client.post("/api/uploads/", files=files, data=data)
    assert r.status_code == 201, r.text
    payload = r.json()
    assert payload["success"] is True
    assert payload["mime"] == "image/png"
    assert payload["filename"] == "resume.png"
    assert "file_url" in payload


@pytest.mark.asyncio
async def test_uploads_endpoint_empty_400():
    from fastapi.testclient import TestClient

    app, _ = _build_test_app()
    client = TestClient(app)
    files = {"file": ("empty.png", b"", "image/png")}
    r = client.post("/api/uploads/", files=files)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_uploads_endpoint_bad_mime_415():
    from fastapi.testclient import TestClient

    app, _ = _build_test_app()
    client = TestClient(app)
    files = {"file": ("evil.exe", b"MZ", "application/x-msdownload")}
    r = client.post("/api/uploads/", files=files)
    assert r.status_code == 415


@pytest.mark.asyncio
async def test_signed_url_endpoint():
    from fastapi.testclient import TestClient

    app, _ = _build_test_app()
    client = TestClient(app)
    files = {"file": ("r.png", b"PNG", "image/png")}
    upload_resp = client.post("/api/uploads/", files=files)
    assert upload_resp.status_code == 201
    j = upload_resp.json()
    path = j["path"]
    bucket = j["bucket"]
    r = client.get(f"/api/uploads/signed-url?path={path}&bucket={bucket}&ttl=600")
    assert r.status_code == 200
    body = r.json()
    assert "file_url" in body
    assert body["ttl"] == 600


@pytest.mark.asyncio
async def test_delete_endpoint():
    from fastapi.testclient import TestClient

    app, _ = _build_test_app()
    client = TestClient(app)
    files = {"file": ("r.png", b"PNG", "image/png")}
    up = client.post("/api/uploads/", files=files)
    j = up.json()
    r = client.delete(f"/api/uploads/?path={j['path']}&bucket={j['bucket']}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True
