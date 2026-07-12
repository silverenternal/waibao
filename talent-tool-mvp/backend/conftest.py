"""Pytest 配置 - 添加 backend 到 Python 路径."""
import sys
import os

# 把 backend 目录加入 sys.path,使得 `import agents` 等顶级导入可以工作
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Load .env.test if it exists (so OPENAI_API_KEY etc. are present for tests).
# pydantic-settings reads .env at class definition, so we need to either
# pre-populate the env or provide a .env file with the test values.
_env_test = os.path.join(backend_dir, ".env.test")
_env_main = os.path.join(backend_dir, ".env")
if os.path.exists(_env_test):
    try:
        with open(_env_test) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                os.environ.setdefault(k, v)
    except Exception:  # noqa: BLE001
        pass
    # Ensure OPENAI_API_KEY has at least a dummy value, since OpenAI client
    # refuses to construct without one.
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-not-real")
    os.environ.setdefault("OPENAI_ADMIN_KEY", "sk-admin-test-dummy")
    # If the main .env is missing, copy .env.test → .env so pydantic-settings
    # can pick up dummy values when constructing Settings() in production code.
    if not os.path.exists(_env_main):
        try:
            import shutil
            shutil.copy(_env_test, _env_main)
        except Exception:  # noqa: BLE001
            pass