# How Each Part Works (step by step)

This expands [solution.md](solution.md). For every part, it says in plain steps what the system
does, with a worked example using real simulator numbers. It's not a coding guide.

---

## Before anything: every tick, collect and save

1. Notice that the tick changed.
2. Read everything from the simulator: tanks, depots, roads, supply ships, crises, trucks, new demand rows, score.
3. Check the data makes sense (see Detect, section 5). If it doesn't, stop here and raise an alert.
4. Save it all, together with **each station's demand multiplier at this tick**. The simulator doesn't
   record which multiplier was active, and we need it later to clean the history.
5. Run Predict → Detect → Decide.

---

# PREDICT

## 1. Demand forecast

**Goal:** for each station and fuel, how many liters customers will want in each of the next 24 ticks.

**Steps:**
1. **Start from the published pattern.** Daily liters ÷ 96, times the busy/quiet factor for that hour,
   times the region factor.
   *Example: Tongi diesel at 10:00 = 14,000 ÷ 96 × 1.55 (busy) × 1.00 (Dhaka) ≈ **226 L per tick**.*
2. **Clean the history.** Divide each past demand reading by the multiplier active at that tick, so spike
   periods look like normal days.
   *Example: 156 L during a ×2 spike counts as 78 L of "normal" demand.*
3. **Blend the pattern with real data.** For each station, fuel and hour of day, average the cleaned
   readings we've seen. With little data, trust the published pattern. As readings pile up, trust
   the data more.
   *Example: after 1 reading, it's 80% pattern and 20% data. After 20 readings, it's 20% pattern and 80% data.*
4. **Apply the current multiplier** for as long as the spike lasts. We know when it ends from the crisis's `end_tick`.
   *Example: Mirpur petrol at night is normally 76 L. During a ×2 spike ending at tick 116, forecast 152 L until tick 116, then 76 L again.*
5. **If something breaks,** use simpler forecasts in this order: same time yesterday → average of the last 8 ticks → published pattern alone.

**Check it works:** each tick, compare last tick's forecast with what really happened, and track the average error.
It should be around 10%, which is the simulator's built-in noise. We can't do better than that, and much
worse means something is wrong.

## 2. How sure we are (the range)

**Steps:**
1. Keep a running average of how wrong the forecast was, in percent, for each station and fuel.
2. Use it to put a range around each forecast.
   *Example: forecast 226 L, typical error 8% → "likely 208–244 L".*
3. For several ticks together, the ranges partly cancel out (some ticks are high, some low), so the
   range over 4 ticks is about **twice** one tick's range, not four times.

This range is what the safety buffer (section 7) and the risk percentage (section 3) are built on.

## 3. Tank projection: when will each tank run dry?

