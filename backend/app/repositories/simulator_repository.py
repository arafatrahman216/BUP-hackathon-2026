"""HTTP client for the BUP Fuel Supply Simulator (`/v1/*` only, never `/admin`).

Resilience built in:
- timeout on every call, retries with exponential backoff on network errors and 5xx,
- a circuit breaker (open after N consecutive failures, half-open after a cooldown),
- `X-Simulator-Stale: true` detection (exposed as `SimResponse.stale`),
- both simulator error shapes: `{"detail": {"code", "message"}}` and `{"error": {"code", ...}}`.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SimulatorError(Exception):
    """The simulator could not be reached or returned a server error (transient)."""

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code or "SIMULATOR_UNAVAILABLE"


class SimulatorRejection(Exception):
    """The simulator answered 4xx: the request itself was refused (e.g. 409 ROUTE_DISRUPTED)."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message


class CircuitOpenError(SimulatorError):
    def __init__(self) -> None:
        super().__init__("Simulator circuit breaker is open", code="CIRCUIT_OPEN")


@dataclass
class SimResponse:
    data: Any
    stale: bool = False
    status: int = 200


class CircuitBreaker:
    def __init__(self, threshold: int, cooldown_seconds: float) -> None:
        self.threshold = threshold
        self.cooldown = cooldown_seconds
        self.failures = 0
        self.opened_at: float | None = None

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        return "half_open" if time.monotonic() - self.opened_at >= self.cooldown else "open"

    def allow(self) -> bool:
        return self.state != "open"

    def success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            if self.opened_at is None:
                logger.warning("Simulator circuit breaker opened after %d failures", self.failures)
            self.opened_at = time.monotonic()


def _error_code(response: httpx.Response) -> tuple[str, str]:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP_{response.status_code}", response.text[:200]
    err = body.get("detail") or body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict):
        return str(err.get("code") or f"HTTP_{response.status_code}"), str(err.get("message") or "")
    return f"HTTP_{response.status_code}", str(err or body)[:200]


class SimulatorRepository:
    def __init__(self, settings: Settings, http: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.base_url = settings.SIMULATOR_BASE_URL.rstrip("/")
        self.http = http or httpx.AsyncClient(base_url=self.base_url, timeout=settings.SIMULATOR_TIMEOUT_SECONDS)
        self.breaker = CircuitBreaker(settings.SIMULATOR_BREAKER_THRESHOLD, settings.SIMULATOR_BREAKER_COOLDOWN_SECONDS)
        self.last_error: str | None = None
        self.last_latency_ms: float | None = None

    async def _request(self, method: str, path: str, **kwargs: Any) -> SimResponse:
        if not self.breaker.allow():
            raise CircuitOpenError()
        attempts = 1 + max(0, self.settings.SIMULATOR_RETRIES)
        delay = self.settings.SIMULATOR_BACKOFF_SECONDS
        last_exc: SimulatorError | None = None
        for attempt in range(attempts):
            started = time.perf_counter()
            try:
                response = await self.http.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                last_exc = SimulatorError(f"{method} {path}: {type(exc).__name__} {exc}")
            else:
                self.last_latency_ms = round((time.perf_counter() - started) * 1000, 1)
                if response.status_code >= 500:
                    code, message = _error_code(response)
                    last_exc = SimulatorError(f"{method} {path}: {response.status_code} {code} {message}",
                                              status=response.status_code, code=code)
                else:
                    self.breaker.success()
                    self.last_error = None
                    if response.status_code >= 400:
                        code, message = _error_code(response)
                        raise SimulatorRejection(response.status_code, code, message)
                    stale = response.headers.get("X-Simulator-Stale", "").lower() == "true"
                    return SimResponse(response.json(), stale=stale, status=response.status_code)
            if attempt < attempts - 1:
                await asyncio.sleep(delay)
                delay *= 2
        self.breaker.failure()
        self.last_error = str(last_exc)
        raise last_exc  # type: ignore[misc]

    # --- reads ---
    async def health(self) -> SimResponse:
        return await self._request("GET", "/v1/health")

    async def instance(self) -> SimResponse:
        return await self._request("GET", "/v1/instance")

    async def depots(self) -> SimResponse:
        return await self._request("GET", "/v1/depots")

    async def stations(self) -> SimResponse:
        return await self._request("GET", "/v1/stations")

    async def routes(self) -> SimResponse:
        return await self._request("GET", "/v1/routes")

    async def supply_arrivals(self) -> SimResponse:
        return await self._request("GET", "/v1/supply-arrivals")

    async def events(self) -> SimResponse:
        return await self._request("GET", "/v1/events")

    async def allocations(self) -> SimResponse:
        return await self._request("GET", "/v1/allocations")

    async def demand_history(self, limit: int, station_id: str | None = None) -> SimResponse:
        params: dict[str, Any] = {"limit": max(1, min(2000, limit))}
        if station_id:
            params["station_id"] = station_id
        return await self._request("GET", "/v1/demand-history", params=params)

    async def metrics(self) -> SimResponse:
        return await self._request("GET", "/v1/metrics")

    # --- the only write ---
    async def create_allocation(self, body: dict[str, Any]) -> SimResponse:
        return await self._request("POST", "/v1/allocations", json=body)

    def stream(self) -> Any:
        """Opens `/v1/stream` (SSE). Use as `async with repo.stream() as response:`."""
        return self.http.stream("GET", "/v1/stream", timeout=httpx.Timeout(None, connect=self.settings.SIMULATOR_TIMEOUT_SECONDS))

    async def aclose(self) -> None:
        await self.http.aclose()


_repository: SimulatorRepository | None = None


def get_simulator_repository() -> SimulatorRepository:
    global _repository
    if _repository is None:
        _repository = SimulatorRepository(get_settings())
    return _repository


async def close_simulator_repository() -> None:
    global _repository
    if _repository is not None:
        await _repository.aclose()
        _repository = None
