"""Bounded delivery review metadata for the currently selected Chrono destination."""
from collections import Counter
from core import dealer_bridge as bridge, bridge_chrono as outbox
from core.bridge_contracts import timestamp
from core.dealeros import ledger

STATES = frozenset({"unacknowledged", "all", "blocked", "retrying", "in_flight", "delivered"})


def read(actor, status="unacknowledged", limit=25, before_id=None):
    bridge.authorize(actor)
    if status not in STATES or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Bounded delivery review filters required")
    if before_id is not None and (not isinstance(before_id,str) or not 1 <= len(before_id) <= 120):
        raise ValueError("Use a delivery cursor from the selected destination")
    with bridge.LOCK:
        config = outbox.status(actor)
        destination = config["authorized_sink"]
        events = {event.id:event for event in outbox._events()}
        records, excluded = [], 0
        for record in ledger.get_all().values():
            value = record.attributes
            if (record.entity_type != "BridgeChronoDelivery" or value.get("workspace_id") != ledger.tenant.workspace_id or
                    (value.get("sink_name"),value.get("sink_revision")) != (destination["name"],destination["revision"])):
                continue
            event = events.get(value.get("event_id"))
            if event is None or record.id != outbox.receipt_id(event.id,destination["name"],destination["revision"]):
                excluded += 1
                continue
            records.append(record)
        # Observation import order is immutable across delivery attempts/retries.
        def order(record):
            event = events[record.attributes["event_id"]]
            return timestamp(event.attributes["import_timestamp"]), event.id
        anchor = None
        if before_id is not None:
            cursor = next((record for record in records if record.id == before_id),None)
            if cursor is None: raise ValueError("Delivery cursor does not belong to the selected destination")
            anchor = order(cursor)
        counts = dict(Counter(record.attributes["status"] for record in records))
        matching = [record for record in records if status == "all" or
                    (record.attributes["status"] != "delivered" if status == "unacknowledged" else record.attributes["status"] == status)]
        eligible = sorted((record for record in matching if anchor is None or order(record) < anchor),key=order,reverse=True)
        selected = eligible[:limit]
        receipts = []
        for record in selected:
            value = record.attributes
            active_lease = bool(value.get("lease_until") and timestamp(value["lease_until"]) > outbox.utcnow())
            receipts.append({"id":record.id,"event_id":value["event_id"],"status":value["status"],
                "attempts":value["attempts"],"last_attempt_at":value.get("last_attempt_at"),
                "next_attempt_at":value.get("next_attempt_at"),"acknowledged_at":value.get("acknowledged_at"),
                "last_error":value.get("last_error"),"retry_available":config["effective_status"] == "ready" and
                value["status"] != "delivered" and not active_lease})
        return {"receipts":receipts,"status_counts":counts,"matching_receipts":len(matching),
            "next_before_id":selected[-1].id if len(eligible) > len(selected) else None,
            "excluded_receipts":excluded,"destination":destination,"effective_status":config["effective_status"],
            "reason":config["reason"],"notice":"Recorded delivery attempts only, ordered by observation import time. Observations never attempted have no receipt here. Live results can change; refresh for newly attempted observations. Review does not deliver or authorize data."}