**Steps:**
1. Start with the tank's current level.
2. For each of the next 24 ticks: **subtract** forecast demand, **add** any of our trucks arriving that tick.
3. Stop the level at 0 (it can't go negative). Whatever demand is left over is liters we fail to serve.

**Results:**
- **Time until empty:** the first tick the tank hits 0.
- **Liters unserved:** the total shortfall over 6 hours.
- **Risk %:** the chance the tank runs dry before a truck could arrive. We compare fuel on hand against
  demand until the fastest truck arrives, including the range from section 2.

*Example: Tongi diesel at 12:00 has 3,997 L and uses about 230 L per tick → empty in about 17 ticks (16:15).
The fastest truck takes 2 ticks, so it's not urgent yet. At 15:00 there are about 1,200 L left, 5 ticks
of fuel. Risk is now low but climbing, so it's time to plan.*

## 4. Depot projection

**Steps:**
1. Start with the depot's current fuel.
2. For each future tick: **add** scheduled supply ships (using the updated tick and amount if a crisis
   delayed or shrank them), and **subtract** shipments we plan to send.
3. Cap at the depot's tank size. Anything above that is **wasted supply**, which the tests confirmed.

**Results:**
- **Runway:** how long the depot can keep supplying.
- **Overflow warning:** the depot will be full when a ship arrives.
- **Rationing flag:** the depots together can't cover forecast demand.

*Example: Gazipur diesel is at 83,000 L out of 90,000 L, and a 12,000 L ship is due in 2 ticks → 5,000 L
would be wasted. Send at least 5,000 L out before then.*

## 5. Confidence score (0 to 1)

Start at 1.0 and reduce it:
- If the recent forecast error is large (for example, 25% instead of the normal 10%), reduce it a lot.
- If the data is stale or ticks were missed, reduce it.
- If a crisis is active at this station or depot, reduce it a little.

It's used for one thing: **deciding whether a human must approve** (section 13).

## Additional ideas: Predict

- **Latest safe order time.** For each station and fuel, the last tick you can still send a truck and avoid
  running dry (empty time − truck travel time − a small margin). Operators understand it instantly:
  *"Tongi diesel: order by 15:30."*
- **Refill window.** The earliest tick a full truckload fits in the tank, plus the latest safe order time,
  make a window. Sending inside the window means no overflow and no stockout.
- **Next busy period warning.** Predict when each station's next rush starts and how much fuel it will use.
  *"Mirpur morning rush in 2 hours uses 1,400 L of petrol. You have 900 L."* Refill just before rushes.
- **Region and depot demand.** Add up station forecasts per region and fuel. It shows whether each depot's
  supply ships cover its region until the next ship arrives (ships come every 64 ticks).
- **Crisis impact preview.** When a crisis is scheduled for later, run the projection with it included and
  report the damage ahead of time. *"The Dhaka spike starting at tick 100 will cause 3,000 L unserved unless we pre-fill."*
- **Spike length guess.** If demand jumps without an announced crisis, assume it lasts a typical time
  (learned from past spikes) and update each tick.
- **Wasted supply forecast.** Predict how many liters each incoming ship will waste at a full depot, so the planner moves fuel out first.
- **Truck failure risk.** Flag trucks waiting to leave on a road that is about to be cut.
- **"Doing nothing" shadow score.** Keep a running estimate of what the service level would be **without
  our system** and show "liters saved by our system" live. This is strong demo evidence.
- **Score forecast.** Predict the service level for the next 24 hours under the current plan.
- **Best forecast per station.** Run 2–3 forecast methods side by side and automatically use whichever has
  been most accurate recently for that station and fuel.
- **Learn from past crises.** Record how demand behaved in each crisis type, so the next one is recognized and forecast faster.
- **Weekly pattern check.** After a week of simulated data, check whether weekdays differ. Add it to the forecast if they do.

---

# DETECT

## 6. What we check every tick

### a) Compare this tick with the last one
Look for any change in:
- road status,
- station status,
- depot status,
- a station's multiplier,
- a supply ship's tick or amount,
- a new crisis (including crises scheduled for later).

Each change becomes an alert with a clear cause.
*Example: "Road Gazipur→Mirpur cut from tick 100 to tick 116. 1 truck waiting may fail."*

### b) Unusual demand (two checks together)
1. **Single-tick check:** how far this reading is from the forecast, measured in units of the normal
   range. More than 3 units away means **suspicious**.
2. **Running-total check:** add up small overshoots tick after tick, and let the total shrink a little
   each tick. If the total passes a threshold, demand has **shifted**. This catches slow, steady
   increases that the single-tick check misses.
3. **Raise an alert only if it lasts 2 or more ticks,** so one noisy reading doesn't trigger it.
4. **Estimate how big it is:** average (actual ÷ forecast) over the last few ticks.

*Example: Mirpur petrol forecast 76 L, actual 156 L, normal range ±8 L → 10 units away. Next tick
it's the same → alert "Mirpur petrol demand about ×2", and the forecast uses ×2 from now on.*

### c) Tank levels that don't add up
Expected level = last level − liters sold + liters our trucks delivered. If the real level is noticeably
different, something is wrong: bad data, an overflow loss, or a problem we don't know about. Raise an alert.

### d) Bottlenecks
- A depot uses 90% or more of its sending limit for several ticks in a row.
- The planner wanted to send more but was blocked by a limit.
- The same shipment keeps being refused, or trucks keep failing.

### e) Regional trouble
If 2 or more stations in the same region are in trouble at once, raise **one** region alert instead of several.

### f) Bad data (stop and hold)
- the stale flag is on,
- fuel is negative or more than the tank holds,
- the tick didn't move or went backwards (backwards means a reset, so start fresh),
- fields are missing or have odd values.

→ Alert, and **don't make decisions** until the data is good again. Keep showing the last good data, marked "stale".

## 7. Alert handling

1. Give every alert a name built from its type and target (for example "unusual demand – Mirpur – petrol").
2. The same problem next tick **updates** the existing alert instead of creating a new one.
3. Severity levels:
   - **info:** a crisis is scheduled for later.
   - **warning:** a risk is building.
   - **critical:** a station is running dry soon, or the data is bad.
4. The operator can acknowledge an alert.
5. When the problem has been gone for a few ticks, the alert **closes itself** and the recovery is logged.

## Additional ideas: Detect

- **Incidents that group alerts.** Link related alerts into one story with a timeline.
  *"Dhaka spike → Mirpur risk → rationing on → spike ended → recovered."* The operator sees one incident, not five alerts.
- **Crisis countdown.** For scheduled crises, show "road cut starts in 3 ticks" so there's time to act.
- **Forecast drifting.** If the forecast is wrong in the same direction for many ticks, it's biased. Recalibrate it automatically and log that it happened.
- **Missed ticks.** If the simulator runs faster than we process, we skip ticks. Detect the gap and fill it from the demand history.
- **Clock watch.** Detect the simulator being paused or resumed, or its speed changing (measure ticks per real second).
- **Live stream health.** The simulator says "running" but no tick message has arrived for a while → the stream is dead, so switch to polling.
- **Early signs of trouble.** Rising response times or error rates from the simulator → go into degraded mode *before* it fails completely.
- **Our own mistakes.** The simulator's audit log shows when a truck delivered less than it carried (overflow) or a
  ship added less than planned (full depot). Flag these as our errors and learn from them.
- **Unbalanced depots.** One depot is overflowing while the other region runs short → suggest using the long backup road across regions.
- **Rush-hour pile-up.** Several stations entering a busy period with low fuel at the same time → an early warning, before each becomes urgent.
- **Score dropping.** The service level trend turns downward → open an incident, even if no single alert fired.
- **Silent supply problems.** A ship didn't arrive at its planned tick but isn't marked delayed → alert.
- **Operator disagreement.** The operator keeps rejecting or editing the same kind of recommendation → the planner's settings may be off. Flag it for review.

---

# DECIDE

## 8. Rolling planning (the loop)

Every tick:
1. Plan all shipments for the next 6 hours.
2. **Send only the ones that must leave this tick.**
3. Throw the rest of the plan away. Next tick, plan again from fresh data.

This way surprises are handled automatically, because the plan is never older than 15 minutes.

## 9. The main planner (optimizer)

**What it does:** it tries every possible mix of "how much of which fuel on which road at which tick"
and picks the mix with the best score. A free optimization tool does the searching, and the problem
is small enough to solve in under a second.

**What it tries to achieve, in order:**
1. **Least unserved demand.** This is the simulator's score.
2. **Keep tanks above their safety buffer.** Being below the buffer is allowed, but costs points.
3. **Share shortages fairly** when fuel is scarce (section 12).
4. **Tie-breakers:**
   - prefer short roads and fewer trucks,
   - avoid depot overflow (wasted supply),
   - avoid leaving tanks empty at the end of the 6-hour window.

**Rules it must follow** (so the simulator never refuses a shipment):
- only open roads, including cuts announced for later,
- no shipping to closed stations,
- the depot has the fuel,
- a depot's total per tick is within its sending limit,
- **fuel on hand + fuel already on the way + new fuel fits in the tank.** The tests showed the
  simulator doesn't check this and just loses the overflow, so we check it ourselves.

**After it answers:**
1. Round amounts down to a tidy number (for example, the nearest 50 L).
2. Drop tiny shipments (for example, under 500 L) unless a tank is about to run dry.
3. Split big amounts into several trucks of up to the road's limit. Several trucks per road per tick are allowed.

*Example: Mirpur and Tongi both need diesel from Gazipur this tick, but Gazipur can only send 12,000 L. The
planner sends 7,000 L to Tongi (empty in 3 ticks) and 5,000 L to Mirpur (empty in 9 ticks). Mirpur's
remaining need goes out next tick.*

## 10. The backup rule (always works)

**Steps, for every station and fuel, most urgent first:**
1. **Reorder point** = demand expected while a truck travels + safety buffer.
   - **Safety buffer** = about 1.65 × the range over the travel time. That gives about 95% protection.
2. Look at the tank's projected level **when a truck sent now would arrive**. If it's below the reorder point, send fuel.
3. **Amount** = tank size − (projected level at arrival + fuel already on the way).
4. **Road** = the fastest open road from a depot that has the fuel.
5. Cap the amount by what the depot has and what's left of its sending limit this tick.
   Whatever can't be sent rolls over to the next tick.

*Example: Tongi diesel, busy hours at 230 L per tick, truck takes 2 ticks, range ±8%.
Demand during travel = 460 L. Buffer ≈ 1.65 × 26 ≈ 45 L, rounded up to about 100 L to be safe.
Reorder point ≈ 560 L. When the projected level 2 ticks from now drops below 560 L, send enough to fill
the tank. In practice you'd use a **bigger buffer** (for example, 2–3 hours of demand), because the
depot limit and other stations can delay a shipment. The test bench (section 15) picks the best buffer.*

**Used when:**
- the optimizer fails or takes more than about 2 seconds,
- confidence is low,
- as the benchmark to beat.

## 11. Handling known crises in advance

| Crisis | What the planner does |
|---|---|
| Road cut scheduled for later | Before the cut, fill that station more. During the cut, the road is off-limits, so use the backup road |
| Demand spike active | Forecast the higher demand until it ends, so refills naturally come sooner and are bigger |
| Supply ship delayed or smaller | The depot projection shrinks, so rationing may start. The other depot can help through the backup road |
| Station outage | Don't send (it's refused). Plan a refill for the moment it reopens |
| Depot constrained | Add a small extra "cost" to that depot, so the other one is preferred when both work |

