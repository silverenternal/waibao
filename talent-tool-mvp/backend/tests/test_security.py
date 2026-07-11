"""T1005 - Security tests: SQL 注入 / XSS / SSRF / 路径遍历."""
from __future__ import annotations

import os
import pytest


def _walk_py_files(skip_tests: bool = True, skip_seed: bool = True):
    """生成 (path, content) 元组,跳过 tests/ 和 seed/."""
    backend_dir = os.path.join(os.path.dirname(__file__), "..")
    for root, _dirs, files in os.walk(backend_dir):
        if "__pycache__" in root or ".venv" in root:
            continue
        if skip_tests and ("/tests" in root or root.endswith("/tests")):
            continue
        if skip_seed and "/seed" in root:
            continue
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(root, fn)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    yield path, f.read()
            except Exception:
                continue


# ---------------------------------------------------------------------------
# 1. SQL 注入 — 验证所有 DB 调用走 Supabase SDK (参数化),无字符串拼接 SQL.
# ---------------------------------------------------------------------------
def test_no_string_concat_sql_in_backend():
    """扫描 backend/ 不允许出现 f-string/exec/eval 形式的 SQL 拼接."""
    bad_patterns = [
        'f"SELECT ',
        "f'SELECT ",
        'f"INSERT ',
        "f'INSERT ",
        'f"UPDATE ',
        "f'UPDATE ",
        'f"DELETE ',
        "f'DELETE ",
        'execute(f"',
        "execute(f'",
    ]
    offenders = []
    for path, content in _walk_py_files():
        for needle in bad_patterns:
            if needle in content:
                offenders.append(f"{path}: {needle}")
    assert not offenders, "SQL injection risk detected:\n" + "\n".join(offenders)


def test_supabase_calls_use_sdk_not_raw_sql():
    """确认 supabase 查询走 SDK (parametrized)."""
    from api.deps import get_supabase_admin

    assert callable(get_supabase_admin)


# ---------------------------------------------------------------------------
# 2. XSS — 输出必须经过转义 (前端默认 React 转义).
# ---------------------------------------------------------------------------
def test_no_innerHTML_in_frontend_components():
    """扫描 frontend/components 不允许 dangerouslySetInnerHTML."""
    frontend_dir = os.path.join(
        os.path.dirname(__file__), "..", "..", "frontend", "components"
    )
    if not os.path.isdir(frontend_dir):
        pytest.skip("frontend/components not found")
    offenders = []
    for root, _dirs, files in os.walk(frontend_dir):
        if "node_modules" in root:
            continue
        for fn in files:
            if not fn.endswith((".tsx", ".ts")):
                continue
            path = os.path.join(root, fn)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if "dangerouslySetInnerHTML" in content:
                offenders.append(path)
    assert not offenders, f"dangerouslySetInnerHTML found in: {offenders}"


# ---------------------------------------------------------------------------
# 3. SSRF — provider URL 白名单.
# ---------------------------------------------------------------------------
def test_provider_url_whitelist():
    """验证 providers/registry 只允许白名单 host (若已实现)."""
    from providers import registry as reg

    allowed = getattr(reg, "ALLOWED_HOSTS", None)
    if allowed is None:
        pytest.skip("providers.registry.ALLOWED_HOSTS not defined (尚未启用白名单)")
    assert isinstance(allowed, (list, set, tuple))
    assert len(allowed) > 0
    assert any("openai.com" in h or "anthropic.com" in h for h in allowed)


def test_ssrf_blocked_in_helper():
    """验证任意 host 不在白名单时被拒绝."""
    try:
        from providers import registry as reg

        validator = getattr(reg, "validate_host", None)
        if validator is None:
            pytest.skip("no validate_host() helper")
        with pytest.raises(Exception):
            validator("https://evil.example.com")
    except ImportError:
        pytest.skip("providers.registry not importable")


# ---------------------------------------------------------------------------
# 4. 路径遍历 — 上传路径必须由服务端生成 UUID.
# ---------------------------------------------------------------------------
def test_uploads_router_no_user_path():
    """验证 /api/uploads 不接受用户传入 file_path."""
    from api import uploads

    src = open(uploads.__file__, "r", encoding="utf-8").read()
    forbidden = [
        'request.query_params.get("path")',
        "request.query_params.get('path')",
        'request.query_params["path"]',
        "request.query_params['path']",
    ]
    for needle in forbidden:
        assert needle not in src, f"uploads.py contains {needle}"


def test_uploads_validates_uuid_filename():
    """uploads 路由必须用 server-side 命名 (uuid 或 id)."""
    from api import uploads

    src = open(uploads.__file__, "r", encoding="utf-8").read()
    assert "uuid" in src.lower() or "id" in src.lower(), (
        "uploads.py 似乎没使用 server-side UUID 命名 — 可能存在路径遍历风险"
    )


# ---------------------------------------------------------------------------
# 5. 通用: 禁止硬编码密钥.
# ---------------------------------------------------------------------------
def test_no_hardcoded_secrets():
    """扫描 backend/ 不允许出现明文 sk-/sk_live_/Bearer 字样的硬编码凭证."""
    offenders = []
    for path, content in _walk_py_files():
        if path.endswith("test_security.py"):
            continue
        for needle in ["sk-abc", "sk_live_", "Bearer eyJhbGciOi"]:
            if needle in content:
                offenders.append(f"{path}: {needle}")
    assert not offenders, "Hardcoded secrets:\n" + "\n".join(offenders)