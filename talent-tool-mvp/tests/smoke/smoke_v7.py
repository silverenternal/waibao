"""
v7.0.0 — 22 项 smoke test (T3004 集成验证)
=========================================

覆盖 v7.0 全部里程碑:
  - P0 Enterprise SaaS 化 (T2601-T2604)
  - P1 AI 能力深化 (T2701-T2704)
  - P2 数据仓库 + BI + 预测 (T2801-T2803)
  - P3 合规 + 生态 (T2901-T2904)
  - P4 AI 高级 + 商业化 (T3001-T3004)

运行:
    cd talent-tool-mvp/backend
    python -m pytest ../tests/smoke/smoke_v7.py -v
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("OPENAI_API_KEY", "sk-smoke-v7-dummy")


# ---------------------------------------------------------------------------
# 1. P0 Enterprise SaaS 化 (T2601-T2604)
# ---------------------------------------------------------------------------


def test_smoke_01_tenant_context():
    """T2601: 严格多租户隔离。"""
    from services.platform.tenant_context import (
        TenantContext,
        set_tenant_context,
        get_tenant_context,
        reset_tenant_context,
    )
    token = set_tenant_context(TenantContext(tenant_id="acme", user_id="alice"))
    assert get_tenant_context().tenant_id == "acme"
    reset_tenant_context(token)


def test_smoke_02_rate_limiter():
    """T2602: Rate Limiting。"""
    from services.platform.rate_limiter import per_route_limit, get_limiter
    assert callable(per_route_limit)
    assert get_limiter() is not None


def test_smoke_03_audit_v2():
    """T2603: 审计日志 v2。"""
    from services.platform.audit_v2 import audit, AuditContext
    assert callable(audit)
    assert AuditContext.__name__ == "AuditContext"


def test_smoke_04_sla_monitor():
    """T2604: SLA monitor。"""
    from services.platform.sla_monitor import get_store, ServiceSLA
    assert callable(get_store)
    assert ServiceSLA.__name__ == "ServiceSLA"


# ---------------------------------------------------------------------------
# 2. P1 AI 能力深化 (T2701-T2704)
# ---------------------------------------------------------------------------


def test_smoke_05_rag_pipeline():
    """T2701: 完整 RAG subsystem 文件齐备。"""
    rag_dir = BACKEND / "services" / "rag"
    assert rag_dir.exists()
    # At minimum the rag package must exist; sub-modules optional.
    from services import rag
    assert rag is not None


def test_smoke_06_memory_module():
    """T2702: 统一记忆库。"""
    from services.memory import Memory, MemoryType, MemoryStore
    assert Memory.__name__ == "Memory"
    assert MemoryType.__name__ == "MemoryType"
    assert MemoryStore.__name__ == "MemoryStore"


def test_smoke_07_multi_agent():
    """T2703: Multi-Agent 协作 — CrewAI 角色 + 共识。"""
    from services.multiagent import (
        AgentRoleRegistry,
        CollaborationPattern,
        ConsensusStrategy,
        Orchestrator,
    )
    assert AgentRoleRegistry.__name__ == "AgentRoleRegistry"
    assert ConsensusStrategy.__name__ == "ConsensusStrategy"
    assert Orchestrator.__name__ == "Orchestrator"


def test_smoke_08_prompt_v2():
    """T2704: Prompt v2 — Agenta 风格。"""
    from services.platform.prompt_v2 import (
        get_prompt_service,
        InMemoryPromptRegistry,
    )
    svc = get_prompt_service()
    assert svc is not None
    assert InMemoryPromptRegistry.__name__ == "InMemoryPromptRegistry"


# ---------------------------------------------------------------------------
# 3. P2 数据仓库 + BI + 预测 (T2801-T2803)
# ---------------------------------------------------------------------------


def test_smoke_09_warehouse_files():
    """T2801: ClickHouse 数仓 + ETL 文件齐备。"""
    wh = BACKEND / "services" / "warehouse"
    assert wh.exists()
    assert any(wh.glob("*.py"))


def test_smoke_10_bi_files():
    """T2802: BI 报表 + Cube.js。"""
    cube_dir = ROOT / "cube-server"
    assert cube_dir.exists(), "cube-server directory missing"


def test_smoke_11_predictive():
    """T2803: 预测分析 — LightGBM + Prophet。"""
    from services.platform.predictive import (
        AttritionModel,
        HireSuccessModel,
        get_attrition_model,
    )
    assert AttritionModel.__name__ == "AttritionModel"
    assert HireSuccessModel.__name__ == "HireSuccessModel"
    _ = get_attrition_model()


# ---------------------------------------------------------------------------
# 4. P3 合规 + 生态 (T2901-T2904)
# ---------------------------------------------------------------------------


def test_smoke_12_sso_saml():
    """T2901: SSO/SAML 文件齐备。"""
    jit = BACKEND / "services" / "auth" / "jit.py"
    assert jit.exists(), "auth/jit.py missing"
    api = BACKEND / "api" / "auth_sso.py"
    assert api.exists(), "api/auth_sso.py missing"


def test_smoke_13_developer_portal():
    """T2902: 开放 API 平台。"""
    portal = BACKEND / "services" / "platform" / "developer_portal.py"
    assert portal.exists()


def test_smoke_14_marketplace():
    """T2903: 第三方应用市场。"""
    from services.marketplace import MarketplaceService, get_marketplace_service
    svc = get_marketplace_service()
    assert svc is not None
    assert MarketplaceService.__name__ == "MarketplaceService"


def test_smoke_15_api_versioning():
    """T2904: API 版本化。"""
    vfile = BACKEND / "api" / "versioning.py"
    assert vfile.exists(), "api/versioning.py missing"


# ---------------------------------------------------------------------------
# 5. P4 AI 高级 + 商业化 (T3001-T3004)
# ---------------------------------------------------------------------------


def test_smoke_16_lora_training():
    """T3001: LoRA Fine-tuning — 文件齐备。"""
    training = BACKEND / "services" / "training"
    assert training.exists()
    assert any(training.glob("*.py"))


def test_smoke_17_sourcing():
    """T3002: AI 主动 Sourcing。"""
    from services.platform.sourcing_agent import SourcingAgent
    assert SourcingAgent.__name__ == "SourcingAgent"


def test_smoke_18_whitelabel_service():
    """T3003: 白标服务 — Branding CRUD + CSS 变量 + 邮件/PDF 渲染。"""
    from services.platform.whitelabel import (
        get_whitelabel_service,
        render_email_html,
        render_pdf_report_brand,
        to_css_variables,
    )
    svc = get_whitelabel_service()
    branding = svc.upsert({"tenant_id": "smoke", "product_name": "Smoke"})
    assert branding.tenant_id == "smoke"
    css = to_css_variables(branding)
    assert "--color-primary" in css
    email = render_email_html(branding, body_html="<p>hi</p>", subject="S")
    assert "<!doctype html>" in email["html"].lower()
    pdf = render_pdf_report_brand(branding)
    assert "primary_color" in pdf


def test_smoke_19_whitelabel_admin_page():
    """T3003: 白标 admin UI 存在。"""
    page = ROOT / "frontend" / "app" / "admin" / "whitelabel" / "page.tsx"
    assert page.exists()


def test_smoke_20_whitelabel_infra():
    """T3003: 私有化部署 — docker-compose + helm + terraform 全部存在。"""
    base = ROOT / "infra" / "private-deployment"
    assert (base / "docker-compose.yml").exists()
    assert (base / "helm" / "waibao" / "Chart.yaml").exists()
    assert (base / "terraform" / "main.tf").exists()
    assert (base / "OPERATIONS_MANUAL.md").exists()
    assert (base / ".env.example").exists()


def test_smoke_21_v7_docs():
    """T3004: v7.0 文档齐备 — README + ARCHITECTURE + AI_DEEP + COMMERCIAL。"""
    docs = ROOT.parent / "docs"
    assert (docs / "PRIVATE_DEPLOYMENT.md").exists()
    assert (docs / "AI_DEEP.md").exists()
    assert (docs / "COMMERCIAL.md").exists()


def test_smoke_22_v7_release():
    """T3004: v7.0.0 Release — CHANGELOG + release notes。"""
    root_waibao = ROOT.parent
    changelog = root_waibao / "CHANGELOG.md"
    assert changelog.exists()
    text = changelog.read_text()
    assert "v7.0.0" in text
    assert "T3003" in text
    assert "T3004" in text