# Handoff: Fuel Ops Console (operator dashboard)

Target: `arafatrahman216/BUP-hackathon-2026` → `frontend/` (Vite + React 19, CSS modules, existing `components/ui` Button/Card, `api/api.js`).

## Overview
Single-page operator console for the BUP Fuel Supply Simulator "brain". It shows the network (map or full state tables), a deadline-sorted action queue of recommended shipments with approve/edit/reject, and an action log with lifecycle + verification. Clicking a queue item or log row opens a modal; clicking a map node opens a side panel.

## About the design files
`Fuel Ops Console v3.dc.html` is a **design reference built in HTML**, not production code. Recreate it in the existing frontend using its patterns (React components + CSS modules, `useDashboard` hook, `api.js`). All data in the file is the sample scenario from the UI context doc (Day 2 13:30, Dhaka spike) and must be replaced by backend data.

## Fidelity
High-fidelity. Match colors, type, spacing and states below.

## Layout (top → bottom)
1. **Nav bar** (sticky, white, 1px bottom border, padding 14px 32px): logo square 30px (accent, radius 8, letter "F") + "Fuel Ops" 19px/600 + "SIMULATED NETWORK" tag (12px/500, letter-spacing .06em, 1px border, radius 6). Right side: clock pill (soft bg, radius 9; "Day 2 · 15:30" 16px/600 tabular + Pause/Play button), health dot + text ("All systems healthy · data 2 s old"), "Dark mode" toggle button.
2. **Page header** (padding 28px 32px 0): H1 "Operations" 26px/600, subtitle 16px muted.
3. **Incident cards**: grid `repeat(auto-fit, minmax(min(100%,340px),1fr))`, gap 16. Each card: white bg, **1.5px solid ink border**, radius 12, padding 16px 20px; 14px urgency circle (red = crisis, yellow = warning); title 17px/600; right-aligned time/countdown 15px/600 ("12:00 – 22:00", "in 2h 15m"); one-line detail 15px muted.
4. **Simulator-down banner** (only when simulator unreachable): "Simulator not responding · Showing data from 13:28 · retrying · autopilot paused".
5. **KPI cards** (grid auto-fit minmax 210px, gap 16; white, 1px border, radius 12, padding 16px 20px): Mode (dot + "Crisis"/"Normal" 22px/600, reason), Service level (96.4%, "+15.2 pts vs no action"), Trucks on the road (count, "N actions waiting"), Autopilot (40×23 switch, On/Off/Paused, caption).
6. **Main**: flex-wrap, gap 24, `align-items: stretch` so both columns end at the same bottom edge.
   - **Network card** (flex 1.5 1 580px): H2 "Network" 20px/600 + segmented toggle Map | All states.
     - **Map**: real Bangladesh geography (d3-geo Mercator, world-atlas countries-110m TopoJSON; Bangladesh fill white, neighbours #f0f1f4, water `oklch(0.965 0.018 235)`; labels BANGLADESH, INDIA, MYANMAR, *Bay of Bengal*). Aspect 640/520. Depots = 20px accent squares; stations = 20px white circles with 5px ring coloured by **lowest fuel %**. Roads: main solid, backup dashed, scheduled closure red dashed; trucks = accent dots on the road. Pan by drag, zoom by wheel and +/−/Fit buttons (k 1–5, clamped); markers counter-scale so they stay the same size. Hover → tooltip (white card, per-fuel bars); click → side panel. Node positions are approximate (Dhaka sites spread for legibility).
     - **All states**: legend (Low/Medium/Good), then Stations, Depots and Roads tables. Fuel cell = % (16px/600) + litres (13px muted) + 8px bar coloured by level.
   - **Right column** (flex 1 1 400px): 
     - **Action queue** ("Earliest deadline first"): cards sorted by deadline asc. Left 96px tinted deadline box ("DECIDE BY", time 24px/600, "15m left"); right: title 17px/600, "7,000 L · Gazipur → Mirpur" 15px muted, severity pill + optional "Needs your review" pill. Empty state: "All stations covered until 18:00".
     - **Action log** ("Action · newest first" / "Status"): sorted by time desc. Title 16px/600; actor tag (Autopilot = accent text on pale blue; Operator = ink on grey) + "Day 2 · 13:15"; status pill (dot + 14px/600, tinted bg + border).

## Modals / panels
- **Recommendation modal** (max 620px): severity + title; "Decide by" + time 38px/600 + "Xh Ym left"; shipment box ("Send 7,000 L · Gazipur → Mirpur", "Arrives ~16:30 · 30 min · confidence high" or needs-review reason); Station state (4 figures: level now, empty at, demand vs forecast, cause); 3 tiles: Importance, Risk before (red), Risk after (green); "Ask why" + preset questions (Why not Patiya? / Wait an hour? / If the road closes?) → answer block with source badge ("Written by AI (Gemini)" or "Template text · AI unavailable"); footer Reject / Edit quantity (−/+ stepper, 500 L steps, max = road truck limit) / Approve.
- **Log modal** (max 600px): time · actor, title; 4-step progress (Action taken → Departed → Arrived → Verified) with times; AI summary + badge; "State when decided" figures; footer "Lowest level: predicted X · actual Y" + verdict dot.
- **Side panel** (right drawer 400px): station → per-fuel level bar, empty at / order by / in-transit, demand vs forecast, next rush, "Open action" button if one is pending. Depot → per-fuel level + runway, next ship, overflow risk, dispatch used this step.
- Toast on approve/reject.

## Behaviour / state
- Clock ticks 15 min per poll; deadlines show time left = deadline − now.
- Approve → item leaves queue, new log entry (status Departing, truck appears on the road). Reject → log entry Rejected. If simulator down: Approve is labelled "(held)" and entry status "Held".
- Demo states (dev only): Normal, Crisis, Simulator down, AI down, Empty queue.
- Theme toggle light/dark.

## Level colour rule (everywhere)
`< 25%` low (red) · `25–50%` medium (yellow) · `> 50%` good (green).

## Design tokens
Light: bg #f5f6f8 · surface #ffffff · soft #eef0f3 · ink #1b2130 · muted #4a5263 · faint #6b7282 · line #e3e6eb · accent oklch(0.53 0.12 250) · hover oklch(0.97 0.012 250) · hoverLine oklch(0.84 0.05 250).
Dark: bg #12151b · surface #1a1e26 · soft #252a35 · ink #e9ebf0 · muted #b6bcc8 · faint #959cab · line #2d3340 · accent oklch(0.7 0.11 250).
Status: low/urgent oklch(0.6 0.17 27) · mid/watch oklch(0.77 0.14 82) · good/safe oklch(0.63 0.13 152) · plan-ahead oklch(0.58 0.11 295).
Type: IBM Plex Sans 400/500/600. Base 15px/1.5; H1 26; H2 20; card titles 16–17; secondary 14; captions 13.
Radius: 6 (tags), 8 (buttons), 10–12 (cards), 14 (panels), 16 (modals). Shadow: `0 1px 2px rgba(20,30,50,.04), 0 4px 14px rgba(20,30,50,.04)`.

## Data needed from backend (see UI context doc §5)
Recommendation (id, severity, station, fuel, deadline, action{quantity, depot, road, travel, arrives}, impact, signals, confidence, needs_human_because, importance, risk before/after, explanation{source, summary, answers}), station risk, depot outlook, shipments, decision log + verification, mode, health, score, events (for incident cards).

## Files
- `Fuel Ops Console v3.dc.html`: the design reference (open in a browser).
