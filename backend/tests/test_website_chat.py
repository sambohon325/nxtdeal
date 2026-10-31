"""
Test coverage for core/website_chat.py -- website live chat (REST + polling, not a
new WebSocket, per this module's own documented scoping decision), covering the
real session lifecycle (start/get/claim/close/list), visitor + employee messaging
(including the auto-claim-on-first-reply and reopen-a-closed-session behaviors),
the AI Receptionist auto-trigger + its real templated fallback (mocked client,
matching test_website_wizard.py's established _FakeClient pattern -- this sandbox
has no outbound OpenAI network access), the cross-site unified inbox, message
polling (the `since` filter), and promote_session_to_lead()'s real one-click CRM
tie (a real Lead via core.lead_intake.create_lead(), source="Website").

Added per BUILD_QUEUE.md's standing "convert to a real pytest suite as each module
gets touched" rule (CAF-00123 missing_test_coverage work).

No save_graph stubbing -- same lightweight pattern as
tests/test_workflow_automation.py/tests/test_manager_dashboard.py etc.: every
mutating call in this module is a single, human-paced action (starting a chat,
sending one message, claiming a session), never a bulk loop, so a real save() per
call is not a performance concern the way it is for a scan/seed function -- relies
purely on conftest.py's isolated tempdir DEALEROS_STORAGE_DIR for real, fast,
harmless disk writes.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import WEBSITE_CHAT_SESSION, WEBSITE_CHAT_MESSAGE, LEAD

import core.website_chat as wc
from core.websites import create_website, approve_website, update_admin_settings


@pytest.fixture(autouse=True)
def fresh_ledger(monkeypatch):
    from core import website_ai_credentials
    monkeypatch.setattr(website_ai_credentials,"completion",lambda site,**kw:wc.client.chat.completions.create(model="gpt-4o-mini",**kw))
    ledger.reset()
    yield
    ledger.reset()


# ---------------------------------------------------------------------------
# Fake OpenAI client, matching test_website_wizard.py's established shape
# exactly -- core.website_chat._draft_ai_reply()'s client.chat.completions.create()
# call has the identical response.choices[0].message.content -> json.loads() shape.
# ---------------------------------------------------------------------------

class _FakeCompletions:
    def __init__(self, response_content=None, raise_exc=None):
        self._response_content = response_content
        self._raise_exc = raise_exc
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self._raise_exc is not None:
            raise self._raise_exc
        return _FakeResponse(self._response_content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeClient:
    def __init__(self, response_content=None, raise_exc=None):
        self.chat = _FakeChat(_FakeCompletions(response_content, raise_exc))


def _published_site(name="Test Dealer", employee_id="EMP-1"):
    site = create_website(name, employee_id)
    approve_website(site.id, "EMP-ADMIN")
    return site


def _draft_site(name="Draft Dealer", employee_id="EMP-1"):
    return create_website(name, employee_id)


class TestListDepartments:

    def test_returns_the_real_four_departments(self):
        assert wc.list_departments() == ["sales", "service", "finance", "general"]

    def test_returns_a_fresh_list_each_call_not_the_shared_constant(self):
        result = wc.list_departments()
        result.append("mutated")
        assert wc.list_departments() == ["sales", "service", "finance", "general"]


class TestStartChatSession:

    def test_unknown_website_returns_site_not_found(self):
        result = wc.start_chat_session("SITE-99999")
        assert result == {"error": "Site not found"}

    def test_draft_unpublished_site_returns_site_not_found(self):
        site = _draft_site()
        result = wc.start_chat_session(site.id)
        assert result == {"error": "Site not found"}

    def test_published_site_creates_a_real_open_session(self):
        site = _published_site()
        session = wc.start_chat_session(site.id, visitor_name="Jane Buyer", visitor_email="jane@example.com")

        assert session.entity_type == WEBSITE_CHAT_SESSION
        assert session.attributes["website_id"] == site.id
        assert session.attributes["visitor_name"] == "Jane Buyer"
        assert session.attributes["visitor_email"] == "jane@example.com"
        assert session.attributes["status"] == "open"
        assert session.attributes["claimed_by"] is None
        assert session.attributes["lead_id"] is None
        assert session.attributes["last_ai_reply_at"] is None

    def test_department_defaults_to_general_when_not_supplied(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)
        assert session.attributes["department"] == "general"

    def test_department_defaults_to_general_when_unrecognized(self):
        site = _published_site()
        session = wc.start_chat_session(site.id, department="billing")
        assert session.attributes["department"] == "general"

    def test_a_real_recognized_department_is_stored_as_given(self):
        site = _published_site()
        session = wc.start_chat_session(site.id, department="service")
        assert session.attributes["department"] == "service"

    def test_no_initial_message_creates_zero_chat_messages(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)
        assert wc.list_messages(session.id) == []

    def test_initial_message_creates_one_real_visitor_message(self):
        site = _published_site()
        session = wc.start_chat_session(site.id, initial_message="Do you have any trucks?")

        messages = wc.list_messages(session.id)
        assert len(messages) == 1
        assert messages[0].attributes["sender"] == "visitor"
        assert messages[0].attributes["body"] == "Do you have any trucks?"


class TestGetSession:

    def test_unknown_id_returns_none(self):
        assert wc.get_session("WCS-99999") is None

    def test_wrong_entity_type_returns_none(self):
        ledger.add_entity(Entity(id="WCS-1", entity_type=WEBSITE_CHAT_MESSAGE, attributes={}))
        assert wc.get_session("WCS-1") is None

    def test_real_session_id_returns_the_entity(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)
        assert wc.get_session(session.id) is session


class TestSendVisitorMessage:

    def test_unknown_session_returns_error(self):
        result = wc.send_visitor_message("WCS-99999", "hello")
        assert result == {"error": "Chat session not found"}

    def test_empty_body_returns_error(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)
        result = wc.send_visitor_message(session.id, "   ")
        assert result == {"error": "Message body is required"}

    def test_message_body_is_stripped(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)
        message = wc.send_visitor_message(session.id, "  hi there  ")
        assert message.attributes["body"] == "hi there"

    def test_creates_a_real_visitor_message_with_no_sender_id(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)
        message = wc.send_visitor_message(session.id, "hello")

        assert message.entity_type == WEBSITE_CHAT_MESSAGE
        assert message.attributes["session_id"] == session.id
        assert message.attributes["sender"] == "visitor"
        assert message.attributes["sender_id"] is None

    def test_updates_session_last_message_at_and_updated_at(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)
        assert session.attributes["last_message_at"] is None

        wc.send_visitor_message(session.id, "hello")

        assert session.attributes["last_message_at"] is not None

    def test_closed_session_reopens_to_open_on_a_new_visitor_message(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)
        wc.close_session(session.id)
        assert session.attributes["status"] == "closed"

        wc.send_visitor_message(session.id, "still there?")

        assert session.attributes["status"] == "open"

    def test_ai_receptionist_off_by_default_no_ai_message_created(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)

        wc.send_visitor_message(session.id, "Any trucks in stock?")

        messages = wc.list_messages(session.id)
        assert len(messages) == 1
        assert all(m.attributes["sender"] != "ai" for m in messages)

    def test_ai_receptionist_enabled_and_unclaimed_auto_triggers_a_real_ai_reply(self, monkeypatch):
        monkeypatch.setattr(wc, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(wc, "record_call_attempt", lambda *a, **k: None)
        fake = _FakeClient(response_content='{"reply_text": "Yes! We have a great truck lineup."}')
        monkeypatch.setattr(wc, "client", fake)

        site = _published_site()
        update_admin_settings(site.id, {"ai_receptionist_enabled": True})
        session = wc.start_chat_session(site.id)

        wc.send_visitor_message(session.id, "Any trucks in stock?")

        messages = wc.list_messages(session.id)
        assert len(messages) == 2
        assert messages[0].attributes["sender"] == "visitor"
        assert messages[1].attributes["sender"] == "ai"
        assert messages[1].attributes["body"] == "Yes! We have a great truck lineup."
        assert messages[1].attributes["ai_generated"] is True

    def test_ai_receptionist_enabled_but_session_already_claimed_by_employee_does_not_fire(self, monkeypatch):
        # Docstring's own stated guarantee: never talk over a human who's already
        # engaged. A "claimed" session (status flipped by send_employee_message)
        # fails the status == "open" check even if the site has AI on.
        monkeypatch.setattr(wc, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(wc, "record_call_attempt", lambda *a, **k: None)
        monkeypatch.setattr(wc, "client", _FakeClient(response_content='{"reply_text": "hi"}'))

        site = _published_site()
        update_admin_settings(site.id, {"ai_receptionist_enabled": True})
        session = wc.start_chat_session(site.id)
        wc.send_employee_message(session.id, "EMP-1", "Hi, I'm here to help!")

        wc.send_visitor_message(session.id, "Great, thanks")

        messages = wc.list_messages(session.id)
        assert all(m.attributes["sender"] != "ai" for m in messages)

    def test_ai_receptionist_never_fires_once_an_employee_has_ever_replied_even_after_reopen(self, monkeypatch):
        # A session that was claimed, then closed, then reopened by a new visitor
        # message still has a real historical employee reply on file --
        # _has_employee_reply() looks across all messages, not just current status,
        # so the AI must stay silent even though status is back to "open".
        monkeypatch.setattr(wc, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(wc, "record_call_attempt", lambda *a, **k: None)
        monkeypatch.setattr(wc, "client", _FakeClient(response_content='{"reply_text": "hi"}'))

        site = _published_site()
        update_admin_settings(site.id, {"ai_receptionist_enabled": True})
        session = wc.start_chat_session(site.id)
        wc.send_employee_message(session.id, "EMP-1", "On it!")
        wc.close_session(session.id)

        wc.send_visitor_message(session.id, "Are you still there?")

        assert session.attributes["status"] == "open"
        messages = wc.list_messages(session.id)
        assert all(m.attributes["sender"] != "ai" for m in messages)


class TestSendEmployeeMessage:

    def test_unknown_session_returns_error(self):
        result = wc.send_employee_message("WCS-99999", "EMP-1", "hi")
        assert result == {"error": "Chat session not found"}

    def test_empty_body_returns_error(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)
        result = wc.send_employee_message(session.id, "EMP-1", "  ")
        assert result == {"error": "Message body is required"}

    def test_open_session_auto_claims_on_first_employee_reply(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)

        wc.send_employee_message(session.id, "EMP-1", "Hi there!")

        assert session.attributes["status"] == "claimed"
        assert session.attributes["claimed_by"] == "EMP-1"

    def test_closed_session_auto_claims_on_a_new_employee_reply(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)
        wc.close_session(session.id)

        wc.send_employee_message(session.id, "EMP-2", "Following up!")

        assert session.attributes["status"] == "claimed"
        assert session.attributes["claimed_by"] == "EMP-2"

    def test_already_claimed_session_keeps_original_owner_on_a_second_reply(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)
        wc.send_employee_message(session.id, "EMP-1", "First reply")

        wc.send_employee_message(session.id, "EMP-2", "Second reply")

        assert session.attributes["status"] == "claimed"
        assert session.attributes["claimed_by"] == "EMP-1"

    def test_creates_a_real_employee_message_with_sender_id(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)

        message = wc.send_employee_message(session.id, "EMP-7", "  Welcome!  ")

        assert message.entity_type == WEBSITE_CHAT_MESSAGE
        assert message.attributes["sender"] == "employee"
        assert message.attributes["sender_id"] == "EMP-7"
        assert message.attributes["body"] == "Welcome!"


class TestHasEmployeeReply:

    def test_no_messages_at_all_is_false(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)
        assert wc._has_employee_reply(session.id) is False

    def test_only_visitor_messages_is_false(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)
        wc.send_visitor_message(session.id, "hi")
        assert wc._has_employee_reply(session.id) is False

    def test_one_employee_message_is_true(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)
        wc.send_employee_message(session.id, "EMP-1", "hi")
        assert wc._has_employee_reply(session.id) is True

    def test_employee_reply_on_a_different_session_does_not_count(self):
        site = _published_site()
        session_1 = wc.start_chat_session(site.id)
        session_2 = wc.start_chat_session(site.id)
        wc.send_employee_message(session_1.id, "EMP-1", "hi")

        assert wc._has_employee_reply(session_2.id) is False


class TestAiRespondToSession:

    def test_unknown_session_returns_error(self):
        result = wc.ai_respond_to_session("WCS-99999")
        assert result == {"error": "Chat session not found"}

    def test_platform_flag_disabled_uses_the_real_fallback_and_records_blocked(self, monkeypatch):
        monkeypatch.setattr(wc, "is_feature_enabled", lambda key: False)
        calls = []
        monkeypatch.setattr(wc, "record_call_attempt", lambda feature, outcome, detail=None: calls.append((feature, outcome)))

        site = _published_site(name="Sam's Autos")
        session = wc.start_chat_session(site.id)

        message = wc.ai_respond_to_session(session.id)

        assert message.attributes["sender"] == "ai"
        assert message.attributes["ai_generated"] is True
        assert "Sam's Autos" in message.attributes["body"]
        assert calls == [("website_ai_receptionist", "blocked")]

    def test_successful_completion_posts_the_real_drafted_reply(self, monkeypatch):
        monkeypatch.setattr(wc, "is_feature_enabled", lambda key: True)
        calls = []
        monkeypatch.setattr(wc, "record_call_attempt", lambda feature, outcome, detail=None: calls.append((feature, outcome)))
        fake = _FakeClient(response_content='{"reply_text": "We have 3 trucks on the lot right now!"}')
        monkeypatch.setattr(wc, "client", fake)

        site = _published_site()
        session = wc.start_chat_session(site.id)

        message = wc.ai_respond_to_session(session.id)

        assert message.attributes["body"] == "We have 3 trucks on the lot right now!"
        assert calls == [("website_ai_receptionist", "succeeded")]

    def test_exception_falls_back_and_records_fell_back_with_detail(self, monkeypatch):
        monkeypatch.setattr(wc, "is_feature_enabled", lambda key: True)
        calls = []
        monkeypatch.setattr(wc, "record_call_attempt", lambda feature, outcome, detail=None: calls.append((feature, outcome, detail)))
        monkeypatch.setattr(wc, "client", _FakeClient(raise_exc=ConnectionError("no network")))

        site = _published_site(name="Sam's Autos")
        session = wc.start_chat_session(site.id)

        message = wc.ai_respond_to_session(session.id)

        assert "Sam's Autos" in message.attributes["body"]
        assert calls[0][1] == "fell_back"
        assert calls[0][2] == "Dealer provider unavailable"

    def test_empty_reply_text_falls_back_and_records_fell_back(self, monkeypatch):
        monkeypatch.setattr(wc, "is_feature_enabled", lambda key: True)
        calls = []
        monkeypatch.setattr(wc, "record_call_attempt", lambda feature, outcome, detail=None: calls.append((feature, outcome)))
        monkeypatch.setattr(wc, "client", _FakeClient(response_content='{"reply_text": "   "}'))

        site = _published_site(name="Sam's Autos")
        session = wc.start_chat_session(site.id)

        message = wc.ai_respond_to_session(session.id)

        assert "Sam's Autos" in message.attributes["body"]
        assert calls == [("website_ai_receptionist", "fell_back")]

    def test_updates_session_last_ai_reply_at_and_last_message_at(self, monkeypatch):
        monkeypatch.setattr(wc, "is_feature_enabled", lambda key: False)
        monkeypatch.setattr(wc, "record_call_attempt", lambda *a, **k: None)

        site = _published_site()
        session = wc.start_chat_session(site.id)
        assert session.attributes["last_ai_reply_at"] is None

        message = wc.ai_respond_to_session(session.id)

        assert session.attributes["last_ai_reply_at"] == message.attributes["created_at"]
        assert session.attributes["last_message_at"] == message.attributes["created_at"]

    def test_callable_on_an_already_claimed_session(self, monkeypatch):
        # Manual trigger by an employee remains available at any time, unlike the
        # auto-trigger inside send_visitor_message().
        monkeypatch.setattr(wc, "is_feature_enabled", lambda key: False)
        monkeypatch.setattr(wc, "record_call_attempt", lambda *a, **k: None)

        site = _published_site()
        session = wc.start_chat_session(site.id)
        wc.send_employee_message(session.id, "EMP-1", "hi")

        message = wc.ai_respond_to_session(session.id)
        assert message.attributes["sender"] == "ai"


class TestListUnifiedInbox:

    def test_no_filter_returns_every_session_across_every_site(self):
        site_1 = _published_site(name="Dealer 1")
        site_2 = _published_site(name="Dealer 2")
        s1 = wc.start_chat_session(site_1.id)
        s2 = wc.start_chat_session(site_2.id)

        result = wc.list_unified_inbox()

        ids = {s.id for s in result}
        assert ids == {s1.id, s2.id}

    def test_website_ids_filter_restricts_to_those_sites_only(self):
        site_1 = _published_site(name="Dealer 1")
        site_2 = _published_site(name="Dealer 2")
        s1 = wc.start_chat_session(site_1.id)
        wc.start_chat_session(site_2.id)

        result = wc.list_unified_inbox(website_ids=[site_1.id])

        assert [s.id for s in result] == [s1.id]

    def test_status_filter(self):
        site = _published_site()
        s1 = wc.start_chat_session(site.id)
        s2 = wc.start_chat_session(site.id)
        wc.close_session(s2.id)

        result = wc.list_unified_inbox(status="open")

        assert [s.id for s in result] == [s1.id]

    def test_department_filter(self):
        site = _published_site()
        s1 = wc.start_chat_session(site.id, department="service")
        wc.start_chat_session(site.id, department="sales")

        result = wc.list_unified_inbox(department="service")

        assert [s.id for s in result] == [s1.id]

    def test_sorted_by_most_recent_activity_first(self):
        site = _published_site()
        older = wc.start_chat_session(site.id)
        newer = wc.start_chat_session(site.id)
        wc.send_visitor_message(older.id, "first")
        wc.send_visitor_message(newer.id, "second")

        result = wc.list_unified_inbox()

        assert result[0].id == newer.id
        assert result[1].id == older.id


class TestListMessages:

    def test_no_messages_returns_empty_list(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)
        assert wc.list_messages(session.id) == []

    def test_only_returns_messages_for_the_given_session(self):
        site = _published_site()
        session_1 = wc.start_chat_session(site.id)
        session_2 = wc.start_chat_session(site.id)
        wc.send_visitor_message(session_1.id, "in session 1")
        wc.send_visitor_message(session_2.id, "in session 2")

        result = wc.list_messages(session_1.id)

        assert len(result) == 1
        assert result[0].attributes["body"] == "in session 1"

    def test_returns_oldest_first(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)
        wc.send_visitor_message(session.id, "first")
        wc.send_employee_message(session.id, "EMP-1", "second")

        result = wc.list_messages(session.id)

        assert [m.attributes["body"] for m in result] == ["first", "second"]

    def test_since_filter_only_returns_strictly_newer_messages(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)
        first = wc.send_visitor_message(session.id, "first")
        wc.send_employee_message(session.id, "EMP-1", "second")

        result = wc.list_messages(session.id, since=first.attributes["created_at"])

        assert len(result) == 1
        assert result[0].attributes["body"] == "second"

    def test_since_at_the_latest_timestamp_returns_nothing(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)
        last = wc.send_visitor_message(session.id, "only message")

        result = wc.list_messages(session.id, since=last.attributes["created_at"])

        assert result == []


class TestClaimSession:

    def test_unknown_session_returns_error(self):
        result = wc.claim_session("WCS-99999", "EMP-1")
        assert result == {"error": "Chat session not found"}

    def test_real_claim_sets_status_and_claimed_by(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)

        result = wc.claim_session(session.id, "EMP-3")

        assert result.attributes["status"] == "claimed"
        assert result.attributes["claimed_by"] == "EMP-3"

    def test_claiming_an_already_claimed_session_reassigns_the_owner(self):
        # Unlike send_employee_message()'s "first responder keeps it" rule,
        # claim_session() is an unconditional, explicit reassignment.
        site = _published_site()
        session = wc.start_chat_session(site.id)
        wc.claim_session(session.id, "EMP-1")

        wc.claim_session(session.id, "EMP-2")

        assert session.attributes["claimed_by"] == "EMP-2"


class TestCloseSession:

    def test_unknown_session_returns_error(self):
        result = wc.close_session("WCS-99999")
        assert result == {"error": "Chat session not found"}

    def test_real_close_sets_status_closed(self):
        site = _published_site()
        session = wc.start_chat_session(site.id)

        result = wc.close_session(session.id)

        assert result.attributes["status"] == "closed"


class TestListSessions:

    def test_no_filter_returns_every_session(self):
        site = _published_site()
        s1 = wc.start_chat_session(site.id)
        s2 = wc.start_chat_session(site.id)

        result = wc.list_sessions()

        assert {s.id for s in result} == {s1.id, s2.id}

    def test_website_id_filter(self):
        site_1 = _published_site(name="Dealer 1")
        site_2 = _published_site(name="Dealer 2")
        s1 = wc.start_chat_session(site_1.id)
        wc.start_chat_session(site_2.id)

        result = wc.list_sessions(website_id=site_1.id)

        assert [s.id for s in result] == [s1.id]

    def test_status_filter(self):
        site = _published_site()
        s1 = wc.start_chat_session(site.id)
        s2 = wc.start_chat_session(site.id)
        wc.close_session(s2.id)

        result = wc.list_sessions(status="closed")

        assert [s.id for s in result] == [s2.id]


class TestPromoteSessionToLead:

    def test_unknown_session_returns_error(self):
        result = wc.promote_session_to_lead("WCS-99999", "EMP-1")
        assert result == {"error": "Chat session not found"}

    def test_already_linked_session_returns_the_existing_lead_id_in_the_error(self):
        site = _published_site()
        session = wc.start_chat_session(site.id, visitor_email="jane@example.com")
        first = wc.promote_session_to_lead(session.id, "EMP-1")

        result = wc.promote_session_to_lead(session.id, "EMP-2")

        assert result == {"error": f"This chat is already linked to lead {first['lead_id']}"}

    def test_no_email_and_no_phone_anywhere_returns_error(self):
        site = _published_site()
        session = wc.start_chat_session(site.id, visitor_name="No Contact")

        result = wc.promote_session_to_lead(session.id, "EMP-1")

        assert result == {"error": "An email or phone number is required to create a lead"}

    def test_phone_alone_is_sufficient_with_no_email_anywhere(self):
        site = _published_site()
        session = wc.start_chat_session(site.id, visitor_name="Phone Only")

        result = wc.promote_session_to_lead(session.id, "EMP-1", phone="555-0100")

        assert "lead_id" in result

    def test_real_lead_created_with_website_source_and_session_linkage(self):
        site = _published_site()
        session = wc.start_chat_session(site.id, visitor_name="Jane Buyer", visitor_email="jane@example.com")

        result = wc.promote_session_to_lead(session.id, "EMP-9")

        lead = ledger.get_entity(result["lead_id"])
        assert lead.entity_type == LEAD
        assert lead.attributes["Source"] == "Website"
        assert lead.attributes["FirstName"] == "Jane"
        assert lead.attributes["LastName"] == "Buyer"
        assert lead.attributes["Email"] == "jane@example.com"
        assert lead.attributes["AssignedSalesperson"] == "EMP-9"
        assert lead.attributes["WebsiteChatSessionID"] == session.id
        assert lead.attributes["WebsiteID"] == site.id
        assert result["assigned_to"] == "EMP-9"

    def test_single_word_name_gets_an_empty_last_name(self):
        site = _published_site()
        session = wc.start_chat_session(site.id, visitor_name="Cher", visitor_email="cher@example.com")

        result = wc.promote_session_to_lead(session.id, "EMP-1")

        lead = ledger.get_entity(result["lead_id"])
        assert lead.attributes["FirstName"] == "Cher"
        assert lead.attributes["LastName"] == ""

    def test_no_name_anywhere_defaults_to_website_chat_visitor(self):
        site = _published_site()
        session = wc.start_chat_session(site.id, visitor_email="anon@example.com")

        result = wc.promote_session_to_lead(session.id, "EMP-1")

        lead = ledger.get_entity(result["lead_id"])
        assert lead.attributes["FirstName"] == "Website"
        assert lead.attributes["LastName"] == "Chat Visitor"

    def test_explicit_name_email_phone_override_the_sessions_captured_values(self):
        site = _published_site()
        session = wc.start_chat_session(site.id, visitor_name="Original Name", visitor_email="original@example.com")

        result = wc.promote_session_to_lead(
            session.id,
            "EMP-1",
            name="Override Name",
            email="override@example.com",
            phone="555-0199",
        )

        lead = ledger.get_entity(result["lead_id"])
        assert lead.attributes["FirstName"] == "Override"
        assert lead.attributes["LastName"] == "Name"
        assert lead.attributes["Email"] == "override@example.com"
        assert lead.attributes["Phone"] == "555-0199"

    def test_session_updated_to_claimed_with_lead_id_and_claimed_by(self):
        site = _published_site()
        session = wc.start_chat_session(site.id, visitor_email="jane@example.com")

        result = wc.promote_session_to_lead(session.id, "EMP-9")

        assert session.attributes["lead_id"] == result["lead_id"]
        assert session.attributes["status"] == "claimed"
        assert session.attributes["claimed_by"] == "EMP-9"
