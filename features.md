# Features

This is the build list for the project. The human writes features here; the coding agent
reads this file (together with [design.md](design.md)) and implements them.

## How to use this file

**Human:** add a feature using the template below. Keep it short: what the user can do,
the rules that matter, and what "done" looks like. Leave blank anything you don't know yet.

**Coding agent:**
1. Read [design.md](design.md) first and follow its structure and conventions.
2. Build features whose status is `todo`, from top to bottom, unless told otherwise.
3. Follow design.md §3.6 (model → schema → repository → service → dependency →
   controller → register router). This project is backend-only; don't build frontend pages.
4. Add or update tests for what you build.
5. When a feature is done, set its status to `done` and list what you added under **Notes**
   (endpoints, tables).
6. If you make a new design decision (library, pattern, data model), record it in the
   decision log in design.md.
7. If something here is unclear or contradicts design.md, ask. Don't guess.

Status values: `todo` · `in-progress` · `done` · `blocked`

---



---

## Features

<!-- Add your features below this line -->

### Baseline tick pipeline (read → post)
**Status:** done
**What:** Every simulator tick: read → validate → save → detect → predict → decide → explain →
(important? operator approves/edits/rejects : auto) → post, with a fallback at every step.
Rules are hard-coded (no model, no optimization); the model/solution plugs in later.
**Notes:**
- Endpoints: `GET /dashboard`, `GET /stream` (SSE), `POST /pipeline/run`, `GET /snapshots`,
  `GET /recommendations`, `GET /recommendations/{id}`, `POST /recommendations/{id}/approve`, `POST /recommendations/{id}/reject`; `/health` now reports simulator + pipeline.
- Tables: `tick_snapshots`, `recommendations`.
- Code: `app/pipeline/`, `services/pipeline_service.py`, `services/recommendation_service.py`, `repositories/simulator_repository.py`. Swap stages in `app/pipeline/__init__.py`.
- Env: `SIMULATOR_*`, `PIPELINE_*`, `FORECAST_WINDOW_TICKS`, `SAFETY_TICKS`, `URGENT_MARGIN_TICKS`, `MIN_SHIPMENT_LITERS`, `DEPOT_RESERVE_LITERS`, `AUTO_POST_ENABLED`, `APPROVAL_TTL_TICKS`, `APPROVAL_MIN_SECONDS`, `SNAPSHOT_EVERY_TICKS`.
- Not yet: refusal handling beyond recording the code, shipment tracking/replacement, cancel, operator auth, LLM explanations.

### Operator dashboard
**Status:** done
**What:** Live web page for the operator: simulator link and tick, score, pipeline stage health, station fuel
levels with risk, approval queue (approve / edit quantity / reject), alerts and blocked needs, depots, routes,
trucks, incoming ships and crises, decision log, stale banner.
**Notes:** `frontend/src/pages/Dashboard/`, `components/dashboard/`, `hooks/useDashboard.js` (SSE, polling fallback). Tests in `DashboardPage.test.jsx`.

