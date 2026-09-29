"""Structural demand model (intelligence-plan P1).

The simulator generates demand as `daily / ticks_per_day x hour_factor x region x multiplier x noise`.
We learn it online per station and fuel:

    rate(s, f, t) = level[s, f] x shape[s, hour(t)] x multiplier(s, t)

- `level` is liters per tick at an average hour (EWMA per station x fuel),
- `shape` is the hour-of-day factor, shared by the three fuels of a station,
- both are blended with a prior from the published profile tables, so the model works from tick 0,
- the multiplier is divided out before learning, so a demand spike doesn't leak into the base rate.

`ingest()` returns, for each new observation, the forecast the model had made *before* seeing it.
The Detector uses those residuals for demand anomalies (z-score + CUSUM).
"""

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# Published profile tables (simulator guide 8.5 / 8.6). Only a prior: the data overrides it.
PROFILE_DAILY: dict[str, dict[str, float]] = {
    "urban_high": {"DIESEL": 8500, "PETROL": 10500, "OCTANE": 5600},
    "industrial": {"DIESEL": 14000, "PETROL": 4500, "OCTANE": 2200},
    "highway": {"DIESEL": 10500, "PETROL": 11000, "OCTANE": 6200},
    "regional": {"DIESEL": 7200, "PETROL": 7600, "OCTANE": 3600},
}
# Noise is uniform in [1 - n, 1 + n] (measured on simulator/dataset: Mirpur ratios 0.900..1.100),
# so its standard deviation is n / sqrt(3), not n.
PROFILE_NOISE = {"urban_high": 0.10, "industrial": 0.08, "highway": 0.12, "regional": 0.10}
UNIFORM_SD = 1 / math.sqrt(3)


def prior_hour_factor(profile: str | None, hour: int) -> float:
    if profile == "urban_high":
        return 1.45 if 7 <= hour <= 9 or 16 <= hour <= 20 else 0.70
    if profile == "industrial":
        return 1.55 if 6 <= hour <= 17 else 0.45
    if profile == "highway":
        return 1.35 if 6 <= hour <= 9 or 16 <= hour <= 20 else 0.75
    if profile == "regional":
        return 1.25 if 7 <= hour <= 20 else 0.65
    return 1.0


# ---------- crisis helpers (shared by predict, detect and decide) ----------
def event_touches(event: dict[str, Any], *, station: dict[str, Any] | None = None, route_id: str | None = None,
                  depot_id: str | None = None) -> bool:
    """Guide 7.8: id lists are filters; an empty list means "all entities of that type"."""
    params = event.get("parameters") or {}
    if station is not None:
        ids, regions = params.get("station_ids") or [], params.get("region_ids") or []
        if not ids and not regions:
            return True
        return station.get("id") in ids or station.get("region_id") in regions
    if route_id is not None:
        return not params.get("route_ids") or route_id in params["route_ids"]
    if depot_id is not None:
        return not params.get("depot_ids") or depot_id in params["depot_ids"]
    return False


def active_at(event: dict[str, Any], tick: int, *, by_window: bool = False) -> bool:
    """Is the event in force at `tick`? by_window=True ignores the status (for past ticks,
    where a spike that is RESOLVED now was still active back then)."""
    if event.get("status") == "RESOLVED" and not by_window:
        return False
    start, end = event.get("start_tick"), event.get("end_tick")
    return start is not None and end is not None and int(start) <= tick < int(end)


def spike_factor(events: list[dict[str, Any]], station: dict[str, Any], tick: int) -> float:
    factor = 1.0
    for e in events:
        if e.get("type") == "demand_spike" and active_at(e, tick, by_window=True) and event_touches(e, station=station):
            factor *= float((e.get("parameters") or {}).get("multiplier") or 1.5)
    return factor


def multiplier_at(world_events: list[dict[str, Any]], station: dict[str, Any], now: int, tick: int) -> float:
    """Multiplier at any past or future tick: the live value, rescaled by the known spikes."""
    live = float(station.get("demand_multiplier") or 1.0)
    now_f = spike_factor(world_events, station, now)
    return live * spike_factor(world_events, station, tick) / (now_f or 1.0)


