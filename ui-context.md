# UI Context: Fuel Supply Operations Console

The full context for designing the operator interface: what the project is, who uses the
screen, the simulated world, the data available (including our collected dataset), and every
UI idea we want covered.

**This document says WHAT the interface must show and let people do. It deliberately does not
decide HOW (layout, placement, chart types, visual style).** Those are the designer's decisions.

---

## 1. The project in brief

This is a hackathon project (BUP CSE Fest 2026, finals). The organizers provide the **BUP Fuel
Supply Simulator**, a simulated fuel supply network in Bangladesh. The simulator is only "the
world":

- ships deliver fuel to depots on a schedule,
- customers buy fuel at stations every 15 minutes,
- trucks move fuel from a depot to a station **only when someone orders a shipment**.

The simulator never predicts, recommends or decides anything. If nobody acts, the stations run
dry while the depots overflow.

**We build "the brain" on top of it**, a decision-support platform that:

1. **Observes** the network (fuel levels, roads, ships, crises),
2. **Detects** problems (unusual demand, road closures, delayed ships, bad data),
3. **Predicts** demand and when each station runs out of each fuel,
4. **Decides** which shipments to send (which depot, which road, how much, by when),
5. **Simulates** the effect of a decision before it's sent (with it vs without it),
6. **Acts**: sends shipments after operator approval, or automatically for safe cases,
7. **Monitors** shipments, the network and our own software health,
8. **Recovers** from crises and software failures without stopping.

An LLM (AI) writes plain-language explanations, incident summaries and answers to operator
questions. **The AI never makes the decisions and never invents numbers**; our engine computes
every number.

### Who looks at the screen

| Audience | What they need |
|---|---|
| **Operator** (primary user) | What needs attention, what to do, by when, and why, understood in seconds. Approve, edit or reject recommendations. |
| **Judges** (live demo) | To follow the reasoning behind every decision without ML knowledge, and to watch the system detect, decide, act and recover. |

**The main goal of the UI: every decision's logic is easy to follow and interpret.**

### What the judges score (relevant to the UI)

Working product and UX 20% · intelligence and decision quality 20% · resilience and incident
response 10% · observability 10% · demo and problem understanding 10%. The brief says: "a
notebook alone is not a complete submission"; "important recommendations should be
inspectable"; "human operators should remain able to inspect important decisions"; and
"distinguish simulated results from real-world fuel conditions".

The brief's required UI content (§6, "a meaningful subset of"): current fuel inventory,
depot and station status, regional demand, shortage alerts, projected shortage risk, incoming
supply, disruptions, recommended allocations, expected impact of decisions, system alerts,
decision history, service health.

### The demo story the UI must support

1. Normal operations
2. Operator dashboard
3. Demand starts increasing
4. System detects risk
5. Shortage predicted
6. Recommendation generated
7. Operator inspects the recommendation
8. Shipment is sent and tracked
9. A crisis occurs
10. System adapts
11. A software failure is injected
12. Monitoring shows the failure
13. Fallback and recovery activate
14. Operations continue

---

## 2. The simulated world

Fixed structure. Every scenario uses the same world. Use these real names.

### Regions
| Region | Demand factor |
|---|---|
| Dhaka Division | 1.00 |
| Chattogram Division | 1.08 |

### Depots (big storage, refilled by ships)
| Depot | Region | Max sent per 15 min (all fuels) | Capacity D / P / O (L) | Start D / P / O (L) |
|---|---|---|---|---|
| Gazipur | Dhaka | 12,000 L | 90,000 / 70,000 / 45,000 | 60,000 / 45,000 / 26,000 |
| Patiya | Chattogram | 11,000 L | 85,000 / 65,000 / 40,000 | 55,000 / 42,000 / 24,000 |

Depot status: `OPEN` or `CONSTRAINED` (a warning label; shipments still work).

