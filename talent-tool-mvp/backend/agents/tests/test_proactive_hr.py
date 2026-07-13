"""T3709 - daily suggestions tests."""
import pytest
from services.daily_suggestions import (
    generate_suggestions, priority_summary,
    ACTION_OFFER, ACTION_INTERVIEW, ACTION_TICKET, ACTION_CARE, ACTION_REVIEW,
)


class TestGenerateSuggestions:
    def test_empty(self):
        assert generate_suggestions() == []

    def test_offer_suggestion(self):
        sugs = generate_suggestions(pending_offers=[
            {"candidate_name": "Alice", "days_waiting": 5,
             "candidate_id": "c1", "role": "前端"}
        ])
        assert any(s.action_type == ACTION_OFFER for s in sugs)

    def test_offer_low_priority(self):
        sugs = generate_suggestions(pending_offers=[
            {"candidate_name": "Bob", "days_waiting": 1,
             "candidate_id": "c2", "role": "后端"}
        ])
        offer_sugs = [s for s in sugs if s.action_type == ACTION_OFFER]
        assert offer_sugs[0].priority == 2

    def test_offer_high_priority(self):
        sugs = generate_suggestions(pending_offers=[
            {"candidate_name": "C", "days_waiting": 5, "candidate_id": "x"}
        ])
        offer = [s for s in sugs if s.action_type == ACTION_OFFER][0]
        assert offer.priority == 1

    def test_interview_suggestion(self):
        sugs = generate_suggestions(pending_interviews=[
            {"candidate_name": "X", "scheduled_at": "2099-01-01T10:00:00",
             "candidate_id": "c"}
        ])
        assert any(s.action_type == ACTION_INTERVIEW for s in sugs)

    def test_ticket_suggestion(self):
        sugs = generate_suggestions(open_tickets=[{"id": "T1", "age_hours": 24}])
        assert any(s.action_type == ACTION_TICKET for s in sugs)

    def test_ticket_high_priority_after_48h(self):
        sugs = generate_suggestions(open_tickets=[{"id": "T1", "age_hours": 60}])
        ticket = [s for s in sugs if s.action_type == ACTION_TICKET][0]
        assert ticket.priority == 1

    def test_care_suggestion(self):
        sugs = generate_suggestions(waiting_candidates=[
            {"name": "D", "id": "c", "days_waiting": 7}
        ])
        assert any(s.action_type == ACTION_CARE for s in sugs)

    def test_jd_review(self):
        sugs = generate_suggestions(stale_jds=[
            {"title": "前端", "age_days": 14, "id": "r1"}
        ])
        assert any(s.action_type == ACTION_REVIEW for s in sugs)

    def test_priority_sort(self):
        sugs = generate_suggestions(
            pending_offers=[{"candidate_name": "X", "days_waiting": 5,
                             "candidate_id": "c"}],
            open_tickets=[{"id": "T1", "age_hours": 60}],
        )
        priorities = [s.priority for s in sugs]
        assert priorities == sorted(priorities)

    def test_limit_3_offers(self):
        offers = [{"candidate_name": str(i), "days_waiting": 1,
                   "candidate_id": f"c{i}"} for i in range(10)]
        sugs = generate_suggestions(pending_offers=offers)
        offer_sugs = [s for s in sugs if s.action_type == ACTION_OFFER]
        assert len(offer_sugs) == 3


class TestPrioritySummary:
    def test_empty(self):
        assert priority_summary([]) == {}

    def test_groups_by_priority(self):
        sugs = generate_suggestions(
            open_tickets=[{"id": "T1", "age_hours": 60},
                          {"id": "T2", "age_hours": 1}],
        )
        s = priority_summary(sugs)
        assert s

    def test_total_count(self):
        sugs = generate_suggestions(
            open_tickets=[{"id": "T1", "age_hours": 60}],
            stale_jds=[{"title": "X", "age_days": 1}],
        )
        s = priority_summary(sugs)
        total = sum(s.values())
        assert total == len(sugs)


@pytest.mark.parametrize("payload", [
    [{"candidate_name": "X", "days_waiting": 1, "candidate_id": "c"}],
    [{"id": "T", "age_hours": 1}],
    [{"name": "X", "id": "c", "days_waiting": 1}],
    [{"title": "X", "age_days": 1, "id": "r"}],
    [{"candidate_name": "X", "scheduled_at": "2099-01-01T10:00:00",
      "candidate_id": "c"}],
])
def test_each_payload_type(payload):
    """Test each suggestion source individually."""
    candidates = ["pending_offers", "pending_interviews", "open_tickets",
                  "waiting_candidates", "stale_jds"]
    # Try each slot
    for name in candidates:
        kwargs = {name: payload}
        try:
            sugs = generate_suggestions(**kwargs)
            # May or may not produce suggestions - just must not raise
        except Exception as e:
            pytest.fail(f"{name}: {e}")
