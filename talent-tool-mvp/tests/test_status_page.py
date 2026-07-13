"""T2604 — Tests for the customer support integration.

Verifies the vendor-neutral protocol plus the stub adapter that backs the
in-app widget during local dev. Real Intercom/Zendesk adapters require
network access and creds, so they are validated separately by the smoke
suite (see tests/smoke/test_real_intercom_zendesk.py).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from services.support import (  # type: ignore
    TicketDraft, SupportTicket,
    get_default_client, reset_default_client_for_tests,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def stub_client():
    reset_default_client_for_tests()
    # Wipe INTERCOM / ZENDESK env so get_default_client() picks the stub.
    for k in ("INTERCOM_ACCESS_TOKEN", "ZENDESK_API_TOKEN", "ZENDESK_SUBDOMAIN"):
        os.environ.pop(k, None)
    client = get_default_client()
    assert client.name == "stub"
    return client


@pytest.fixture
def draft() -> TicketDraft:
    return TicketDraft(
        subject="Need help",
        body="The dashboard isn't loading",
        tenant_id="t-100",
        user_id="u-7",
        user_email="alice@example.com",
        user_name="Alice",
        tags=["feature:dashboard"],
        error_logs="NetworkError: timeout after 5s",
        extra_context={"page": "/dashboard", "ua": "Mozilla/5.0"},
    )


# ---------------------------------------------------------------------------
# Stub adapter
# ---------------------------------------------------------------------------

def test_stub_create_returns_ticket_with_minimum_fields(stub_client, draft):
    t = stub_client.create_ticket(draft)
    assert isinstance(t, SupportTicket)
    assert t.subject == "Need help"
    assert t.requester_email == "alice@example.com"
    assert t.status == "open"
    assert t.public_id.startswith("WAI-")
    assert t.url and t.url.endswith(t.public_id)


def test_stub_create_requires_user_email(stub_client):
    bad = TicketDraft(subject="x", body="y")
    with pytest.raises(ValueError):
        stub_client.create_ticket(bad)


def test_stub_get_ticket_roundtrip(stub_client, draft):
    created = stub_client.create_ticket(draft)
    fetched = stub_client.get_ticket(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.subject == created.subject


def test_stub_list_tickets_for_user_isolated_by_user_id(stub_client, draft):
    draft_a = draft
    draft_b = TicketDraft(
        subject="Other", body="Other body - unrelated",
        user_id="u-99", user_email="bob@example.com",
    )
    stub_client.create_ticket(draft_a)
    t = stub_client.create_ticket(draft_b)
    listing = stub_client.list_tickets_for_user("u-7", limit=10)
    assert len(listing) == 1
    assert listing[0].subject == "Need help"
    listing_b = stub_client.list_tickets_for_user("u-99", limit=10)
    assert any(x.id == t.id for x in listing_b)


def test_stub_reply_updates_status(stub_client, draft):
    created = stub_client.create_ticket(draft)
    replied = stub_client.reply_to_ticket(created.id, "thanks", from_agent=True)
    assert replied.status == "pending"
    again = stub_client.reply_to_ticket(created.id, "any update?", from_agent=False)
    assert again.status == "open"


def test_stub_sync_status_returns_get(stub_client, draft):
    created = stub_client.create_ticket(draft)
    assert stub_client.sync_status(created.id) == stub_client.get_ticket(created.id)


# ---------------------------------------------------------------------------
# Protocol round-trip
# ---------------------------------------------------------------------------

def test_ticket_draft_to_dict_redacts_none(draft):
    d = draft.to_dict()
    assert d["subject"] == "Need help"
    assert d["tenant_id"] == "t-100"
    assert "user_id" in d


def test_support_ticket_from_dict_defaults():
    t = SupportTicket.from_dict({"id": "abc", "public_id": "WAI-9", "subject": "x"})
    assert t.status == "open"
    assert t.requester_email is None
    assert t.created_at is None


# ---------------------------------------------------------------------------
# Env-driven adapter selection
# ---------------------------------------------------------------------------

def test_default_client_picks_stub_when_no_creds(monkeypatch):
    for k in ("INTERCOM_ACCESS_TOKEN", "ZENDESK_API_TOKEN", "ZENDESK_SUBDOMAIN"):
        monkeypatch.delenv(k, raising=False)
    reset_default_client_for_tests()
    c = get_default_client()
    assert c.name == "stub"
    reset_default_client_for_tests()


def test_default_client_picks_intercom_when_token(monkeypatch):
    monkeypatch.setenv("INTERCOM_ACCESS_TOKEN", "test-token")
    monkeypatch.delenv("ZENDESK_API_TOKEN", raising=False)
    monkeypatch.delenv("ZENDESK_SUBDOMAIN", raising=False)
    reset_default_client_for_tests()
    c = get_default_client()
    assert c.name == "intercom"
    reset_default_client_for_tests()
    monkeypatch.delenv("INTERCOM_ACCESS_TOKEN", raising=False)


def test_default_client_picks_zendesk_when_subdomain(monkeypatch):
    monkeypatch.delenv("INTERCOM_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("ZENDESK_API_TOKEN", "test-token")
    monkeypatch.setenv("ZENDESK_SUBDOMAIN", "waibao")
    monkeypatch.setenv("ZENDESK_USER_EMAIL", "ops@waibao.cn")
    reset_default_client_for_tests()
    c = get_default_client()
    assert c.name == "zendesk"
    reset_default_client_for_tests()
    monkeypatch.delenv("ZENDESK_API_TOKEN", raising=False)
    monkeypatch.delenv("ZENDESK_SUBDOMAIN", raising=False)
    monkeypatch.delenv("ZENDESK_USER_EMAIL", raising=False)


# ---------------------------------------------------------------------------
# Intercom dry-run (no network)
# ---------------------------------------------------------------------------

def test_intercom_dry_run_creates_local_ticket(monkeypatch):
    monkeypatch.setenv("INTERCOM_ACCESS_TOKEN", "ignored")
    monkeypatch.setenv("INTERCOM_DRY_RUN", "1")
    monkeypatch.delenv("ZENDESK_API_TOKEN", raising=False)
    monkeypatch.delenv("ZENDESK_SUBDOMAIN", raising=False)
    reset_default_client_for_tests()
    c = get_default_client()
    assert c.name == "intercom"
    t = c.create_ticket(TicketDraft(
        subject="x", body="y", user_email="a@b.com",
        tenant_id="t-1", user_id="u-1",
    ))
    assert t.id.startswith("dryrun-")
    reset_default_client_for_tests()