## 12. When there isn't enough fuel (rationing)

1. Detect it: the depot projection says total fuel < total forecast demand for the coming hours.
2. Switch the planner's goal to include **fairness**: keep the worst-off station's shortage as small as possible,
   not only the total.
   *Example: 10,000 L available for two stations that each need 8,000 L. Maximizing the total might give
   8,000 + 2,000. "Fair" gives about 5,000 + 5,000, so both stations stay open part of the time.*
3. Show the operator that rationing is on, and let them switch between "fair" and "maximize total".
4. Rationing shipments **always need approval**.

## 13. Who approves what

**Sent automatically only if all of these are true:**
- confidence is high (for example ≥ 0.8),
- it uses a normal (main) road,
- no active crisis touches this station or depot,
- the amount is routine (for example, within one truckload),
- the optimizer and backup rule roughly agree,
- the operator has auto mode switched on.

**Otherwise the operator decides:**
- **approve:** it's sent.
- **edit:** change the amount or road. The system re-checks the rules, then sends it.
- **reject:** it's logged with a reason.

**Pending recommendations expire after a few ticks** and are replaced by fresh ones, so nobody approves an outdated plan.

## 14. Explaining each recommendation

For every recommendation, collect these facts:
1. **Why:** current level, forecast use, time until empty, risk %.
2. **Limits that shaped it:** for example "capped at 4,000 L: tank space" or "capped by Gazipur's sending limit".
3. **Expected result:** run the tank projection **twice**, with and without the shipment.
   *Example: "risk 72% → 19%, unserved liters 1,800 → 0".*
