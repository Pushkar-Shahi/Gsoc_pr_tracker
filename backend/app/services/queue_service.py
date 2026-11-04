"""
Pluggable Distributed Task Queue Service.
Provides a unified FIFO queue interface for background jobs (issue discovery,
PR synchronization, validation runs, and runner jobs).
Supports Redis when REDIS_URL is configured, with seamless, zero-crash fallback
to in-memory asyncio.Queue when offline or unconfigured.
"""

import abc
import asyncio
import json
import logging
import uuid
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class QueueBackend(abc.ABC):
    """Abstract interface for task queue backends."""

    @abc.abstractmethod
    async def enqueue(self, queue_name: str, payload: Dict[str, Any]) -> str:
        """Enqueues a job payload into the named queue. Returns unique job ID."""
        pass

    @abc.abstractmethod
    async def dequeue(self, queue_name: str, timeout: float = 0.0) -> Optional[Dict[str, Any]]:
        """Pops the next available job payload in FIFO order, or None if empty."""
        pass

    @abc.abstractmethod
    async def get_length(self, queue_name: str) -> int:
        """Returns the number of queued jobs waiting in the named queue."""
        pass


class InMemoryAsyncQueueBackend(QueueBackend):
    """
    In-memory async FIFO queue implementation.
    Zero external dependencies, ideal for single-node deployments, local execution, and fallback.
    """

    def __init__(self):
        self._queues: Dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()

    def _get_queue(self, queue_name: str) -> asyncio.Queue:
        if queue_name not in self._queues:
            self._queues[queue_name] = asyncio.Queue()
        return self._queues[queue_name]

    async def enqueue(self, queue_name: str, payload: Dict[str, Any]) -> str:
        job_id = payload.get("job_id") or str(uuid.uuid4())
        job_payload = {**payload, "job_id": job_id}
        queue = self._get_queue(queue_name)
        await queue.put(job_payload)
        return job_id

    async def dequeue(self, queue_name: str, timeout: float = 0.0) -> Optional[Dict[str, Any]]:
        queue = self._get_queue(queue_name)
        if queue.empty():
            if timeout <= 0:
                return None
            try:
                return await asyncio.wait_for(queue.get(), timeout=timeout)
            except asyncio.TimeoutError:
                return None
        return queue.get_nowait()

    async def get_length(self, queue_name: str) -> int:
        queue = self._get_queue(queue_name)
        return queue.qsize()


class RedisQueueBackend(QueueBackend):
    """
    Redis-backed distributed queue implementation.
    Uses LPUSH / RPOP for distributed FIFO queueing across multiple worker processes.
    Gracefully falls back to InMemoryAsyncQueueBackend if Redis becomes unreachable.
    """

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._fallback = InMemoryAsyncQueueBackend()
        self._client = None
        self._connected = False

    async def _get_client(self):
        if self._client is not None and self._connected:
            return self._client

        try:
            # Lazy import redis asyncio client
            import redis.asyncio as aioredis
            self._client = aioredis.from_url(self.redis_url, decode_responses=True)
            await self._client.ping()
            self._connected = True
            logger.info(f"Connected to Redis task queue at {self.redis_url}")
            return self._client
        except Exception as e:
            self._connected = False
            logger.warning(f"Redis unavailable ({e}); gracefully falling back to in-memory queue.")
            return None

    async def enqueue(self, queue_name: str, payload: Dict[str, Any]) -> str:
        client = await self._get_client()
        job_id = payload.get("job_id") or str(uuid.uuid4())
        job_payload = {**payload, "job_id": job_id}

        if client and self._connected:
            try:
                key = f"issuetopr:queue:{queue_name}"
                await client.lpush(key, json.dumps(job_payload))
                return job_id
            except Exception as e:
                logger.warning(f"Redis enqueue failed ({e}), falling back to in-memory.")
                self._connected = False

        return await self._fallback.enqueue(queue_name, job_payload)

    async def dequeue(self, queue_name: str, timeout: float = 0.0) -> Optional[Dict[str, Any]]:
        client = await self._get_client()
        if client and self._connected:
            try:
                key = f"issuetopr:queue:{queue_name}"
                raw = await client.rpop(key)
                if raw:
                    return json.loads(raw)
                return None
            except Exception as e:
                logger.warning(f"Redis dequeue failed ({e}), falling back to in-memory.")
                self._connected = False

        return await self._fallback.dequeue(queue_name, timeout)

    async def get_length(self, queue_name: str) -> int:
        client = await self._get_client()
        if client and self._connected:
            try:
                key = f"issuetopr:queue:{queue_name}"
                return await client.llen(key)
            except Exception:
                self._connected = False
        return await self._fallback.get_length(queue_name)


class QueueService:
    """
    Central queue service singleton providing dispatch and polling methods.
    """
    _instance: Optional["QueueService"] = None

    def __init__(self, backend: Optional[QueueBackend] = None):
        self.backend = backend or InMemoryAsyncQueueBackend()

    @classmethod
    def get_instance(cls, redis_url: Optional[str] = None) -> "QueueService":
        if cls._instance is None:
            if redis_url:
                backend = RedisQueueBackend(redis_url)
            else:
                backend = InMemoryAsyncQueueBackend()
            cls._instance = cls(backend)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Used in test fixtures to clear singleton state."""
        cls._instance = None

    async def enqueue(self, queue_name: str, payload: Dict[str, Any]) -> str:
        return await self.backend.enqueue(queue_name, payload)

    async def dequeue(self, queue_name: str, timeout: float = 0.0) -> Optional[Dict[str, Any]]:
        return await self.backend.dequeue(queue_name, timeout)

    async def get_length(self, queue_name: str) -> int:
        return await self.backend.get_length(queue_name)


# Default global queue instance
queue_service = QueueService.get_instance()
