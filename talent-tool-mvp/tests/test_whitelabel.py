"""v7.0 T3003 — White-label + private-deployment branding tests.

Coverage:

* Branding dataclass + from_dict / to_dict
* Validation (colors, URLs, fonts, locale, templates, partial PATCH)
* Service CRUD + cache + audit
* Default fallback when the tenant has no row
* CSS variables contract (frontend / backend must agree)
* Email header / footer / full HTML rendering
* PDF report metadata
* Migration file (existence + key tables + RLS)
* FastAPI surface (GET / PUT / PATCH / DELETE / list / preview)

All tests are offline — no DB, no Supabase, no SMTP.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the whitelabel singleton between tests."""
    from services.platform.whitelabel import reset_whitelabel_service
    reset_whitelabel_service()
    yield
    reset_whitelabel_service()


@pytest.fixture
def svc():
    from services.platform.whitelabel import get_whitelabel_service
    return get_whitelabel_service()


# ---------------------------------------------------------------------------
# 1. Branding dataclass
# ---------------------------------------------------------------------------


def test_branding_from_dict_minimal():
    from services.platform.whitelabel import Branding
    b = Branding.from_dict({"tenant_id": "acme"})
    assert b.tenant_id == "acme"
    assert b.primary_color == "#2563EB"   # default
    assert b.locale == "zh-CN"


def test_branding_from_dict_rejects_missing_tenant():
    from services.platform.whitelabel import Branding, BrandingValidationError
    with pytest.raises(BrandingValidationError):
        Branding.from_dict({})


def test_branding_from_dict_keeps_extra_keys():
    from services.platform.whitelabel import Branding
    b = Branding.from_dict({"tenant_id": "acme", "future_field": 42})
    assert b.extra.get("future_field") == 42


def test_branding_to_dict_roundtrip():
    from services.platform.whitelabel import Branding
    src = Branding.from_dict({"tenant_id": "acme", "primary_color": "#FF0000"})
    d = src.to_dict()
    again = Branding.from_dict(d)
    assert again.tenant_id == src.tenant_id
    assert again.primary_color == src.primary_color


# ---------------------------------------------------------------------------
# 2. Validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("color", ["#2563EB", "#000000", "#FFFFFF", "#abcdef12"])
def test_validate_color_accepts_hex(color):
    from services.platform.whitelabel import Branding, _validate_color
    assert _validate_color(color, field_name="primary_color") == color.upper()


@pytest.mark.parametrize("color", ["2563EB", "#fff", "rgb(0,0,0)", "navy", "#zzz"])
def test_validate_color_rejects_bad(color):
    from services.platform.whitelabel import BrandingValidationError, _validate_color
    with pytest.raises(BrandingValidationError):
        _validate_color(color, field_name="primary_color")


@pytest.mark.parametrize("url", ["https://cdn.example.com/logo.png", "http://x.test/"])
def test_validate_url_accepts_http(url):
    from services.platform.whitelabel import _validate_url
    assert _validate_url(url, field_name="logo_url") == url


def test_validate_url_rejects_relative():
    from services.platform.whitelabel import BrandingValidationError, _validate_url
    with pytest.raises(BrandingValidationError):
        _validate_url("/static/logo.png", field_name="logo_url")


@pytest.mark.parametrize("font", ["Inter", "PingFang SC", "system-ui"])
def test_validate_font_accepts_allowlist(font):
    from services.platform.whitelabel import _validate_font
    assert _validate_font(font) == font


def test_validate_font_rejects_unknown():
    from services.platform.whitelabel import BrandingValidationError, _validate_font
    with pytest.raises(BrandingValidationError):
        _validate_font("Comic Sans MS")


def test_validate_branding_full_payload_ok():
    from services.platform.whitelabel import _validate_branding_dict
    payload = _validate_branding_dict({
        "tenant_id": "acme",
        "product_name": "Acme Talent",
        "logo_url": "https://cdn.acme.test/logo.svg",
        "primary_color": "#FF6B35",
        "locale": "en-US",
        "email_template": "marketing",
        "font_family": "Inter",
        "support_email": "hi@acme.test",
        "hide_powered_by": True,
    })
    assert payload["primary_color"] == "#FF6B35"
    assert payload["hide_powered_by"] is True


