"""In-memory progress tracker for streaming pipeline updates via SSE/WebSocket."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional


class ProgressManager:
    """Manage job-scoped progress queues and final results in memory."""

    def __init__(self) -> None:
        self._queues: Dict[str, List[asyncio.Queue]] = {}
        self._results: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def create_job(self, job_id: str) -> None:
        """Initialise the subscription bucket for a new job identifier."""

        async with self._lock:
            if job_id not in self._queues:
                self._queues[job_id] = []
            # Drop any stale cached result for a recycled identifier.
            self._results.pop(job_id, None)

    async def subscribe(self, job_id: str) -> Optional[asyncio.Queue]:
        """Register a new subscriber queue for a job."""

        async with self._lock:
            if job_id not in self._queues:
                return None
            queue: asyncio.Queue = asyncio.Queue()
            self._queues[job_id].append(queue)
            return queue

    async def publish(self, job_id: str, event: Dict[str, Any]) -> None:
        queues = self._queues.get(job_id)
        if not queues:
            return
        await asyncio.gather(*(queue.put(event) for queue in list(queues)))

    def set_result(self, job_id: str, result: Any) -> None:
        self._results[job_id] = result

    def get_result(self, job_id: str) -> Optional[Any]:
        return self._results.get(job_id)

    async def finalize(self, job_id: str) -> None:
        """Push the completion sentinel to subscribers."""

        queues = self._queues.get(job_id)
        if not queues:
            return
        closing = {"type": "job", "status": "closed", "job_id": job_id}
        await asyncio.gather(*(queue.put(closing) for queue in list(queues)))
        await asyncio.gather(*(queue.put(None) for queue in list(queues)))

    async def discard(self, job_id: str, queue: Optional[asyncio.Queue] = None) -> None:
        """Remove queue(s) for a finished job while keeping cached results."""

        async with self._lock:
            if queue is None:
                self._queues.pop(job_id, None)
                return
            watchers = self._queues.get(job_id)
            if not watchers:
                return
            try:
                watchers.remove(queue)
            except ValueError:  # pragma: no cover - defensive
                return
            if not watchers:
                self._queues.pop(job_id, None)

    def forget(self, job_id: str) -> None:
        """Explicitly remove cached results when no longer needed."""

        self._results.pop(job_id, None)


progress_manager = ProgressManager()
