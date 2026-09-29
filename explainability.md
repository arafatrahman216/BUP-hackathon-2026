# Explainability ("Ask AI"): design decisions

Operators can ask an LLM about any recommendation in the **approval queue** or the **decision log**. The answer
is grounded in the system's own data and stored with the exact data the model saw. This document records
how it works, the decisions behind it, and what is still missing. The short version is also in
[design.md](design.md) §7b, with rows in its decision log.

## How it works

```
Operator clicks "Ask AI" on a recommendation, then picks a suggested question or types one
  → POST /api/v1/explain/recommendations/{id}  {"question": "..."}
  → profile "recommendation" in backend/app/explainability/profiles.json → list of metrics
  → snapshot: the pipeline's cached World + Forecasts (predict) + Alerts (detect) + blocked needs
      (no cache yet → same read_world() + predictor + detect() code, run live)
    + open recommendations (DB) + longer demand history for the station (simulator, optional)
  → each metric writes one block of a JSON context
  → system prompt + profile instructions + question + JSON → LLMClient (Gemini 3.8 Flash, fallback chain)
  → answer is stored in `action_questions` and shown under the card, with "Data the AI used"
```

| Endpoint | Purpose |
|---|---|
| `GET /explain/recommendations/{id}` | Suggested questions for the recommendation's status, plus earlier Q&A (newest first) |
| `POST /explain/recommendations/{id}` | Ask about that recommendation; the Q&A is stored |
| `POST /explain` | Any question about a station, depot, allocation, inline action or the network (not stored) |
| `POST /explain/context` | The JSON the LLM would get, without calling it (for tuning metrics) |
| `GET /explain/profiles` | Profiles, params, suggested questions and the metric catalog |

## Decisions

### 1. Reuse the pipeline's detect and predict output; never recompute it
Metrics read the same `World`, `Forecast` and `Alert` objects the tick pipeline decided with, taken from its
in-memory cache. `forecast`, `alerts`, `station_ranking` and `risk_rules` pass that output through; they do
not re-implement it.
- **Why:** an explanation must match the decision. If the explainer had its own formulas, it could say
  "safe" while the pipeline said "urgent". Swapping in a model predictor in `app/pipeline/__init__.py`
  changes the explanations automatically.
