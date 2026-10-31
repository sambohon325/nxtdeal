"""
hub_core/code_auditor_scheduler.py -- the Code Auditor's real background scan
(2026-07-19). Sam, right after the first manual sweep shipped: "and have a
scheduled run / analysis" -- hub_core/code_auditor.py previously only ran when
a NXTDeal staffer clicked "Run Scan Now" in the Hub console. Same real
`asyncio` background task pattern backend/core/bot_scheduler.py /
backend/core/compliance_scheduler.py already established in the tenant
codebase (started/stopped via the app's FastAPI lifespan hook, not a
"compute when someone opens a page" shortcut) -- this is the first
background scheduler on the Hub side, mirrored from that same precedent
rather than invented fresh.

Runs hub_core.code_auditor_api.run_code_audit_scan_api(triggered_by="scheduler")
on a fixed interval (TICK_SECONDS, default 24 hours) rather than at a
specific wall-clock time -- the same honestly-documented simplification
compliance_scheduler.py's own module docstring already carries ("a real
production deployment would want this aligned to specific times... which
is a small follow-up, not a redesign, if Sam wants exact times later").
Deliberately reuses run_code_audit_scan_api() rather than calling
hub_core.code_auditor.run_scan() directly, so a scheduled run gets the exact
same persistence (_save_all()) and hub_audit logging (record_and_save())
a manual "Run Scan Now" click already gets -- one real save/log path, not
two divergent ones.

Same documented single-process/in-memory limitation as every other
background loop in this codebase (hub_core/ws_manager.py's ConnectionManager,
hub_core/bot_scheduler.py, hub_core/compliance_scheduler.py) -- resets on
restart, no persistent job queue, no cross-process coordination. The
in-memory `last_scheduled_run`/`next_scheduled_run_at` state this module
exposes is a real, live signal for the Hub console to show ("last
automated run: 3 hours ago", "next: in 21 hours"), not a stored,
cross-restart-durable schedule -- if the process restarts, the next tick
starts counting from that restart, same as the two tenant-side
precedents.
"""

import asyncio
from datetime import datetime, timezone, timedelta

from hub_core.code_auditor_api import run_code_audit_scan_api


TICK_SECONDS = 24 * 60 * 60  # 24 hours -- once a day while the process is up.

_task = None

last_scheduled_run = None
last_scheduled_run_at = None
next_scheduled_run_at = None


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _set_next_run_at():
    global next_scheduled_run_at
    next_scheduled_run_at = (
        datetime.now(timezone.utc) + timedelta(seconds=TICK_SECONDS)
    ).isoformat()


async def _run_scan():

    global last_scheduled_run, last_scheduled_run_at

    last_scheduled_run = run_code_audit_scan_api(triggered_by="scheduler")
    last_scheduled_run_at = _now_iso()


async def _tick_loop():

    while True:

        try:
            await _run_scan()
        except Exception:
            # A bad scan should never take the background loop down permanently --
            # same defensive shape hub_core/bot_scheduler.py's/hub_core/compliance_scheduler.py's
            # _tick_loop() already use.
            pass

        _set_next_run_at()
        await asyncio.sleep(TICK_SECONDS)


def get_scheduler_status():
    """A real, live read of the scheduler's own in-memory state -- backs the
    Hub console's "last automated run" / "next run" display. Distinct from
    hub_core.code_auditor_api.get_code_audit_overview_api(), which reports on
    every run regardless of who triggered it."""

    return {
        "running": _task is not None,
        "tick_seconds": TICK_SECONDS,
        "last_scheduled_run": last_scheduled_run,
        "last_scheduled_run_at": last_scheduled_run_at,
        "next_scheduled_run_at": next_scheduled_run_at,
    }


def start():
    global _task

    if _task is None:
        _set_next_run_at()
        _task = asyncio.get_event_loop().create_task(_tick_loop())


def stop():
    global _task

    if _task is not None:
        _task.cancel()
        _task = None