4. **Alternatives:** try other depot and road options, and say why each one lost.
   *Example: "Patiya→Mirpur: arrives 2 ticks later, risk only drops to 40%".*
5. **Confidence**, and which method produced it (optimizer or backup rule).

Then:
- Give these facts to the AI model and ask for a 2–3 sentence explanation **using only these numbers**.
- If the AI is slow or down, fill in a ready-made sentence template instead.
- The AI **never** changes the decision.

## Additional ideas: Decide

- **Send inside the refill window.** Don't send too early (overflow, and it ties up fuel) or too late. Aim for the
  middle of each station's window.
- **Cancel trucks when plans change.** If a road cut or station outage is announced while a truck is still
  waiting to leave, cancel it (the depot gets its fuel back) and replan.
- **Replace failed trucks right away.** A failed truck goes back into the next tick's plan at top priority.
- **Fix refusals automatically.** Each refusal reason has a fix:
  - too big for the road → split it,
  - depot limit hit → send next tick,
  - tank too full → send less,
  - road cut → use the other road.
- **Fill up before rushes and before road cuts.** Pre-fill stations ahead of busy hours and before known cuts, so they ride through without a truck.
- **Use the overflowing depot.** When one depot would waste supply, send its fuel to the other region over the long backup road, even if it's slower.
- **Priority settings.** Let the operator set priorities, for example "diesel at industrial and highway stations first".
  The brief mentions priority-based allocation explicitly.