### Stations (customers buy fuel here)
| Station | Region | Type | Capacity D / P / O (L) | Start D / P / O (L) |
|---|---|---|---|---|
| Mirpur | Dhaka | urban, busy | 15,000 / 14,000 / 9,000 | 9,000 / 9,000 / 5,000 |
| Tongi | Dhaka | industrial | 18,000 / 9,000 / 6,000 | 11,000 / 6,000 / 3,500 |
| Karnaphuli | Chattogram | highway | 14,000 / 15,000 / 9,000 | 8,500 / 9,500 / 5,200 |
| Cox's Bazar | Chattogram | regional | 12,000 / 12,000 / 7,000 | 7,500 / 7,500 / 4,200 |

Station status: `OPEN` or `OUTAGE` (closed: sells nothing, and all demand is lost).

### Roads (depot → station)
| Road | Travel time | Max per truck | Role |
|---|---|---|---|
| Gazipur → Mirpur | 30 min | 7,000 L | main |
| Gazipur → Tongi | 30 min | 6,500 L | main, **Tongi's only road** |
| Patiya → Karnaphuli | 30 min | 7,000 L | main |
| Patiya → Cox's Bazar | 45 min | 6,000 L | main, **Cox's Bazar's only road** |
| Gazipur → Karnaphuli | 60 min | 5,000 L | backup, cross-region |
| Patiya → Mirpur | 60 min | 5,000 L | backup, cross-region |

Road status: `AVAILABLE` or `DISRUPTED` (closed). Mirpur and Karnaphuli have a backup road;
Tongi and Cox's Bazar do not, so a closure cuts them off completely.

### Fuels
Diesel, Petrol, Octane.

### Time
- The clock moves in **15-minute steps** ("ticks"); 96 steps make a day. The simulation starts
  at Day 1, 00:00.
- During the demo it runs at about 1 step per second, so the screen updates roughly every 1–2 s.
  Show clock time (Day 2 · 16:45), never step numbers.

### Shipment rules (why the simulator can refuse a shipment)
A shipment is refused if:
- the road doesn't connect that depot and station,
- the station is closed or the road is closed,
- the amount exceeds the road's maximum per truck,
- the depot doesn't have the fuel,
- the depot has already sent its per-15-minute maximum,
- **the station's tank has no room for it.**

Arriving too early is as bad as too late: a full tank rejects the shipment.

Shipment lifecycle: `PENDING` (waiting to leave) → `IN_TRANSIT` → `ARRIVED`, or `FAILED` (its
road closed before it left), or `CANCELLED` (only possible while waiting). Resending the same
order never creates a duplicate.

### Supply ships
- 22 scheduled deliveries to the depots: 4 early on Day 1 (03:00–05:00), then 3 waves of 6
  (Day 1 16:00–21:00, Day 2 08:00–13:00, Day 3 00:00–05:00).
- **The last ship arrives around Day 3, 05:00. There is no more supply after that.** From then on
  the job becomes rationing a finite stock.
- Ship status: `SCHEDULED` → `ARRIVED`, or `DELAYED` (pushed later).
- **Fuel arriving at a full depot is wasted.**

### Score
**Service level** = litres served ÷ litres demanded (100% = nobody turned away). Unserved demand
is lost, not carried over to later.

---

## 3. What goes wrong (crises and failures)

Crises are injected by judges or by us for testing. They appear in the event list, and **future
ones are visible in advance as `SCHEDULED`**, so the system can act before they start.

| Crisis | What happens |
|---|---|
| Demand spike | Demand at chosen stations or regions × a multiplier (for example ×1.8) for a period |
| Road closure | Chosen roads closed; shipments on them are refused, and waiting ones fail |
| Station outage | Station closed: sells nothing, all demand lost, refuses shipments |
| Depot constraint | Depot flagged `CONSTRAINED` (warning only) |
| Ship delay | Upcoming ships pushed later (permanent, one-shot) |
| Supply shortfall | Upcoming ships carry less, for example half (permanent) |

Software failures injected into the simulator's data feed:

| Failure | What happens |
|---|---|
| Unavailable | Every data request fails; the system must keep working on its last good data |
| Error rate | A share of requests fail randomly |
| Latency | Every request slows down |
| Stale data | Responses are flagged "may be out of date"; don't act on them |
| Stream disconnect | The live update feed drops; fall back to polling |

