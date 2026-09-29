# Intelligence and Application Cases

A catalog of what our platform can predict, detect, decide, explain and show, based on what
the BUP Fuel Supply Simulator actually exposes. It expands the example lists in
[problem.md](problem.md) §6 (application) and §7 (intelligence), and pulls in cases from
§9, §10, §11, §14 and §21.

★ marks niche cases that come from how this particular simulator works. Most teams are
unlikely to find them, so they are our best way to stand out.

For the domain background, see [project-context.md](project-context.md). For the API, see
[BUP_Fuel_Supply_Simulator_Integration_Guide_Final.md](BUP_Fuel_Supply_Simulator_Integration_Guide_Final.md).

---

## 1. Verified facts that the niche cases rely on

These come from a 10-day run with no actions (baseline scenario, seed 12345, ticks 0–959),
stored in `simulator/dataset/20260929-095304/`.

### 1.1 Supply that doesn't fit in a depot is thrown away

When a ship arrives, depot inventory is capped at its capacity and the extra fuel
disappears. In the run with no shipments going out, **73,000 L was wasted**.

| Arrival | Depot / fuel | Before | + Qty | After | Capacity | Wasted |
|---|---|---|---|---|---|---|
| supply-201 | Gazipur diesel | 90,000 | 12,000 | 90,000 | 90,000 | 12,000 |
| supply-202 | Gazipur petrol | 69,000 | 10,000 | 70,000 | 70,000 | 9,000 |
| supply-304 | Patiya diesel | 85,000 | 10,000 | 85,000 | 85,000 | 10,000 |

An arrival shows up in depot inventory one tick after its `actual_tick`. For example,
supply-001 arrives at tick 12, and Gazipur diesel goes from 60,000 L at tick 12 to 78,000 L
at tick 13.

### 1.2 Fuel is finite

All 22 supply arrivals land by **tick 212 (about day 2.2)** and never repeat.

| Fuel | Scheduled supply | Total fuel in the world (supply + depots + stations) | Day-1 demand | Days of cover |
|---|---|---|---|---|
| Diesel | 100,000 L | 251,000 L | 40,886 L | 6.1 |
| Petrol | 68,000 L | 187,000 L | 34,234 L | **5.5** |
| Octane | 48,000 L | 115,900 L | 17,934 L | 6.5 |

After about day 2 the job changes from restocking to **rationing**, and petrol runs out
first. After 10 days with no action, the service level was 0.09.

### 1.3 Demand keeps being recorded after a station runs dry

When a station is empty, `served_liters` is 0 but `demand_liters` still holds the full
demand (10,370 such rows in the run). The history isn't cut off by stockouts, so the
forecaster should learn from `demand_liters`, not `served_liters`.

**Not yet verified:** whether demand is still recorded during a `station_outage`. The dataset
has no crises, so inject one event and check before relying on it.

### 1.4 Two stations have only one route

From the route table:

| Station | Routes | Backup? |
|---|---|---|
| Mirpur | Gazipur→Mirpur (2 ticks), Patiya→Mirpur (4 ticks) | yes |
| Karnaphuli | Patiya→Karnaphuli (2 ticks), Gazipur→Karnaphuli (4 ticks) | yes |
| **Tongi** | Gazipur→Tongi only | **no** |
| **Cox's Bazar** | Patiya→Cox's Bazar only | **no** |

If a `route_disruption` hits Tongi's or Cox's Bazar's only route, that station can't be
reached at all until the disruption ends.

---

## 2. Predict

| Case | From brief? | Signal / approach |
|---|---|---|
| Demand forecast per station × fuel × hour of day | §7 | demand history × current `demand_multiplier` |
| Stockout time and stockout probability | §7 | inventory, forecast, forecast variance |
| Supply arrival time | §7 | `planned_tick` vs `actual_tick`, delay events |
| ★ **Time until stockout, adjusted for the hour of day** | | Tongi runs at 1.55× demand from 06:00 to 17:59 and 0.45× at night, a 3.4× swing. A straight-line estimate made at 05:45 is badly wrong. Show our estimate next to the naive one. |
| ★ **Depot overflow forecast** | | "supply-201 arrives in 6 ticks; Gazipur has room for 0 L; ship out 12,000 L first or lose it" (§1.1) |
| ★ **When the world runs out** | | total supply + stock vs forecast demand, giving the day each fuel runs out network-wide (§1.2) |
| ★ **Delivery window** | | Earliest tick a shipment of Q litres fits in the station tank (otherwise `DESTINATION_CAPACITY_EXCEEDED`) and latest tick before it runs dry. Ship inside that window. |
| ★ **Dispatch congestion** | | Several stations needing fuel from the same depot in the same tick hit its per-tick dispatch limit (12,000 or 11,000 L, shared by all fuels and stations) |
| ★ **Allocation will fail** | | A pending shipment whose route has a `route_disruption` event scheduled before it departs will end up `FAILED`. Cancel it and reroute. |
| ★ **Rebound after a crisis** | | When a demand spike ends, demand drops back and a station stocked for the spike may overflow |
| Projected service level (do nothing vs our plan) | §6 "expected impact" | forecast + plan |
| Long-term depot deficit after a supply cut | | `supply_shortfall` is permanent, so the gap in litres per day is structural |

## 3. Detect

