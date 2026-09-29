# Solution Design: Predict, Detect, Decide

This covers how our system thinks: what it predicts, what it watches for, and how it chooses
shipments. It lists design decisions only, no code. For the simulator facts behind
these choices, see `project-context.md`.

---

## 1. What kind of problem this is

In the research, this is a known problem called **inventory routing**: a supplier watches
its customers' tank levels and decides when, where and how much to deliver. It's been studied a
lot for **fuel delivery to petrol stations**. The standard recipe has three parts:

1. **Forecast demand**, so you know how fast each tank empties.
2. **Reorder point + safety stock**: send fuel when the tank will drop below "what's used while the truck travels + a buffer".
3. **Rolling horizon**: every period, plan a few hours ahead, carry out only the first step, then plan again with fresh data.

Our case is small (2 depots, 4 stations, 6 roads, 3 fuels) and the roads and truck times
are fixed. That means we can do the "ideal" version properly instead of settling for rough shortcuts.

## 2. Guiding principles

- **Simple, explainable methods first.** Every number has to be explainable to an operator. A method we can't explain doesn't go in.
- **Always have a backup.** Every smart component has a simple fallback that always works.
- **Use what we know.** The simulator's demand rules are published. We start from them and let data correct us, instead of learning from scratch.
- **Measure, don't guess.** The simulator gives the same result for the same inputs, so we can replay the same scenario and compare methods fairly (§7).
- **Plan ahead, commit a little.** Plan the next few hours, send only what's needed now, and replan every tick.

---

## 3. PREDICT: what we forecast

### 3.1 Demand, per station, per fuel, for each of the next 24 ticks (6 hours)

**Why 6 hours:** the slowest road takes 4 ticks, and a big delivery may need several ticks
to send because of the depot's sending limit. 6 hours covers this with room to spare.

**Decision: a "known pattern + correction" forecast.**
- **Start from the published pattern:** daily volume ÷ 96 × time-of-day factor × region factor. This works from tick 0, before we have any history.
- **Correct it with real data:** for each station, fuel and hour of day, compare the pattern to actual demand and keep a running correction factor. If our pattern is slightly off, the data fixes it.
- **Apply the current demand multiplier** (the spike setting), and keep it until the spike's known `end_tick`.
- **Clean the history first:** history rows don't record which multiplier was active, so we save the multiplier on every tick. Demand from a spike period gets divided back down, so one crisis doesn't distort "normal".

**Backups, simplest last:** same hour yesterday → average of the last 8 ticks → the published pattern alone.

**Chosen over:** Holt-Winters, ARIMA and machine-learning models. They're all fine for daily and
hourly patterns, but they have to discover a pattern that is already published, they need
days of history before they're reliable, and they're harder to explain. We **test them as
challengers** (§7) and only switch if they're clearly better.

### 3.2 How sure we are (uncertainty)
- Track the forecast's recent errors per station and fuel. The size of those errors gives us a **range**, for example "Tongi diesel: 220 L per tick, likely between 190 and 250".
- The published noise is about 8–12%, so a well-calibrated range should be about that wide. If our errors get much bigger, something unusual is happening, which feeds into detection.

### 3.3 Station tank projection (the most important prediction)
Starting from each tank's current level, step forward tick by tick:
**next level = current level − forecast demand + trucks arriving that tick.**

This gives us:
- **Time until empty**, for example "runs out at 16:15, in 5 hours".
- **Liters we'd fail to serve** in the next 6 hours if we do nothing.
- **Chance of running out before help can arrive**, calculated from the uncertainty range. This is where "risk 72%" comes from.

### 3.4 Depot projection
The same idea for depots: **fuel in + scheduled supply ships (adjusted for delays and shortfalls) − planned shipments out.** This tells us:
- how long each depot can keep supplying (its runway),
- whether fuel will run short, so we have to ration (§5.5),
- whether a depot will **overflow** when a supply ship arrives. We observed depots full at capacity, and any extra supply is probably wasted, so we move fuel out ahead of time.

