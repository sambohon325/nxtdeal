"""
Tests for core/bot_scheduler.py -- the bot's real background asyncio scheduler
(session 36, trimmed session 37): a single tick loop, started once at FastAPI
startup, that runs the whitelisted auto-actions (core/bot_actions.run_action) for
every currently-active "auto" mode BotCoverage window on every tick.

Same real-async-loop testing convention already established in this suite by
tests/test_compliance.py's test_compliance_scheduler_scan_runs_without_error --
`asyncio.run(module._some_async_function())` inside a plain sync test function,
no pytest-asyncio dependency needed.

`list_coverage`/`generate_tasks`/`run_action` are all imported into bot_scheduler's
own module namespace via `from ... import ...`, so they're patched on bot_scheduler
itself ("patch where it's used"), not on their origin modules.

Run from backend/ with `pytest`.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import bot_scheduler


@pytest.fixture(autouse=True)
def reset_scheduler_task():
    # The module keeps a single global `_task` -- make sure no test leaks a live
    # task (or a stale reference) into the next one.
    bot_scheduler._task = None
    yield
    if bot_scheduler._task is not None:
        bot_scheduler._task.cancel()
    bot_scheduler._task = None


class TestRunAutoCoverage:

    def test_no_coverage_windows_runs_no_actions(self, monkeypatch):
        monkeypatch.setattr(bot_scheduler, "list_coverage", lambda active_only=False: [])
        calls = []
        monkeypatch.setattr(
            bot_scheduler, "run_action", lambda key, emp, admin: calls.append((key, emp, admin))
        )

        asyncio.run(bot_scheduler._run_auto_coverage())

        assert calls == []

    def test_non_auto_mode_coverage_is_skipped(self, monkeypatch):
        monkeypatch.setattr(
            bot_scheduler,
            "list_coverage",
            lambda active_only=False: [
                {"employee_id": "EMP-1", "mode": "manual", "role": "SALES", "section": "sales"}
            ],
        )
        monkeypatch.setattr(bot_scheduler, "generate_tasks", lambda *a, **k: [{"key": "should_not_run"}])
        calls = []
        monkeypatch.setattr(
            bot_scheduler, "run_action", lambda key, emp, admin: calls.append((key, emp, admin))
        )

        asyncio.run(bot_scheduler._run_auto_coverage())

        assert calls == []

    def test_auto_mode_coverage_generates_and_runs_every_task(self, monkeypatch):
        monkeypatch.setattr(
            bot_scheduler,
            "list_coverage",
            lambda active_only=False: [
                {
                    "employee_id": "EMP-1",
                    "mode": bot_scheduler.MODE_AUTO,
                    "role": "SERVICE",
                    "section": "service",
                    "activated_by": "EMP-ADMIN",
                }
            ],
        )
        generate_calls = []

        def fake_generate_tasks(employee_id, role, section):
            generate_calls.append((employee_id, role, section))
            return [{"key": "task_a"}, {"key": "task_b"}]

        monkeypatch.setattr(bot_scheduler, "generate_tasks", fake_generate_tasks)
        run_calls = []
        monkeypatch.setattr(
            bot_scheduler, "run_action", lambda key, emp, admin: run_calls.append((key, emp, admin))
        )

        asyncio.run(bot_scheduler._run_auto_coverage())

        assert generate_calls == [("EMP-1", "SERVICE", "service")]
        assert run_calls == [
            ("task_a", "EMP-1", "EMP-ADMIN"),
            ("task_b", "EMP-1", "EMP-ADMIN"),
        ]

    def test_missing_role_and_section_default_to_sales(self, monkeypatch):
        monkeypatch.setattr(
            bot_scheduler,
            "list_coverage",
            lambda active_only=False: [
                {"employee_id": "EMP-1", "mode": bot_scheduler.MODE_AUTO}
            ],
        )
        generate_calls = []
        monkeypatch.setattr(
            bot_scheduler,
            "generate_tasks",
            lambda employee_id, role, section: generate_calls.append((employee_id, role, section)) or [],
        )
        monkeypatch.setattr(bot_scheduler, "run_action", lambda *a: None)

        asyncio.run(bot_scheduler._run_auto_coverage())

        assert generate_calls == [("EMP-1", "SALES", "sales")]

    def test_multiple_auto_coverage_windows_are_all_processed(self, monkeypatch):
        monkeypatch.setattr(
            bot_scheduler,
            "list_coverage",
            lambda active_only=False: [
                {"employee_id": "EMP-1", "mode": bot_scheduler.MODE_AUTO, "role": "SALES", "section": "sales"},
                {"employee_id": "EMP-2", "mode": bot_scheduler.MODE_AUTO, "role": "FINANCE", "section": "finance"},
            ],
        )
        monkeypatch.setattr(bot_scheduler, "generate_tasks", lambda emp, role, section: [{"key": "t"}])
        run_calls = []
        monkeypatch.setattr(
            bot_scheduler, "run_action", lambda key, emp, admin: run_calls.append(emp)
        )

        asyncio.run(bot_scheduler._run_auto_coverage())

        assert run_calls == ["EMP-1", "EMP-2"]

    def test_list_coverage_is_called_with_active_only_true(self, monkeypatch):
        seen = {}

        def fake_list_coverage(active_only=False):
            seen["active_only"] = active_only
            return []

        monkeypatch.setattr(bot_scheduler, "list_coverage", fake_list_coverage)

        asyncio.run(bot_scheduler._run_auto_coverage())

        assert seen["active_only"] is True


class TestTickLoopResilience:

    def test_a_bad_tick_does_not_kill_the_background_loop(self, monkeypatch):
        # Real behavior documented in the module's own docstring: "A bad tick should
        # never take the background loop down permanently." Force _run_auto_coverage
        # to raise on every call, run the real tick loop briefly with a near-zero
        # tick interval, then confirm the task is still alive (not finished/crashed)
        # until explicitly cancelled.
        monkeypatch.setattr(bot_scheduler, "TICK_SECONDS", 0.01)

        call_count = {"n": 0}

        async def always_raises():
            call_count["n"] += 1
            raise RuntimeError("simulated tick failure")

        monkeypatch.setattr(bot_scheduler, "_run_auto_coverage", always_raises)

        async def scenario():
            task = asyncio.get_event_loop().create_task(bot_scheduler._tick_loop())
            # Give it several real ticks to prove the exception doesn't propagate
            # and end the loop.
            await asyncio.sleep(0.08)
            still_running = not task.done()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            return still_running

        still_running = asyncio.run(scenario())

        assert still_running is True
        assert call_count["n"] >= 2


class TestStartStop:

    def test_start_creates_a_real_asyncio_task(self):
        async def scenario():
            bot_scheduler.start()
            task = bot_scheduler._task
            assert task is not None
            assert isinstance(task, asyncio.Task)
            bot_scheduler.stop()

        asyncio.run(scenario())

    def test_start_is_idempotent_and_does_not_replace_an_existing_task(self):
        async def scenario():
            bot_scheduler.start()
            first_task = bot_scheduler._task
            bot_scheduler.start()
            second_task = bot_scheduler._task
            assert first_task is second_task
            bot_scheduler.stop()

        asyncio.run(scenario())

    def test_stop_cancels_the_task_and_clears_the_reference(self):
        async def scenario():
            bot_scheduler.start()
            task = bot_scheduler._task
            bot_scheduler.stop()
            assert bot_scheduler._task is None
            # Give the cancellation a moment to actually land.
            await asyncio.sleep(0)
            assert task.cancelled() or task.done()

        asyncio.run(scenario())

    def test_stop_when_never_started_is_a_safe_no_op(self):
        assert bot_scheduler._task is None
        bot_scheduler.stop()
        assert bot_scheduler._task is None