Failures in our own system the UI must also show: the AI explainer is down (fall back to
template text), the optimizer fails (fall back to a simple rule), the database is down, or the
simulator resets to Day 1.

---

## 4. The dataset we collected

We ran the simulator for **10 simulated days (960 steps, Day 1 00:00 → Day 10 23:45) with no
shipments sent** (baseline scenario, seed 12345, no crises, no failures), and saved everything.
Location: `simulator/dataset/20260929-095304/`.

### Files and structure

| File | Rows | Columns |
|---|---|---|
| `instance.csv` | 961 (one per step) | tick, sim_time, status, tick_minutes, scenario_id, seed, wall_time, stale |
| `station_inventory.csv` | 11,532 (step × station × fuel) | tick, sim_time, station_id, region_id, status, demand_profile, demand_multiplier, fuel_type, inventory, capacity |
| `depot_inventory.csv` | 5,766 (step × depot × fuel) | tick, sim_time, depot_id, region_id, status, dispatch_capacity_per_tick, fuel_type, inventory, capacity |
| `route_status.csv` | 5,766 (step × road) | tick, sim_time, id, source_depot_id, destination_station_id, transit_ticks, max_shipment, status |
| `demand_history.csv` | 11,520 (step × station × fuel) | id, station_id, fuel_type, tick, sim_time, demand_liters, served_liters, unmet_liters |
| `metrics.csv` | 961 | tick, sim_time, served_demand_liters, unmet_demand_liters, service_level, allocation_liters, allocation_failures |
| `supply_arrivals.csv` | 22 | id, depot_id, fuel_type, quantity, planned_tick, actual_tick, status |
| `entity_changes.csv` | 44 | tick, kind, entity_id, old_status, new_status, row (every status change of a ship, event, shipment or fault) |
| `audit.csv` | 983 | id, wall_time, sim_time, tick, action, entity_type, entity_id, result, metadata_json |
| `events.csv`, `allocations.csv`, `faults.csv` | 0 | (none in this run) |
| `snapshots.jsonl` | 961 | raw JSON of the whole world per step: tick, sim_time, wall_time, stale, instance, depots, stations, routes, metrics, supply_arrivals, events, allocations, faults |

### What the data shows

**1. With no action, every station runs dry within about a day and a half.** First time each
fuel hit zero:

| Station · fuel | Empty at |
|---|---|
| Tongi · Diesel | Day 1, 16:30 (first) |
| Karnaphuli · Diesel | Day 1, 18:45 |
| Karnaphuli · Octane | Day 1, 19:15 |
| Karnaphuli · Petrol | Day 1, 20:00 |
| Cox's Bazar · Petrol | Day 1, 20:45 |
| Mirpur · Petrol | Day 1, 21:00 |
| Mirpur · Octane | Day 1, 22:00 |
| Cox's Bazar · Diesel | Day 1, 23:00 |
| Cox's Bazar · Octane | Day 2, 03:15 |
| Mirpur · Diesel | Day 2, 04:00 |
| Tongi · Petrol | Day 2, 09:30 |
| Tongi · Octane | Day 2, 13:30 (last) |

**2. The service level collapses without action:**

| Time | Service level |
|---|---|
| Day 1, 12:00 | 100% |
| Day 2, 00:00 | 87.9% |
| Day 3, 00:00 | 46.1% |
| Day 4, 00:00 | 30.7% |
| Day 6, 00:00 | 18.5% |
| Day 10, 23:45 | 9.2% (844,000 L unserved) |

This is the "do nothing" baseline our system is compared against.

**3. Supply is wasted at full depots.** Depots fill up because nothing leaves them, so later
ships can't unload: **73,000 L wasted** (for example, 12,000 L of diesel arriving at Gazipur
while it's already full at 90,000 L).

**4. Fuel is finite.** Supply stops after about Day 3, 05:00. Total fuel in the world (ships +
starting stock) covers about **6.1 days of diesel, 5.5 days of petrol and 6.5 days of octane**
at normal demand. Petrol runs out first.

