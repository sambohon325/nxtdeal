"""Single-process durable-cursor Sales follow-up scheduler; never sends messages."""
import asyncio
import logging

_task = None


async def loop():
    from api.routers.sales_crm_advanced import run_due
    while True:
        try:
            run_due()
        except Exception:
            logging.getLogger(__name__).exception("Sales sequence scheduling failed")
        await asyncio.sleep(60)


def start():
    global _task
    if _task is None:
        _task = asyncio.create_task(loop())


def stop():
    """Request cancellation and return the owned task for lifespan cleanup."""
    global _task
    task = _task
    if task is not None:
        task.cancel()
        _task = None
    return task
