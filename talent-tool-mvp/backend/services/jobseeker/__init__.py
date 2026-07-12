"""v5.0 services/jobseeker/ public API."""
from __future__ import annotations

from .ai_interviewer import AnswerScore, FeedbackReport, DEFAULT_DIMENSIONS, AIInterviewer  # noqa: F401,F403
from .learning_resources import CACHE_TTL_SEC, DEFAULT_TIMEOUT, LearningResource, CourseraProvider, GeekbangProvider, JuejinProvider, ImoocProvider, BilibiliProvider, LearningResourcesService, get_learning_resources_service, reset_learning_resources_cache  # noqa: F401,F403
from .negotiation_advisor import NegotiationTactic, NegotiationScript, generate_negotiation_script  # noqa: F401,F403
from .offer_calculator import VALID_REGIONS, OfferInput, AnnualTotal, OfferComparison, RATE_TO_CNY, calculate_total_comp, compare_offers, get_market_band, compute_percentile  # noqa: F401,F403
from .plan_tracker import Milestone, PlanItem, CareerPlan, Checkin, Adjustment, PlanTrackerService, get_plan_tracker, reset_plan_tracker  # noqa: F401,F403
from .profile_extractor import extract_profile_from_text, extract_profile_from_url, ocr_image, parse_email, parse_phone  # noqa: F401,F403
from .question_bank import Question, ROLE_CATEGORIES, QuestionBank  # noqa: F401,F403
from .resume_parser import extract_text_from_url, parse_resume_from_url, parse_resume_sync  # noqa: F401,F403
from .video_interview_service import VideoInterviewService  # noqa: F401,F403
from .video_processing import VideoMeta, UploadTicket, make_object_key, create_upload_ticket, parse_video_meta, upload_to_storage, generate_thumbnail_url  # noqa: F401,F403

__all__: list[str] = [
    "AnswerScore",
    "FeedbackReport",
    "DEFAULT_DIMENSIONS",
    "AIInterviewer",
    "CACHE_TTL_SEC",
    "DEFAULT_TIMEOUT",
    "LearningResource",
    "CourseraProvider",
    "GeekbangProvider",
    "JuejinProvider",
    "ImoocProvider",
    "BilibiliProvider",
    "LearningResourcesService",
    "get_learning_resources_service",
    "reset_learning_resources_cache",
    "NegotiationTactic",
    "NegotiationScript",
    "generate_negotiation_script",
    "VALID_REGIONS",
    "OfferInput",
    "AnnualTotal",
    "OfferComparison",
    "RATE_TO_CNY",
    "calculate_total_comp",
    "compare_offers",
    "get_market_band",
    "compute_percentile",
    "Milestone",
    "PlanItem",
    "CareerPlan",
    "Checkin",
    "Adjustment",
    "PlanTrackerService",
    "get_plan_tracker",
    "reset_plan_tracker",
    "extract_profile_from_text",
    "extract_profile_from_url",
    "ocr_image",
    "parse_email",
    "parse_phone",
    "Question",
    "ROLE_CATEGORIES",
    "QuestionBank",
    "extract_text_from_url",
    "parse_resume_from_url",
    "parse_resume_sync",
    "VideoInterviewService",
    "VideoMeta",
    "UploadTicket",
    "make_object_key",
    "create_upload_ticket",
    "parse_video_meta",
    "upload_to_storage",
    "generate_thumbnail_url",
]
