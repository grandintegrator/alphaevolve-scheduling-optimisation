"""Deterministic evaluator for the Metro Parcel Network linehaul-dispatch problem.

Scores a candidate program (mutated program.py source) by executing it and
playing its dispatch policy through a discrete-event simulation of one
12-hour parcel intake day, on the primary network plus two deterministic
perturbations (to discourage overfitting to one layout).

Simulation rules:
  - A truck cycle: travel empty to the assigned delivery centre -> queue (DCs
    belt-load one truck at a time, FIFO) -> load (capacity / dispatch_rate) ->
    travel loaded to a sorting hub (of the two, the one that gets the truck
    unloaded soonest: arrival + dock queue) -> queue (each hub unloads one
    truck at a time, FIFO) -> unload (capacity / sort_rate) -> ask the policy
    for the next job. Travel minutes = dist / speed.
  - Parcels only count if sorted within the shift; an unload in progress at
    the linehaul cutoff counts pro-rata.

A policy is only accepted if every assignment references a valid depot id on
every instance.

Score returned to AlphaEvolve: parcels_per_shift = mean parcels sorted across
the three instances. Higher is better; invalid or crashing candidates
get -1e9.
"""
import copy
import heapq
import json
import math
import random
import signal
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "network.json"
FAIL_SCORE = -1e9
TIMEOUT_SECS = 20
MAX_ASSIGNMENTS = 20000  # runaway-policy guard per instance


def load_instances():
    base = json.loads(DATA.read_text())
    instances = [base]
    for seed in (7, 13):
        rng = random.Random(seed)
        inst = copy.deepcopy(base)
        for d in inst["depots"]:
            d["x"] = min(985, max(15, d["x"] + rng.uniform(-30, 30)))
            d["y"] = min(745, max(15, d["y"] + rng.uniform(-30, 30)))
            d["dispatch_rate"] = max(40, round(d["dispatch_rate"] * rng.uniform(0.88, 1.12)))
        for t in inst["trucks"]:
            t["capacity"] = max(1400, t["capacity"] + rng.choice((-100, 0, 100)))
        instances.append(inst)
    return instances


def dist(a, b):
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def travel_min(a, b, speed):
    return dist(a, b) / speed


