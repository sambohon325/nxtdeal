"""Lifespan-owned bounded loyalty reconciliation; no external messages sent."""
import asyncio
import logging
from core.loyalty_workflows import reconcile


async def run():
    while True:
        try:
            await asyncio.to_thread(reconcile)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger(__name__).exception("Loyalty reconciliation failed")
        await asyncio.sleep(60)


_task = None


def start():
    global _task
    if _task is None:
        _task = asyncio.create_task(run())


def stop():
    global _task
    task = _task
    if task is not None:
        task.cancel()
        _task = None
    return task