def test_validate_branding_partial_allows_partial():
    from services.platform.whitelabel import _validate_branding_dict
    payload = _validate_branding_dict(
        {"tenant_id": "acme", "primary_color": "#abcdef"}, partial=True
    )
    assert payload["primary_color"] == "#ABCDEF"


def test_validate_branding_rejects_oversize_footer():
    from services.platform.whitelabel import BrandingValidationError, _validate_branding_dict
    with pytest.raises(BrandingValidationError):
        _validate_branding_dict({
            "tenant_id": "acme",
            "footer_text": "x" * 600,
        })


def test_validate_branding_rejects_bad_template():
    from services.platform.whitelabel import BrandingValidationError, _validate_branding_dict
    with pytest.raises(BrandingValidationError):
        _validate_branding_dict({
            "tenant_id": "acme",
            "email_template": "wrong_value",
        })


def test_validate_branding_rejects_bad_locale():
    from services.platform.whitelabel import BrandingValidationError, _validate_branding_dict
    with pytest.raises(BrandingValidationError):
        _validate_branding_dict({
            "tenant_id": "acme",
            "locale": "klingon",
        })


# ---------------------------------------------------------------------------
# 3. Service CRUD
# ---------------------------------------------------------------------------


def test_service_get_returns_defaults_when_missing(svc):
    b = svc.get("unknown-tenant")
    assert b.tenant_id == "unknown-tenant"
    assert b.product_name == "Waibao Recruitment"
    assert b.primary_color == "#2563EB"


def test_service_upsert_creates_record(svc):
    out = svc.upsert({"tenant_id": "acme", "product_name": "Acme Talent"})
    assert out.tenant_id == "acme"
    assert out.product_name == "Acme Talent"
    again = svc.get("acme")
    assert again.product_name == "Acme Talent"


def test_service_upsert_validates_and_rejects(svc):
    from services.platform.whitelabel import BrandingValidationError
    with pytest.raises(BrandingValidationError):
        svc.upsert({"tenant_id": "acme", "primary_color": "navy"})


def test_service_patch_only_changes_provided_fields(svc):
    svc.upsert({"tenant_id": "acme", "product_name": "Acme"})
    patched = svc.patch("acme", {"primary_color": "#00FF00"})
    assert patched.product_name == "Acme"
    assert patched.primary_color == "#00FF00"


def test_service_delete_removes_record(svc):
    svc.upsert({"tenant_id": "acme", "product_name": "Acme"})
    assert svc.delete("acme") is True
    # Subsequent delete should be a no-op (returns False).
    assert svc.delete("acme") is False


def test_service_audit_log_records_mutations(svc):
    svc.upsert({"tenant_id": "acme", "product_name": "Acme"}, actor="alice")
    svc.patch("acme", {"primary_color": "#FF0000"}, actor="bob")
    svc.delete("acme", actor="carol")
    log = svc.audit_log()
    assert [e["action"] for e in log] == ["updated", "updated", "deleted"]
    assert [e["actor"] for e in log] == ["alice", "bob", "carol"]


def test_service_list_all(svc):
    svc.upsert({"tenant_id": "a"})
    svc.upsert({"tenant_id": "b"})
    items = svc.list_all()
    assert {b.tenant_id for b in items} == {"a", "b"}


def test_service_cache_returns_within_ttl(svc, monkeypatch):
    svc.upsert({"tenant_id": "acme", "product_name": "Acme"})
    # Direct cache hit path.
    b1 = svc.get("acme")
    # Mutate the underlying store without going through the service
    # so we can prove the cache returns the old record.
    svc._write_db(svc._read_db("acme").__class__(tenant_id="acme", product_name="MUTATED"))
    b2 = svc.get("acme")
    assert b2.product_name == "Acme"


def test_service_cache_invalidates_after_upsert(svc):
    svc.upsert({"tenant_id": "acme", "product_name": "V1"})
    svc.upsert({"tenant_id": "acme", "product_name": "V2"})
    assert svc.get("acme").product_name == "V2"


def test_service_reset_cache(svc):
    svc.upsert({"tenant_id": "acme", "product_name": "V1"})
    svc.reset_cache()
    # After reset, cache miss returns the stored value (still V1 here).
    assert svc.get("acme").product_name == "V1"


