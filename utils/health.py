"""Probe Telegram over the running client, without sending chat messages."""

import asyncio
import logging
import os
import time
from pathlib import Path

from telethon import functions

log = logging.getLogger(__name__)
HEALTH_FILE = Path(os.getenv("TELEGRAM_HEALTH_FILE", "/tmp/telegram-health"))


async def monitor_telegram(client, health_file=HEALTH_FILE, interval=30, timeout=20):
    """Publish monotonic time only after a successful authenticated RPC."""
    health_file.unlink(missing_ok=True)
    while True:
        try:
            await asyncio.wait_for(client(functions.updates.GetStateRequest()), timeout)
        except Exception as exc:
            health_file.unlink(missing_ok=True)
            log.warning("Telegram health check failed: %s", type(exc).__name__)
        else:
            temporary = health_file.with_suffix(".tmp")
            temporary.write_text(str(time.monotonic()))
            temporary.replace(health_file)
        await asyncio.sleep(interval)


def is_healthy(health_file=HEALTH_FILE, max_age=90):
    try:
        age = time.monotonic() - float(health_file.read_text())
        return 0 <= age < max_age
    except (OSError, ValueError):
        return False


if __name__ == "__main__":
    raise SystemExit(0 if is_healthy() else 1)
