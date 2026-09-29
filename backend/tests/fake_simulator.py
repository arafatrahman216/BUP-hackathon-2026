"""An in-memory stand-in for the simulator's /v1 API, served through httpx.MockTransport."""

import copy
import json

import httpx

from app.core.config import get_settings
from app.repositories.simulator_repository import SimulatorRepository

FUELS = ("DIESEL", "PETROL")


def base_world() -> dict:
    return {
        "instance": {"id": 1, "tick": 100, "sim_time": "2026-01-02T01:00:00", "tick_minutes": 15, "status": "RUNNING"},
        "depots": [
            {"id": "depot-gazipur", "name": "Gazipur Depot", "region_id": "region-dhaka", "status": "OPEN",
             "dispatch_capacity_per_tick": 12000, "capacity": {"DIESEL": 90000, "PETROL": 70000},
             "inventory": {"DIESEL": 60000, "PETROL": 45000}},
            {"id": "depot-patiya", "name": "Patiya Depot", "region_id": "region-chattogram", "status": "OPEN",
             "dispatch_capacity_per_tick": 11000, "capacity": {"DIESEL": 85000, "PETROL": 65000},
             "inventory": {"DIESEL": 55000, "PETROL": 42000}},
        ],
        "stations": [
            {"id": "station-mirpur", "name": "Mirpur", "region_id": "region-dhaka", "status": "OPEN",
             "demand_profile": "urban_high", "demand_multiplier": 1.0,
             "capacity": {"DIESEL": 15000, "PETROL": 14000}, "inventory": {"DIESEL": 9000, "PETROL": 9000}},
            {"id": "station-tongi", "name": "Tongi", "region_id": "region-dhaka", "status": "OPEN",
             "demand_profile": "industrial", "demand_multiplier": 1.0,
             "capacity": {"DIESEL": 18000, "PETROL": 9000}, "inventory": {"DIESEL": 11000, "PETROL": 6000}},
        ],
        "routes": [
            {"id": "route-gazipur-mirpur", "source_depot_id": "depot-gazipur", "destination_station_id": "station-mirpur",
             "transit_ticks": 2, "max_shipment": 7000, "status": "AVAILABLE"},
            {"id": "route-gazipur-tongi", "source_depot_id": "depot-gazipur", "destination_station_id": "station-tongi",
             "transit_ticks": 2, "max_shipment": 6500, "status": "AVAILABLE"},
            {"id": "route-patiya-mirpur", "source_depot_id": "depot-patiya", "destination_station_id": "station-mirpur",
             "transit_ticks": 4, "max_shipment": 5000, "status": "AVAILABLE"},
        ],
        "supply-arrivals": [],
        "events": [],
        "allocations": [],
        "metrics": {"served_demand_liters": 1000.0, "unmet_demand_liters": 0.0, "service_level": 1.0,
                    "allocation_liters": 0.0, "allocation_failures": 0},
    }


class FakeSimulator:
    def __init__(self) -> None:
        self.world = base_world()
        self.rates: dict[tuple[str, str], float] = {}  # demand per tick, default 100
        self.down = False
        self.stale = False
        self.refuse: str | None = None  # 409 code to return on POST /v1/allocations
        self.lose_answer = False  # POST creates the allocation but answers 503 (response lost)
        self.posts: list[dict] = []

    def station(self, station_id: str) -> dict:
        return next(s for s in self.world["stations"] if s["id"] == station_id)

    def route(self, route_id: str) -> dict:
        return next(r for r in self.world["routes"] if r["id"] == route_id)

    def _history(self, limit: int) -> list[dict]:
        rows, tick = [], self.world["instance"]["tick"]
        for t in range(tick - 1, tick - 20, -1):
            for st in self.world["stations"]:
                for fuel in FUELS:
                    demand = self.rates.get((st["id"], fuel), 100.0)
                    rows.append({"station_id": st["id"], "fuel_type": fuel, "tick": t, "sim_time": "x",
                                 "demand_liters": demand, "served_liters": demand, "unmet_liters": 0.0})
        return rows[:limit]

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            return httpx.Response(503, json={"error": {"code": "FAULT_INJECTED", "message": "down"}})
        headers = {"X-Simulator-Stale": "true"} if self.stale else {}
        path = request.url.path
        if request.method == "POST" and path == "/v1/allocations":
            body = json.loads(request.content)
            if self.refuse:
                return httpx.Response(409, json={"detail": {"code": self.refuse, "message": "refused"}})
            earlier = next((a for a in self.world["allocations"] if a["idempotency_key"] == body["idempotency_key"]), None)
            if earlier:  # idempotent replay
                return httpx.Response(201, json=earlier)
            allocation = {**body, "id": len(self.posts) + 1, "created_tick": self.world["instance"]["tick"],
                          "departure_tick": None, "expected_arrival_tick": None, "actual_arrival_tick": None,
                          "status": "PENDING", "failure_reason": None}
            self.posts.append(body)
            self.world["allocations"].insert(0, allocation)
            if self.lose_answer:
                return httpx.Response(503, json={"error": {"code": "FAULT_INJECTED", "message": "lost"}})
            return httpx.Response(201, json=allocation)
        if path == "/v1/demand-history":
            return httpx.Response(200, json=self._history(int(request.url.params.get("limit", 200))), headers=headers)
        key = path.removeprefix("/v1/")
        if key in self.world:
            return httpx.Response(200, json=copy.deepcopy(self.world[key]), headers=headers)
        return httpx.Response(404, json={"detail": {"code": "NOT_FOUND", "message": path}})

    def repository(self) -> SimulatorRepository:
        settings = get_settings()
        http = httpx.AsyncClient(base_url="http://sim", transport=httpx.MockTransport(self.handler))
        return SimulatorRepository(settings, http=http)