**5. Demand follows a strong daily rhythm.** Average litres per 15 minutes, measured:

| Station · fuel | Quiet hours | Busy hours | Busy window | Litres per day |
|---|---|---|---|---|
| Mirpur · Petrol | ~76 | ~159 | 07–09 and 16–20 | ~10,000 |
| Mirpur · Diesel | ~62 | ~129 | 07–09 and 16–20 | ~8,100 |
| Mirpur · Octane | ~41 | ~84 | 07–09 and 16–20 | ~5,300 |
| Tongi · Diesel | ~65 | ~226 (3.5×) | 06:00–17:59 | ~14,000 |
| Tongi · Petrol | ~21 | ~73 | 06:00–17:59 | ~4,500 |
| Tongi · Octane | ~10 | ~36 | 06:00–17:59 | ~2,200 |
| Karnaphuli · Petrol | ~93 | ~167 | 06–09 and 16–20 | ~11,600 |
| Karnaphuli · Diesel | ~88 | ~160 | 06–09 and 16–20 | ~11,000 |
| Karnaphuli · Octane | ~52 | ~94 | 06–09 and 16–20 | ~6,500 |
| Cox's Bazar · Petrol | ~56 | ~107 | 07:00–20:59 | ~8,200 |
| Cox's Bazar · Diesel | ~53 | ~102 | 07:00–20:59 | ~7,800 |
| Cox's Bazar · Octane | ~26 | ~51 | 07:00–20:59 | ~3,900 |

This is why "time until empty" must account for the upcoming rush: a station that looks fine
at 05:45 can drain 3.5× faster from 06:00.

**6. Demand keeps being recorded after a station is empty.** Served drops to 0 and all demand
counts as unserved, so the lost litres can be shown.

### Example raw rows

A demand row:
```json
{"station_id": "station-tongi", "fuel_type": "DIESEL", "tick": 66, "sim_time": "2026-01-01T16:30:00",
 "demand_liters": 233.9, "served_liters": 0.0, "unmet_liters": 233.9}
```

A station, as the simulator returns it:
```json
{"id": "station-mirpur", "name": "Mirpur Fuel Station", "region_id": "region-dhaka", "status": "OPEN",
 "demand_profile": "urban_high", "demand_multiplier": 1.0,
 "capacity": {"DIESEL": 15000, "PETROL": 14000, "OCTANE": 9000},
 "inventory": {"DIESEL": 9000, "PETROL": 9000, "OCTANE": 5000}}
```

A shipment:
```json
{"id": 1, "source_depot_id": "depot-gazipur", "destination_station_id": "station-tongi",
 "route_id": "route-gazipur-tongi", "fuel_type": "DIESEL", "quantity": 6000,
 "created_tick": 96, "departure_tick": 96, "expected_arrival_tick": 98, "actual_arrival_tick": 98,
 "status": "ARRIVED", "failure_reason": null}
```

A crisis event:
```json
{"id": 1, "type": "demand_spike", "start_tick": 8, "end_tick": 20, "status": "ACTIVE",
 "parameters": {"region_ids": ["region-dhaka"], "multiplier": 1.8}}
```

A supply ship:
```json
{"id": "supply-201", "depot_id": "depot-gazipur", "fuel_type": "DIESEL", "quantity": 12000,
 "planned_tick": 128, "actual_tick": null, "status": "SCHEDULED"}
```

---

## 5. Data our backend will produce for the UI

These objects are **planned**; field names may change. They are what the interface can display
on top of the raw simulator data.

