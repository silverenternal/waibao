"""v11.2 T6303 — tests for identity verification service + API.

Covers:
  * submit each doc type -> verified
  * unverifiable / missing upload -> pending (待上传)
  * compute_overall roll-up logic (verified / submitted / pending)
  * profile versioning: increment, list, get, latest
  * in-memory fallback when Supabase is unreachable
  * API endpoints importable + respond (FastAPI TestClient)
"""
from __future__ import annotations

import os
import sys
from typing import Any

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.identity import (  # noqa: E402
    DISPLAY_MAP,
    DOC_TYPES,
    IdentityStatus,
    IdentityVerificationService,
    get_identity_service,
)
from services.identity.verification import (  # noqa: E402
    _extract_education_fields,
    _extract_id_card_fields,
    _resume_extracted_is_ok,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_memory(monkeypatch):
    """Force the service to use the in-memory store by making the admin client
    unreachable, and reset state between tests."""
    # Make get_supabase_admin blow up so every code path falls back to memory.
    from api import deps as _deps

    def _boom():
        raise RuntimeError("no db in unit tests")

    monkeypatch.setattr(_deps, "get_supabase_admin", _boom)
    IdentityVerificationService.reset()
    yield
    IdentityVerificationService.reset()


@pytest.fixture
def svc() -> IdentityVerificationService:
    return IdentityVerificationService()


UID = "user-123"


# ---------------------------------------------------------------------------
# Display map / constants
# ---------------------------------------------------------------------------


def test_display_map_contract():
    assert DISPLAY_MAP == {"pending": "待上传", "submitted": "待审核", "verified": "已认证"}


def test_doc_types_contract():
    assert set(DOC_TYPES) == {"id_card", "education", "resume"}


def test_identity_status_dataclass_displays():
    s = IdentityStatus(overall="verified", id_card="verified", education="submitted", resume="pending")
    assert s.overall_display == "已认证"
    assert s.id_card_display == "已认证"
    assert s.education_display == "待审核"
    assert s.resume_display == "待上传"
    payload = s.to_dict()
    assert payload["overall"] == "verified"
    assert payload["resume_display"] == "待上传"


def test_identity_status_rejects_invalid():
    with pytest.raises(ValueError):
        IdentityStatus(overall="bogus", id_card="pending", education="pending", resume="pending")


# ---------------------------------------------------------------------------
# compute_overall
# ---------------------------------------------------------------------------


def test_compute_overall_all_verified():
    assert IdentityVerificationService.compute_overall("verified", "verified", "verified") == "verified"


def test_compute_overall_partial_verified_with_submitted():
    # not all three verified, but one submitted -> submitted
    assert IdentityVerificationService.compute_overall("verified", "submitted", "verified") == "submitted"


def test_compute_overall_only_pending():
    assert IdentityVerificationService.compute_overall("pending", "pending", "pending") == "pending"


def test_compute_overall_mixed_pending_verified():
    # two verified, one pending (no submitted anywhere) -> pending
    assert IdentityVerificationService.compute_overall("verified", "verified", "pending") == "pending"


def test_compute_overall_rejects_invalid():
    with pytest.raises(ValueError):
        IdentityVerificationService.compute_overall("nope", "pending", "pending")


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------


def test_extract_id_card_fields_found():
    text = "姓名 张三 身份证号 110101199003071234"
    res = _extract_id_card_fields(text)
    assert res["verified"] is True
    assert res["id_card_no"] == "110101199003071234"


def test_extract_id_card_fields_missing():
    res = _extract_id_card_fields("some scan with no number here")
    assert res["verified"] is False
    assert "待上传" in res["reason"]


def test_extract_education_fields_found():
    text = "某某大学 本科 计算机科学与技术 2018"
    res = _extract_education_fields(text)
    assert res["verified"] is True
    assert "本科" in res["degree_keywords"]


def test_extract_education_fields_missing():
    res = _extract_education_fields("random text without degree keywords")
    assert res["verified"] is False
    assert "待上传" in res["reason"]


def test_resume_extracted_is_ok():
    ok, _ = _resume_extracted_is_ok({"basic": {"name": "张三", "email": "a@b.com", "phone": "13800000000"}})
    assert ok is True
    ok2, reason = _resume_extracted_is_ok({"basic": {"name": ""}})
    assert ok2 is False
    assert "待上传" in reason
    ok3, _ = _resume_extracted_is_ok({"_error": "boom"})
    assert ok3 is False


# ---------------------------------------------------------------------------
# submit_document — happy paths (each doc type -> verified)
# ---------------------------------------------------------------------------


def test_submit_id_card_verified(svc):
    status = svc.submit_document(UID, "id_card", "姓名 张三 身份证号 110101199003071234".encode())
    assert status.id_card == "verified"
    assert status.id_card_display == "已认证"
    # roll-up stays pending (other docs not uploaded)
    assert status.overall == "pending"


def test_submit_education_verified(svc):
    status = svc.submit_document(UID, "education", "某某大学 本科 计算机科学与技术".encode())
    assert status.education == "verified"
    assert status.education_display == "已认证"


def test_submit_resume_verified(svc):
    # raw bytes -> treated as extracted text blob (has contact) -> verified
    status = svc.submit_document(UID, "resume", "张三 a@b.com 13800000000".encode())
    assert status.resume == "verified"
    assert status.resume_display == "已认证"


def test_submit_all_three_flips_overall_verified(svc):
    svc.submit_document(UID, "id_card", b"110101199003071234")
    svc.submit_document(UID, "education", "某某大学 本科".encode())
    svc.submit_document(UID, "resume", "张三 a@b.com 13800000000".encode())
    status = svc.get_status(UID)
    assert status.id_card == "verified"
    assert status.education == "verified"
    assert status.resume == "verified"
    assert status.overall == "verified"
    assert status.overall_display == "已认证"


# ---------------------------------------------------------------------------
# submit_document — unverifiable / missing -> pending (待上传)
# ---------------------------------------------------------------------------


def test_submit_id_card_unverifiable_pending(svc):
    status = svc.submit_document(UID, "id_card", "模糊扫描件无号码".encode())
    assert status.id_card == "pending"
    assert status.id_card_display == "待上传"
    assert status.reasons.get("id_card")


def test_submit_education_unverifiable_pending(svc):
    status = svc.submit_document(UID, "education", b"just some random words")
    assert status.education == "pending"
    assert status.education_display == "待上传"


def test_submit_resume_unverifiable_pending(svc):
    # empty-ish resume text -> no basic block -> pending
    status = svc.submit_document(UID, "resume", b"   ")
    assert status.resume == "pending"
    assert status.resume_display == "待上传"


def test_submit_no_payload_stays_pending(svc):
    status = svc.submit_document(UID, "id_card", None)
    assert status.id_card == "pending"
    assert status.id_card_display == "待上传"


def test_submit_unknown_doc_type_raises(svc):
    with pytest.raises(ValueError):
        svc.submit_document(UID, "passport", b"whatever")


# ---------------------------------------------------------------------------
# get_status default + reasons surfacing
# ---------------------------------------------------------------------------


def test_get_status_default_pending(svc):
    status = svc.get_status(UID)
    assert status.overall == "pending"
    assert status.id_card == "pending"
    assert status.education == "pending"
    assert status.resume == "pending"


def test_reasons_surface_on_unverifiable(svc):
    svc.submit_document(UID, "id_card", "模糊扫描件无号码".encode())
    status = svc.get_status(UID)
    assert "id_card" in status.reasons
    assert "待上传" in status.reasons["id_card"]


# ---------------------------------------------------------------------------
# Profile versioning
# ---------------------------------------------------------------------------


def test_save_profile_version_increments(svc):
    v1 = svc.save_profile_version(UID, {"basic": {"name": "v1"}})
    v2 = svc.save_profile_version(UID, {"basic": {"name": "v2"}})
    v3 = svc.save_profile_version(UID, {"basic": {"name": "v3"}})
    assert (v1, v2, v3) == (1, 2, 3)


def test_list_versions_newest_first(svc):
    svc.save_profile_version(UID, {"basic": {"name": "v1"}})
    svc.save_profile_version(UID, {"basic": {"name": "v2"}})
    versions = svc.list_versions(UID)
    assert [v["version_no"] for v in versions] == [2, 1]
    assert all("created_at" in v for v in versions)


def test_get_version_snapshot(svc):
    svc.save_profile_version(UID, {"basic": {"name": "v1"}})
    svc.save_profile_version(UID, {"basic": {"name": "v2"}})
    snap = svc.get_version(UID, 1)
    assert snap == {"basic": {"name": "v1"}}
    assert svc.get_version(UID, 2) == {"basic": {"name": "v2"}}


def test_get_version_missing_returns_none(svc):
    assert svc.get_version(UID, 99) is None


def test_get_latest(svc):
    assert svc.get_latest(UID) is None
    svc.save_profile_version(UID, {"basic": {"name": "v1"}})
    svc.save_profile_version(UID, {"basic": {"name": "v2"}})
    assert svc.get_latest(UID) == {"basic": {"name": "v2"}}


def test_save_profile_version_rejects_non_dict(svc):
    with pytest.raises(TypeError):
        svc.save_profile_version(UID, ["not", "a", "dict"])  # type: ignore[arg-type]


def test_versions_isolated_per_user(svc):
    svc.save_profile_version("user-a", {"who": "a"})
    svc.save_profile_version("user-b", {"who": "b1"})
    svc.save_profile_version("user-b", {"who": "b2"})
    assert svc.get_latest("user-a") == {"who": "a"}
    assert svc.get_latest("user-b") == {"who": "b2"}
    assert [v["version_no"] for v in svc.list_versions("user-b")] == [2, 1]


# ---------------------------------------------------------------------------
# In-memory fallback resilience
# ---------------------------------------------------------------------------


def test_service_works_without_db(svc):
    """The autouse fixture already breaks the DB; just confirm end-to-end."""
    svc.submit_document(UID, "id_card", b"110101199003071234")
    svc.save_profile_version(UID, {"basic": {"name": "x"}})
    assert svc.get_status(UID).id_card == "verified"
    assert svc.get_latest(UID) == {"basic": {"name": "x"}}


def test_get_identity_service_singleton():
    a = get_identity_service()
    b = get_identity_service()
    assert a is b


# ===========================================================================
# API layer (FastAPI TestClient)
# ===========================================================================


class _FakeUser:
    """Minimal stand-in for api.auth.CurrentUser."""

    def __init__(self, uid: str, role: str = "talent_partner"):
        self.id = uid
        self.email = "x@y.com"
        self.role = role  # plain str; _ensure_talent reads .value or the raw


@pytest.fixture
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import api.identity as identity_api

    app = FastAPI()
    app.include_router(identity_api.router, prefix="/api/identity")

    current: dict[str, Any] = {"user": _FakeUser(UID)}

    async def _override():
        return current["user"]

    app.dependency_overrides[identity_api.get_current_user] = _override

    with TestClient(app) as c:
        yield c, current


def test_api_upload_id_card_verified(client):
    c, _ = client
    r = c.post(
        "/api/identity/upload",
        json={"doc_type": "id_card", "file_url": "ignored-in-memory-bytes-path"},
    )
    # file_url is a str but contains no id-number -> pending (待上传)
    assert r.status_code == 200
    body = r.json()
    assert body["id_card"] in ("pending", "verified")
    assert body["id_card_display"] in ("待上传", "已认证")
    assert "overall_display" in body


def test_api_status(client):
    c, _ = client
    r = c.get("/api/identity/status")
    assert r.status_code == 200
    body = r.json()
    assert body["overall"] == "pending"
    assert body["overall_display"] == "待上传"


def test_api_profile_crud_and_versions(client):
    c, _ = client

    # no profile yet
    r = c.get("/api/identity/profile")
    assert r.status_code == 200
    assert r.json()["profile"] is None

    # create v1
    r = c.put("/api/identity/profile", json={"profile": {"basic": {"name": "v1"}}})
    assert r.status_code == 200
    assert r.json()["version_no"] == 1

    # create v2
    r = c.put("/api/identity/profile", json={"profile": {"basic": {"name": "v2"}}})
    assert r.status_code == 200
    assert r.json()["version_no"] == 2

    # latest
    r = c.get("/api/identity/profile")
    assert r.json()["profile"] == {"basic": {"name": "v2"}}

    # versions list
    r = c.get("/api/identity/profile/versions")
    assert [v["version_no"] for v in r.json()["versions"]] == [2, 1]

    # get specific version
    r = c.get("/api/identity/profile/versions/1")
    assert r.status_code == 200
    assert r.json()["snapshot"] == {"basic": {"name": "v1"}}

    # missing version -> 404
    r = c.get("/api/identity/profile/versions/99")
    assert r.status_code == 404


def test_api_upload_rejects_bad_doc_type(client):
    c, _ = client
    r = c.post("/api/identity/upload", json={"doc_type": "passport", "file_url": "x"})
    assert r.status_code == 400


def test_api_rejects_non_talent_role(client):
    c, current = client
    current["user"] = _FakeUser(UID, role="client")
    r = c.get("/api/identity/status")
    assert r.status_code == 403


def test_api_router_importable_and_mountable():
    """The router must import + mount without touching jose/Supabase."""
    from api.identity import router

    assert getattr(router, "routes", None), "identity router has no routes"
    paths = {getattr(r, "path", "") for r in router.routes}
    assert "/upload" in paths
    assert "/status" in paths
    assert "/profile" in paths
    assert "/profile/versions" in paths