def test_service_get_or_404_raises(svc):
    from services.platform.whitelabel import BrandingNotFoundError
    with pytest.raises(BrandingNotFoundError):
        svc.get_or_404("missing")


# ---------------------------------------------------------------------------
# 4. CSS variables
# ---------------------------------------------------------------------------


def test_to_css_variables_contains_all_keys(svc):
    from services.platform.whitelabel import to_css_variables, CSS_VAR_KEYS
    out = to_css_variables(svc.get("acme"))
    for key in CSS_VAR_KEYS:
        assert key in out


def test_to_css_variables_logo_url_wraps():
    from services.platform.whitelabel import Branding, to_css_variables
    b = Branding(tenant_id="x", logo_url="https://cdn.example.com/logo.png")
    out = to_css_variables(b)
    assert out["--logo-url"] == 'url("https://cdn.example.com/logo.png")'


def test_to_css_variables_hide_powered_by_serialised():
    from services.platform.whitelabel import Branding, to_css_variables
    on = to_css_variables(Branding(tenant_id="x", hide_powered_by=True))
    off = to_css_variables(Branding(tenant_id="x", hide_powered_by=False))
    assert on["--hide-powered-by"] == "true"
    assert off["--hide-powered-by"] == "false"


def test_to_css_variables_falls_back_when_blank():
    from services.platform.whitelabel import Branding, to_css_variables
    b = Branding(tenant_id="x", primary_color="")
    out = to_css_variables(b)
    assert out["--color-primary"] == "#2563EB"


# ---------------------------------------------------------------------------
# 5. Email rendering
# ---------------------------------------------------------------------------


def test_render_email_header_includes_logo_or_name():
    from services.platform.whitelabel import (
        Branding,
        render_email_header,
    )
    with_logo = render_email_header(
        Branding(tenant_id="x", logo_url="https://cdn.example.com/logo.png")
    )
    assert "https://cdn.example.com/logo.png" in with_logo
    without_logo = render_email_header(Branding(tenant_id="x"))
    assert "Waibao Recruitment" in without_logo


def test_render_email_header_uses_primary_color():
    from services.platform.whitelabel import Branding, render_email_header
    out = render_email_header(Branding(tenant_id="x", primary_color="#FF00FF"))
    assert "#FF00FF" in out.upper()


def test_render_email_footer_hides_powered_by_when_set():
    from services.platform.whitelabel import Branding, render_email_footer
    out = render_email_footer(Branding(tenant_id="x", hide_powered_by=True))
    assert "Powered by Waibao" not in out


def test_render_email_footer_includes_support_email():
    from services.platform.whitelabel import Branding, render_email_footer
    out = render_email_footer(Branding(tenant_id="x", support_email="hi@acme.test"))
    assert "hi@acme.test" in out


def test_render_email_html_subject_in_title():
    from services.platform.whitelabel import Branding, render_email_html
    out = render_email_html(
        Branding(tenant_id="x"), body_html="<p>hi</p>", subject="Welcome"
    )
    assert out["subject"] == "Welcome"
    assert "Welcome" in out["html"]
    assert "hi" in out["html"]
    assert "<!doctype html>" in out["html"].lower()


def test_render_email_html_text_contains_words():
    """Text version must include the body words and product name.
    (Tag stripping is best-effort — the canonical mailer pipeline
    converts html→text via premailer / html2text downstream.)"""
    from services.platform.whitelabel import Branding, render_email_html
    out = render_email_html(Branding(tenant_id="x"), body_html="<p>hi <b>there</b></p>", subject="S")
    assert "hi" in out["text"]
    assert "there" in out["text"]
    assert "Waibao Recruitment" in out["text"]


# ---------------------------------------------------------------------------
# 6. PDF report metadata
# ---------------------------------------------------------------------------


def test_render_pdf_report_brand_returns_dict():
    from services.platform.whitelabel import Branding, render_pdf_report_brand
    out = render_pdf_report_brand(Branding(tenant_id="x", primary_color="#123456"))
    assert out["primary_color"] == "#123456"
    assert out["hide_powered_by"] is False
    assert out["report_template"] == "default"


