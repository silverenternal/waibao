"""pytest configuration for the repository-root ``tests/`` suite.

The backend service modules live under ``backend/`` and are imported as
top-level packages (``services.platform...``, ``agents...``).  This conftest
ensures ``backend/`` is on ``sys.path`` for every test collected here, so
individual test files do not need to repeat the ``sys.path.insert`` boilerplate.
"""
from __future__ import annotations

import os
import sys

_BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
_BACKEND_DIR = os.path.abspath(_BACKEND_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Ensure dummy API keys exist so optional providers do not refuse to construct.
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-not-real")
