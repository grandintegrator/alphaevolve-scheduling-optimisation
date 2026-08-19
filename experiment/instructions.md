# Metro Parcel Network Linehaul Dispatch — Parcels Sorted Maximisation

## Problem

A metro parcel network runs a 12-hour intake day (720 minutes) with a fleet
of 7 linehaul trucks, 7 suburban delivery centres (DCs) and 2 parcel sorting
facilities (a large eastern hub and a smaller western one), all on a 2-D
plane (1 unit = 10 m). Whenever a truck becomes free at a hub, your dispatch
policy is asked one question: which DC should it load parcels at next?

Simulation rules (the evaluator plays your policy through a deterministic
discrete-event simulation):

- Truck cycle: travel empty to the assigned DC → wait if the DC's dock is
  busy (DCs belt-load one truck at a time, in dispatch order) → load
  (`capacity / dispatch_rate` minutes) → travel loaded to a sorting hub —
  the simulator picks whichever of the two hubs gets the truck unloaded
  soonest (arrival + dock queue) → wait if that hub's dock is busy (each
  hub unloads one truck at a time, in dispatch order) → unload onto the
  sorter (`capacity / sort_rate` minutes) → ask for the next job. Speeds:
  `speed_empty` / `speed_loaded` units/min; travel minutes =
  `dist(a, b) / speed`.
- Only parcels sorted within the shift count; an unload in progress at the
  linehaul cutoff counts pro-rata.

## Objective

Maximise `parcels_per_shift`: total parcels through the two sorters,
averaged over three related network instances. Higher is better.

## Contract for assign_truck (the evolve block)

```
assign_truck(truck, net, state) -> {"depot": str}
```

- `truck`: `{"id", "capacity", "x", "y"}` — current position and payload
- `net`: the full network dict — `depots` (each `id`, `name`, `x`, `y`,
  `dispatch_rate` parcels/min), `hubs` (each `x`, `y`, `sort_rate`; `hub`
  is the main eastern one), `trucks`, `speed_empty`, `speed_loaded`,
  `shift_minutes`
- `state`: `{"now": minutes, "depot_free": {depot_id: booked-until},
  "hub_free": earliest hub booked-until, "hub_free_by_id":
  {hub_id: booked-until}, "parcels_sorted": parcels}`

Hard validity rules (violations score as failures):
- every assignment references a valid depot id
- the policy returns a dict with a "depot" key, promptly, for every call

## Guidance

- The baseline is a fixed greedy roster: it pairs each truck with one DC
  (nearest DC to the main hub first) and never rebalances — so trucks
  assigned to the slow manual-load DCs spend most of the shift parked at a
  dock, regardless of demand elsewhere. DCs differ enormously in
  `dispatch_rate` (fast automated belts vs slow manual ones) and in
  distance to the two hubs. Known-better directions: dispatch dynamically
  on *expected* turnaround (empty travel + dock wait via
  `state["depot_free"]` + load time + loaded run to a hub), and prefer
  fast docks even when they are further away.
- Must be deterministic (no randomness, or fixed seeds only) and pure Python
  standard library. Keep runtime well under ~15 seconds; the policy is
  called a few hundred times per instance.
- Helpers available outside the evolve block (they mirror the simulator's
  exact travel model): `dist(a, b)` and `travel_min(a, b, speed)` — as is
  `math`.
