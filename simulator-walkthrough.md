# Simulator Walkthrough: How the Data Flows

This walkthrough shows what the BUP Fuel Supply Simulator does and how our system will
work with it. Every number here comes from a real test run against the simulator
(started paused, then moved forward 15 minutes at a time).

To run the simulator yourself:

```bash
cd simulator
SIMULATOR_START_MODE=paused docker compose up -d
curl -s http://localhost:8000/v1/health
```

The simulator's own dashboard is at http://localhost:8000/admin.

---

## The big picture

```
          ┌──────────── SIMULATOR (the world) ─────────────┐
          │ ships arrive at depots → depots → roads →       │
          │ stations → customers buy fuel every 15 minutes  │
          └──────▲──────────────────────────────┬──────────┘
                 │ 3. send a shipment            │ 1. read what's happening
                 │                               ▼
          ┌──────┴──── OUR SYSTEM (the brain) ─────────────┐
          │ 2. spot trouble → predict → pick the best      │
          │    shipment → explain it → operator approves   │
          └────────────────────────────────────────────────┘
                 4. time moves on → read again → repeat
```

**The key point:** the simulator never moves fuel from a depot to a station on its own.
Supply ships refill the depots automatically, but stations only get fuel when our system
sends it.

## The world

- **2 regions:** Dhaka and Chattogram
- **2 depots** (big storage): Gazipur (Dhaka) and Patiya (Chattogram)
- **4 stations** (where customers buy fuel): Mirpur, Tongi, Karnaphuli, Cox's Bazar
- **6 roads** from depots to stations. Each road has a travel time and a limit on how much one shipment can carry.
- **3 fuels:** Diesel, Petrol, Octane
- **Time:** one step (a "tick") is 15 minutes. 96 ticks make one day.
- **Supply ships:** 22 scheduled deliveries to the depots

| Road | Travel time | Max per shipment |
|---|---|---|
| Gazipur → Mirpur | 30 min | 7,000 L |
| Gazipur → Tongi | 30 min | 6,500 L |
| Patiya → Karnaphuli | 30 min | 7,000 L |
| Patiya → Cox's Bazar | 45 min | 6,000 L |
| Gazipur → Karnaphuli (backup) | 60 min | 5,000 L |
| Patiya → Mirpur (backup) | 60 min | 5,000 L |

---

## What happened in the test run

### 1. Doing nothing for one day

Tick 0 is midnight and tick 96 is the next midnight.

| Time | Tongi diesel | Mirpur petrol | Gazipur depot diesel |
|---|---|---|---|
| 00:00 | 11,000 L | 9,000 L | 60,000 L |
| 12:00 | 3,997 L | 4,326 L | refilled by ship |
| 16:15 | **empty** | 1,866 L (at 18:00) | |
| 24:00 | 0 | **0** | **90,000 L (completely full)** |

- 11,245 L of demand went unserved.
- **The service level (our score) fell to 88%.**
- The depots were overflowing with fuel while the stations ran dry. **This is the problem our system solves.**

Every tick, the simulator records one line per station and fuel (12 lines per tick), for example:

```json
{"station_id": "station-tongi", "fuel_type": "DIESEL", "tick": 31,
 "sim_time": "2026-01-01T07:45:00",
 "demand_liters": 228.0, "served_liters": 228.0, "unmet_liters": 0.0}
```

Once a station is empty, `served` drops to 0 and all demand becomes `unmet`. This demand
history is what we use to predict demand.

### 2. Sending a shipment

We sent 6,000 L of diesel from Gazipur to Tongi:

```json
POST /v1/allocations
{"idempotency_key": "story-001",
 "source_depot_id": "depot-gazipur", "destination_station_id": "station-tongi",
 "route_id": "route-gazipur-tongi", "fuel_type": "DIESEL", "quantity": 6000}
```

