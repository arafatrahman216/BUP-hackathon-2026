"""Tick watcher: decides WHEN the pipeline runs.

- Primary: the simulator's SSE stream (`simulation.tick`, `simulator.notice` for resets).
- Fallback: polling `/v1/instance` every PIPELINE_POLL_SECONDS (always on; it also
  notices a paused simulator being stepped, and the simulator going down).
- One worker runs the pipeline; triggers that arrive while it runs are coalesced,
  so a fast simulator makes us skip ticks instead of queueing them.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import Settings
from app.pipeline.state import PipelineState
from app.repositories.simulator_repository import SimulatorRepository
from app.utils.logger import get_logger

logger = get_logger(__name__)


class TickWatcher:
    def __init__(self, sim: SimulatorRepository, state: PipelineState, settings: Settings,
                 run: Callable[[], Awaitable[Any]]) -> None:
        self.sim = sim
        self.state = state
        self.settings = settings
        self.run = run
        self._wake = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self.sse_connected = False

    def start(self) -> None:
        self._tasks = [asyncio.create_task(self._worker(), name="pipeline-worker"),
                       asyncio.create_task(self._poll_loop(), name="pipeline-poll")]
        if self.settings.PIPELINE_SSE_ENABLED:
            self._tasks.append(asyncio.create_task(self._sse_loop(), name="pipeline-sse"))
        self.trigger()

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    def trigger(self) -> None:
        self._wake.set()

    def _set_link(self) -> None:
        self.state.link = "sse" if self.sse_connected else ("polling" if self.state.sim_connected else "down")

    async def _worker(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            try:
                await self.run()
            except Exception:
                logger.exception("Pipeline run crashed")
            self._set_link()

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.PIPELINE_POLL_SECONDS)
            try:
                tick = int((await self.sim.instance()).data.get("tick", -1))
            except Exception as exc:
                if self.state.sim_connected:  # just went down: run once so the UI shows it
                    logger.warning("Simulator poll failed: %s", exc)
                    self.trigger()
                continue
            if tick != self.state.last_processed_tick or not self.state.sim_connected:
                self.trigger()

    async def _sse_loop(self) -> None:
        backoff = 1.0
        while True:
            try:
                async with self.sim.stream() as response:
                    if response.status_code != 200:
                        raise RuntimeError(f"stream returned {response.status_code}")
                    self.sse_connected, backoff = True, 1.0
                    self._set_link()
                    logger.info("Connected to simulator SSE stream")
                    self.trigger()  # no replay on reconnect: re-read REST
                    event = None
                    async for line in response.aiter_lines():
                        if line.startswith("event:"):
                            event = line[6:].strip()
                        elif line.startswith("data:") and event:
                            self._on_event(event, line[5:].strip())
                        elif not line:
                            event = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Simulator SSE unavailable (%s); polling fallback active", exc)
            self.sse_connected = False
            self._set_link()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 15.0)

    def _on_event(self, event: str, data: str) -> None:
        if event in ("simulation.tick", "simulator.notice", "allocation.status_changed"):
            if event == "simulator.notice":
                logger.info("Simulator notice: %s", data)
            self.trigger()
        elif event == "inventory.updated":
            try:
                self.state.publish("depot", json.loads(data))
            except ValueError:
                pass