- **No cache yet** (the pipeline hasn't run): the service runs the pipeline's own `read_world()`,
  `build_predictor().predict()`, `detect()` and `stockout_alerts()`, so the numbers are the same. I extracted
  both functions from `PipelineService` so the two paths share them. `_meta.data_source` says which path was used.
- **Rejected:** reading the simulator per question with separate calculations. That was the first standalone
  version; it duplicated the prediction logic and made more simulator calls.

### 2. What goes to the LLM is configuration, not code
`profiles.json` maps each question type (`recommendation`, `station`, `depot`, `general`) to its list of
metrics, its instructions and its suggested questions. It also holds tuning params (`history_ticks`,
`ranking_size`, `trend_min_slope`, ...). The file is re-read on every request, and one request can override
it with `metrics` / `params`. New metrics are one decorated function (`@metric("name")`) in `metrics.py`.
- **Why:** you asked to be able to change the metrics, and how they are found, after the rest is built.
  `/explain/context` lets you check the JSON without spending LLM calls.

### 3. One compact JSON context, which states what is degraded
The context is `{"_meta": {...}, "<metric>": ..., "_unavailable": [...]}`. `_meta.notes` states every
compromise in plain words:
- the data was read live;
- the action was proposed at an earlier tick than the current data;
- the long demand history couldn't be read;
- the database is down.

A metric that raises is listed in `_unavailable` instead of failing the request.
- **Why:** the prompt tells the model to say what is missing. That only works if the context says so.
  A partial answer is more useful to an operator than an error.
- If there is no cache and no simulator, the request returns 503 `SIMULATOR_UNAVAILABLE`, because there is
  nothing to ground an answer in.

### 4. Metrics added because real questions failed without them
A first test used realistic operator questions. The failures showed which data was missing:

| Metric | Question it made answerable |
|---|---|
| `risk_rules` (thresholds + this station's verdict) | "Why hasn't the system sent anything?" |
| `demand.cover_ticks_if_trend_continues` (linear trend) | "When will Tongi *actually* run out?" (average said 15 ticks, the trend says ~11) |
| `forecast.margin_ticks`, `free_space_l` | "Will it arrive in time?", "Can I send less?" |
| `depot_commitments`, `depot_stations` | "Is there enough petrol left for everyone else?" |
| `station_ranking` | "Which station is closest to running dry?" |
| `open_recommendations` | "What should I do first?" |
| `action.ticks_since_proposed` + a note | Questions from the decision log about old actions |

### 5. Prompt rules, each from an observed failure

| Rule in `SYSTEM_PROMPT` | Failure it fixes |
|---|---|
| "You may calculate from context values ... show the calculation" | It refused a simple what-if ("cut to 4,000 L") |
| "Prefer the trend-based cover" | It reported the average-based run-out while demand was climbing |
| "Do not contradict `action.reasons` / `risk_rules`" | It called a 0.7-tick margin safe although the planner flagged it |
| "Separate at risk from already harmed" | It said a failed shipment "hurt" a station that had 60 ticks of stock |
| "Do not guess causes" | It linked the flood to a failure without evidence |
| "Direct answer, then ≤ 5 bullets" | Answers are read on a small card |

### 6. Ask AI is scoped to a recommendation, and every Q&A is stored
Each approval card and each decision-log row gets its own panel. The endpoints live under
`/explain/recommendations/{id}`, not under `/recommendations`.
- **Why that path:** the rate limiter works by path prefix. `/api/v1/explain` limits LLM calls without also
  rate-limiting approve and reject.
- **Why store it:** the table `action_questions` holds the question, answer, model, tick and the exact
  context. That is an audit trail of what the operator was told before they approved, and reloading the page
  shows earlier answers. Nothing is stored when the LLM call fails.

### 7. Suggested questions by status
`PENDING_APPROVAL` suggests "Why does this need my approval?", "What happens if I reject it?", "Can I send
less...?". Other statuses get their own lists: `REFUSED` gets "Why was this refused?" and "What should I do
instead?". They live in `profiles.json` next to the metrics they depend on.

### 8. The AI advises; it never acts
Answers are text only. Approve, edit and reject stay with the operator and go through the existing
endpoints. The LLM has no tool that can post an allocation.

### 9. Model: Gemini 3.8 Flash, through the existing fallback chain
`GEMINI_MODEL=gemini-3.8-flash` (the default in `config.py` and both env files). I compared three models on
the same six operator questions:

| Model | Result |
|---|---|
| 2.5 Flash | 1 fully correct, 4–15 s |
| **3.8 Flash** | Best accuracy together with 3.1 Pro, **4–7 s**, not a preview |
| 3.1 Pro Preview | Similar accuracy, speculated more, 10–17 s, preview |

- `EXPLAIN_PROVIDER` is empty, so the `AI_PROVIDER_ORDER` chain (`gemini,groq,gemini`) is used. A transient
  Gemini network error, which I did see once, falls back instead of failing.
- Temperature is 0.2: explanations should be repeatable, not creative.

### 10. Show the evidence in the UI
Every answer has a collapsible "Data the AI used" section showing the stored context. It also shows the
model and tick, and any metric that was missing.
- **Why:** operators and judges can check any number in the answer against the data it came from.

### 11. Security
The Gemini key stays in `backend/.env`, and the browser only talks to the backend. `/api/v1/explain` is in
`RATE_LIMIT_PATH_PREFIXES` (20 POSTs per minute per IP by default), so free-tier quotas are protected.

## Evaluation (final run, Gemini 3.8 Flash, dummy world)
Dummy world: Mirpur petrol 300 L at 110 L per tick (urgent, pending); Tongi diesel demand +6 L every tick;
a flood in the Dhaka region; a blocked route; a delayed ship; a failed allocation.

| Question | Result |
|---|---|
| Cut to 4,000 L: will Mirpur be OK? | ✅ Arrives with 80 L left, lasts ~39 ticks; Tongi petrol is safe at 60 ticks |
| Hold until the flood ends? | ✅ No: dry from tick 102.7 to 122, ≈ 2,120 L unmet |
| Why nothing for Tongi diesel, and when does it run out? | ✅ 15-tick cover ≥ the 10-tick watch threshold, so "safe"; with the trend, ~10.8 ticks |
| Did failed allocation 7 hurt Tongi? | ✅ No harm (60 ticks of stock, 0 unmet); no need to resend now |
| Enough petrol at Gazipur until the ship? | ✅ 38,000 L left vs ≈ 1,680 L needed over 8 ticks |
| Which station is closest to dry? | ⚠️ Correct (Mirpur, approve recommendation 1), but it wrongly linked the blocked Patiya route to allocation 7 |

Each answer took about 5–15 s.

## Known limitations and next steps
- **Old actions are explained with current data.** The world at decision time is not reconstructed (the
  `tick_snapshots` rows are compact), so this is only flagged in `_meta.notes`. Next step: store the decision
  inputs (forecast, depot stock, route) on the recommendation when it is created.
- **The `general` profile has no demand trend per station,** so "closest to dry" uses average-based cover. Add
  a trend column to `station_ranking` if needed.
- **It can still link facts wrongly.** Q6 above: the alerts say allocation 7 failed, but not on which route. Add
  the route to failure alerts, or add `recent_allocations` to the general profile.
- **No streaming:** the answer appears after 5–15 s.
- **The UI only has Ask AI on recommendations.** The API already answers station, depot and network questions
  (`POST /explain`), so buttons on station cards and alerts are an easy next step.
- The pipeline's own "explain" stage still writes template text; the LLM is used only on demand.
