"""Built-in workflow templates — ready-to-run DAG definitions.

Each template is a ``WorkflowDefinition`` ready to be registered with a
``WorkflowEngine`` or persisted to the ``workflows`` table. Templates are
exercised end-to-end in :mod:`backend.tests.test_workflow_engine` and the
frontend "Templates" gallery.
"""

from __future__ import annotations

from typing import List

from .workflow_engine import Edge, Node, WorkflowDefinition


# ---------------------------------------------------------------------------
# 1. New-employee onboarding
# ---------------------------------------------------------------------------
ONBOARDING_TEMPLATE = WorkflowDefinition(
    name="onboarding",
    version="1.0",
    description=(
        "Triggered by `employee.hired`: create profile, schedule 30/90/180 day "
        "check-ins, then run training."
    ),
    start_node="trigger",
    nodes=[
        Node(id="trigger", type="trigger",
             config={"event": "employee.hired"}),
        Node(id="create_profile", type="agent",
             config={"agent": "hr_service_agent",
                     "input": {"employee": "$__input__"},
                     "output": {"profile_id": "profile_id"}}),
        Node(id="delay_30d", type="delay", config={"seconds": 0,
             "label": "30-day check-in"}),
        Node(id="delay_90d", type="delay", config={"seconds": 0,
             "label": "90-day check-in"}),
        Node(id="delay_180d", type="delay", config={"seconds": 0,
             "label": "180-day check-in"}),
        Node(id="notify_30", type="action",
             config={"kind": "event",
                     "event": "onboarding.checkin",
                     "params": {"day": 30,
                                "profile_id": "$profile_id"}}),
        Node(id="notify_90", type="action",
             config={"kind": "event",
                     "event": "onboarding.checkin",
                     "params": {"day": 90,
                                "profile_id": "$profile_id"}}),
        Node(id="notify_180", type="action",
             config={"kind": "event",
                     "event": "onboarding.checkin",
                     "params": {"day": 180,
                                "profile_id": "$profile_id"}}),
        Node(id="training", type="agent",
             config={"agent": "intake_agent",
                     "input": {"profile_id": "$profile_id"},
                     "output": {"training_done": "training_done"}}),
    ],
    edges=[
        Edge(from_node="trigger", to_node="create_profile"),
        Edge(from_node="create_profile", to_node="delay_30d"),
        Edge(from_node="delay_30d", to_node="notify_30"),
        Edge(from_node="notify_30", to_node="delay_90d"),
        Edge(from_node="delay_90d", to_node="notify_90"),
        Edge(from_node="notify_90", to_node="delay_180d"),
        Edge(from_node="delay_180d", to_node="notify_180"),
        Edge(from_node="notify_180", to_node="training"),
    ],
    variables={"profile_id": None, "training_done": False},
)


# ---------------------------------------------------------------------------
# 2. Interview pipeline
# ---------------------------------------------------------------------------
INTERVIEW_TEMPLATE = WorkflowDefinition(
    name="interview_pipeline",
    version="1.0",
    description=(
        "Triggered by `candidate.applied`: initial screening, scheduling, "
        "interview, evaluation and decision notification."
    ),
    start_node="trigger",
    nodes=[
        Node(id="trigger", type="trigger",
             config={"event": "candidate.applied"}),
        Node(id="screening", type="agent",
             config={"agent": "resume_scorer",
                     "input": {"candidate": "$__input__"},
                     "output": {"score": "match_score"}}),
        Node(id="branch", type="condition",
             config={"expression": "match_score and match_score >= 0.6"}),
        Node(id="schedule", type="agent",
             config={"agent": "calendar_agent",
                     "input": {"candidate": "$__input__"},
                     "output": {"interview_id": "interview_id"}}),
        Node(id="interview", type="agent",
             config={"agent": "ai_interview_agent",
                     "input": {"interview_id": "$interview_id"},
                     "output": {"summary": "interview_summary"}}),
        Node(id="evaluate", type="agent",
             config={"agent": "mutual_evaluator",
                     "input": {"summary": "$interview_summary",
                                "candidate": "$__input__"},
                     "output": {"verdict": "verdict"}}),
        Node(id="notify", type="action",
             config={"kind": "event",
                     "event": "interview.completed",
                     "params": {"verdict": "$verdict",
                                "candidate": "$__input__"}}),
        Node(id="reject", type="action",
             config={"kind": "event",
                     "event": "interview.rejected",
                     "params": {"reason": "low_score",
                                "candidate": "$__input__"}}),
    ],
    edges=[
        Edge(from_node="trigger", to_node="screening"),
        Edge(from_node="screening", to_node="branch"),
        Edge(from_node="branch", to_node="schedule", condition="true"),
        Edge(from_node="branch", to_node="reject", condition="false"),
        Edge(from_node="schedule", to_node="interview"),
        Edge(from_node="interview", to_node="evaluate"),
        Edge(from_node="evaluate", to_node="notify"),
    ],
    variables={"match_score": 0.0, "interview_id": None,
               "interview_summary": None, "verdict": None},
)