| Case | From brief? | Signal / approach |
|---|---|---|
| Unusual demand | §7 | how far actual demand is from the forecast, per station |
| Abnormal inventory changes | §7 | ★ **Inventory reconciliation:** `Δinventory` should equal arrivals − served − dispatched. Anything left over is unexplained (a bug, a reset or tampering). |
| Supply-chain bottlenecks | §7 | dispatch limit saturated, route shipment limit maxed, depot full |
| Region-wide disruption | §7 | several stations in one region showing anomalies at once, so infer a regional event |
| ★ **Single points of failure** | | Tongi and Cox's Bazar have one route each (§1.4). Hold a larger safety stock there and raise risk sooner. |
| ★ **Silent supply changes** | | Diff successive snapshots: a planned arrival's `quantity` shrank (shortfall) or its `planned_tick` moved (delay) |
| ★ **Demand change with no event behind it** | | `demand_multiplier` changed, or demand jumped, but `/v1/events` shows nothing |
| ★ **Wasted supply** | | Arrival quantity minus the actual inventory gain. Measure and report the litres lost (§1.1). |
| ★ **Clock problems** | | Tick went backwards (a reset, so resync). Tick skipped (our loop fell behind). Tick frozen while status is RUNNING (stale data we caught ourselves). |
| Invalid simulator data | §11 | inventory above capacity, negative values, unknown ids, schema validation failure |
| ★ **Stuck shipments** | | still `PENDING` or `IN_TRANSIT` after `expected_arrival_tick` |
| ★ **Forecast drift** | §21 | forecast error trending upward, so retrain or widen the uncertainty |
| ★ **Wrong demand profile** | | the learned daily pattern doesn't match the station's declared `demand_profile` |
| ★ **Our own planning mistakes** | §14 | Rate of 409 rejections by code. A good planner should get close to 0. |
| ★ **Operator not responding** | | recommendations expiring before anyone approves them |

## 4. Decide

| Case | From brief? | Idea |
|---|---|---|
| LP, greedy, priority rules, RL, hybrid policies | §7, §8 | core allocation engine |
| ★ **Act before scheduled events** | | `/v1/events` shows `SCHEDULED` crises before they start. Stock up before a spike or route cut instead of reacting to it. |
| ★ **Empty depots ahead of ships** | | Time shipments so every arrival has room, which recovers the wasted supply (§1.1) |
| ★ **Ration a finite supply** | | After about day 2 no more fuel arrives (§1.2). Decide who runs short: total unmet litres vs the longest stockout at any one station vs fairness between regions. |
| ★ **Use cross-region routes to rebalance** | | Use Gazipur→Karnaphuli and Patiya→Mirpur to move stock from a fuller depot, not only as backups |
| ★ **Split the dispatch limit across fuels** | | Decide which fuel gets this tick's 12,000 L at Gazipur (11,000 L at Patiya) |
| ★ **Cancel and reroute before failure** | | Cancel `PENDING` shipments that will fail, then resend on another route |
| ★ **Refill right after an outage** | | A station in outage freezes and rejects shipments. Queue a delivery for the tick it reopens. |
| ★ **Recommend waiting** | §9 "alternative actions" | "Don't ship yet: the tank has no room, or a ship arrives in 3 ticks" |
| Low-confidence decisions go to a human | §11 | confidence threshold → review queue |

## 5. Generative AI

The brief (§7) says LLMs must support operations, not just be a chatbot bolted on. The LLM
explains and summarizes; it never makes the numbers or the decisions.

| Case | From brief? |
|---|---|
| Incident explanation, network state summary, investigation help, decision explanations | §7 |
| ★ **Shift handover report** every N ticks: what changed, what's at risk, what's pending | |
| ★ **Automatic post-incident review** built from alerts, decisions and the audit log | |
| ★ **What-if questions in plain language**: "What if Gazipur→Mirpur closes for 6 h?" The LLM turns the question into a scenario and our engine computes the numbers. | §21 counterfactual simulation |
| ★ **Plain-language 409 explanations**, e.g. "rejected: Mirpur's diesel tank has room for only 1,200 L" | |
| ★ **Grouping alerts**: many related alerts summarized as one incident | §21 automated incident detection |

## 6. Application screens

§6 lists 12 items: inventory, depot/station status, regional demand, shortage alerts,
projected shortage risk, incoming supply, disruptions, recommended allocations, expected
impact, system alerts, decision history and service health.

Screens worth adding:

- Shipment tracker with arrival countdowns
- Depot headroom vs incoming ships (shows the overflow risk)
- Timeline of scheduled crises
- Forecast vs actual chart
- Service-level trend
- Our plan vs doing nothing
- What-if panel
- Approval queue with expiry timers
- Route map that highlights single-route stations
- Data freshness indicator and degraded-mode banner
- Replay slider over stored snapshots

---

## 7. Recommended niche

### Main pick: "anticipate, don't react", backed by our own copy of the simulator

- The simulator is deterministic and its formulas are documented (Integration Guide
  §8.5–8.7), so we can rebuild it inside our backend. That copy covers the **Simulate**
  step of the loop.
- Before sending anything, we run each candidate plan through the copy, measure how far its
  results drift from the real simulator, and show "plan vs do nothing."
- On top of the copy we use three things most teams will miss:
  - scheduled events visible in advance
  - supply wasted at depot capacity (§1.1)
  - the finite fuel horizon (§1.2)

It improves `service_level` directly, gives inspectable reasoning with before/after numbers
(brief §9), and is easy to demo. For example: "a crisis is scheduled for tick 300; we stocked
Mirpur at tick 290; here's the counterfactual."

### Backup pick: single-route vulnerability + inventory reconciliation

It's cheap to build and scores well on resilience and detection (§1.4 and the reconciliation
row in §3).

---

## 8. Open checks

- [ ] Is `demand_liters` still recorded while a station is in `station_outage`? (§1.3)
- [ ] Does supply wasted at depot capacity show up anywhere in `/v1/metrics` or `/admin/audit`, or only in the inventory numbers?
- [ ] Could a judging image have a different supply schedule? Read `/v1/supply-arrivals` at runtime; never hard-code the tick-212 horizon.
