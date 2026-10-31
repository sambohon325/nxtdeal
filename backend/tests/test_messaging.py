"""
Tests for graph-native Communications (core/messaging.py, core/messaging_api.py,
core/ws_manager.py) -- session 28. Run from backend/ with `pytest`.
"""

import asyncio
import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger
from core import auth as auth_module
from core import messaging
from core import messaging_api
from core.ws_manager import manager as ws_manager
from core.permissions import ADMIN, OPERATIONS, SALES, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():

    ledger.reset()
    messaging.seed_channels()

    yield

    ledger.reset()


@pytest.fixture(autouse=True)
def fresh_credential_store():

    auth_module.credential_store.reset()

    yield

    auth_module.credential_store.reset()


@pytest.fixture(autouse=True)
def fresh_connections():

    ws_manager.reset()

    yield

    ws_manager.reset()


# --- Channels ---


def test_seed_channels_is_idempotent():

    before = len(ledger.get_all())

    messaging.seed_channels()
    messaging.seed_channels()

    assert len(ledger.get_all()) == before


def test_admin_sees_every_channel():

    channels = messaging.list_channels_for_role(ADMIN)

    assert {c["key"] for c in channels} == {"sales", "service", "managers"}


def test_sales_role_sees_sales_and_managers_not_service():

    channels = {c["key"] for c in messaging.list_channels_for_role(SALES)}

    assert "sales" in channels
    assert "managers" in channels
    assert "service" not in channels


def test_can_access_channel_denies_wrong_role():

    assert messaging.can_access_channel(SERVICE, "sales") is False
    assert messaging.can_access_channel(SERVICE, "service") is True


def test_can_access_channel_unknown_channel_key():

    assert messaging.can_access_channel(ADMIN, "not-a-real-channel") is False


def test_send_and_get_channel_messages_ordered():

    messaging.send_channel_message("sales", "EMP-00001", "first")
    messaging.send_channel_message("sales", "EMP-00002", "second")

    messages = messaging.get_channel_messages("sales")

    assert [m.attributes["content"] for m in messages] == ["first", "second"]


def test_channel_messages_scoped_to_their_own_channel():

    messaging.send_channel_message("sales", "EMP-00001", "sales msg")
    messaging.send_channel_message("service", "EMP-00002", "service msg")

    sales_messages = messaging.get_channel_messages("sales")

    assert len(sales_messages) == 1
    assert sales_messages[0].attributes["content"] == "sales msg"


def test_post_channel_message_api_denies_wrong_role():

    result = messaging_api.post_channel_message_api(
        "service", SALES, "EMP-00001", "hello"
    )

    assert "error" in result


def test_post_channel_message_api_rejects_empty_content():

    result = messaging_api.post_channel_message_api(
        "sales", SALES, "EMP-00001", "   "
    )

    assert "error" in result


def test_post_channel_message_api_success_shape():

    result = messaging_api.post_channel_message_api(
        "sales", SALES, "EMP-00001", "hello team"
    )

    assert "error" not in result
    assert result["content"] == "hello team"
    assert result["sender_id"] == "EMP-00001"
    assert result["channel_key"] == "sales"
    assert "id" in result


# --- Direct messages ---


def test_direct_messages_only_between_the_two_parties():

    messaging.send_direct_message("EMP-00001", "EMP-00002", "hi")
    messaging.send_direct_message("EMP-00001", "EMP-00003", "unrelated")

    thread = messaging.get_direct_messages("EMP-00001", "EMP-00002")

    assert len(thread) == 1
    assert thread[0].attributes["content"] == "hi"


def test_direct_messages_visible_regardless_of_who_sent_first():

    messaging.send_direct_message("EMP-00002", "EMP-00001", "reply")

    thread_a = messaging.get_direct_messages("EMP-00001", "EMP-00002")
    thread_b = messaging.get_direct_messages("EMP-00002", "EMP-00001")

    assert len(thread_a) == 1
    assert len(thread_b) == 1


