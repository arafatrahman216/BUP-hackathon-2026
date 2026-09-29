Main dashboard (always visible)
Station cards: a fuel bar for each fuel, colored safe / watch / urgent, plus time until empty and latest safe order time ("order by 15:30").
Depot cards: fuel levels, runway, and an overflow warning when a ship is coming.
Score strip: the service level, "liters saved vs doing nothing", and trucks on the road.
Mode badge: normal / crisis / save-fuel, with the reason ("Crisis: Dhaka spike").
System health bar: simulator OK / slow / down, and "data is 3 ticks old" when stale.
Alerts and incidents panel
Incidents, not raw alerts, e.g. "Dhaka spike → Mirpur at risk → rationing on", each with a timeline.
Crisis countdown: "Road cut starts in 3 ticks".
Acknowledge buttons, and incidents close themselves when resolved.
Recommendations panel (the main work area)
Each card shows:
the shipment: amount, depot, road, arrival time,
why: a 2–3 sentence explanation,
the impact: "risk 72% → 19%", unserved liters before and after,
alternatives: the next-best options and why they lost,
a confidence badge.
Approve / edit / reject buttons, and a "needs your approval because…" reason.
A 6-hour plan timeline: what the system intends to send next.
An auto mode switch and a stop button.
Station detail (click a station)
A fuel level chart: history plus the projected future line with its range.
Demand, actual vs forecast, with the spike marked.
The refill window and the next rush ("morning rush in 2 hours").
Other screens
Shipments: trucks waiting, on the road, arrived or failed. Failed ones show the replacement, and waiting ones have a cancel button.
Decision log: every recommendation, what the operator did, and what happened.
What-if tool: try a shipment or an imaginary crisis and see the result.
Settings: priorities, fair vs maximize-total rationing, and the settings history with rollback.
Keep hidden (internal, or on the monitoring dashboard only)
The forecast math: blending weights, the running-total and single-tick check values, the optimizer's internal scores.
Model accuracy per station, drift corrections, missed-tick catch-up, stream health details. These belong in Grafana, where judges look at observability.
The test bench results: those go into the demo slides and README, not the operator screen.
Priority if time is short: station cards, alerts, and recommendation cards with approve buttons, plus the health bar. Those four cover most of the brief's §6 list.

