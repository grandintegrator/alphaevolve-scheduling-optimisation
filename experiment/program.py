"""Metro Parcel Network linehaul dispatch — seed program for AlphaEvolve.

Whenever a truck finishes unloading at a sorting hub and becomes free, the
dispatcher is asked one question: which delivery centre (DC) should it load
parcels at next? The truck then drives there, queues if the DC's dock is
busy (one truck loads at a time), loads, then drives loaded to whichever of
the two sorting hubs gets it unloaded soonest (each hub unloads one truck at
a time). The simulator in evaluate.py plays the policy over a 12-hour intake
day; the score is total parcels through the sorters.

Only assign_truck() between the EVOLVE-BLOCK markers may be changed. It must
return {"depot": <depot_id>}.
"""
import math


def dist(a, b):
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def travel_min(a, b, speed):
    return dist(a, b) / speed


# EVOLVE-BLOCK-START
def assign_truck(truck, net, state):
    """Baseline policy: a fixed greedy pairing. Walk the trucks in fleet
    order and give each one the nearest still-unclaimed DC to the main hub
    (truck 1 gets the closest DC, truck 2 the next closest, ...). Each truck
    then shuttles its own DC for the whole shift — no rebalancing, no regard
    for dock speed, hub choice or cycle time.
    """
    order = sorted(net["depots"], key=lambda d: dist(net["hub"], d))
    fleet = [t["id"] for t in net["trucks"]]
    d = order[fleet.index(truck["id"]) % len(order)]
    return {"depot": d["id"]}
# EVOLVE-BLOCK-END


def solve(net):
    """Return the dispatch policy the simulator will call."""
    return assign_truck
