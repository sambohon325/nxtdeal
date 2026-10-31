"""Lifecycle failure rehearsal with fake workers only: never start real schedulers."""
import asyncio
import importlib

import pytest

app_module = importlib.import_module('api.app')
NAMES = ['bot', 'compliance', 'agent_events', 'sales_sequence_scheduler',
         'dealer_cloud', 'bridge_sync', 'bridge_chrono']


def workers(monkeypatch, fail_start=None, fail_stop=None):
    events = []
    monkeypatch.setattr(app_module, 'warn_on_dev_fallbacks', lambda: None)
    for name in NAMES:
        def start(name=name):
            events.append(('start', name))
            if name == fail_start:
                raise RuntimeError('synthetic startup failure')
        def stop(name=name):
            events.append(('stop', name))
            if name == fail_stop:
                raise RuntimeError('synthetic shutdown failure')
        if name in ('bot', 'compliance'):
            monkeypatch.setattr(app_module, 'start_' + name + '_scheduler', start)
            monkeypatch.setattr(app_module, 'stop_' + name + '_scheduler', stop)
        else:
            module = importlib.import_module('core.' + name)
            monkeypatch.setattr(module, 'start', start)
            monkeypatch.setattr(module, 'stop', stop)
    return events


@pytest.mark.parametrize('failed', NAMES)
def test_partial_startup_cleans_every_attempted_worker(monkeypatch, failed):
    events = workers(monkeypatch, fail_start=failed)
    async def run():
        async with app_module.lifespan(app_module.app):
            pytest.fail('Startup should not complete')
    with pytest.raises(RuntimeError, match='startup failure'):
        asyncio.run(run())
    attempted = NAMES[:NAMES.index(failed) + 1]
    assert events == [('start', name) for name in attempted] + [('stop', name) for name in reversed(attempted)]


@pytest.mark.parametrize('failure', ['none', 'body', 'stop'])
def test_all_workers_cleanup_on_normal_body_error_or_stop_error(monkeypatch, failure):
    events = workers(monkeypatch, fail_stop='agent_events' if failure == 'stop' else None)
    async def run():
        async with app_module.lifespan(app_module.app):
            if failure == 'body':
                raise RuntimeError('synthetic body failure')
    if failure == 'none':
        asyncio.run(run())
    else:
        with pytest.raises(RuntimeError):
            asyncio.run(run())
    assert events == [('start', name) for name in NAMES] + [('stop', name) for name in reversed(NAMES)]


@pytest.mark.parametrize('failure', ['none', 'body', 'stop'])
def test_lifespan_waits_for_owned_coroutine_finalization(monkeypatch, failure):
    workers(monkeypatch, fail_stop='agent_events' if failure == 'stop' else None)
    owned = []
    finished = []

    async def inert_worker():
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            finished.append(True)

    def start():
        owned.append(asyncio.create_task(inert_worker()))

    def stop():
        owned[0].cancel()
        return owned[0]

    monkeypatch.setattr(app_module, 'start_bot_scheduler', start)
    monkeypatch.setattr(app_module, 'stop_bot_scheduler', stop)

    async def exercise():
        try:
            async with app_module.lifespan(app_module.app):
                await asyncio.sleep(0)
                if failure == 'body':
                    raise RuntimeError('synthetic body failure')
        finally:
            # Assert before asyncio.run's own cancellation cleanup could hide a leak.
            assert finished == [True]
            assert owned[0].cancelled()

    if failure == 'none':
        asyncio.run(exercise())
    else:
        with pytest.raises(RuntimeError, match='synthetic'):
            asyncio.run(exercise())
