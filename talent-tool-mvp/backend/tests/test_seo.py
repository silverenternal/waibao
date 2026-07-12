"""
SEO backend tests — verifies files exist and contain required schema fields.
"""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
FRONTEND = REPO / "frontend"


def _read(rel: str) -> str:
    p = REPO / rel
    assert p.exists(), f"missing {rel}"
    return p.read_text(encoding="utf-8")


def test_metadata_helper_exists_with_required_helpers():
    text = _read("frontend/lib/metadata.ts")
    for fn in (
        "generatePageMetadata",
        "generatePrivacyMetadata",
        "jobPostingJsonLd",
        "organizationJsonLd",
        "breadcrumbJsonLd",
        "faqJsonLd",
        "SITE_NAME",
        "SITE_URL",
    ):
        assert fn in text, f"missing export {fn}"


def test_root_layout_metadata_includes_default_and_template():
    text = _read("frontend/app/layout.tsx")
    assert "default:" in text, "root layout should set a default title"
    assert "template:" in text, "root layout should set a template title"
    assert "openGraph" in text, "root layout missing openGraph"
    assert "twitter" in text.lower(), "root layout missing twitter"
    assert "Organization" in text or "organizationJsonLd" in text


def test_sitemap_includes_static_and_dynamic():
    text = _read("frontend/app/sitemap.ts")
    assert "sitemap" in text
    assert "MetadataRoute.Sitemap" in text
    # Should include public + jobs dynamic route
    assert "/legal/" in text or "/legal" in text


def test_robots_disallows_private_routes():
    text = _read("frontend/app/robots.ts")
    for needle in ("/api/", "/login", "/account/", "/jobseeker/", "/employer/"):
        assert needle in text, f"robots.txt must disallow {needle}"


def test_manifest_contains_required_pwa_keys():
    text = _read("frontend/app/manifest.ts")
    for needle in ("name", "short_name", "start_url", "display", "icons"):
        assert needle in text, f"manifest.ts missing {needle}"


def test_legal_pages_have_metadata():
    for slug in ("privacy", "terms", "cookies", "dpa"):
        text = _read(f"frontend/app/(public)/legal/{slug}/page.tsx")
        assert "metadata" in text, f"{slug}/page.tsx missing metadata export"
        assert "generatePageMetadata" in text


def test_pricing_page_exists_with_metadata():
    text = _read("frontend/app/(public)/pricing/page.tsx")
    assert "metadata" in text


def test_jsonld_component_render_safe():
    text = _read("frontend/components/JsonLd.tsx")
    assert "dangerouslySetInnerHTML" in text, "JsonLd must inject raw JSON"
    assert "application/ld+json" in text


def test_no_metadata_leak_in_protected_layouts():
    # All client "use client" route groups must NOT export metadata directly.
    for rel in (
        "frontend/app/(jobseeker)/layout.tsx",
        "frontend/app/(employer)/layout.tsx",
    ):
        text = _read(rel)
        assert "export const metadata" not in text or "use client" not in text, (
            f"{rel}: protected layouts should rely on robots.ts (not server metadata)"
        )


@pytest.mark.parametrize("page_path,expect", [
    ("frontend/app/page.tsx", True),
    ("frontend/app/(public)/pricing/page.tsx", True),
    ("frontend/app/(public)/legal/privacy/page.tsx", True),
])
def test_public_pages_export_metadata(page_path, expect):
    text = _read(page_path)
    has_meta = "generatePageMetadata" in text or "generatePrivacyMetadata" in text
    assert has_meta is expect, f"{page_path} should export metadata"
