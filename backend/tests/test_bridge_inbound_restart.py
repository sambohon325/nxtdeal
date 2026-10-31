from concurrent.futures import ThreadPoolExecutor

import pytest
from core import bridge_inbound as inbound, bridge_event_imports as imports, bridge_event_retention as retention, dealer_bridge as b
from core.dealeros import ledger
from tests.test_bridge_inbound import configured, delivery, ENDPOINT, KEY, bindings  # noqa: F401
from tests.test_bridge_restart import disk_graph, restart  # noqa: F401
from tests.test_bridge_sync import A, B, isolated  # noqa: F401


def test_receipt_survives_restart_rebind_and_finished_staging_cleanup(disk_graph):
    _, profile, _, _, verifier = configured()
    first = inbound.receive(*delivery())
    job = b.get(first["receipt_id"],"BridgeInboundDelivery")["job_id"]
    inbound.unbind(ENDPOINT)
    restart(disk_graph)
    with pytest.raises(ValueError): inbound.receive(*delivery())
    inbound.bind(ENDPOINT,profile_id=profile,revision="gateway-v1",environment="synthetic",verifier=verifier)
    assert inbound.receive(*delivery())["status"] == "already_received"
    imports.validate(A,job); imports.activate(B,job)
    review = retention.preview(A,job)
    retention.cleanup(B,job,review["review_token"],"Reviewed synthetic event staging retention")
    restart(disk_graph)
    assert inbound.receive(*delivery())["receipt_id"] == first["receipt_id"]
    assert imports.report(A,job)["receipt_integrity"] == "consistent"
    assert len([e for e in ledger.get_all().values() if e.entity_type == "BridgeEventJob"]) == 1
    from pathlib import Path
    saved = Path(disk_graph).read_text(encoding="utf-8")
    assert KEY not in saved and delivery()[3] not in saved


def test_simultaneous_identical_deliveries_create_one_durable_job(disk_graph):
    configured()
    values = delivery()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _:inbound.receive(*values),range(2)))
    assert {result["status"] for result in results} == {"received_for_review","already_received"}
    assert len({result["receipt_id"] for result in results}) == 1
    restart(disk_graph)
    assert len([e for e in ledger.get_all().values() if e.entity_type == "BridgeEventJob"]) == 1
    assert inbound.receive(*delivery())["status"] == "already_received"
