import asyncio
from unittest.mock import AsyncMock

import pytest

from incidentlab.lab import SCENARIOS, Lab
from incidentlab.store import Store


async def test_collection_failure_still_resets_every_service():
    store = Store(":memory:")
    lab = Lab(store)
    lab.reset = AsyncMock()
    lab.load = AsyncMock(side_effect=RuntimeError("network disconnected"))
    await lab._run(SCENARIOS[0], "failed-run")
    assert lab.reset.await_count == 2
    assert lab.status["phase"] == "error"
    assert "network disconnected" in lab.status["message"]
    assert store.incidents() == []
    await lab.client.aclose()
    store.close()


async def test_experiment_cancellation_attempts_recovery():
    store = Store(":memory:")
    lab = Lab(store)
    lab.reset = AsyncMock()
    collecting = asyncio.Event()

    async def blocked_load(_count):
        collecting.set()
        await asyncio.Future()

    lab.load = blocked_load
    task = asyncio.create_task(lab._run(SCENARIOS[0], "cancelled-run"))
    await asyncio.wait_for(collecting.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert lab.reset.await_count == 2
    await lab.client.aclose()
    store.close()


async def test_recovery_failure_is_visible():
    store = Store(":memory:")
    lab = Lab(store)
    lab.reset = AsyncMock(side_effect=RuntimeError("inventory unreachable"))
    await lab._run(SCENARIOS[0], "reset-failure")
    assert lab.status["phase"] == "error"
    assert "Recovery failed" in lab.status["message"]
    assert not store.incidents()
    await lab.client.aclose()
    store.close()
