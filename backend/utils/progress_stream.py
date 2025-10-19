"""In-memory progress tracker for streaming pipeline updates via SSE/WebSocket."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional


class ProgressManager:
    """Manage job-scoped progress queues and final results in memory."""

    def __init__(self) -> None:
        self._queues: Dict[str, asyncio.Queue] = {}
        self._results: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def create_job(self, job_id: str) -> None:
        """Initialise a queue for a new job identifier."""

        async with self._lock:
            if job_id in self._queues:
                return
            self._queues[job_id] = asyncio.Queue()

    def get_queue(self, job_id: str) -> Optional[asyncio.Queue]:
        return self._queues.get(job_id)

    async def publish(self, job_id: str, event: Dict[str, Any]) -> None:
        queue = self._queues.get(job_id)
        if queue is None:
            return
        await queue.put(event)

    def set_result(self, job_id: str, result: Any) -> None:
        self._results[job_id] = result

    def get_result(self, job_id: str) -> Optional[Any]:
        return self._results.get(job_id)

    async def finalize(self, job_id: str) -> None:
        """Push the completion sentinel to subscribers."""

        queue = self._queues.get(job_id)
        if queue is None:
            return
        await queue.put({"type": "job", "status": "closed", "job_id": job_id})
        await queue.put(None)

    def discard(self, job_id: str) -> None:
        """Remove queue for a finished job while keeping cached results."""

        self._queues.pop(job_id, None)

    def forget(self, job_id: str) -> None:
        """Explicitly remove cached results when no longer needed."""

        self._results.pop(job_id, None)


progress_manager = ProgressManager()

