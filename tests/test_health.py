import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from utils.health import is_healthy, monitor_telegram


class HealthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "health"

    async def run_monitor(self, client, timeout=0.02):
        task = asyncio.create_task(
            monitor_telegram(client, self.path, interval=60, timeout=timeout)
        )
        try:
            await asyncio.sleep(0.06)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_successful_rpc_marks_client_healthy(self):
        client = AsyncMock()
        await self.run_monitor(client)
        self.assertTrue(is_healthy(self.path))
        client.assert_awaited_once()

    async def test_failed_rpc_removes_previous_success(self):
        self.path.write_text(str(time.monotonic()))
        await self.run_monitor(AsyncMock(side_effect=ConnectionError))
        self.assertFalse(is_healthy(self.path))

    async def test_hung_rpc_times_out(self):
        async def hang(_):
            await asyncio.Event().wait()

        await self.run_monitor(hang)
        self.assertFalse(is_healthy(self.path))

    async def test_missing_stale_future_and_invalid_heartbeat_fail(self):
        self.assertFalse(is_healthy(self.path))
        for value in (time.monotonic() - 100, time.monotonic() + 100, "bad", "nan"):
            self.path.write_text(str(value))
            self.assertFalse(is_healthy(self.path))
