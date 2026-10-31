"""Real task ownership/cancellation with inert loops, no provider or business work."""
import asyncio
import importlib

import pytest


@pytest.mark.parametrize('name,task_name,loop_name', [
    ('bot_scheduler', '_task', '_tick_loop'),
    ('compliance_scheduler', '_task', '_tick_loop'),
    ('agent_events', '_task', 'loop'),
    ('sales_sequence_scheduler', '_task', 'loop'),
    ('dealer_cloud', '_task', '_loop'),
    ('bridge_sync', '_TASK', 'loop'),
    ('bridge_chrono', '_TASK', 'loop'),
])
def test_worker_start_is_idempotent_and_stop_cancels_owned_task(monkeypatch, name, task_name, loop_name):
    module = importlib.import_module('core.' + name)
    monkeypatch.setattr(module, task_name, None)
    tasks = []
    finished = []

    async def inert_loop():
        try:
            await asyncio.Event().wait()
        finally:
            finished.append(asyncio.current_task())

    monkeypatch.setattr(module, loop_name, inert_loop)

    async def exercise():
        try:
            module.stop()  # Safe before startup, as used by partial-start cleanup.
            for _ in range(2):
                module.start()
                task = getattr(module, task_name)
                tasks.append(task)
                module.start()
                assert getattr(module, task_name) is task
                await asyncio.sleep(0)  # Enter the inert loop before cancellation.
                assert module.stop() is task
                if name in ('bridge_sync', 'bridge_chrono', 'dealer_cloud'):
                    assert module.stop() is task
                    module.start()
                    assert getattr(module, task_name) is task
                else:
                    assert module.stop() is None
                    assert getattr(module, task_name) is None
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, timeout=1)
                assert task.done() and task.cancelled()
                assert getattr(module, task_name) is None
            assert tasks[0] is not tasks[1]
            assert finished == tasks
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(exercise())