### 3.5 Confidence score
Each prediction gets a confidence level, based on:
- recent forecast error,
- data freshness (stale data or missing ticks),
- whether a crisis is active.

Low confidence means **ask a human** (§5.6).

**Not predicted:** truck delays. In this simulator, trucks always take the road's exact travel
time. Delays only come from announced crises, which we **read** instead of predicting.

---

## 4. DETECT: what we watch for

Detection works on two levels: **what the simulator tells us directly**, and **what we notice ourselves**.

### 4.1 Announced changes (compare every tick with the previous one)
| Signal | Means |
|---|---|
| A new crisis in `/events` (including upcoming ones) | A crisis is coming or has started. Plan ahead |
| A road's status changes to `DISRUPTED` | Reroute, and check trucks waiting to use that road |
| A station's status changes to `OUTAGE` | Stop sending to it. Its demand is lost for now |
| A depot's status changes to `CONSTRAINED` | Warning. Prefer the other depot |
| A supply ship's tick moves later / its amount shrinks | The depot will be short later. Re-check its runway |
| A station's demand multiplier changes | Demand spike. Update forecasts immediately |

### 4.2 Things we notice ourselves
- **Unusual demand:** actual demand is far above the forecast. We use **two checks together**:
  - **A single-tick check:** one reading far outside the expected range. Catches sudden jumps fast.
  - **A running-total check (CUSUM):** small overshoots that keep adding up. Catches slow, steady increases that a single-tick check misses.

  An alert is raised only if it lasts 2 or more ticks, so normal noise doesn't trigger it.
  Actual ÷ forecast also **estimates the size of the spike**, even without an announcement.
- **Unexpected fuel changes:** a tank's level doesn't match "previous − sold + delivered". That points to missing deliveries or bad data.
- **Bottlenecks:**
  - a depot keeps hitting its sending limit,
  - the same shipment keeps getting refused,
  - trucks fail.
- **Regional trouble:** several stations in the same region at risk at once. Report it as a region problem, not four separate alerts.
- **Bad data:** stale flag, readings that don't make sense (negative fuel, more than the tank holds), the tick stuck or going backwards (a reset).

  Decision: **don't act on bad data**. Alert, and hold decisions.

### 4.3 Alert handling
- Every alert has a severity (info / warning / critical), a cause, and the stations affected.
- Alert states: open → acknowledged → resolved.
- The same problem produces **one alert that updates**, not a new alert every tick.
- Alerts clear automatically when the condition ends. Recovery is logged, which shows "the system recovered".

---

## 5. DECIDE: how we choose shipments

### 5.1 Decision: rolling-horizon planner with a simple rule-based fallback
Every tick:
1. Plan shipments for the next 6 hours using the predictions.
2. **Send only the shipments that must leave now.** Later ones are just a plan.
3. Next tick, plan again with fresh data.

This is the standard approach in the inventory-routing research. It adapts to surprises
automatically, because the plan is never older than 15 minutes.

### 5.2 The planner (main method): a small optimization
The problem is tiny (6 roads × 3 fuels × 24 ticks), so a standard optimization solver can find
the **best plan in well under a second**.

**Goal, in order of importance:**
1. **Unmet demand** as small as possible. This is the score.
2. **No tank below its safety buffer** (a smaller penalty).
3. **Fair shortage**: when fuel is scarce, spread the shortfall across stations instead of letting one run completely dry (§5.5).
4. **Prefer short roads, fewer trucks, and no depot overflow** (tie-breakers).

**Must respect every simulator rule**, so shipments aren't refused:
- the road is open (including cuts announced for later),
- amount ≤ the road's limit,
- the depot has the fuel,
- the depot's total sent per tick ≤ its sending limit,
- **the station has room right now.** The simulator checks tank space when the order is placed, not when the truck arrives, so we can't send a big load too early. We also count fuel already on the way.

### 5.3 The backup: order-point rule (always available)
The standard textbook replenishment rule:
- **Reorder point** = demand during truck travel time + safety buffer
- **Safety buffer** = service factor × uncertainty over the travel time (about 95% protection)

