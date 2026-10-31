"""Keep worker coroutine ownership until an already-started thread job finishes."""
import asyncio


async def run_worker_io(function, /, *args, **kwargs):
    job = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(job)
    except asyncio.CancelledError:
        # Python cannot cancel a running thread. Keep the worker pending so the
        # lifespan's bounded wait reports unfinished work instead of false success.
        # Repeated cancellation must not detach the thread job either.
        while not job.done():
            try:
                await asyncio.shield(job)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not job.cancelled():
            job.exception()  # Observe failures without leaking provider details.
        raise
