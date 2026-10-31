"""Executor shutdown acceptance using blocked fictional jobs, never providers."""
import asyncio
import contextvars
import importlib
import threading

import pytest

from core.worker_io import run_worker_io
from core.worker_shutdown import WorkerShutdown


def test_result_exception_and_context_are_preserved():
    marker = contextvars.ContextVar('synthetic_marker')

    async def exercise():
        marker.set('fictional')
        assert await run_worker_io(lambda *, suffix: marker.get() + suffix, suffix='-ok') == 'fictional-ok'

        def fail():
            raise ValueError('fictional failure')

        with pytest.raises(ValueError, match='fictional failure'):
            await run_worker_io(fail)

    asyncio.run(exercise())


@pytest.mark.parametrize('fails', [False, True])
def test_cancel_retains_thread_until_completion_and_survives_repeat_cancel(fails):
    async def exercise():
        entered = asyncio.Event()
        release = threading.Event()
        finished = threading.Event()
        loop = asyncio.get_running_loop()

        def job():
            loop.call_soon_threadsafe(entered.set)
            try:
                assert release.wait(3), 'Test did not release fictional job'
                if fails:
                    raise ValueError('fictional provider detail')
            finally:
                finished.set()

        task = asyncio.create_task(run_worker_io(job))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            shutdown = WorkerShutdown(timeout=0.01)
            shutdown.stop(lambda: task)
            with pytest.raises(RuntimeError, match='shutdown timed out'):
                await shutdown.wait()
            assert not finished.is_set()
            release.set()
            await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 1)
            assert task.cancelled() and finished.is_set()
            await shutdown.wait()
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())


@pytest.mark.parametrize('name,loop_name,job_name', [
    ('bridge_sync', 'loop', 'tick'),
    ('bridge_chrono', 'loop', 'tick'),
    ('dealer_cloud', '_loop', 'run_backup'),
])
def test_actual_worker_loop_keeps_inflight_job_owned(monkeypatch, name, loop_name, job_name):
    module = importlib.import_module('core.' + name)
    task_name = '_task' if name == 'dealer_cloud' else '_TASK'
    monkeypatch.setattr(module, task_name, None)
    monkeypatch.setenv('NXTDEAL_CLOUD_BACKUPS_ENABLED', 'true')
    original_sleep = asyncio.sleep

    async def fast_sleep(delay):
        await original_sleep(0)

    monkeypatch.setattr(module.asyncio, 'sleep', fast_sleep)

    async def exercise():
        entered = asyncio.Event()
        release = threading.Event()
        calls = []
        loop = asyncio.get_running_loop()

        def fictional_job(**kwargs):
            calls.append(kwargs)
            loop.call_soon_threadsafe(entered.set)
            assert release.wait(3), 'Test did not release fictional job'

        monkeypatch.setattr(module, job_name, fictional_job)
        module.start()
        task = getattr(module, task_name)
        try:
            await asyncio.wait_for(entered.wait(), 1)
            assert module.stop() is task
            await original_sleep(0)
            assert not task.done()
            module.start()
            assert getattr(module, task_name) is task
            release.set()
            await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 1)
            assert task.cancelled()
            assert getattr(module, task_name) is None
            assert calls == ([{'due': True}] if name == 'dealer_cloud' else [{}])
        finally:
            release.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())