For every station and fuel, **most urgent first**:
1. If the projected level at arrival time < reorder point, fill up as far as the tank allows.
2. Use the fastest open road from a depot that has fuel.
3. Stay within the depot's sending limit. Leftover need rolls over to the next tick.

**Used when:**
- the optimizer fails or is too slow,
- predictions have low confidence,
- as the **benchmark** the optimizer must beat (§7).

It's also easy to explain, which is useful on its own.

### 5.4 Planning ahead for known crises
- **Road cut coming:** send extra fuel over that road *before* the cut, and use the backup road during it.
- **Demand spike active:** forecast the higher demand until `end_tick`. Top up affected stations sooner.
- **Supply ship delayed or smaller:** the depot runway shrinks, so switch to rationing sooner. The other depot may serve the region over the backup road.
- **Station outage:** don't send to it (it's refused anyway). Plan to refill it right after it reopens.
- **Depot constrained:** prefer the other depot where possible.

### 5.5 When there isn't enough fuel (rationing)
When the depots can't cover everyone:
- **Rule:** minimize total unmet demand, but **no station falls far behind the others**. Balance the "hours of fuel left" across stations.
- The research on fair allocation under shortage uses the same idea: minimize the worst station's shortfall.
- This is a **policy choice the operator can see** (and possibly switch), for example "fair" versus "maximize total served".

### 5.6 When a human must approve
Recommendations are **sent automatically** only when all of these hold:
- confidence is high,
- the road is normal,
- no crisis affects this station or depot,
- the amount is routine,
- the planner and the backup rule broadly agree.

Everything else **waits for the operator**:
- a crisis is active,
- it uses a backup road,
- it uses scarce fuel (rationing),
- confidence is low,
- it's a large amount,
- the two methods disagree strongly.

Auto mode can be switched off entirely. Approved, edited and rejected recommendations all go into the decision log.

### 5.7 Every recommendation explains itself
Each recommendation carries:
- **Why:** the forecast, current level, time until empty, risk.
- **Limits that shaped it:** for example "limited to 4,000 L because Tongi's tank has only that much room".
- **Expected result:** projected risk and unmet liters **with versus without** this shipment. We get this by running the tank projection twice.
- **Alternatives:** the next-best depot or road, and why it lost (slower, depot low, road cut).
- **Confidence**, and which method produced it (planner or backup rule).

The AI model turns this into a short, readable paragraph. It explains; it never decides. If the AI is down, a template sentence is used instead.

---

## 6. How the three layers connect, every tick

```
fresh data → check data quality ──bad──► alert, hold decisions, use saved state
                  │ good
                  ▼
PREDICT   demand forecast (+range) → tank projections → depot projections → confidence
                  ▼
DETECT    announced changes + unusual demand + bottlenecks + regional trouble → alerts
                  ▼            (detection also adjusts predictions, e.g. spike size)
DECIDE    planner (backup: order-point rule) → shipments to send now
                  ▼
          safe & routine? ──yes──► send automatically
                  │ no
                  ▼
          operator approves / edits / rejects → send → track → log outcome
```

---

## 7. Finding the best and most robust approach: a test bench

The simulator gives the same result for the same inputs, so we build a **scenario test bench**
that replays the same situation against different methods and scores them.

**Scenarios** (each is a script of crises at set ticks, run for 2–3 simulated days):
1. Normal operations
2. Demand spike in one region
3. Main road cut
4. Supply ship delayed + smaller
5. Station outage
6. Depot constrained
7. Combined crisis (spike + road cut + supply shortfall)
8. Software faults during operation (outage, errors, stale data)

**Methods compared:**
- do nothing (the baseline: 0.88 service level after one day)
- backup rule only
- planner
- planner with different forecast models

**Scores:**
- service level
- total unmet liters
- ticks any station was empty
- refused or failed shipments
- depot overflow
- forecast error
- how quickly alerts fired after each crisis started

