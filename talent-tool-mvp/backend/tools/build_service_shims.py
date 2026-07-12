#!/usr/bin/env python3
"""Generate shim files at services/<old>.py that re-export from
services/<domain>/<old>.py.  Mirrors REFACTOR_MAP.md v5.0 layout.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "services"

# (legacy module name -> new sub-package name)
SHIMS: list[tuple[str, str]] = [
    # jobseeker
    ("resume_parser", "jobseeker"),
    ("plan_tracker", "jobseeker"),
    ("learning_resources", "jobseeker"),
    ("offer_calculator", "jobseeker"),
    ("negotiation_advisor", "jobseeker"),
    ("ai_interviewer", "jobseeker"),
    ("video_processing", "jobseeker"),
    ("question_bank", "jobseeker"),
    ("profile_extractor", "jobseeker"),
    ("video_interview_service", "jobseeker"),
    # employer
    ("compliance_service", "employer"),
    ("ticket_service", "employer"),
    ("ats_sync", "employer"),
    ("ats_sync_scheduler", "employer"),
    ("channel_attribution", "employer"),
    ("recruitment_funnel", "employer"),
    ("corp_sync", "employer"),
    ("dingtalk_sync", "employer"),
    ("feishu_sync", "employer"),
    ("dingtalk_approval", "employer"),
    ("calendar_sync", "employer"),
    ("assessment_service", "employer"),
    ("background_check_service", "employer"),
    # matching
    ("feedback_loop", "matching"),
    ("calibration", "matching"),
    ("global_search", "matching"),
    # billing
    ("billing", "billing"),
    # observability
    ("telemetry", "observability"),
    ("metrics", "observability"),
    ("sentry", "observability"),
    ("audit", "observability"),
    ("llm_cache", "observability"),
    ("llm_budget", "observability"),
    ("cost_tracker", "observability"),
    # integrations
    ("collaboration_room", "integrations"),
    ("candidate_recommender", "integrations"),
    ("push_engine", "integrations"),
    ("job_subscription", "integrations"),
    ("api_key", "integrations"),
    ("persona_memory", "integrations"),
    ("pii_field_encryption", "integrations"),
    ("pilot_invitation", "integrations"),
    ("funnel_events", "integrations"),
    ("transcribe", "integrations"),
    ("file_storage", "integrations"),
    ("realtime_router", "integrations"),
    # platform (ab_test not in map but moved for consistency)
    ("ab_test", "platform"),
    ("i18n", "platform"),
    ("permissions", "platform"),
    ("handoff", "platform"),
    ("collection", "platform"),
    ("quote", "platform"),
    ("credit_code_validator", "platform"),
    ("crypto", "platform"),
    ("backup", "platform"),
    ("region_router", "platform"),
    ("region_config", "platform"),
]


def main() -> None:
    created = 0
    skipped = 0
    for name, domain in SHIMS:
        target = ROOT / f"{name}.py"
        if target.exists():
            skipped += 1
            continue
        body = (
            f'"""v5.0 shim — moved to services/{domain}/{name}.py.\n\n'
            f'This file is kept for backward compatibility (v5.0..v5.1).\n'
            f'New code should import from services.{domain}.{name} directly.\n'
            '"""\n'
            'from __future__ import annotations\n\n'
            f'from .{domain}.{name} import *  # noqa: F401,F403\n'
        )
        target.write_text(body, encoding="utf-8")
        created += 1
        print(f"  shim {name}.py -> {domain}.{name}")
    print(f"created={created}, skipped={skipped}")


if __name__ == "__main__":
    main()