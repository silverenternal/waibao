"""
Onboarding + product tour tests — verify the components, hook and routes exist
and have the required structure. Component-level behavior is covered by Vitest
in frontend/tests/test_a11y.spec.ts and the in-product Playwright suite.
"""
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    p = REPO / rel
    assert p.exists(), f"missing {rel}"
    return p.read_text(encoding="utf-8")


def test_product_tour_component_exists_and_supports_keyboard():
    text = _read("frontend/components/ProductTour.tsx")
    for needle in (
        "TourStep",
        "ProductTourProps",
        "useEscapeToClose",
        "useFocusTrap",
        "role=\"dialog\"",
        "aria-modal",
        "ArrowRight",
        "ArrowLeft",
        "Home",
        "End",
    ):
        assert needle in text, f"ProductTour missing {needle}"


def test_onboarding_checklist_supports_both_roles():
    text = _read("frontend/components/OnboardingChecklist.tsx")
    for needle in (
        "role: \"jobseeker\" | \"employer\"",
        "useOnboarding",
        "Progress",
        "Sparkles",
    ):
        assert needle in text, f"OnboardingChecklist missing {needle}"


def test_onboarding_hook_persists_progress():
    text = _read("frontend/hooks/use-onboarding.ts")
    for needle in (
        "JOBSEEKER_STEPS",
        "EMPLOYER_STEPS",
        "STORAGE_KEY",
        "TOUR_KEY",
        "markProductTourDone",
        "isProductTourDone",
        "resetProductTour",
    ):
        assert needle in text, f"use-onboarding missing {needle}"


def test_welcome_pages_exist_both_personas():
    for path in (
        "frontend/app/(jobseeker)/onboarding/welcome/page.tsx",
        "frontend/app/(employer)/onboarding/welcome/page.tsx",
    ):
        text = _read(path)
        for needle in ("ProductTour", "OnboardingChecklist", "markProductTourDone"):
            assert needle in text, f"{path} missing {needle}"


def test_dashboards_auto_trigger_tour():
    for path in (
        "frontend/app/(jobseeker)/dashboard/page.tsx",
        "frontend/app/(employer)/dashboard/page.tsx",
    ):
        text = _read(path)
        for needle in ("isProductTourDone", "setTourOpen(true)", "ProductTour"):
            assert needle in text, f"{path} missing {needle}"


def test_onboarding_design_doc_exists():
    text = _read("docs/ONBOARDING_DESIGN.md")
    for section in ("Goals", "Tour Design Principles", "Onboarding Checklist", "Files"):
        assert section in text, f"ONBOARDING_DESIGN.md missing section {section}"


def test_tour_step_indicator_uses_aria_live():
    text = _read("frontend/components/ProductTour.tsx")
    assert 'aria-live' in text, "step indicator must be screen-reader announced"