**How we choose:** the method that is **best in the worst scenario** without losing in the normal
one. Robustness beats a small win on average. Tuning settings (safety buffer size, planning window,
alert thresholds) are chosen the same way.

This test bench also gives us demo evidence: "our system vs. doing nothing, across 8 scenarios."

---

## 8. Deliberately not doing

- **Reinforcement learning (optional in the brief).** The world is small and its rules are known, so a planner with forecasts is already close to the best possible. Reinforcement learning would need lots of training runs, be harder to explain, and bring little benefit. It's a stretch goal only, compared against the planner on the test bench.
- **Deep-learning forecasts.** There's too little data and too little to gain given the published pattern.
- **Truck delay prediction.** Truck times are fixed. Delays are announced, so we read them.
- **An AI chatbot as the "intelligence".** The brief says a chatbot isn't enough. AI is used for explanations and summaries only.

---

## 9. Simulator rules checked by testing

1. **Truck arrives and the tank would overflow → the extra fuel is lost.** The truck still shows
   `ARRIVED` and the depot was charged the full amount (a 4,000 L truck delivered only 75 L). The simulator's
   order check ignores trucks already on the way, so it happily accepts orders that will overflow.
   **We must count fuel already on the way ourselves.**
2. **Several trucks on the same road in the same tick: allowed.** So a big delivery can be split into
   several trucks of up to the road's limit, all sent in one tick.
3. **Supply arriving at a full depot: the extra is lost** (a 12,000 L ship added only 7,000 L). Move fuel out before ships arrive.
4. **Depot constrained: only the label changes.** It's just a warning.
5. **Unmet demand: appears lost** (demand after a stockout stayed at normal levels, with no catch-up).
6. **The depot sending limit resets every tick.** It counts only orders placed this tick; trucks
   already on the road don't count. A truck ordered at tick T leaves at T and arrives at T + travel time.

---

## Sources

- Inventory routing for fuel delivery, rolling horizon: [Carotenuto et al., 2017](https://art.torvergata.it/bitstream/2108/194665/2/CarotenutoEtAl%282017%29.pdf), [Wernekinck, EUR thesis](https://thesis.eur.nl/pub/30376/Wernekinck.pdf), [Jaillet et al., rolling-horizon delivery costs (MIT)](https://www.mit.edu/~jaillet/general/rolling.pdf), [Delivery Cost Approximations for IRP in a Rolling Horizon (INFORMS)](https://pubsonline.informs.org/doi/fpi/10.1287/trsc.36.3.292.7829), [Matheuristic for the multivehicle IRP (ESSEC)](https://faculty.essec.edu/research/a-matheuristic-for-the-multivehicle-inventory-routing-problem)
- Reorder point, safety stock and (s,S) policy: [MetricGate: (s,S) policy](https://metricgate.com/docs/inventory-ss-policy-optimal/), [MetricGate: reorder point with safety stock](https://metricgate.com/docs/inventory-rop-safety-stock/), [Cleverence: reorder point with safety stock](https://www.cleverence.com/articles/for-business/calculating-reorder-point-with-safety-stock-6283/)
- Short-term forecasting with daily patterns (Holt-Winters vs simple benchmarks): [Taylor, minute-by-minute load forecasting (Oxford)](https://users.ox.ac.uk/~mast0315/MinByMinLoad.pdf), [Hourly short-term load forecasting (arXiv)](https://arxiv.org/pdf/2501.19234)
- Anomaly detection with forecast errors (z-score and CUSUM): [CUSUM for control of demand forecasts (INFORMS)](https://pubsonline.informs.org/doi/fpi/10.1287/opre.12.2.325), [Change-point detection of supply chain disruptions (arXiv)](https://arxiv.org/pdf/2211.12091), [Forecasting-based anomaly detection benchmark (arXiv)](https://arxiv.org/pdf/2510.11141)
- Fair allocation under shortage (minimize the worst unmet-demand ratio): [Fair resource allocation, COVID-19 plasma case (arXiv)](https://arxiv.org/pdf/2106.14667)