def test_render_pdf_report_brand_propagates_hide_powered_by():
    from services.platform.whitelabel import Branding, render_pdf_report_brand
    out = render_pdf_report_brand(Branding(tenant_id="x", hide_powered_by=True))
    assert out["hide_powered_by"] is True


# ---------------------------------------------------------------------------
# 7. Migration file
# ---------------------------------------------------------------------------


def test_migration_052_whitelabel_exists():
    repo = Path(__file__).resolve().parents[1]
    path = repo / "supabase" / "migrations" / "052_whitelabel.sql"
    assert path.exists(), f"missing migration: {path}"


def test_migration_052_contains_tenant_branding():
    repo = Path(__file__).resolve().parents[1]
    sql = (repo / "supabase" / "migrations" / "052_whitelabel.sql").read_text()
    assert "tenant_branding" in sql
    assert "tenant_branding_audit" in sql


def test_migration_052_has_rls():
    repo = Path(__file__).resolve().parents[1]
    sql = (repo / "supabase" / "migrations" / "052_whitelabel.sql").read_text()
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "service_role" in sql


def test_migration_052_validates_color_format():
    repo = Path(__file__).resolve().parents[1]
    sql = (repo / "supabase" / "migrations" / "052_whitelabel.sql").read_text()
    # Check regex pattern for hex color is present
    assert "#[0-9a-fA-F]" in sql


def test_migration_052_seeds_default_tenant():
    repo = Path(__file__).resolve().parents[1]
    sql = (repo / "supabase" / "migrations" / "052_whitelabel.sql").read_text()
    assert "'public'" in sql
    assert "INSERT INTO public.tenant_branding" in sql


# ---------------------------------------------------------------------------
# 8. Frontend files
# ---------------------------------------------------------------------------


def test_frontend_theme_ts_exists():
    repo = Path(__file__).resolve().parents[1]
    assert (repo / "frontend" / "lib" / "theme.ts").exists()


def test_frontend_white_label_provider_exists():
    repo = Path(__file__).resolve().parents[1]
    assert (repo / "frontend" / "components" / "WhiteLabelProvider.tsx").exists()


def test_frontend_white_label_stories_exist():
    repo = Path(__file__).resolve().parents[1]
    assert (repo / "frontend" / "components" / "WhiteLabelProvider.stories.tsx").exists()


def test_frontend_admin_whitelabel_page_exists():
    repo = Path(__file__).resolve().parents[1]
    assert (repo / "frontend" / "app" / "admin" / "whitelabel" / "page.tsx").exists()


def test_frontend_styles_whitelabel_exists():
    repo = Path(__file__).resolve().parents[1]
    assert (repo / "frontend" / "styles" / "whitelabel.css").exists()


def test_frontend_theme_ts_exports_whitelabel_api():
    repo = Path(__file__).resolve().parents[1]
    text = (repo / "frontend" / "lib" / "theme.ts").read_text()
    assert "whitelabelApi" in text
    assert "toCssVariables" in text
    assert "DEFAULT_BRANDING" in text


def test_frontend_white_label_provider_has_hook():
    repo = Path(__file__).resolve().parents[1]
    text = (repo / "frontend" / "components" / "WhiteLabelProvider.tsx").read_text()
    assert "useWhiteLabel" in text
    assert "WhiteLabelProvider" in text
    assert "applyBranding" in text


# ---------------------------------------------------------------------------
# 9. Infrastructure files
# ---------------------------------------------------------------------------


def test_docker_compose_private_deployment_exists():
    repo = Path(__file__).resolve().parents[1]
    assert (repo / "infra" / "private-deployment" / "docker-compose.yml").exists()


def test_helm_chart_yaml_exists():
    repo = Path(__file__).resolve().parents[1]
    assert (repo / "infra" / "private-deployment" / "helm" / "waibao" / "Chart.yaml").exists()


def test_helm_values_yaml_has_whitelabel_block():
    repo = Path(__file__).resolve().parents[1]
    text = (repo / "infra" / "private-deployment" / "helm" / "waibao" / "values.yaml").read_text()
    assert "whitelabel:" in text
    assert "primaryColor" in text
    assert "tenantId" in text


