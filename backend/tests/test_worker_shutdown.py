"""No real workers or provider calls: cancellation and timeout acceptance."""
import asyncio

import pytest

from core.worker_shutdown import WorkerShutdown


def test_wait_finishes_async_finalizers_and_observes_worker_failure():
    async def exercise():
        finished = []

        async def worker():
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                finished.append(True)

        task = asyncio.create_task(worker())
        await asyncio.sleep(0)
        shutdown = WorkerShutdown()

        def stop():
            task.cancel()
            return task

        shutdown.stop(stop)
        await shutdown.wait()
        assert finished == [True]
        assert task.cancelled()

        async def failed_worker():
            raise ValueError('synthetic private provider detail')

        failed = asyncio.create_task(failed_worker())
        await asyncio.sleep(0)
        shutdown.stop(lambda: failed)
        with pytest.raises(RuntimeError, match='^Worker coroutine failed before shutdown completed$'):
            await shutdown.wait()

    asyncio.run(exercise())


def test_timeout_reports_unfinished_worker_without_indefinite_wait():
    async def exercise():
        release = asyncio.Event()

        async def stubborn_worker():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await release.wait()

        task = asyncio.create_task(stubborn_worker())
        await asyncio.sleep(0)
        shutdown = WorkerShutdown(timeout=0.01)

        def stop():
            task.cancel()
            return task

        shutdown.stop(stop)
        try:
            with pytest.raises(RuntimeError, match='shutdown timed out'):
                await asyncio.wait_for(shutdown.wait(), timeout=1)
            assert not task.done()
        finally:
            release.set()
            await task

    asyncio.run(exercise())