# ---------------------------------------------------------------------------
# 3. Resume scoring with feedback
# ---------------------------------------------------------------------------
RESUME_SCORING_TEMPLATE = WorkflowDefinition(
    name="resume_scoring",
    version="1.0",
    description=(
        "Triggered by `resume.uploaded`: score and route to HR if high; "
        "auto-reject and email feedback otherwise."
    ),
    start_node="trigger",
    nodes=[
        Node(id="trigger", type="trigger",
             config={"event": "resume.uploaded"}),
        Node(id="score", type="agent",
             config={"agent": "resume_scorer",
                     "input": {"resume": "$__input__"},
                     "output": {"score": "match_score"}}),
        Node(id="branch", type="condition",
             config={"expression": "match_score and match_score >= 0.75"}),
        Node(id="route_hr", type="action",
             config={"kind": "ticket",
                     "params": {"queue": "hr_review",
                                "score": "$match_score",
                                "resume": "$__input__"}}),
        Node(id="feedback", type="action",
             config={"kind": "email",
                     "params": {"to": "$__input__.email",
                                "subject": "Thanks for applying",
                                "body": "We will keep your resume on file."}}),
    ],
    edges=[
        Edge(from_node="trigger", to_node="score"),
        Edge(from_node="score", to_node="branch"),
        Edge(from_node="branch", to_node="route_hr", condition="true"),
        Edge(from_node="branch", to_node="feedback", condition="false"),
    ],
    variables={"match_score": 0.0},
)


# ---------------------------------------------------------------------------
# 4. Bias review (multi-agent)
# ---------------------------------------------------------------------------
BIAS_REVIEW_TEMPLATE = WorkflowDefinition(
    name="bias_review",
    version="1.0",
    description=(
        "Triggered by `vision.submitted` or `strategy.submitted`: parallel "
        "review by 3 agents, then escalate to HRBP if any flag concerns."
    ),
    start_node="trigger",
    nodes=[
        Node(id="trigger", type="trigger",
             config={"event": "vision.submitted"}),
        Node(id="compliance_review", type="agent",
             config={"agent": "compliance_agent",
                     "input": {"doc": "$__input__"},
                     "output": {"flags": "compliance_flags"}}),
        Node(id="policy_review", type="agent",
             config={"agent": "policy_agent",
                     "input": {"doc": "$__input__"},
                     "output": {"flags": "policy_flags"}}),
        Node(id="hr_review", type="agent",
             config={"agent": "persona_agent",
                     "input": {"doc": "$__input__"},
                     "output": {"flags": "persona_flags"}}),
        Node(id="branch", type="condition",
             config={"expression":
                     "(compliance_flags or 0) + (policy_flags or 0) + (persona_flags or 0) > 0"}),
        Node(id="flag", type="action",
             config={"kind": "event",
                     "event": "bias.flagged",
                     "params": {"doc": "$__input__",
                                "compliance_flags": "$compliance_flags",
                                "policy_flags": "$policy_flags",
                                "persona_flags": "$persona_flags"}}),
        Node(id="notify_hrbp", type="action",
             config={"kind": "email",
                     "params": {"to": "hrbp@company",
                                "subject": "Bias review escalation",
                                "body": "Please review the flagged document."}}),
        Node(id="noop", type="action",
             config={"kind": "event",
                     "event": "bias.cleared",
                     "params": {"doc": "$__input__"}}),
    ],
    edges=[
        Edge(from_node="trigger", to_node="compliance_review"),
        Edge(from_node="trigger", to_node="policy_review"),
        Edge(from_node="trigger", to_node="hr_review"),
        Edge(from_node="compliance_review", to_node="branch"),
        Edge(from_node="policy_review", to_node="branch"),
        Edge(from_node="hr_review", to_node="branch"),
        Edge(from_node="branch", to_node="flag", condition="true"),
        Edge(from_node="flag", to_node="notify_hrbp"),
        Edge(from_node="branch", to_node="noop", condition="false"),
    ],
    variables={"compliance_flags": 0, "policy_flags": 0, "persona_flags": 0},
)