- **Operating modes.** Normal / crisis / save-fuel. The system switches mode automatically (and shows why),
  and each mode changes the buffer size, the approval rules and the fairness setting.
- **Plan for the bad case at critical stations.** For stations where running dry hurts most, plan against the high end of the forecast range, not the average.
- **"What if" tool.** The operator tries a shipment or an imaginary crisis ("what if the Gazipur→Tongi road is cut now?")
  and sees the projected result before acting. The brief lists this as advanced work (counterfactual simulation).
- **Upcoming plan timeline.** Show all shipments planned for the next 6 hours, not just the ones for right now, so the operator sees what's coming.
- **Stop button.** The operator can pause all automatic sending instantly.
- **Settings history and rollback.** Save each version of the planner's settings. If the service level drops
  after a change, switch back with one click (the brief mentions policy rollback).
- **Learn from operator edits.** If operators keep raising amounts for a station, raise its default buffer.
- **Transport effort score.** Track liters × travel time as a simple cost measure, and prefer plans that serve the same demand with less transport.

---

# PROVING IT WORKS

## 15. Test bench

**Steps:**
1. **Write scenarios.** Each is a list of crises at set ticks.
   *Example: "Dhaka demand ×2 at ticks 100–116, plus Gazipur→Mirpur cut at ticks 104–120."*
   Make 8:
   - normal
   - spike
   - road cut
   - late + small supply
   - station outage
   - depot constrained
   - combined
   - software faults
2. **For each scenario and each method** (do nothing, backup rule, optimizer):
   1. reset the simulator,
   2. load the scenario's crises,
   3. step through 2–3 simulated days, running our system every tick,
   4. collect the results.
3. **Compare on these measures:**
   - service level
   - liters unserved
   - ticks with any empty tank
   - refused or failed trucks
   - wasted supply
   - forecast error
   - how many ticks alerts took to fire
4. **Choose the method, and its settings, that does best in the worst scenario.** Settings include buffer
   size, planning window and alert thresholds. Change one setting at a time and re-run.
5. **Keep the result table.** It's the demo evidence: "our system vs. doing nothing, in 8 scenarios."

The simulator gives the same result for the same inputs, so every comparison is fair and repeatable.

## Additional ideas: Proving it works

- **Random crisis generator.** Besides the 8 fixed scenarios, generate many random crisis combinations
  (each from a numbered seed, so any run can be repeated). This shows the system survives situations we didn't plan for.
- **Speed test.** Raise the simulator speed step by step and find the fastest speed at which our system still handles every tick.
- **Replay.** Save a whole run and play it back on the dashboard. This is useful for the demo, and when judges ask "what happened at tick 100?"
- **Scenario files.** Store each scenario as a small file, so a judge's surprise can be written down and re-run later.
- **Results history.** Record every test bench run with the settings used, so you can show how the system improved over time.
- **Live comparison on the dashboard.** Show the "doing nothing" shadow score next to the real one during the demo.

---

## Order to build it

1. Collect and save (the start of this document)
2. Published-pattern forecast (section 1, steps 1 and 4) → tank projection (3) → backup rule (10) → send automatically
   → **first working version.** The service level should beat 0.88.
3. Test bench (15), so everything after this can be measured
4. Blend with real data, the range, confidence (1–2, 5), depot projection (4)
5. Detection and alerts (6–7)
6. Optimizer (9), crisis handling (11), rationing (12). Keep it only if it beats the backup rule on the test bench.
7. Approval rules (13), explanations (14)
