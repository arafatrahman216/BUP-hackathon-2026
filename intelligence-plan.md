# Intelligence Plan: What We Keep

This is the final selection from [solution-details.md](solution-details.md) (the how) and
[intelligence-cases.md](intelligence-cases.md) (the catalog of cases). For each part it lists
**what we build**, **what's a stretch goal**, and **what we drop**.

**How we chose:** does it move the service level, does it make a strong demo moment, can it be
built in hackathon time, and does it use something about this simulator that most teams will miss.

---

## 0. Facts that change the plan

1. **Fuel is finite.** The last supply ship arrives at tick 212 (about day 2.2), which we
   re-checked on the live simulator. After that, the world holds only 5.5–6.5 days of demand. At
   demo speed (1 tick per second, one day ≈ 1.6 min), **a 15-minute demo covers about 9 simulated days**, so the
   judges will see the rationing phase.
2. **Wasted fuel is lost for good.** Doing nothing wasted **73,000 L** at full depots. Our tests
   also showed that trucks lose any fuel that doesn't fit in the station tank.
3. **Consequence:** once fuel is finite, the total liters served is capped by how much fuel exists. So the score comes down to:
   - **waste nothing**: no depot overflow, no tank overflow,
   - **get the fuel to where the demand is**: don't strand it in the wrong place,
   - **choose who runs short, and when**: rationing.

   **Rationing is the main mode after day 2, not an edge case.**

**Open checks from intelligence-cases.md §8, now answered:**
- **Demand during a station outage *is* still recorded.** Our outage test showed Tongi at tick 1 with demand 64 L, served 0, unmet 64.
- **Wasted supply is visible in the audit log:** `supply.arrived` has `added` (for example 7,000 of a 12,000 L ship), and `allocation.arrived` has `received`. It's **not** in `/v1/metrics`.
- **Never hard-code tick 212.** Always read the supply schedule from the simulator.

---

## 1. Core idea: "anticipate, don't react", powered by our own copy of the simulator

We take the **main pick from intelligence-cases.md §7**. It's the same engine as the tank and depot
projection in solution-details.md, extended into a full **copy of the simulator** inside our backend.
The simulator's rules are published, so we can predict its next hours. One engine then powers:
- forecasts and time until empty,
- the "with vs without" impact of each recommendation,
- "our plan vs doing nothing",
- crisis impact previews,
- the what-if tool.

We check the copy against the real simulator every tick. How far it drifts is itself a quality measure.

---

## 2. PREDICT

### Build
| # | What | Why it's kept |
|---|---|---|
| P1 | **Demand forecast that knows the time of day:** published pattern + blended with real data + current multiplier. Learns from `demand_liters` (true demand), not `served_liters` | Everything else depends on it. The time-of-day part matters: Tongi swings 3.4× between day and night |
| P2 | **Time until empty + risk %** per station and fuel. Shown **next to the naive straight-line estimate** | Core warning. The side-by-side shows why our estimate is better |
| P3 | **Refill window:** the earliest tick a truckload fits in the tank, and the **latest safe order time** | Clear for operators ("order by 15:30"). Prevents both overflow and stockouts |
| P4 | **Depot overflow forecast:** "ship arrives in 6 ticks, room for 0 L, move 12,000 L out first" | Directly recovers wasted fuel (73,000 L in the no-action run) |
| P5 | **Fuel runs out network-wide:** for each fuel, the day the whole network runs out (total supply + stock vs forecast demand) | Tells us when to switch to rationing. Petrol goes first |
| P6 | **Impact of every plan:** run the copy of the simulator with and without the plan → risk and unserved liters before and after, plus a live **"our plan vs doing nothing"** score | The brief's §9 example ("72% → 19%") and the strongest demo evidence |
| P7 | **Scheduled crisis preview:** include `SCHEDULED` crises in the projection → "the spike at tick 300 will cause 3,000 L unserved unless we pre-fill". Also flag **trucks that will fail** because their road is cut before they leave | Makes "anticipate" visible |
| P8 | **Simple confidence:** recent forecast error + data freshness + active crisis → one score from 0 to 1 | Drives the human-approval rule (brief §11) |

