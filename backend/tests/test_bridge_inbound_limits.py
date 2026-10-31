"""Receiver resource bounds remain effective through disconnects and failures."""
import asyncio
from threading import BoundedSemaphore

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api.routers import bridge_inbound as route
from core import bridge_inbound as inbound
from core.dealeros import ledger
from tests.test_bridge_inbound import configured, delivery, ENDPOINT, bindings  # noqa: F401
from tests.test_bridge_inbound_http import headers, client
from tests.test_bridge_sync import isolated  # noqa: F401


def request(values, receive):
    return Request({"type":"http", "method":"POST", "path":"/",
        "headers":[(key.lower().encode(), value.encode()) for key,value in headers(values).items()]}, receive)


def test_stalled_body_times_out_and_releases_capacity(monkeypatch):
    configured()
    slots = BoundedSemaphore(1)
    monkeypatch.setattr(route, "_SLOTS", slots)
    monkeypatch.setattr(route, "_BODY_TIMEOUT_SECONDS", 0.01)

    async def run():
        async def stalled():
            await asyncio.Event().wait()
        with pytest.raises(HTTPException) as error:
            await route.receive_adf(ENDPOINT, request(delivery(), stalled))
        assert error.value.status_code == 408
    asyncio.run(run())
    assert slots.acquire(blocking=False)
    slots.release()
    assert not any(e.entity_type == "BridgeEventJob" for e in ledger.get_all().values())


def test_inflight_body_capacity_rejects_before_read_and_cancellation_releases_slot(monkeypatch):
    configured()
    slots = BoundedSemaphore(1)
    monkeypatch.setattr(route, "_SLOTS", slots)

    async def run():
        entered = asyncio.Event()
        async def stalled():
            entered.set()
            await asyncio.Event().wait()
        first = asyncio.create_task(route.receive_adf(ENDPOINT, request(delivery(), stalled)))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            async def unexpected_read():
                pytest.fail("Saturated receiver must reject before reading the request body")
            with pytest.raises(HTTPException) as error:
                await route.receive_adf(ENDPOINT, request(delivery("second"), unexpected_read))
            assert error.value.status_code == 503
            assert error.value.headers == {"Retry-After":"30"}
        finally:
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
        assert slots.acquire(blocking=False)
        slots.release()
    asyncio.run(run())
    assert not any(e.entity_type == "BridgeEventJob" for e in ledger.get_all().values())


def test_preflight_infrastructure_failure_is_redacted_retryable_and_releases_capacity(monkeypatch):
    configured()
    slots = BoundedSemaphore(1)
    monkeypatch.setattr(route, "_SLOTS", slots)
    def unavailable(endpoint):
        raise OSError("PRIVATE storage location and internal failure")
    monkeypatch.setattr(inbound, "accepting", unavailable)
    api, _ = client()
    values = delivery()
    result = api.post(f"/dealer-bridge/inbound/adf/{ENDPOINT}", headers=headers(values), content=values[4])
    assert result.status_code == 503 and result.headers["retry-after"] == "30"
    assert "PRIVATE" not in result.text
    assert slots.acquire(blocking=False)
    slots.release()
    assert not any(e.entity_type == "BridgeEventJob" for e in ledger.get_all().values())
