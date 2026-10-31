"""
core/compliance_scheduler.py -- the compliance agent's real background scan (2026-07-13,
session 38). Sam: "scan records / deals / etc at least twice a day and flag compliance
issues and notify managers / admin." Same real `asyncio` background task pattern
core/bot_scheduler.py already established (started/stopped via api/app.py's FastAPI
startup/shutdown hooks) -- not a "compute when someone opens a page" shortcut.

Runs core/compliance.run_full_scan() on a fixed interval (TICK_SECONDS, default 12
hours) rather than at two specific wall-clock times -- an honestly-documented
simplification, same shape as core/kpi_snapshots.py's "fires whenever a dashboard is
fetched" tradeoff and core/bot_scheduler.py's "every 5 minutes, not wall-clock aligned"
one. As long as the process stays up, this produces at least two scans a day; a real
production deployment would want this aligned to specific times (e.g. 6am/6pm) via a
proper cron-style scheduler, which is a small follow-up, not a redesign, if Sam wants
exact times later.

Same documented single-process/in-memory limitation as every other background loop in
this backend (core/ws_manager.py's ConnectionManager, core/bot_scheduler.py) -- resets
on restart, no persistent job queue.
"""

import asyncio

from core.compliance import run_full_scan


TICK_SECONDS = 12 * 60 * 60  # 12 hours -- "at least twice a day" while the process is up.

_task = None

last_scan_result = None


async def _run_scan():

    global last_scan_result

    last_scan_result = run_full_scan()


async def _tick_loop():

    while True:

        try:
            await _run_scan()
        except Exception:
            # A bad scan should never take the background loop down permanently --
            # same defensive shape core/bot_scheduler.py's _tick_loop() already uses.
            pass

        await asyncio.sleep(TICK_SECONDS)


def start():
    global _task

    if _task is None:
        _task = asyncio.get_event_loop().create_task(_tick_loop())


def stop():
    """Request cancellation and return the owned task for lifespan cleanup."""
    global _task
    task = _task
    if task is not None:
        task.cancel()
        _task = None
    return task
