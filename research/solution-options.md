# Solution Options: BUP Fuel Supply Operations Platform

Options for each layer and problem, from simplest to most advanced. **★ = recommended**, **↩ = fallback**.
Effort assumes a small team building for 1–3 days. Facts are from `project-context.md` and the simulator guide.

---

## 1. Simulator integration

| Problem | Options | Pick |
|---|---|---|
| HTTP client | (a) plain `httpx` calls · (b) `httpx.AsyncClient` + `tenacity` retry · (c) b + circuit breaker (`purgatory`/`aiobreaker` or ~40 lines of our own) + bulkhead semaphore | ★ c |
| Retry policy | fixed delay · exponential backoff + jitter (3 tries, 0.2→0.8 s) on 503/timeout/conn errors · adaptive (respect breaker state) | ★ exp+jitter; POST is safe to retry because of `idempotency_key` |
| Tick detection | poll `/v1/instance` · SSE `simulation.tick` · **hybrid** (SSE primary, 1 s poll while SSE is down) | ★ hybrid (`httpx-sse`) |
| Validation | none · Pydantic v2 models · strict models + sanity rules (inventory ≤ capacity, tick monotonic) | ★ strict + sanity → reject + alert |
| Stale / reset | ignore · flag `X-Simulator-Stale` · flag + block auto-dispatch; tick going backwards → full resync | ★ last |

## 2. Data and state

