"""Bounded completion of worker coroutine cancellation, not executor work drain."""
import asyncio


class WorkerShutdown:
    def __init__(self, timeout=5.0):
        self.timeout = timeout
        self.tasks = set()

    def stop(self, callback):
        task = callback()
        if task is not None:
            self.tasks.add(task)

    async def wait(self):
        if not self.tasks:
            return
        # Unlike wait_for, wait does not wait indefinitely for a task that ignores
        # cancellation. All workers already received cancellation before this wait.
        done, pending = await asyncio.wait(self.tasks, timeout=self.timeout)
        failed = [task for task in done if not task.cancelled() and task.exception() is not None]
        if pending:
            raise RuntimeError("Worker coroutine shutdown timed out")
        if failed:
            # Do not expose worker exceptions that might include provider secrets.
            raise RuntimeError("Worker coroutine failed before shutdown completed")