### Recommendation (a proposed shipment)
```json
{
  "id": 42, "status": "PENDING_REVIEW",
  "severity": "URGENT",
  "station": "Mirpur", "fuel": "PETROL",
  "stockout_at": "Day 2 16:45", "deadline": "Day 2 16:00",
  "action": {"quantity_l": 7000, "depot": "Gazipur", "road": "Gazipur → Mirpur",
             "travel_min": 30, "arrives": "Day 2 16:30"},
  "impact": {"without": {"empty_at": "16:45", "unserved_l": 4800},
             "with": {"never_empty": true, "safe_until": "Day 3 06:00"},
             "service_level_delta_pts": 1.2},
  "signals": [{"label": "Dhaka demand spike ×1.8", "effect_pct": 80},
              {"label": "Evening rush 16:00–20:00", "effect_pct": 45}],
  "quantity_limits": [
    {"label": "Needed until next safe restock", "value_l": 9200},
    {"label": "Room in tank at arrival", "value_l": 13550},
    {"label": "Road's max per truck", "value_l": 7000, "limiting": true},
    {"label": "Depot dispatch left this step", "value_l": 12000},
    {"label": "Depot stock above reserve", "value_l": 38000}],
  "alternatives": [
    {"label": "Patiya → Mirpur (backup road)", "rejected_because": "60 min, max 5,000 L, arrives after empty"},
    {"label": "Wait until 16:00", "rejected_because": "no safety margin left"},
    {"label": "Do nothing", "rejected_because": "~4,800 L unserved"}],
  "checks": [{"rule": "Road open", "ok": true}, {"rule": "Fits in station tank", "ok": true}],
  "confidence": {"level": "HIGH", "reasons": ["fresh data", "forecast error 6%"]},
  "needs_human_because": null,
  "forecast": {"times": ["13:30", "..."], "with_l": [2400, "..."], "without_l": [2400, "..."],
               "capacity_l": 14000, "safety_l": 1000},
  "lifecycle": [{"step": "Detected", "at": "12:15"}, {"step": "Recommended", "at": "13:30"}],
  "method": "optimizer",
  "explanation": {"source": "ai", "provider": "gemini",
                  "summary": "The Dhaka demand spike and the 16:00 rush will empty ...",
                  "why_at_risk": ["..."], "why_this": "...", "why_not_others": ["..."]}
}
```
- `severity`: `URGENT` / `WATCH` / `PLAN_AHEAD` / `SAFE`.
- `status`: `PENDING_REVIEW` / `AUTO_SENT` / `APPROVED` / `REJECTED` / `SENT` / `EXPIRED` / `REJECTED_BY_SIMULATOR`.
- `method`: `optimizer` or `fallback_rule`.
- `explanation.source`: `ai` or `template` (used when the AI is down or its text failed the number check).

### Other objects
| Object | Main fields |
|---|---|
| Station risk | station, fuel, level_l, capacity_l, pct, time_until_empty, empty_at, order_by, next_rush, risk level, in-transit litres |
| Depot outlook | depot, fuel, level, capacity, next ship (time, litres), overflow_l if nothing is sent, "runway" (hours of cover) |
| Alert | severity, type, entity, message, time, status (open / acknowledged / resolved) |
| Incident | title (e.g. "Dhaka spike → Mirpur at risk"), linked alerts, timeline, AI summary (what happened / noticed / did / result), status |
| Timeline event | time, loop stage (Observe…Recover), text, links to a recommendation, shipment or incident; future items marked scheduled |
| Shipment | status, litres, road, departed, expected and actual arrival, failure reason, replacement recommendation |
| Decision log entry | time, recommendation, actor (system / operator), action (approve / edit / reject / auto), what was sent, outcome |
| Verification | recommendation id, predicted vs actual arrival, predicted vs actual lowest level, verdict |
| Mode | `NORMAL` / `CRISIS` / `SAVE_FUEL` (rationing), with a reason |
| Health | per component (simulator, database, forecaster, optimizer, AI explainer, data freshness): healthy / degraded / down, detail; plus p95 latency, error rate, requests/s |
| Score | service level now; the same for the do-nothing twin; litres saved vs doing nothing; trucks on the road |

---

## 6. UI ideas to cover (content, not layout)

Each item says what information or action must exist. How and where it appears is up to the
designer.