| Tick | Shipment status | Tongi diesel |
|---|---|---|
| 96 | waiting, then leaves the depot | 0 L |
| 97 | on the road | 0 L |
| 98 | **arrived** (30 minutes later) | 5,934 L |

- Sending the exact same request again did **not** create a second shipment, so retrying is safe.
- Reusing the same request ID with a different amount was **rejected**.

### 3. Shipments the simulator refuses

| What we tried | Answer |
|---|---|
| 9,000 L on a road with a 7,000 L limit | *Too big for this road* |
| Gazipur fuel on the Patiya → Mirpur road | *Road doesn't connect these places* |
| Fuel type "KEROSENE" | *Invalid input* |

It also refuses shipments when a road is cut, a station is closed, the depot doesn't have
enough fuel, the depot has already sent too much this tick, or the station tank would
overflow. **Our system should check all of this before sending anything.**

### 4. A crisis

We set off three problems at once:

| Problem | What we saw |
|---|---|
| Dhaka demand doubled | Mirpur petrol demand went from about 80 L to **156 L** every 15 minutes, all of it unserved |
| Gazipur → Mirpur road cut | A shipment on that road was refused: *road disrupted* |
| Gazipur supply ship delayed | The next delivery moved from tick 128 to tick 136 |

- **Rerouting worked:** a shipment through the backup Patiya → Mirpur road was accepted.
  It took **60 minutes instead of 30**.
- When the crisis ended, the road reopened and demand returned to normal.
- Crises can also include a station closing, a depot being limited, or a supply ship bringing less fuel than planned.

### 5. The simulator itself breaking

| Fault | What happened |
|---|---|
| "Unavailable" | Every data request failed with an error, **but the health check still said "ok"**. Our system has to keep going on its last saved data and retry. |
| "Stale data" | Responses carried a warning flag (`X-Simulator-Stale: true`), so we shouldn't trust those numbers. |

Other faults: slow responses, random failures, and the live update feed disconnecting.

**By the end, the score was 81%**, because only a few shipments were sent.

---

## What this means for our system

| Step | Our system does | Example from this run |
|---|---|---|
| **Watch** | Read stations, depots, roads and ships every tick | Tongi diesel is falling about 230 L per 15 minutes during work hours |
| **Warn** | Estimate when each station runs out | "Tongi diesel runs out at 16:15" |
| **Recommend** | Choose which depot, which road and how much, within the limits | "Send 6,000 L from Gazipur, arrives in 30 minutes" |
| **Explain** | Show why, and what changes | "Unserved demand drops from 3,000 L to about 0" |
| **Adapt** | When a road is cut, switch to the backup road | Patiya → Mirpur, 60 minutes instead of 30 |
| **Survive** | When the simulator breaks, use saved data and retry | Keep working through the "unavailable" fault |
| **Record** | Keep a history of every decision and what happened | Shipment #1: sent at tick 96, arrived at tick 98 |

**The goal:** keep the service level close to 100%, even during crises and failures.

---

## Useful commands for testing

| Action | Command |
|---|---|
| Move time forward 15 minutes | `curl -X POST localhost:8000/admin/step` |
| Start / pause the clock | `curl -X POST localhost:8000/admin/run` / `.../admin/pause` |
| Reset everything | `curl -X POST localhost:8000/admin/reset` |
| Start a crisis | `curl -X POST localhost:8000/admin/events -H 'Content-Type: application/json' -d '{"type":"demand_spike","start_tick":10,"duration_ticks":16,"parameters":{"region_ids":["region-dhaka"],"multiplier":2.0}}'` |
| Break the simulator for 30 s | `curl -X POST localhost:8000/admin/faults -H 'Content-Type: application/json' -d '{"type":"unavailable","duration_seconds":30}'` |
| Clear all faults | `curl -X POST localhost:8000/admin/faults/clear` |
| See the score | `curl localhost:8000/v1/metrics` |

**Note:** the simulator uses port 8000, which is also our backend's default port. Run
the backend on another port (for example `BACKEND_PORT=8001`) when both are running.