# ---------------------------------------------------------------------------
# 5. Ticket SLA escalation
# ---------------------------------------------------------------------------
SLA_TEMPLATE = WorkflowDefinition(
    name="ticket_sla",
    version="1.0",
    description=(
        "Triggered by `ticket.created`: countdown timer; when threshold is "
        "reached, escalate and notify; further delay triggers manager."
    ),
    start_node="trigger",
    nodes=[
        Node(id="trigger", type="trigger",
             config={"event": "ticket.created"}),
        Node(id="branch_threshold", type="condition",
             config={"expression": "sla_minutes >= 60"}),
        Node(id="wait_sla", type="delay",
             config={"seconds": 0, "label": "wait for SLA window"}),
        Node(id="branch_pending", type="condition",
             config={"expression": "status == 'pending'"}),
        Node(id="escalate", type="action",
             config={"kind": "event",
                     "event": "ticket.escalated",
                     "params": {"ticket": "$__input__",
                                "reason": "sla_warning"}}),
        Node(id="notify_responder", type="action",
             config={"kind": "email",
                     "params": {"to": "$__input__.assignee",
                                "subject": "Ticket SLA warning",
                                "body": "Please respond ASAP."}}),
        Node(id="escalate_manager", type="action",
             config={"kind": "event",
                     "event": "ticket.escalated",
                     "params": {"ticket": "$__input__",
                                "reason": "sla_breach"}}),
    ],
    edges=[
        Edge(from_node="trigger", to_node="branch_threshold"),
        Edge(from_node="branch_threshold", to_node="wait_sla", condition="true"),
        Edge(from_node="branch_threshold", to_node="notify_responder", condition="false"),
        Edge(from_node="wait_sla", to_node="branch_pending"),
        Edge(from_node="branch_pending", to_node="escalate", condition="true"),
        Edge(from_node="branch_pending", to_node="escalate_manager", condition="false"),
    ],
    variables={"sla_minutes": 30, "status": "pending"},
)


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

BUILTIN_TEMPLATES: List[WorkflowDefinition] = [
    ONBOARDING_TEMPLATE,
    INTERVIEW_TEMPLATE,
    RESUME_SCORING_TEMPLATE,
    BIAS_REVIEW_TEMPLATE,
    SLA_TEMPLATE,
]


def list_templates() -> List[dict]:
    """Return JSON-friendly metadata for the built-in templates."""
    return [
        {
            "name": wf.name,
            "version": wf.version,
            "description": wf.description,
            "node_count": len(wf.nodes),
            "edge_count": len(wf.edges),
            "start_node": wf.start_node,
            "definition": wf.to_dict(),
        }
        for wf in BUILTIN_TEMPLATES
    ]


def get_template(name: str) -> WorkflowDefinition:
    for wf in BUILTIN_TEMPLATES:
        if wf.name == name:
            return wf
    raise KeyError(f"unknown workflow template {name!r}")