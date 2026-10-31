"""
core/bot_scheduler.py — the agentic bot's real background scheduler (2026-07-13,
session 36; trimmed session 37). Sam's scoping answer on prompt timing was explicit:
"build real backend scheduling," not just compute-a-fresh-list-whenever-someone-opens-
the-page. This is a single asyncio background task, started once at FastAPI startup
(api/app.py) and cancelled at shutdown, that wakes up every TICK_SECONDS and runs the
whitelisted auto-actions (core/bot_actions.py) for every currently-active "auto" mode
BotCoverage window.

Session 37 removed this module's other original job -- pushing new bot tasks as direct
messages from a virtual "BOT" sender over core/messaging.py/core/ws_manager.py. Sam:
"lets go ahead and take bot out of the direct messages, that seems redundant with the
actual bot button near send" -- the square robot-icon button (components/BotWidget.tsx)
already fetches GET /bot/tasks on demand, so a second, passive delivery channel for the
exact same suggestions was duplicate surface area, not a second real feature. The
background loop itself stays real (this is still "real backend scheduling," not a
compute-on-open shortcut) because "auto" mode coverage needs something running even if
nobody opens the admin panel or the bot widget while the covered employee is out.

Same documented limitation as core/ws_manager.py's ConnectionManager and every other
piece of this backend that "runs in the background": single-process, resets on restart
-- there's no persistent job queue here, just a real running loop.
"""

import asyncio

from core.bot_tasks import generate_tasks
from core.bot_coverage import list_coverage, MODE_AUTO
from core.bot_actions import run_action

TICK_SECONDS = 300  # 5 minutes -- frequent enough that an "auto" coverage window
                     # starts getting acted on soon after it goes active, without
                     # re-scanning the whole graph too aggressively.

_task = None


async def _run_auto_coverage():

    for coverage in list_coverage(active_only=True):

        if coverage.get("mode") != MODE_AUTO:
            continue

        employee_id = coverage["employee_id"]
        role = coverage.get("role") or "SALES"
        section = coverage.get("section") or "sales"

        tasks = generate_tasks(employee_id, role, section)

        for task in tasks:
            run_action(task["key"], employee_id, coverage.get("activated_by"))


async def _tick_loop():

    while True:

        try:
            await _run_auto_coverage()
        except Exception:
            # A bad tick should never take the background loop down permanently.
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