def simulate(net, policy):
    """Play `policy` over one shift. Returns a result dict with parcels sorted
    and per-depot linehaul flows for the UI.

    Raises ValueError on an invalid assignment.
    """
    shift = net["shift_minutes"]
    depots = {d["id"]: d for d in net["depots"]}
    hubs = {h["id"]: h for h in net.get("hubs", [net["hub"]])}
    main_hub = net["hub"]

    # DCs and the hubs serve trucks one at a time, in dispatch order: an
    # assignment books the resource from the truck's arrival, so the
    # busy-until clocks below are the congestion signal policies dispatch on.
    depot_free = {d: 0.0 for d in depots}         # DC dock booked-until
    hub_free = {h: 0.0 for h in hubs}             # hub dock booked-until
    hub_busy = {h: 0.0 for h in hubs}             # unloading minutes (capped at shift)
    sorted_parcels = 0.0
    flows = {}                                    # (depot, hub) -> [runs, parcels]
    schedule = {t["id"]: [] for t in net["trucks"]}  # per-truck (t0, t1, type, at)
    assignments = 0
    runs = 0
    # trucks start the shift parked at the main hub
    trucks = [dict(t, x=main_hub["x"], y=main_hub["y"]) for t in net["trucks"]]

    # event heap: (time, seq, truck_index); each event = "truck needs a job"
    seq = 0
    events = [(0.0, i, i) for i in range(len(trucks))]
    heapq.heapify(events)
    seq = len(trucks)

    while events:
        now, _, ti = heapq.heappop(events)
        if now >= shift:
            continue
        truck = trucks[ti]

        state = {
            "now": now,
            "depot_free": dict(depot_free),
            "hub_free": min(hub_free.values()),   # earliest-free hub (scalar, for compat)
            "hub_free_by_id": dict(hub_free),
            "parcels_sorted": sorted_parcels,
        }
        job = policy({"id": truck["id"], "capacity": truck["capacity"],
                      "x": truck["x"], "y": truck["y"]},
                     net, state)
        assignments += 1
        if assignments > MAX_ASSIGNMENTS:
            raise ValueError("policy exceeded assignment limit")
        if not isinstance(job, dict) or "depot" not in job:
            raise ValueError(f"bad assignment {job!r}")
        dep_id = job["depot"]
        if dep_id not in depots:
            raise ValueError(f"unknown depot {dep_id!r}")

        dep = depots[dep_id]

        # travel empty -> queue at DC -> load
        arrive = now + travel_min(truck, dep, net["speed_empty"])
        start_load = max(arrive, depot_free[dep_id])
        load_min = truck["capacity"] / dep["dispatch_rate"]
        loaded_at = start_load + load_min
        depot_free[dep_id] = loaded_at

        segs = schedule[truck["id"]]
        segs.append((now, arrive, "travel_empty", dep_id))
        if start_load > arrive:
            segs.append((arrive, start_load, "wait", dep_id))
        segs.append((start_load, loaded_at, "load", dep_id))

        # travel loaded to a hub -> queue -> unload; the truck tips at
        # whichever hub gets it unloaded soonest (arrival + dock queue),
        # ties broken by hub id for determinism
        def _unload_start(hid):
            arr = loaded_at + travel_min(dep, hubs[hid], net["speed_loaded"])
            return max(arr, hub_free[hid])
        hub_id = min(sorted(hubs), key=_unload_start)
        hub = hubs[hub_id]
        arrive_hub = loaded_at + travel_min(dep, hub, net["speed_loaded"])
        start_unload = max(arrive_hub, hub_free[hub_id])
        unload_min = truck["capacity"] / hub["sort_rate"]
        done = start_unload + unload_min
        hub_free[hub_id] = done
        if start_unload < shift:
            usable = min(done, shift) - start_unload
            hub_busy[hub_id] += usable
            sorted_parcels += usable * hub["sort_rate"]
        truck["x"], truck["y"] = hub["x"], hub["y"]
        segs.append((loaded_at, arrive_hub, "travel_loaded", hub_id))
        if start_unload > arrive_hub:
            segs.append((arrive_hub, start_unload, "wait", hub_id))
        segs.append((start_unload, done, "unload", hub_id))

        if done <= shift:
            runs += 1
            f = flows.setdefault((dep_id, hub_id), [0, 0.0])
            f[0] += 1
            f[1] += truck["capacity"]
        if done < shift:
            heapq.heappush(events, (done, seq, ti))
            seq += 1

    return {
        "parcels": round(sorted_parcels, 1),
        "runs": runs,
        "hub_utilisation": round(sum(hub_busy.values()) / (shift * len(hubs)), 3),
        "hub_utilisation_by_id": {h: round(b / shift, 3)
                                  for h, b in sorted(hub_busy.items())},
        "flows": [{"depot": k[0], "dest": k[1], "runs": v[0],
                   "parcels": round(v[1], 1)}
                  for k, v in sorted(flows.items())],
        "schedule": [{"truck": t["id"],
                      "segments": [{"t0": round(a, 1), "t1": round(b, 1),
                                    "type": ty, "at": at}
                                   for a, b, ty, at in schedule[t["id"]]
                                   if a < shift]}
                     for t in net["trucks"]],
    }


class _Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise _Timeout()


def evaluate(program_source: str) -> dict:
    """Evaluator entry point for AlphaEvolve: source in, metrics out."""
    old = signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(TIMEOUT_SECS)
    try:
        ns = {}
        exec(program_source, ns)  # trusted demo context
        totals = []
        for inst in load_instances():
            policy = ns["solve"](copy.deepcopy(inst))
            totals.append(simulate(inst, policy)["parcels"])
        return {"parcels_per_shift": sum(totals) / len(totals)}
    except _Timeout:
        return {"parcels_per_shift": FAIL_SCORE,
                "insight": f"candidate exceeded {TIMEOUT_SECS}s time limit"}
    except Exception as e:
        return {"parcels_per_shift": FAIL_SCORE,
                "insight": f"candidate failed: {type(e).__name__}: {e}"}
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def _self_test():
    src = (Path(__file__).parent / "program.py").read_text()
    r1 = evaluate(src)
    r2 = evaluate(src)
    assert r1 == r2, "evaluator is not deterministic"
    assert r1["parcels_per_shift"] > FAIL_SCORE, f"baseline invalid: {r1}"
    primary = load_instances()[0]
    ns = {}
    exec(src, ns)
    res = simulate(primary, ns["solve"](copy.deepcopy(primary)))
    print(f"baseline OK: {res['parcels']:,.0f} parcels sorted on primary "
          f"network ({res['runs']} runs, sorter {res['hub_utilisation']:.0%} "
          f"busy), score {r1['parcels_per_shift']:.1f}")
    # sanity: a broken candidate must be rejected
    bad = evaluate(src.replace('{"depot": d["id"]}', '{"depot": "LUNCH-ROOM"}'))
    assert bad["parcels_per_shift"] == FAIL_SCORE, "validity gate failed"
    print("validity gate OK (broken candidate rejected)")


if __name__ == "__main__":
    _self_test()
