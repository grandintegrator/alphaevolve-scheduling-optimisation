"""Generate the dummy metro parcel network (deterministic).

Purely fictional data: 7 suburban delivery centres (DCs) ringing a 1000x760
plane (1 unit = 10 m) with two parcel sorting facilities — the main hub to
the east and a smaller western hub. A fleet of 7 rigid linehaul trucks
shuttles parcels from the DCs to the sorters; loaded trucks tip at whichever
hub gets them unloaded soonest. Run once to produce network.json.

The naive baseline greedily pairs each truck with one DC (nearest DC to the
main hub first) and never rebalances — ignoring dock speeds, hub choice and
cycle times.
"""
import json
from pathlib import Path

# dispatch_rate = parcels/min while belt-loading a truck. DC-4/5/6 are big
# automated sites, DC-7 semi-automated; DC-1/2/3 are older manual-load DCs
# with slow belts. The docks are sized so the fast sites queue up when the
# whole fleet piles on — a good dispatcher has to spread and rotate.
DEPOTS = [
    {"id": "DC-1", "name": "Banksia DC",   "x": 140, "y": 180, "dispatch_rate": 110},
    {"id": "DC-2", "name": "Waratah DC",   "x": 120, "y": 420, "dispatch_rate": 100},
    {"id": "DC-3", "name": "Bluegum DC",   "x": 220, "y": 620, "dispatch_rate": 90},
    {"id": "DC-4", "name": "Ironbark DC",  "x": 420, "y": 150, "dispatch_rate": 300},
    {"id": "DC-5", "name": "Coolibah DC",  "x": 700, "y": 90,  "dispatch_rate": 330},
    {"id": "DC-6", "name": "Mulga DC",     "x": 740, "y": 680, "dispatch_rate": 340},
    {"id": "DC-7", "name": "Quandong DC",  "x": 540, "y": 700, "dispatch_rate": 150},
]

HUBS = [
    {"id": "HUB",  "name": "Kurrajong Parcel Facility", "x": 840, "y": 400,
     "sort_rate": 760},  # parcels/min while a truck is unloading
    {"id": "HUB2", "name": "Telopea Parcel Facility",   "x": 90,  "y": 260,
     "sort_rate": 620},  # smaller western sorter
]

# 7-truck linehaul fleet, capacities in parcels (rigid truck with cages)
TRUCKS = [{"id": f"T{i+1:02d}", "capacity": c}
          for i, c in enumerate([1800, 1800, 1700, 1900, 1600, 1800, 1700])]

network = {
    "description": "Fictional metro parcel network for AlphaEvolve demo",
    "units": {"distance": "1 unit = 10 m", "payload": "parcels"},
    "shift_minutes": 720,        # one 12-hour intake day (06:00-18:00)
    "speed_empty": 110,          # units/min (~66 km/h)
    "speed_loaded": 75,          # units/min (~45 km/h)
    "trucks": TRUCKS,
    "depots": DEPOTS,
    "hub": HUBS[0],   # main hub (kept for policy-code compatibility)
    "hubs": HUBS,
}

out = Path(__file__).parent / "network.json"
out.write_text(json.dumps(network, indent=2))
print(f"wrote {out}: {len(DEPOTS)} DCs, {len(TRUCKS)} trucks, "
      f"{len(HUBS)} hubs ({'+'.join(str(h['sort_rate']) for h in HUBS)} "
      f"parcels/min), shift {network['shift_minutes']} min")
