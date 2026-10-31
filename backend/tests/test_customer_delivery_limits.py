"""Synthetic time/concurrency checks; no real provider requests."""
from concurrent.futures import ThreadPoolExecutor
from core import customer_delivery_limits as limits


def test_recipient_limit_is_atomic_across_concurrent_accounts():
    budget = limits.DeliveryBudget()
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: budget.reserve('email', 'fixture@example.com'), range(30)))
    assert sum(results) == 3
    assert all(isinstance(key, bytes) and len(key) == 32 for _, key in budget._events)


def test_contact_budget_expires_at_exact_window(monkeypatch):
    now = [1000]
    monkeypatch.setattr(limits.time, 'monotonic', lambda: now[0])
    budget = limits.DeliveryBudget()
    assert all(budget.reserve('sms', '+15555550123') for _ in range(3))
    now[0] = 1899
    assert not budget.reserve('sms', '+15555550123')
    now[0] = 1900
    assert budget.reserve('sms', '+15555550123')
    assert len(budget._events) == 1


def test_global_budget_limits_distinct_contacts_and_bounds_memory(monkeypatch):
    now = [1000]
    monkeypatch.setattr(limits.time, 'monotonic', lambda: now[0])
    budget = limits.DeliveryBudget()
    for minute in range(20):
        for i in range(60):
            assert budget.reserve('email', f'{minute}-{i}@example.com')
        assert not budget.reserve('sms', '+15555550123')
        assert len(budget._events) <= 900
        now[0] += 60