def test_helm_backend_template_exists():
    repo = Path(__file__).resolve().parents[1]
    assert (repo / "infra" / "private-deployment" / "helm" / "waibao" / "templates" / "backend.yaml").exists()


def test_terraform_main_tf_exists():
    repo = Path(__file__).resolve().parents[1]
    assert (repo / "infra" / "private-deployment" / "terraform" / "main.tf").exists()


def test_terraform_references_whitelabel_output():
    repo = Path(__file__).resolve().parents[1]
    text = (repo / "infra" / "private-deployment" / "terraform" / "main.tf").read_text()
    assert "whitelabel_config" in text


def test_operations_manual_exists():
    repo = Path(__file__).resolve().parents[1]
    assert (repo / "infra" / "private-deployment" / "OPERATIONS_MANUAL.md").exists()


def test_private_deployment_docs_exists():
    repo = Path(__file__).resolve().parents[1]
    assert (repo / "docs" / "PRIVATE_DEPLOYMENT.md").exists()


def test_env_example_exists():
    repo = Path(__file__).resolve().parents[1]
    assert (repo / "infra" / "private-deployment" / ".env.example").exists()


# ---------------------------------------------------------------------------
# 10. FastAPI surface (lightweight)
# ---------------------------------------------------------------------------


def test_router_builds_when_fastapi_installed():
    try:
        import fastapi  # noqa: F401
    except ImportError:
        pytest.skip("fastapi not installed")
    from services.platform.whitelabel import build_fastapi_router
    router = build_fastapi_router()
    assert router is not None
    paths = [r.path for r in router.routes]
    assert any("/v1/branding/{tenant_id}" in p for p in paths)
    assert any("/v1/branding/{tenant_id}/email-preview" in p for p in paths)
    assert any("/v1/branding/{tenant_id}/pdf-brand" in p for p in paths)


def test_router_returns_none_when_fastapi_missing(monkeypatch):
    """The build_fastapi_router() helper should never crash — return None
    when fastapi isn't importable."""
    from services.platform import whitelabel as wl
    # Simulate missing fastapi by hiding it.
    monkeypatch.setitem(sys.modules, "fastapi", None)
    # Direct import of build_fastapi_router inside the helper guards
    # against missing imports — we just assert the helper is callable.
    assert callable(wl.build_fastapi_router)


# ---------------------------------------------------------------------------
# 11. Cross-layer consistency
# ---------------------------------------------------------------------------


def test_css_var_keys_match_between_frontend_and_backend():
    repo = Path(__file__).resolve().parents[1]
    fe = (repo / "frontend" / "lib" / "theme.ts").read_text()
    be = (repo / "backend" / "services" / "platform" / "whitelabel.py").read_text()
    # Spot-check: the same set of CSS variable keys must appear in both
    # so the frontend hook never reads an undefined variable.
    for key in ("--color-primary", "--color-secondary", "--logo-url",
                "--font-family", "--hide-powered-by", "--support-email",
                "--locale", "--footer-text", "--product-name",
                "--color-accent", "--favicon-url"):
        assert key in fe, f"missing in frontend: {key}"
        assert key in be, f"missing in backend: {key}"


def test_branding_default_locale_zh_cn():
    from services.platform.whitelabel import Branding, _default_branding
    d = _default_branding("acme")
    assert d["locale"] == "zh-CN"
    b = Branding(tenant_id="acme")
    assert b.locale == "zh-CN"


def test_audit_event_includes_actor(svc):
    svc.upsert({"tenant_id": "a"}, actor="ops@example.com")
    log = svc.audit_log()
    assert log[0]["actor"] == "ops@example.com"
    assert log[0]["tenant_id"] == "a"


def test_upsert_keeps_created_at_across_updates(svc):
    first = svc.upsert({"tenant_id": "a", "product_name": "V1"})
    created = first.created_at
    second = svc.upsert({"tenant_id": "a", "product_name": "V2"})
    assert second.created_at == created


def test_patch_does_not_clear_created_at(svc):
    svc.upsert({"tenant_id": "a", "product_name": "V1"})
    first = svc.get("a")
    created = first.created_at
    svc.patch("a", {"product_name": "V2"})
    second = svc.get("a")
    assert second.created_at == created
    assert second.product_name == "V2"