### Always-visible status
- Simulated clock (day and time) and whether the simulation is running or paused.
- A **"SIMULATED NETWORK"** label (the brief requires separating simulation from reality).
- Service level, and the same number for a "do nothing" twin, plus litres saved vs doing nothing.
- Trucks on the road.
- **Mode badge**: normal / crisis / save-fuel (rationing), with the reason ("Crisis: Dhaka spike").
- **Autopilot** state (on for safe decisions only, or off), with a switch and a stop button.
- **System health** summary: simulator OK / slow / down, and "data is 3 steps old" when stale.
- **Loop stage indicator**: where the system is in Observe → Detect → Predict → Decide →
  Simulate → Act → Monitor → Recover (helps judges follow the demo).

### Network map
- Depots, stations and the 6 roads between them, with the main / backup distinction.
- Road status (open, closed, closure scheduled) and trucks currently on each road.
- Per-station worst risk at a glance; single-road stations (Tongi, Cox's Bazar) called out.

### Station cards
- Fuel level per fuel against its tank size, with a risk level (safe / watch / urgent / plan ahead).
- Time until empty, and the **latest safe order time** ("order by 15:30").
- Litres already on the way.

### Depot cards
- Fuel levels, runway (hours of cover), status.
- **Overflow warning** when a ship is coming and there's no room ("ship +12,000 L at 00:00;
  8,000 L would be wasted"), and whether the plan already covers it.
- Dispatch used this step vs the per-15-minute maximum.

### Action queue (recommendations, the main work area)
- Pending recommendations **sorted by deadline**.
- Each one shows:
  - the shipment: litres, depot, road, arrival time,
  - the deadline,
  - the impact with vs without (time until empty, unserved litres; optionally stockout risk %),
  - key signals,
  - a confidence level,
  - "needs your approval because…" when a human is required.
- Actions: **approve, edit quantity, reject, see why**.
- Items already sent by autopilot, clearly marked.
- A **6-hour plan timeline**: what the system intends to send next.

### Decision detail ("Why?")
The deep-dive for one recommendation. It answers five questions:

1. What's wrong?
2. What do we do?
3. Why this?
4. What happens with vs without it?
5. How sure are we?

Content:
- **AI summary** in 2–3 plain sentences, with a source badge ("Written by AI (Gemini)" or
  "Template (AI unavailable)"). Optionally an operator / presenter toggle; the presenter version
  adds one line on the method.
- **Forecast with vs without the shipment**: projected fuel level over the coming hours, with
  tank capacity, safety level, truck arrivals, the deadline, when it would run empty, and the
  unserved period.
- **Why it's at risk**: the signals and how much each one moved the forecast (+80% spike, +45%
  rush), plus recent forecast error.
- **How the quantity was set**: the candidate limits (need, tank room, road max, dispatch left,
  depot reserve), with the one that decided the amount highlighted, and any follow-up truck.
- **Options considered**: the alternatives, each with the reason it lost.
- **Safety checks**: the simulator's rules, all passed (road open, station open, depot stock,
  road max, dispatch limit, tank room).
- **Confidence and uncertainty** in plain words ("if demand is 20% higher, still covered").
- **Lifecycle**: Detected → Recommended → Approved → Departed → Arrived → Verified, with times.

### Ask AI
- **Grounded question buttons** on a decision: "Why not Patiya?", "What if we wait an hour?",
  "What if the road closes?". Answers use only engine data and carry the AI source badge.
- Optionally a free-form question box about the current network state. It is read-only: it can
  explain, never send shipments.

### Timeline
- A running story of the day: each item has its time, loop stage and one line of text (for
  example: "12:00 Observe: Dhaka spike started" → "12:15 Detect: Mirpur demand +78%" →
  "12:30 Predict: Mirpur petrol empties 16:45" → "13:15 Act: autopilot sent 3,000 L" →
  "13:30 Decide: 3 waiting for you").
- Future scheduled items (a road closure at 18:00, the next ship) shown as upcoming.
- Links to the related recommendation, shipment or incident.