class Clock:
    """Maps ticks to hour of day using the instance's (tick, sim_time) anchor."""

    def __init__(self, tick: int, sim_time: Any, tick_minutes: int) -> None:
        self.tick, self.tick_minutes = tick, tick_minutes
        try:
            t = datetime.fromisoformat(str(sim_time).replace("Z", "+00:00"))
            self.anchor_minutes = t.hour * 60 + t.minute
        except ValueError:
            self.anchor_minutes = (tick * tick_minutes) % 1440
        self.ticks_per_day = max(1, 1440 // tick_minutes)

    def hour(self, tick: int) -> int:
        return int(((self.anchor_minutes + (tick - self.tick) * self.tick_minutes) % 1440) // 60)


@dataclass
class Residual:
    station_id: str
    fuel_type: str
    tick: int
    actual: float
    predicted: float
    cv: float


class DemandModel:
    LEVEL_ALPHA = 0.05  # ~20 observations memory
    SHAPE_ALPHA = 0.25
    LEVEL_PRIOR_N = 24  # prior weight in observations
    SHAPE_PRIOR_N = 8
    ERR_ALPHA = 0.05

    def __init__(self) -> None:
        self.level: dict[tuple[str, str], float] = {}
        self.n_level: dict[tuple[str, str], int] = {}
        self.shape: dict[tuple[str, int], float] = {}
        self.n_shape: dict[tuple[str, int], int] = {}
        self.sq_err: dict[tuple[str, str], float] = {}  # EWMA of squared log error
        self.abs_err: dict[tuple[str, str], float] = {}  # EWMA of |error| liters (for WAPE)
        self.abs_act: dict[tuple[str, str], float] = {}  # EWMA of actual liters
        self.last_tick: dict[tuple[str, str], int] = {}
        self.stations: dict[str, dict[str, Any]] = {}
        self.tick_minutes = 15

    # ----- priors -----
    def prior_level(self, station_id: str, fuel: str) -> float | None:
        profile = self.stations.get(station_id, {}).get("demand_profile")
        daily = PROFILE_DAILY.get(profile, {}).get(fuel)
        return daily * self.tick_minutes / 1440 if daily else None

    def level_of(self, station_id: str, fuel: str) -> float | None:
        key = (station_id, fuel)
        prior, n = self.prior_level(station_id, fuel), self.n_level.get(key, 0)
        if n == 0:
            return prior
        if prior is None:
            return self.level[key]
        return (n * self.level[key] + self.LEVEL_PRIOR_N * prior) / (n + self.LEVEL_PRIOR_N)

    def shape_of(self, station_id: str, hour: int) -> float:
        prior = prior_hour_factor(self.stations.get(station_id, {}).get("demand_profile"), hour)
        n = self.n_shape.get((station_id, hour), 0)
        if n == 0:
            return prior
        return (n * self.shape[(station_id, hour)] + self.SHAPE_PRIOR_N * prior) / (n + self.SHAPE_PRIOR_N)

    def cv(self, station_id: str, fuel: str) -> float:
        floor = PROFILE_NOISE.get(self.stations.get(station_id, {}).get("demand_profile"), 0.10) * UNIFORM_SD
        sq = self.sq_err.get((station_id, fuel))
        return max(floor, math.sqrt(sq)) if sq is not None else floor

    def wape(self, station_id: str, fuel: str) -> float | None:
        act = self.abs_act.get((station_id, fuel))
        return self.abs_err[(station_id, fuel)] / act if act else None

    def observations(self, station_id: str, fuel: str) -> int:
        return self.n_level.get((station_id, fuel), 0)

    def rate(self, station_id: str, fuel: str, hour: int, multiplier: float) -> float | None:
        level = self.level_of(station_id, fuel)
        return None if level is None else max(0.0, level * self.shape_of(station_id, hour) * multiplier)

    # ----- learning -----
    def ingest(self, world: Any) -> list[Residual]:
        """Learn from demand-history rows we haven't seen. Returns pre-update residuals."""
        self.stations = world.stations
        self.tick_minutes = world.tick_minutes
        clock = Clock(world.tick, world.instance.get("sim_time"), world.tick_minutes)
        rows = sorted((r for r in world.history
                       if int(r.get("tick", -1)) > self.last_tick.get((r.get("station_id"), r.get("fuel_type")), -1)),
                      key=lambda r: int(r["tick"]))
        residuals = []
        for row in rows:
            sid, fuel, tick = row["station_id"], row["fuel_type"], int(row["tick"])
            station = world.stations.get(sid)
            if station is None:
                continue
            demand = float(row.get("demand_liters") or 0.0)
            mult = multiplier_at(world.events, station, world.tick, tick) or 1.0
            hour = clock.hour(tick)
            key = (sid, fuel)
            predicted = self.rate(sid, fuel, hour, mult)
            if predicted is not None and predicted > 0:
                residuals.append(Residual(sid, fuel, tick, demand, predicted, self.cv(sid, fuel)))
                log_err = math.log((demand + 1) / (predicted + 1))
                self.sq_err[key] = self.sq_err.get(key, log_err ** 2) + self.ERR_ALPHA * (log_err ** 2 - self.sq_err.get(key, log_err ** 2))
                self.abs_err[key] = self.abs_err.get(key, 0.0) + self.ERR_ALPHA * (abs(demand - predicted) - self.abs_err.get(key, 0.0))
                self.abs_act[key] = self.abs_act.get(key, demand) + self.ERR_ALPHA * (demand - self.abs_act.get(key, demand))
            base = demand / mult
            level_now = self.level_of(sid, fuel)
            target_level = base / max(self.shape_of(sid, hour), 1e-6)
            if self.n_level.get(key, 0) == 0:
                self.level[key] = target_level
            else:
                self.level[key] += self.LEVEL_ALPHA * (target_level - self.level[key])
            self.n_level[key] = self.n_level.get(key, 0) + 1
            if level_now:
                skey = (sid, hour)
                target_shape = base / level_now
                if self.n_shape.get(skey, 0) == 0:
                    self.shape[skey] = target_shape
                else:
                    self.shape[skey] += self.SHAPE_ALPHA * (target_shape - self.shape[skey])
                self.n_shape[skey] = self.n_shape.get(skey, 0) + 1
            self.last_tick[key] = tick
        return residuals

    # ----- forecasting -----
    def path(self, world: Any, station_id: str, fuel: str, horizon: int) -> list[float] | None:
        """Forecast liters for ticks now .. now+horizon-1 (scheduled spikes included)."""
        station = world.stations[station_id]
        clock = Clock(world.tick, world.instance.get("sim_time"), world.tick_minutes)
        out = []
        for k in range(horizon):
            t = world.tick + k
            r = self.rate(station_id, fuel, clock.hour(t), multiplier_at(world.events, station, world.tick, t))
            if r is None:
                return None
            out.append(r)
        return out

    def daily_rate(self, world: Any, station_id: str, fuel: str) -> float | None:
        """Average liters per tick over a whole day at the current multiplier."""
        level = self.level_of(station_id, fuel)
        if level is None:
            return None
        shape_mean = sum(self.shape_of(station_id, h) for h in range(24)) / 24
        return level * shape_mean * float(world.stations[station_id].get("demand_multiplier") or 1.0)
