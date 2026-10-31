from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.kiosk import create_kiosk_router
from core.kiosk_request_limit import KioskRequestLimit
from core.kiosk_sessions import KioskSessions


def test_rolling_window_does_not_reset_at_clock_boundary(monkeypatch):
    now = 59.0
    monkeypatch.setattr('core.kiosk_request_limit.time.monotonic', lambda: now)
    limit = KioskRequestLimit()
    assert all(limit.allow('fictional-peer') for _ in range(60))
    now = 60.0
    assert not limit.allow('fictional-peer')
    assert limit.allow('other-peer')
    now = 119.0
    assert limit.allow('fictional-peer')
    assert len(limit._requests) == 2


def test_rotating_peers_cannot_exhaust_memory_or_bypass_global_budget(monkeypatch):
    now = 1.0
    monkeypatch.setattr('core.kiosk_request_limit.time.monotonic', lambda: now)
    limit = KioskRequestLimit()
    assert all(limit.allow(str(i)) for i in range(600))
    assert not any(limit.allow(str(i)) for i in range(600, 2000))
    assert len(limit._requests) == len(limit._peers) == 600
    now = 61.0
    assert limit.allow('fresh')
    assert len(limit._requests) == len(limit._peers) == 1


def test_concurrent_admission_preserves_per_peer_budget():
    limit = KioskRequestLimit()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: limit.allow('same-peer'), range(100)))
    assert sum(results) == 60


def test_missing_peer_uses_shared_bucket():
    limit = KioskRequestLimit()
    assert all(limit.allow(None) for _ in range(60))
    assert not limit.allow(None)


def test_http_limit_precedes_auth_and_body_and_ignores_forwarding_headers(monkeypatch):
    monkeypatch.setattr(KioskRequestLimit, 'PER_PEER', 3)
    app = FastAPI()
    app.include_router(create_kiosk_router(KioskSessions('synthetic'), enabled=True))
    with TestClient(app) as client:
        # All three endpoints share admission, even for unauthenticated traffic.
        for path in ('enroll', 'revoke', 'checkin'):
            assert client.post('/kiosk/' + path).status_code == 401
        for path in ('enroll', 'revoke', 'checkin'):
            result = client.post('/kiosk/' + path, content='not-json', headers={
                'X-Forwarded-For': path, 'Forwarded': 'for=fictional-' + path})
            assert result.status_code == 429
            assert result.json() == {'error': 'kiosk_request_limit'}
            assert result.headers['retry-after'] == '60'
            assert result.headers['cache-control'] == 'no-store'
