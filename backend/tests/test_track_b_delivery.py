"""
Track B delivery infrastructure (2026-07-25): the campaign message-delivery pipeline
(routes through the provider seam, per-recipient MessageSend log, real tracking hooks), the
provider-credential store + adapter factory (configuring http_webhook flips notifications
live), and the ads seam. All testable with fake/generic adapters -- no real credentials or
network. Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, MESSAGE_SEND
from core import campaigns
from core import integrations_registry as ir
from core import message_delivery as md
from core import provider_credentials as pc


@pytest.fixture(autouse=True)
def fresh():
    ledger.reset()
    ir._ADAPTERS.clear()      # the seam is process-global; isolate each test
    yield
    ledger.reset()
    ir._ADAPTERS.clear()


def _cust(cid, email="a@b.com", phone="5551112222"):
    ledger.add_entity(Entity(id=cid, entity_type=CUSTOMER, attributes={"name": "X", "email": email, "phone": phone}))


def _campaign(channel="email"):
    _cust("CUST-1")
    _cust("CUST-2", email="c@d.com", phone="5553334444")
    # "general" campaign targets all customers -> audience is CUST-1, CUST-2
    return campaigns.create_campaign("general", "Blast", channel, "EMP-1", {})


# --- delivery pipeline (simulated) ---

def test_deliver_writes_a_record_per_recipient_simulated():
    camp = _campaign("email")
    result = md.deliver_campaign(camp.id, actor="EMP-1")
    assert result["mode"] == "simulated"
    assert result["total_recipients"] == 2
    assert result["simulated"] == 2 and result["sent"] == 0
    sends = md.list_sends(camp.id)
    assert len(sends) == 2
    assert all(s.attributes["status"] == "simulated" for s in sends)
    assert camp.attributes["delivered_count"] == 2


def test_no_contact_recorded_when_channel_field_missing():
    _cust("CUST-1", email="", phone="")   # no email
    camp = campaigns.create_campaign("general", "Blast", "email", "EMP-1", {})
    result = md.deliver_campaign(camp.id, actor="EMP-1")
    assert result["no_contact"] == 1 and result["simulated"] == 0


def test_deliver_is_idempotent_unless_resend():
    camp = _campaign("email")
    md.deliver_campaign(camp.id)
    second = md.deliver_campaign(camp.id)          # everyone already sent -> skipped
    assert second["skipped"] == 2 and second["simulated"] == 0
    third = md.deliver_campaign(camp.id, resend=True)
    assert third["simulated"] == 2


def test_delivery_stats_and_tracking_hooks():
    camp = _campaign("email")
    md.deliver_campaign(camp.id)
    stats = md.get_delivery_stats(camp.id)
    assert stats["delivered"] == 2 and stats["open_rate"] == 0.0
    # A provider webhook would call mark_opened/mark_clicked.
    first = md.list_sends(camp.id)[0]
    md.mark_opened(first.id)
    md.mark_clicked(first.id)                       # implies opened too
    stats2 = md.get_delivery_stats(camp.id)
    assert stats2["opened"] == 1 and stats2["clicked"] == 1
    assert stats2["open_rate"] == 0.5


def test_unsupported_channel_recorded():
    _cust("CUST-1")
    camp = campaigns.create_campaign("general", "Mailer", "direct_mail", "EMP-1", {})
    result = md.deliver_campaign(camp.id)
    assert result["unsupported_channel"] == 1


# --- live path via a fake registered adapter ---

def test_live_adapter_marks_sends_as_sent():
    ir.register_adapter("notifications", lambda to, event, channels: {"provider": "fake", "delivered": True})
    camp = _campaign("email")
    result = md.deliver_campaign(camp.id)
    assert result["mode"] == "live"
    assert result["sent"] == 2 and result["simulated"] == 0
    assert all(s.attributes["status"] == "sent" for s in md.list_sends(camp.id))


# --- provider-credential store + adapter factory ---

def test_configure_http_webhook_goes_live_and_posts(monkeypatch):
    posted = {}

    def fake_post(url, payload, headers, timeout=10):
        posted["url"] = url
        posted["payload"] = payload
        posted["auth"] = headers.get("Authorization")
        return 200, "ok"

    monkeypatch.setattr(pc, "_http_post", fake_post)

    result = pc.configure_credential(
        "notifications", "http_webhook",
        {"url": "https://hooks.example.com/dealeros"},
        {"auth_header": "Bearer secret-token-1234"},
        "EMP-ADMIN",
    )
    assert result["live"] is True
    assert ir.is_live("notifications") is True

    # A campaign send now hits the real (fake) HTTP path and records "sent".
    camp = _campaign("email")
    r = md.deliver_campaign(camp.id)
    assert r["mode"] == "live" and r["sent"] == 2
    assert posted["url"] == "https://hooks.example.com/dealeros"
    assert posted["auth"] == "Bearer secret-token-1234"


def test_unknown_provider_stores_but_stays_simulated():
    result = pc.configure_credential("notifications", "twilio", {}, {"account_sid": "AC123", "auth_token": "xyz"}, "EMP-ADMIN")
    assert result["live"] is False and result["has_builder"] is False
    assert ir.is_live("notifications") is False


def test_secrets_are_masked_on_read():
    pc.configure_credential("notifications", "twilio", {}, {"auth_token": "supersecretvalue"}, "EMP-ADMIN")
    creds = pc.list_credentials()
    assert creds[0]["secrets"]["auth_token"].startswith("****")
    assert "supersecretvalue" not in creds[0]["secrets"]["auth_token"]


def test_remove_credential_returns_to_simulated(monkeypatch):
    monkeypatch.setattr(pc, "_http_post", lambda url, payload, headers, timeout=10: (200, "ok"))
    pc.configure_credential("notifications", "http_webhook", {"url": "https://x"}, {}, "EMP-ADMIN")
    assert ir.is_live("notifications") is True
    out = pc.remove_credential("notifications")
    assert out["live"] is False and ir.is_live("notifications") is False


def test_provider_slots_flag_shippable_builders():
    slots = pc.provider_slots()
    notif = {s["provider"]: s["has_builder"] for s in slots["notifications"]}
    assert notif["http_webhook"] is True
    assert notif["twilio"] is False


# --- ads seam ---

def test_ad_launch_routes_through_seam_simulated():
    from core import advertising
    ad = advertising.create_ad_campaign("EMP-1", "meta", "traffic", "Spring Push", {"headline": "Hi", "daily_budget": 50})
    launched = advertising.launch_ad_campaign(ad.id)
    assert launched.attributes["status"] == "active"
    assert launched.attributes["publish_mode"] == "simulated"


def test_ad_launch_live_when_adapter_registered():
    from core import advertising
    ir.register_adapter("ads", lambda spec: {"provider": "meta", "published": True})
    ad = advertising.create_ad_campaign("EMP-1", "meta", "traffic", "Spring Push", {"headline": "Hi", "daily_budget": 50})
    launched = advertising.launch_ad_campaign(ad.id)
    assert launched.attributes["publish_mode"] == "live"


def test_campaign_suppression_is_failed_not_sent_or_delivered():
    camp = _campaign('email')
    ledger.get_entity('CUST-1').attributes['DoNotContact'] = True
    calls = []
    ir.register_adapter('notifications', lambda to, event, channels: calls.append(to) or {'delivered': True})
    result = md.deliver_campaign(camp.id)
    assert result['failed'] == 1 and result['sent'] == 1
    assert calls == ['c@d.com']
    suppressed = next(s for s in md.list_sends(camp.id) if s.attributes['recipient_id'] == 'CUST-1')
    assert suppressed.attributes['status'] == 'failed'
    assert 'suppressed' in suppressed.attributes['error']
    assert camp.attributes['delivered_count'] == 1
    assert md.get_delivery_stats(camp.id)['delivered'] == 1


@pytest.mark.parametrize('response', [{'error': 'denied', 'simulated': True}, {'dispatched': False}, None, 'bad-result'])
def test_campaign_denied_or_invalid_dispatch_never_counts_as_sent(response):
    camp = _campaign('email')
    ir.register_adapter('notifications', lambda *a: response)
    result = md.deliver_campaign(camp.id)
    assert result['failed'] == 2
    assert result['sent'] == result['simulated'] == 0
    assert camp.attributes['delivered_count'] == 0


@pytest.mark.parametrize('response', [{}, {'provider': 'fake'}, {'delivered': False}, {'sent': False},
                                     {'delivered': 'true'}, {'simulated': 'false'},
                                     {'delivered': True, 'status': 'rejected'}, {'simulated': True, 'sent': False},
                                     {'simulated': 0, 'sent': True}])
def test_campaign_requires_unambiguous_positive_acknowledgement(response):
    camp = _campaign('email')
    ir.register_adapter('notifications', lambda *a: response)
    result = md.deliver_campaign(camp.id)
    assert result['failed'] == 2
    assert result['sent'] == result['simulated'] == 0
    assert camp.attributes['delivered_count'] == 0


@pytest.mark.parametrize('status', ['accepted', 'queued', 'pending'])
def test_provider_queue_acceptance_is_not_sent_delivery(status):
    camp = _campaign('email')
    ir.register_adapter('notifications', lambda *a: {'simulated': False, 'status': status})
    result = md.deliver_campaign(camp.id)
    assert result['queued'] == 2
    assert result['sent'] == result['simulated'] == 0
    assert camp.attributes['delivered_count'] == 0
    assert md.get_delivery_stats(camp.id)['delivered'] == 0