| Problem | Options | Pick |
|---|---|---|
| DB | SQLite · Postgres · TimescaleDB | ★ Postgres (the user's choice); Timescale isn't needed at this scale |
| Snapshots | normalized tables · **JSONB snapshot per tick** + a few typed tables | ★ JSONB snapshots + typed `demand_observations`, `recommendations`, `alerts`, `decision_log` |
| Live state | read the DB every time · in-memory last-good cache · Redis | ★ in-memory cache (single instance); Redis only if we scale out |
| Worker | asyncio tasks in lifespan · APScheduler · separate worker container (arq) | ★ asyncio tasks (simple); ↩ a separate container if the load test shows contention |
| History ingest | on demand · **every tick** (API keeps ≤2,000 rows) | ★ every tick, dedupe by id |

## 3. Demand forecasting (Predict)

The generating formula is known: `daily/96 × hour_factor × region × multiplier × noise(8–12%)`.

| Option | How | Effort | Fit |
|---|---|---|---|
| Seasonal naive | same tick yesterday | 1 h | 2 |
| Guide prior | compute directly from the profile tables | 1 h | 3 (a good cold start) |
| EWMA per hour bucket × live multiplier | 288 learned rates, divide out the multiplier before learning | 3 h | 4 |
| **★ Structural state-space** | log-space: base + **shared hourly shape per station** (all 3 fuels share it) + known multiplier + Kalman drift level; prior from the guide | 1 day | **5** |
| LightGBM (mlforecast) | features: hour, profile, multiplier, lags | 0.5 day | 3 (benchmark only) |
| Foundation models (Chronos-Bolt, TimesFM) | zero-shot | 0.5 day | 2 (heavy, and the multiplier isn't used) |

Apply scheduled spikes to future ticks, and divide out active spikes after their `end_tick`.
Evaluate with a walk-forward backtest on `simulator/dataset/` using **WAPE** at horizons 1/4/12/24 (not MAPE, because night values are tiny).

## 4. Uncertainty and stockout risk

| Problem | Options | Pick |
|---|---|---|
| Intervals | normal from residual σ · quantile regression · **conformal** (split / adaptive ACI via MAPIE or ~30 lines of our own) | ★ adaptive conformal; ↩ normal |
| Projection | deterministic `P[k]=P[k-1]+incoming−D̂` · **Monte Carlo** (1,000 paths, numpy, <10 ms) | ★ MC → p_stockout, expected stockout hours, ETA P10/P50/P90 |
| Delivery risk | ignore · mark trucks on routes about to be disrupted as failing | ★ mark |
| Calibration | — · show coverage ("90% intervals hit 89%") | ★ show it |

## 5. Anomaly, crisis and incident detection

| Problem | Options | Pick |
|---|---|---|
| Structural crises | read `/v1/events` only · **state diffs** (route/station/depot status, supply `planned_tick`/qty compared with first seen, FAILED allocations, reset) | ★ state diffs + events (catches everything with no false positives) |
| Demand anomalies | z-score · **CUSUM / Page-Hinkley on log(actual/forecast)** · BOCPD (`ruptures`/`river`) · Isolation Forest | ★ Kalman innovations + CUSUM; BOCPD is optional |
| Root cause | none · label "explained by event #x" vs "unexplained" | ★ label; unexplained → human review |
| Alert lifecycle | raw log · dedup + severity + ack + auto-resolve (ISA-18.2 style) · incidents = alerts grouped by region/time | ★ all three |

## 6. Allocation decision engine (Decide)

| Option | How | Effort | Fit |
|---|---|---|---|
| (s,S) reorder point | ship when `ETA − transit ≤ margin`; order up to the target | 3 h | 3 |
| Priority greedy | rank by slack, fill within dispatch/inventory budgets | 4 h | 4 ↩ **fallback + warm start** |
| LP rolling horizon | continuous shipments over H ticks | 0.5 day | 4 |
| **★ MIP + MPC** | integer trucks, min truck size, fixed cost per dispatch, stockout-tick binaries, route/outage windows, dispatch cap per depot across fuels, lexicographic objective (service → fewest/shortest trucks → no depot overflow) | 1–1.5 days | **5** |
| Chance-constrained MIP | plan against the demand quantile from §4 | +2 h | 5 (Should tier) |
| Two-stage stochastic MIP (SAA) | 10–20 demand scenarios | +1 day | 3 |
| RL (PPO, SB3) | trained in a digital twin | 2+ days | 2 |

**Solver:** ★ PuLP + **HiGHS** (↩ CBC). OR-Tools CP-SAT is an alternative (needs integer scaling).
**Speed:** relax-and-fix (integers only for t<4), warm start from greedy, 2 s limit, 1% gap, run in a thread pool.
**N-1 contingency reserve** for single-route stations (Tongi, Cox's Bazar), a soft constraint.
**Explainability:** fix the integers, re-solve as an LP, and read the **duals** to name the binding constraint.

## 7. Policy evaluation, digital twin, RL

| Problem | Options | Pick |
|---|---|---|
| Proof of quality | eyeball · **deterministic A/B on the real simulator** (`/admin/reset` + `/admin/step`, same events) | ★ A/B: no-action vs greedy vs MIP |
| Twin | none · numpy re-implementation (validated against the simulator) · SimPy | ★ numpy (Could tier) |
| Tuning | hand-tuned · grid · **Optuna** over a scenario suite | ★ Optuna if time allows |
| RL | skip · PPO baseline for comparison | skip unless everything else is done |

## 8. Human-in-the-loop and explainability

| Problem | Options | Pick |
|---|---|---|
| Autonomy | always approve · **hybrid gates** · full auto | ★ hybrid: auto only if confidence ≥ 0.7, data fresh, no unexplained anomaly, MIP ≈ greedy (agreement check), below the value-at-stake limit |
| Queue | list · expiry + supersession + edit-before-approve | ★ all |
| Inspectability | text · **ALERT card** (brief §9) + signals + binding constraints + before/after + alternatives with rejection reasons + confidence | ★ |
| What-if | none · operator edits qty/route → re-simulate | ★ Should tier |

## 9. Generative AI layer

| Problem | Options | Pick |
|---|---|---|
| Explanations | free text · **structured JSON output grounded in decision data** + numeric-grounding check | ★; ↩ template |
| Incidents | none · summary on open/resolve | ★ |
| Q&A | context stuffing · **read-only tool calling over our API** · text-to-SQL | ★ context snapshot first; tool calling later |
| Cost/latency | live per view · cached per rec/incident + rate limit | ★ cached |

## 10. Observability and resilience

| Problem | Options | Pick |
|---|---|---|
| App metrics | **built-in rolling window** · `prometheus-fastapi-instrumentator` + Grafana · OpenTelemetry + Jaeger | ★ built-in (user choice); Prometheus is a cheap upgrade later |
| System | psutil · cAdvisor | ★ psutil |
| Intelligence | forecast WAPE, interval coverage, confidence, alerts/hour, decisions/cycle, auto vs review, fallback activations, solver time and gap, retries, breaker state, service level | ★ all |
| Logs | plain · **JSON (structlog) with request id + event type**, a viewer in the UI | ★ |
| Health | single `/health` · per-component healthy/degraded/down (backend, DB, simulator + breaker, sync age, forecaster, planner, LLM) | ★ |

## 11. DevOps and load testing

| Problem | Options | Pick |
|---|---|---|
| Deploy | compose · compose + healthchecks/profiles · k8s/Helm | ★ compose with healthchecks (k8s doesn't pay off here) |
| CI | none · GH Actions lint+test+build · + compose smoke test with the real simulator image · + GHCR push | ★ smoke test; push optional |
| Load test | Locust · **k6** · Vegeta | ★ k6: dashboard read path (ramp 1→100 VUs), decision cycle (constant arrival rate), approve path; report p50/p95/p99, RPS, errors, CPU/mem, saturation point |

## 12. Demo and surprise events

- Demo speed `SIMULATION_SPEED=1` (or step mode). Keep a **scenario panel** (clearly labelled *simulation admin*) plus scripts for all 6 crisis types and 5 faults.
- Config flags for everything: horizon, thresholds, planner on/off, autopilot. A surprise event then needs a config change, not new code.
- Evidence pack: architecture diagram, A/B table, load-test report, fault screenshots/logs, decision audit export.

---

## Dashboard (what to show)

**Top bar (every page):** tick · sim time · RUNNING/PAUSED · data freshness (fresh/stale/degraded) · service level · open alerts · autopilot toggle.

| Page | Widgets | Serves |
|---|---|---|
| **Network overview** | schematic map (depots → routes → stations; route colour = available/disrupted, animated trucks in transit) · station×fuel grid: inventory bar vs capacity, ETA (P50 + range), risk colour · depot cards: inventory, dispatch used/cap, next ship, overflow warning · incoming supply timeline | brief §6 inventory, status, supply, disruptions |
| **Recommendations** | review queue (Approve / Edit / Reject, expiry countdown) · auto-sent list · detail: ALERT card, before→after risk, signals, binding constraint, alternatives, confidence, LLM explanation (or a "template" badge), planner used (MIP/greedy) | §9 decision support, human review |
| **Forecast & risk** | demand forecast vs actual with interval band per station/fuel · projected inventory path · WAPE and coverage | intelligence |
| **Alerts & incidents** | alert list (severity, explained/unexplained, ack) · incident cards with LLM summary, time-to-detect, time-to-recover · event timeline | §10 crisis handling |
| **Decision history** | audit log (who/what/when/outcome) · allocation ledger PENDING→IN_TRANSIT→ARRIVED/FAILED · "MIP vs greedy shadow" savings | §20 audit |
| **System health** | component status table · p95 latency, error rate, RPS · CPU/mem · breaker state, retries, fallback counters · recent JSON logs | §14, §15 observability |
| **Assistant** (drawer) | grounded Q&A | GenAI |
| **Scenario control** (admin) | inject crisis/fault, pause/step/run | demo |

**MVP for the demo:** top bar, Network overview, Recommendations (queue + detail), Alerts, System health.

---

## Packages

| Layer | Baseline (safe) | ★ Strong (recommended) | Ambitious |
|---|---|---|---|
| Forecast | guide prior + EWMA | structural + Kalman, shared shape | + LightGBM/foundation benchmark |
| Risk | normal σ, deterministic ETA | Monte Carlo + conformal | + delivery risk, calibration dashboard |
| Detect | state diffs + z-score | + CUSUM, root-cause labels, incidents | + BOCPD |
| Decide | greedy (s,S) | **MIP-MPC** + greedy fallback + duals | chance-constrained / SAA + Optuna-tuned twin, RL comparison |
| Policy | approve all | hybrid gates + agreement check | + what-if |
| LLM | templates | grounded explanations, incidents, Q&A | tool-calling assistant |
| Ops | health + metrics | + JSON logs, fault scripts, k6, CI smoke | + Prometheus/Grafana, GHCR |

## Decisions still needed from you
1. **Package:** Strong (my recommendation), Baseline, or Ambitious?
2. **Backend port:** 8080 (your choice) vs 8001 in `project-context.md`. Which is canonical?
3. **Auth / monitoring:** `project-context.md` lists operator auth and Prometheus/Grafana, but you chose no auth and built-in monitoring. Should I update project-context.md?
4. **Demo speed** (suggest 1 tick/s) and planner cadence (every tick).
5. **Digital twin + Optuna:** is it worth about a day for the evidence it gives?
