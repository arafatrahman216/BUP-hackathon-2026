"""Read side for the operator dashboard: the cached state and the SSE stream."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from app.models.snapshot import TickSnapshot
from app.pipeline.state import PipelineState
from app.repositories.snapshot_repository import SnapshotRepository

KEEPALIVE_SECONDS = 15.0


class DashboardService:
    def __init__(self, state: PipelineState, snapshots: SnapshotRepository | None = None) -> None:
        self.state = state
        self.snapshots = snapshots

    def current(self) -> dict[str, Any]:
        return self.state.to_dashboard()

    async def list_snapshots(self, offset: int, limit: int) -> tuple[list[TickSnapshot], int]:
        return await self.snapshots.list(offset, limit)

    async def stream(self) -> AsyncIterator[str]:
        """SSE: a `state` event right away, then one per pipeline run / operator action."""
        queue = self.state.subscribe()
        try:
            yield f"event: state\ndata: {json.dumps(self.current(), default=str)}\n\n"
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            self.state.unsubscribe(queue)
