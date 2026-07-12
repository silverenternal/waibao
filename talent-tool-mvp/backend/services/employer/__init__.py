"""v5.0 services/employer/ public API."""
from __future__ import annotations

from .assessment_service import AssessmentService  # noqa: F401,F403
from .ats_sync import CandidateRecord, JobRecord, SyncRunResult, CandidateStore, JobStore, SyncLogStore, ConflictStore, make_provider, ATSSyncEngine  # noqa: F401,F403
from .ats_sync_scheduler import ATSSyncScheduler  # noqa: F401,F403
from .background_check_service import DEFAULT_CHECK_TYPES, BackgroundCheckService  # noqa: F401,F403
from .calendar_sync import CalendarEvent, CalendarSyncResult, CalendarSyncService  # noqa: F401,F403
from .channel_attribution import DEFAULT_REVENUE_PER_HIRE_CENTS, ChannelAttribution, ChannelROIReport, ChannelAttributionService  # noqa: F401,F403
from .compliance_service import ComplianceVerdict, assess_company, normalize_for_compare, verify_credential_against_lookup, compute_expiry_alerts, list_expiry_alerts  # noqa: F401,F403
from .corp_sync import ROLE_BOSS, ROLE_HR, ROLE_DEPT_HEAD, ROLE_EMPLOYEE, CorpUser, CorpDept, SyncResult, CorpClient, CorpSyncService  # noqa: F401,F403
from .dingtalk_approval import DEFAULT_TEMPLATE_ID, map_ticket_to_form, submit_ticket_approval, update_instance_result  # noqa: F401,F403
from .dingtalk_sync import DINGTALK_API_BASE, HttpClient, DingTalkCorpClient, DingTalkApproval  # noqa: F401,F403
from .feishu_sync import FEISHU_API_BASE, HttpClient, FeishuCorpClient, FeishuApproval  # noqa: F401,F403
from .recruitment_funnel import StageMetric, FunnelStages, RecruitmentFunnel, stage_conversion_rates  # noqa: F401,F403
from .ticket_service import TICKET_STATUSES, TICKET_PRIORITIES, DEFAULT_SLA_HOURS, Ticket, TicketError, InvalidTransitionError, compute_sla_due_at, compute_sla_due_from_rules, is_valid_transition, assert_valid_transition, create_ticket, get_ticket, list_tickets, list_my_tickets, update_ticket_meta, transition_status, add_comment, list_comments, get_timeline, list_overdue_tickets  # noqa: F401,F403

__all__: list[str] = [
    "AssessmentService",
    "CandidateRecord",
    "JobRecord",
    "SyncRunResult",
    "CandidateStore",
    "JobStore",
    "SyncLogStore",
    "ConflictStore",
    "make_provider",
    "ATSSyncEngine",
    "ATSSyncScheduler",
    "DEFAULT_CHECK_TYPES",
    "BackgroundCheckService",
    "CalendarEvent",
    "CalendarSyncResult",
    "CalendarSyncService",
    "DEFAULT_REVENUE_PER_HIRE_CENTS",
    "ChannelAttribution",
    "ChannelROIReport",
    "ChannelAttributionService",
    "ComplianceVerdict",
    "assess_company",
    "normalize_for_compare",
    "verify_credential_against_lookup",
    "compute_expiry_alerts",
    "list_expiry_alerts",
    "ROLE_BOSS",
    "ROLE_HR",
    "ROLE_DEPT_HEAD",
    "ROLE_EMPLOYEE",
    "CorpUser",
    "CorpDept",
    "SyncResult",
    "CorpClient",
    "CorpSyncService",
    "DEFAULT_TEMPLATE_ID",
    "map_ticket_to_form",
    "submit_ticket_approval",
    "update_instance_result",
    "DINGTALK_API_BASE",
    "HttpClient",
    "DingTalkCorpClient",
    "DingTalkApproval",
    "FEISHU_API_BASE",
    "HttpClient",
    "FeishuCorpClient",
    "FeishuApproval",
    "StageMetric",
    "FunnelStages",
    "RecruitmentFunnel",
    "stage_conversion_rates",
    "TICKET_STATUSES",
    "TICKET_PRIORITIES",
    "DEFAULT_SLA_HOURS",
    "Ticket",
    "TicketError",
    "InvalidTransitionError",
    "compute_sla_due_at",
    "compute_sla_due_from_rules",
    "is_valid_transition",
    "assert_valid_transition",
    "create_ticket",
    "get_ticket",
    "list_tickets",
    "list_my_tickets",
    "update_ticket_meta",
    "transition_status",
    "add_comment",
    "list_comments",
    "get_timeline",
    "list_overdue_tickets",
]