### Stretch
- Picking the most accurate forecast method per station automatically. Do it on the test bench first.
- Guessing how long an unannounced spike will last.

### Drop
- Weekly patterns: no sign they exist.
- Learning from past crises.
- Transport delay prediction: truck times are fixed.
- A separate score forecast: P6 already covers it.
- Rebound after a crisis: P1 and P6 handle it automatically when the multiplier ends.

---

## 3. DETECT

### Build
| # | What | Why it's kept |
|---|---|---|
| D1 | **Change detection each tick:** roads, stations, depots, multipliers, new or scheduled crises, plus **silent supply changes** (a ship's amount shrank or its tick moved) with a **crisis countdown** | Catches every crisis type, including ones announced in advance |
| D2 | **Unusual demand:** single-tick check + running-total check, alerting after 2+ ticks, which estimates the spike size. Also flags **demand changes with no crisis behind them** | Covers "anomalous demand" in the brief's §7 list and catches hidden changes |
| D3 | **Data and clock checks:** stale flag, impossible values, unknown IDs, tick going backwards (reset → resync), skipped or frozen ticks → **hold decisions and show "stale"** | Resilience requirement (brief §11): invalid simulator response → reject + alert |
| D4 | **Inventory reconciliation:** the change in fuel should equal arrivals − sold − shipped out. Leftovers are unexplained. This also **measures wasted fuel** at depots and tanks, using the audit log | Covers "abnormal inventory changes" in the brief. Cheap and distinctive |
| D5 | **Single-route stations:** Tongi and Cox's Bazar have only one road → a permanently higher risk level, a bigger buffer, and a critical alert if their road is cut | Most teams will miss this. Cheap, and it drives better decisions |
| D6 | **Bottlenecks and shipment problems:** a depot's sending limit repeatedly full, trucks stuck past their arrival time, failed trucks | Covers "supply-chain bottlenecks" in the brief |
| D7 | **Incidents:** related alerts grouped into one story with a timeline, which updates and closes itself on recovery | Makes crisis handling visible (brief §10: detect → respond → recover) |

### Put in monitoring (Grafana), not the operator screen
- The rate of refused shipments by reason (our own planning mistakes, which should be close to 0).
- Forecast drift, copy-vs-real drift, live stream health, and simulator response time and error rate.

### Stretch
- Operators ignoring recommendations (they keep expiring).
- Wrong demand profile.
- Region-wide inference beyond the simple "2+ stations in one region".

### Drop
- The rush-hour pile-up warning: the projection already shows it.
- Operator disagreement analysis.

---

## 4. DECIDE

### Build
| # | What | Why it's kept |
|---|---|---|
| X1 | **Rolling planner:** plan 6 h ahead, send only what's needed now, replan every tick. An optimizer is the main method, with the **reorder-point rule as the backup** and benchmark | Standard, proven approach. The backup covers resilience (brief §11: model unavailable → fallback) |
| X2 | **Updated planner goal for a finite world:** (1) least unserved demand, (2) **zero waste** (depot and tank overflow count as heavy penalties), (3) balanced hours of fuel left across stations, (4) short roads as a tie-breaker | Matches §0: after day 2, waste and distribution decide the score |
| X3 | **Every rule respected**, including **fuel already on the way** when checking tank space, and the depot's sending limit per tick shared across all fuels. Big amounts split into several trucks | Nothing wasted and nothing refused |
| X4 | **Act before scheduled crises:** fill up before a spike or road cut, especially **single-route stations before their road closes** | The heart of "anticipate, don't react" |
| X5 | **Empty depots before ships arrive:** time shipments so each arriving ship has room, **using cross-region roads to spread fuel around**, not just as a backup | Recovers the 73,000 L of waste |
| X6 | **Rationing mode:** switches on automatically when P5 says fuel won't last. The default goal is **"no station stays dry much longer than the others"**, and the operator can switch to "maximize total". Clearly shown on screen | This is the main mode after day 2. The brief asks for constrained allocation |
| X7 | **Self-correcting shipments:** cancel waiting trucks whose road will be cut, then reroute; replace failed trucks; queue a refill for the tick an outage ends; fix refusals automatically (split, send next tick, send less) | Resilience and crisis recovery |
| X8 | **"Wait" as a real recommendation:** "don't send yet: no room, or a ship arrives in 3 ticks" | The brief's §9 asks for alternative actions. It shows judgment |
| X9 | **Human approval rules:** auto-send only routine, high-confidence, normal-road shipments. Crisis, rationing, backup-road or low-confidence shipments wait for the operator. Recommendations expire. Auto mode switch + stop button | Brief §24: keep human review for important decisions |
| X10 | **Explanation facts on every recommendation:** why, limits that shaped it, the with/without impact (from P6), alternatives, confidence, which method | Brief §9. Also the input for the AI explanations |

### Stretch
- **What-if tool:** cheap once the copy of the simulator exists, and good for the demo.
- Operator-set priorities per station and fuel.
- Settings history with rollback.

### Drop
- Reinforcement learning: it needs lots of training, is hard to explain, and the planner is already close to the best possible.
- Learning from operator edits.
- The transport effort score.
- Planning for the worst case: the bigger buffer at single-route stations (D5) covers the main need.

---

## 5. GENERATIVE AI (explains, never decides)

### Build
- **Recommendation explanations** from the X10 facts, 2–3 sentences, using only the numbers given. A template sentence is the fallback.
- **Incident summaries** for D7 incidents: what happened, the impact, what we did, the current status.
- **Shift handover report** every N ticks: what changed, what's at risk, what's waiting for approval. Cheap, and it shows the AI doing real operational work.

### Stretch
- Post-incident review built from alerts, decisions and the audit log.
- What-if questions in plain language: the AI turns the question into a scenario, and our copy of the simulator computes the numbers.

### Not the AI's job
Refusal explanations ("Mirpur's tank has room for only 1,200 L"): a template does this better and never fails.

---

## 6. PROVING IT WORKS

### Build
- **Test bench:** 8 fixed scenarios × three methods (do nothing / backup rule / planner), each run for **at least 5 simulated days**
  so the rationing phase is included. Measures:
  - service level
  - liters unserved
  - **liters wasted**
  - hours any station was empty
  - refused and failed trucks
  - alert delay
- **Live "our plan vs doing nothing"** on the dashboard (from P6).

### Stretch
- Random crisis generator (numbered seeds, repeatable).
- Speed test.
- Replay slider.

---

## 7. What the operator sees (from the kept items)

| Screen | Shows | Comes from |
|---|---|---|
| Station cards | Fuel bars, risk color, time until empty (ours vs naive), order-by time, single-route badge | P2, P3, D5 |
| Depot cards | Fuel, **space left vs incoming ships**, overflow warning, wasted liters so far | P4, D4 |
| Network strip | Service level, **our plan vs doing nothing**, days of fuel left per fuel, mode (normal / crisis / rationing) | P5, P6, X6 |
| Incidents | Grouped alerts with timeline, crisis countdown, AI summary | D1, D2, D7, AI |
| Recommendations | Shipment or "wait", why, risk before → after, alternatives, confidence, approve / edit / reject, expiry timer, 6 h plan | X1–X10, P6 |
| Shipments | Trucks with arrival countdown, failed trucks and their replacements, cancel button | X7, D6 |
| Health bar | Simulator ok / slow / down, data age, degraded-mode banner | D3 |
| Decision log + handover | History, outcomes, the AI handover report | X9, AI |

---

## 8. Build order

1. Collect and save each tick + data checks (D3)
2. P1 (published pattern) → P2 → backup rule → auto-send → **first working version**, which should beat doing nothing
3. Copy of the simulator + P6 ("vs doing nothing") + test bench, so everything after this is measured
4. P4, P5, X5, X6: waste and rationing. **This is where the biggest score gains are.**
5. D1, D2, D4, D5, D7 detection and incidents; P7, X4 anticipation
6. The optimizer (X1–X3), which must beat the backup rule on the bench; then X7, X8
7. X9 approvals, X10 + AI explanations, handover report
8. Stretch goals if time allows: what-if tool first