def test_post_direct_message_api_rejects_empty_content():

    result = messaging_api.post_direct_message_api("EMP-00001", "EMP-00002", "")

    assert "error" in result


def test_list_recent_conversations_sorted_most_recent_first():

    messaging.send_direct_message("EMP-00001", "EMP-00002", "older")
    messaging.send_direct_message("EMP-00001", "EMP-00003", "newer")

    conversations = messaging.list_recent_conversations("EMP-00001")

    assert [c["employee_id"] for c in conversations] == ["EMP-00003", "EMP-00002"]


def test_list_recent_conversations_ignores_channel_messages():

    messaging.send_channel_message("sales", "EMP-00001", "not a dm")

    assert messaging.list_recent_conversations("EMP-00001") == []


# --- Directory ---


def test_list_directory_strips_secrets():

    auth_module.credential_store.set_credential(
        "EMP-00001", "temp-pass-123", SALES, email="a@example.com"
    )

    directory = messaging.list_directory()

    assert directory == [{"employee_id": "EMP-00001", "role": SALES, "name": None}]


def test_list_directory_uses_employee_entity_name_when_present():

    from core.entities import Entity
    from core.entity_types import EMPLOYEE

    ledger.add_entity(
        Entity(id="EMP-00001", entity_type=EMPLOYEE, attributes={"Name": "Sarah Chen"})
    )
    auth_module.credential_store.set_credential("EMP-00001", "x", FINANCE)

    directory = messaging.list_directory()

    assert directory[0]["name"] == "Sarah Chen"


# --- Connection manager ---


class _FakeWebSocket:

    def __init__(self):
        self.accepted = False
        self.sent = []

    async def accept(self):
        self.accepted = True

    async def send_json(self, payload):
        self.sent.append(payload)


def test_broadcast_channel_message_only_reaches_allowed_roles():
    """Plain sync test driving the async ConnectionManager via asyncio.run() rather than
    pytest.mark.asyncio -- this codebase has no pytest-asyncio dependency today and
    requirements.txt is already flagged elsewhere as unverified against a real
    environment (no sandbox to confirm a new plugin installs cleanly), so avoiding
    adding one just for these two tests."""

    async def scenario():

        auth_module.credential_store.set_credential("EMP-00001", "x", SALES, must_change_password=False)
        auth_module.credential_store.set_credential("EMP-00002", "x", SERVICE, must_change_password=False)

        sales_socket = _FakeWebSocket()
        service_socket = _FakeWebSocket()

        await ws_manager.connect("EMP-00001", sales_socket, auth_module.issue_token("EMP-00001", auth_module.credential_store.get_record("EMP-00001")["role"]))
        await ws_manager.connect("EMP-00002", service_socket, auth_module.issue_token("EMP-00002", auth_module.credential_store.get_record("EMP-00002")["role"]))

        await ws_manager.broadcast_channel_message("sales", {"event": "test"})

        assert len(sales_socket.sent) == 1
        assert len(service_socket.sent) == 0

    asyncio.run(scenario())


def test_broadcast_direct_message_reaches_both_participants():

    async def scenario():

        auth_module.credential_store.set_credential("EMP-00001", "Fictional2026!", SALES, must_change_password=False)
        auth_module.credential_store.set_credential("EMP-00002", "Fictional2026!", SERVICE, must_change_password=False)
        sender_socket = _FakeWebSocket()
        recipient_socket = _FakeWebSocket()

        await ws_manager.connect("EMP-00001", sender_socket, auth_module.issue_token("EMP-00001", auth_module.credential_store.get_record("EMP-00001")["role"]))
        await ws_manager.connect("EMP-00002", recipient_socket, auth_module.issue_token("EMP-00002", auth_module.credential_store.get_record("EMP-00002")["role"]))

        await ws_manager.broadcast_direct_message(
            "EMP-00001", "EMP-00002", {"event": "test"}
        )

        assert len(sender_socket.sent) == 1
        assert len(recipient_socket.sent) == 1

    asyncio.run(scenario())
