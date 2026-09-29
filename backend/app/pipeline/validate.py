"""Validate stage: sanity checks on what the simulator returned. A fatal issue means
"don't act on this data" (the pipeline still shows it, marked invalid)."""

from app.pipeline.types import World


def validate_world(world: World) -> tuple[list[str], bool]:
    """Returns (issues, fatal)."""
    issues: list[str] = []
    fatal = False
    if not world.stations or not world.depots or not world.routes:
        return ["Simulator returned no stations, depots or routes"], True

    for kind, entities in (("station", world.stations), ("depot", world.depots)):
        for entity_id, entity in entities.items():
            capacity, inventory = entity.get("capacity") or {}, entity.get("inventory") or {}
            if set(capacity) != set(inventory):
                issues.append(f"{kind} {entity_id}: fuel types differ between capacity and inventory")
                fatal = True
            for fuel, level in inventory.items():
                cap = capacity.get(fuel)
                if not isinstance(level, (int, float)) or level < 0:
                    issues.append(f"{kind} {entity_id} {fuel}: invalid inventory {level!r}")
                    fatal = True
                elif isinstance(cap, (int, float)) and level > cap * 1.001:
                    issues.append(f"{kind} {entity_id} {fuel}: inventory {level:.0f} above capacity {cap:.0f}")

    for route_id, route in world.routes.items():
        if route.get("source_depot_id") not in world.depots or route.get("destination_station_id") not in world.stations:
            issues.append(f"route {route_id}: unknown depot or station")
            fatal = True
        if not route.get("transit_ticks") or not route.get("max_shipment"):
            issues.append(f"route {route_id}: missing transit_ticks or max_shipment")
            fatal = True

    if world.stale:
        issues.append("Simulator flagged the data as stale (X-Simulator-Stale)")
        fatal = True
    return issues, fatal