### Alerts and incidents
- **Incidents, not raw alerts**: related alerts grouped into one story ("Dhaka spike → Mirpur at
  risk → rationing on"), each with its own timeline.
- **Crisis countdown**: "Road closure starts in 45 min".
- Acknowledge buttons. Incidents close themselves when resolved.
- An AI incident summary when resolved: what happened / what we noticed and when / what we
  did / result.

### Station detail (click a station)
- Fuel level history plus the projected line with its uncertainty range.
- Demand, actual vs forecast, with spikes marked.
- The refill window (earliest time a truck fits in the tank, latest before it's empty) and the
  next rush ("evening rush in 2 hours").

### Shipments
- Trucks waiting, on the road, arrived or failed, with expected and actual arrival times.
- Failed ones show the reason and a replacement recommendation. Waiting ones have a cancel button.
- Refusals by the simulator shown in plain words ("refused: Mirpur's diesel tank has room for
  only 1,200 L") with the re-plan.

### Decision log and verification
- Every recommendation, what the operator did (approve / edit / reject / auto), what was sent,
  and what happened.
- **"Did our predictions come true?"**: predicted vs actual arrival and lowest level, with a
  verdict. Misses included, since honesty builds trust.

### Rationing (after the last ship, around Day 3)
- Need vs what can be shipped per fuel ("Petrol, next 24 h: need 34,200 L, can ship 26,000 L →
  8,200 L short").
- Allocated vs need per station.
- The active policy: least total unserved / fairest across stations / protect single-road stations.

### What-if tool
- Try a shipment or an imaginary crisis ("close Gazipur → Mirpur for 6 hours") and see the
  predicted result vs the current plan.

### Settings
- Priorities, the rationing policy (fair vs maximize total), autopilot thresholds.
- Settings history with rollback.

### System health (operator-level)
- Per component: simulator, database, forecaster, optimizer, AI explainer, data freshness.
- p95 latency, error rate, requests per second.

---

## 7. States the design must handle

| State | What the operator must understand |
|---|---|
| Normal | All fine; few or no actions pending |
| Crisis | Which crisis, what it affects, what the system is doing about it |
| Save-fuel (rationing) | Not everyone can be served; who gets what, and why |
| Simulator down | "Simulator not responding. Showing last good data from 13:28. Retrying…" Autopilot paused. The screen still works. |
| Stale data | Data may be out of date; autopilot paused; no automatic actions |
| AI down | Explanations switch to template text, labelled as such; nothing else changes |
| Optimizer fallback | "Simple rule used (shortest open road, most urgent first)", labelled on each recommendation |
| Low confidence | The recommendation needs human review, with the reason |
| Shipment refused or failed | Why, and the replacement plan |
| Simulator reset | The clock went back to Day 1; the system resyncs |
| Empty | No recommendations: say so explicitly ("All stations covered until 18:00") |

---

## 8. Content principles

Ideas about what to say, not how it looks:

- Show a **deadline** ("decide by 16:00") in preference to a bare risk score.
  Deadline = time the station runs empty − road travel time − a 15-minute buffer.
- Use **clock time**, never step numbers.
- Use **operator words**:

  | System word | Operator word |
  |---|---|
  | allocation | shipment |
  | route disrupted | road closed |
  | unmet demand | unserved litres |
  | tick | 15 minutes |

- Keep statements short: the situation now → the situation after the action.
- **Every number comes from the engine.** AI text is checked, and if any number doesn't match
  the engine data, the template text is shown instead.
- Consequential shipments need a human. Only safe ones go automatically, and they are labelled.
- Risk levels are consistent everywhere: urgent / watch / safe / plan ahead / stale or unknown.

---

## 9. Example scenario (sample data for mockups)

Use this to fill screens with consistent, realistic numbers.

**Now:** Day 2, 13:30. Simulation running at 1×. Autopilot on (safe decisions only).

**Score:** service level 96.4% vs 81.2% for the do-nothing twin (+15.2 pts). Unserved so far
today: 420 L.

**Crises:**
- Active: Dhaka demand spike ×1.8, 12:00–22:00. Mode: CRISIS ("Dhaka spike").
- Scheduled: road closure Patiya → Cox's Bazar, 18:00–24:00 (Cox's Bazar has no backup road).

**Station levels (% of tank):**

| Station | Diesel | Petrol | Octane |
|---|---|---|---|
| Mirpur | 62% | **17% (urgent)** | 48% |
| Tongi | **31% (watch)** | 55% | 40% |
| Karnaphuli | 58% | 50% | 22% (truck on the way) |
| Cox's Bazar | **44% (plan ahead)** | 61% | 52% |

**Depots:**
- Gazipur diesel 86,000 / 90,000. Ship Day 3 00:00 brings +12,000 L, so 8,000 L would be
  wasted; the plan ships 9,000 L out first.
- Patiya petrol 58,000 / 65,000. Ship Day 3 04:00 brings +8,000 L, so 1,000 L would be wasted;
  covered.

**Recommendations:**

- **URGENT: Mirpur · Petrol.** Decide by 16:00.
  - Send 7,000 L, Gazipur → Mirpur (30 min), arrives ~16:30.
  - Without: empty at 16:45, ~4,800 L unserved by midnight. With: never runs dry.
  - Signals: spike ×1.8 (+80%), evening rush (+45%). Confidence high.
  - The road's 7,000 L max sets the quantity, so a 2,200 L follow-up is planned at 20:30.
  - Forecast (L), without: 13:30 2,400 → 16:00 1,020 → 16:30 450 → 16:45 0.
  - Forecast (L), with: 16:30 450 → 7,450 → 20:00 3,460 → 20:30 2,890 → 5,090 → Day 3 06:00 1,180.
  - Tank 14,000 L; safety level 1,000 L.
- **PLAN AHEAD: Cox's Bazar · Diesel.** Decide by 17:00.
  - Send 6,000 L, Patiya → Cox's Bazar (45 min), arrives ~17:45.
  - Why now: its only road closes 18:00–24:00. Without: empty at 21:30, ~1,600 L unserved.
- **WATCH, NEEDS REVIEW: Tongi · Diesel.** Decide by 19:30.
  - Send 6,500 L, Gazipur → Tongi.
  - Needs a human because forecast error rose to 22% during the spike (autopilot limit 15%).
- **DONE: Karnaphuli · Octane.** 3,000 L sent by autopilot at 13:15, arrives 13:45.

**Timeline:**
- 12:00 Dhaka spike started
- 12:15 Mirpur demand 78% above forecast (detected 1 step after the start)
- 12:30 Forecast rescaled
- 13:15 Autopilot shipment
- 13:30 3 recommendations waiting
- 18:00 (scheduled) Cox's Bazar road closure

**Health:**
- Simulator 38 ms · database OK · forecaster error 6% · optimizer normal · AI (Gemini) 1.2 s ·
  data 2 s old.
- p95 142 ms · errors 0.3% · 12 requests/s.

**Verification (later, Day 2 23:00):**

| # | Station · fuel | Arrival (pred / actual) | Lowest level (pred / actual) | Verdict |
|---|---|---|---|---|
| 38 | Mirpur petrol | 12:45 / 12:45 | 1,400 / 1,520 L | ✓ |
| 42 | Mirpur petrol | 16:30 / 16:30 | 450 / 380 L | ✓ never ran dry |
| 40 | Tongi diesel | | 2,000 / 1,150 L | ✗ forecast too low during the spike |

**Rationing (Day 3 onward):** petrol, next 24 h: need 34,200 L, can ship 26,000 L.

| Station | Allocated / need |
|---|---|
| Mirpur | 8,000 / 10,500 |
| Tongi | 3,600 / 4,500 |
| Karnaphuli | 8,200 / 11,600 |
| Cox's Bazar | 6,200 / 7,600 (single road, protected) |

---

## 10. Out of scope for the operator screen

These belong in the monitoring dashboard (Grafana) or the demo slides:

- Forecast math: blending weights, internal check values, optimizer internal scores.
- Per-station model accuracy tables, drift corrections, missed-step catch-up, live-feed
  connection details.
- Load-test and test-bench results.

## 11. Priority if time is short

1. Station cards
2. Alerts / incidents
3. Recommendation cards with approve buttons, plus the "Why?" detail
4. Health bar

These four cover most of the brief's §6 list. Next: the network map, the timeline, Ask AI,
shipments, the decision log with verification, and rationing.
