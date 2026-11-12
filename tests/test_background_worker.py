import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from app.services.background_worker import BackgroundWorkerService

@pytest.mark.asyncio
async def test_background_worker_lifecycle():
    mock_session_factory = AsyncMock()
    worker = BackgroundWorkerService(
        session_factory=mock_session_factory,
        discovery_interval_sec=1,
        pr_poll_interval_sec=1
    )

    worker.start()
    assert worker._running is True
    assert len(worker._tasks) == 4  # PR tracker + discovery worker + issue reconciler + startup empty-inbox check

    # Allow worker tasks to spin once
    await asyncio.sleep(0.05)

    await worker.stop()
    assert worker._running is False
    assert len(worker._tasks) == 0
