/* Browser port of experiment/evaluate.py's discrete-event shift simulator.
 *
 * It is deliberately a line-for-line port: same event order, same tie-breaks,
 * same rounding, so a policy scored here gets exactly the number AlphaEvolve
 * saw. scripts/check_scheduling_sim.mjs asserts that against the recorded
 * trace (baseline and best-evolved) on every run.
 *
 * On top of the evaluator's output it records the telemetry the explainer UI
 * needs: the decision list, per-DC queueing, and where fleet time went.
 */

export const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
export const travelMin = (a, b, speed) => dist(a, b) / speed;

/* ---------- min-heap on (time, seq), matching Python's heapq tuple order ---------- */
const before = (a, b) => (a[0] - b[0]) || (a[1] - b[1]);
function heapPush(h, v) {
  h.push(v);
  for (let i = h.length - 1; i > 0;) {
    const p = (i - 1) >> 1;
    if (before(h[i], h[p]) >= 0) break;
    [h[i], h[p]] = [h[p], h[i]]; i = p;
  }
}
function heapPop(h) {
  const top = h[0], last = h.pop();
  if (h.length) {
    h[0] = last;
    for (let i = 0;;) {
      const l = 2 * i + 1, r = l + 1;
      let m = i;
      if (l < h.length && before(h[l], h[m]) < 0) m = l;
      if (r < h.length && before(h[r], h[m]) < 0) m = r;
      if (m === i) break;
      [h[i], h[m]] = [h[m], h[i]]; i = m;
    }
  }
  return top;
}

export const SEG_TYPES = ["travel_empty", "wait", "load", "travel_loaded", "unload"];
const MAX_ASSIGNMENTS = 20000;

/** Play `policy` over one shift on `net`. Throws on an invalid assignment. */
export function simulate(net, policy) {
  const shift = net.shift_minutes;
  const depots = Object.fromEntries(net.depots.map(d => [d.id, d]));
  const hubList = net.hubs || [net.hub];
  const hubs = Object.fromEntries(hubList.map(h => [h.id, h]));
  const hubIds = Object.keys(hubs).sort();
  const mainHub = net.hub;

  const depotFree = {}, hubFree = {}, hubBusy = {};
  for (const d of net.depots) depotFree[d.id] = 0;
  for (const h of hubIds) { hubFree[h] = 0; hubBusy[h] = 0; }

  let sortedParcels = 0, runs = 0, assignments = 0;
  const flows = new Map();
  const cycles = Object.fromEntries(net.trucks.map(t => [t.id, []]));
  const dcStats = Object.fromEntries(net.depots.map(
    d => [d.id, {runs: 0, load: 0, queue: 0, parcels: 0}]));
  const hubStats = Object.fromEntries(hubIds.map(
    h => [h, {runs: 0, unload: 0, queue: 0, parcels: 0}]));
  const split = Object.fromEntries(SEG_TYPES.map(t => [t, 0]));

  /* clip a span to the shift window — the evaluator only counts what fits */
  const bank = (bucket, t0, t1) => {
    const v = Math.min(t1, shift) - Math.min(t0, shift);
    if (v > 0) split[bucket] += v;
    return Math.max(0, v);
  };

  const trucks = net.trucks.map(t => ({...t, x: mainHub.x, y: mainHub.y}));
  const events = [];
  trucks.forEach((_, i) => heapPush(events, [0, i, i]));
  let seq = trucks.length;

  while (events.length) {
    const [now, , ti] = heapPop(events);
    if (now >= shift) continue;
    const truck = trucks[ti];

    const state = {
      now,
      depot_free: {...depotFree},
      hub_free: Math.min(...Object.values(hubFree)),
      hub_free_by_id: {...hubFree},
      parcels_sorted: sortedParcels,
    };
    const job = policy({id: truck.id, capacity: truck.capacity, x: truck.x, y: truck.y},
                       net, state);
    if (++assignments > MAX_ASSIGNMENTS) throw new Error("policy exceeded assignment limit");
    if (!job || typeof job !== "object" || !("depot" in job))
      throw new Error(`bad assignment ${JSON.stringify(job)}`);
    const depId = job.depot;
    if (!(depId in depots)) throw new Error(`unknown depot ${JSON.stringify(depId)}`);
    const dep = depots[depId];

    /* travel empty -> queue at the DC dock -> load */
    const arrive = now + travelMin(truck, dep, net.speed_empty);
    const startLoad = Math.max(arrive, depotFree[depId]);
    const loadMin = truck.capacity / dep.dispatch_rate;
    const loadedAt = startLoad + loadMin;
    depotFree[depId] = loadedAt;

    const segs = [{t0: now, t1: arrive, type: "travel_empty", at: depId}];
    if (startLoad > arrive) segs.push({t0: arrive, t1: startLoad, type: "wait", at: depId});
    segs.push({t0: startLoad, t1: loadedAt, type: "load", at: depId});

    /* tip at whichever hub gets this truck unloaded soonest; ties by hub id */
    let hubId = null, bestStart = Infinity;
    for (const hid of hubIds) {
      const s = Math.max(loadedAt + travelMin(dep, hubs[hid], net.speed_loaded), hubFree[hid]);
      if (s < bestStart) { bestStart = s; hubId = hid; }
    }
    const hub = hubs[hubId];
    const arriveHub = loadedAt + travelMin(dep, hub, net.speed_loaded);
    const startUnload = Math.max(arriveHub, hubFree[hubId]);
    const unloadMin = truck.capacity / hub.sort_rate;
    const done = startUnload + unloadMin;
    hubFree[hubId] = done;
    if (startUnload < shift) {
      const usable = Math.min(done, shift) - startUnload;
      hubBusy[hubId] += usable;
      sortedParcels += usable * hub.sort_rate;
    }
    truck.x = hub.x; truck.y = hub.y;
    segs.push({t0: loadedAt, t1: arriveHub, type: "travel_loaded", at: hubId});
    if (startUnload > arriveHub) segs.push({t0: arriveHub, t1: startUnload, type: "wait", at: hubId});
    segs.push({t0: startUnload, t1: done, type: "unload", at: hubId});

    /* telemetry */
    bank("travel_empty", now, arrive);
    const dcQueue = bank("wait", arrive, startLoad);
    bank("load", startLoad, loadedAt);
    bank("travel_loaded", loadedAt, arriveHub);
    const hubQueue = bank("wait", arriveHub, startUnload);
    bank("unload", startUnload, done);
    const ds = dcStats[depId];
    ds.runs += 1; ds.queue += dcQueue;
    ds.load += Math.min(loadedAt, shift) - Math.min(startLoad, shift);
    ds.parcels += truck.capacity;
    const hs = hubStats[hubId];
    hs.runs += 1; hs.queue += hubQueue;
    hs.unload += Math.min(done, shift) - Math.min(startUnload, shift);

    cycles[truck.id].push({
      depot: depId, hub: hubId, t0: now, t1: done, segs,
      driveEmpty: arrive - now, queueDC: startLoad - arrive, load: loadMin,
      driveLoaded: arriveHub - loadedAt, queueHub: startUnload - arriveHub,
      unload: unloadMin, parcels: truck.capacity,
      complete: done <= shift,
    });

    if (done <= shift) {
      runs += 1;
      const k = depId + "|" + hubId;
      const f = flows.get(k) || {depot: depId, dest: hubId, runs: 0, parcels: 0};
      f.runs += 1; f.parcels += truck.capacity;
      flows.set(k, f);
      hubStats[hubId].parcels += truck.capacity;
    }
    if (done < shift) heapPush(events, [done, seq++, ti]);
  }

  const fleetMinutes = shift * net.trucks.length;
  return {
    parcels: Math.round(sortedParcels * 10) / 10,   // evaluate.py rounds here too
    runs,
    decisions: assignments,
    hub_utilisation: Math.round(sum(Object.values(hubBusy)) / (shift * hubIds.length) * 1000) / 1000,
    hub_utilisation_by_id: Object.fromEntries(
      hubIds.map(h => [h, Math.round(hubBusy[h] / shift * 1000) / 1000])),
    flows: [...flows.values()].sort((a, b) => (a.depot + a.dest).localeCompare(b.depot + b.dest)),
    schedule: net.trucks.map(t => ({
      truck: t.id,
      cycles: cycles[t.id],
      segments: cycles[t.id].flatMap(c => c.segs).filter(s => s.t0 < shift),
    })),
    dcStats, hubStats, split, fleetMinutes,
  };
}

const sum = xs => xs.reduce((a, b) => a + b, 0);

/** Score a policy the way evaluate.py does: mean parcels over all instances. */
export function scoreAll(instances, factory) {
  const per = instances.map(net => simulate(net, factory(net)));
  return {per, mean: sum(per.map(r => r.parcels)) / per.length};
}

/* ------------------------------------------------------------------ *
 * Policies. Each is one answer to the only question the dispatcher is
 * ever asked: this truck is free — which DC does it load at next?
 * ------------------------------------------------------------------ */

const byHubDistance = net => [...net.depots].sort((a, b) => dist(net.hub, a) - dist(net.hub, b));

/** pick the depot maximising `score`; first-wins ties, like Python's max() */
function pick(net, score) {
  let best = null, bestS = null;
  for (const d of net.depots) {
    const s = score(d);
    if (bestS === null || s > bestS) { best = d; bestS = s; }
  }
  return {depot: best.id};
}

/** Full-cycle forecast for sending `truck` to depot `d` right now. */
export function forecast(truck, d, net, state) {
  const hubList = net.hubs || [net.hub];
  const now = state.now;
  const drive = travelMin(truck, d, net.speed_empty);
  const arrive = now + drive;
  const wait = Math.max(0, state.depot_free[d.id] - arrive);
  const load = truck.capacity / d.dispatch_rate;
  const loadedAt = arrive + wait + load;
  let eta = null, hubQueue = null, hub = null, driveLoaded = null, unload = null;
  for (const h of hubList) {
    const dl = travelMin(d, h, net.speed_loaded);
    const atHub = loadedAt + dl;
    const startSort = Math.max(atHub, state.hub_free_by_id[h.id]);
    const done = startSort + truck.capacity / h.sort_rate;
    if (eta === null || done < eta) {
      eta = done; hubQueue = startSort - atHub; hub = h;
      driveLoaded = dl; unload = truck.capacity / h.sort_rate;
    }
  }
  const cycle = eta - now;
  return {drive, wait, load, driveLoaded, hubQueue, unload, eta, cycle, hub,
          rate: truck.capacity / cycle};
}

export const POLICIES = [
  {
    id: "pileup",
    label: "Everyone to the nearest DC",
    short: "All to the nearest DC",
    tag: "pathological",
    blurb: "Send every truck to the DC closest to the main hub. Perfectly consistent, and the whole fleet spends the day in one queue.",
    code: `def assign_truck(truck, net, state):
    # the DC closest to the main hub — always
    closest = min(net["depots"], key=lambda d: dist(net["hub"], d))
    return {"depot": closest["id"]}`,
    make: net => { const d = byHubDistance(net)[0]; return () => ({depot: d.id}); },
  },
  {
    id: "baseline",
    label: "Fixed roster (the seed program)",
    short: "Fixed roster (seed)",
    tag: "baseline",
    blurb: "Pair truck 1 with the nearest DC, truck 2 with the next nearest, and so on. Every truck shuttles its own DC all day. This is the program we hand AlphaEvolve.",
    code: `def assign_truck(truck, net, state):
    # fixed greedy pairing: one truck per DC, for the whole shift
    order = sorted(net["depots"], key=lambda d: dist(net["hub"], d))
    fleet = [t["id"] for t in net["trucks"]]
    d = order[fleet.index(truck["id"]) % len(order)]
    return {"depot": d["id"]}`,
    make: net => {
      const order = byHubDistance(net), fleet = net.trucks.map(t => t.id);
      return truck => ({depot: order[fleet.indexOf(truck.id) % order.length].id});
    },
  },
  {
    id: "roundrobin",
    label: "Fair rotation",
    short: "Fair rotation",
    tag: "fair",
    blurb: "Hand out the DCs in a cycle so every site gets served in turn. Fairer than the roster and slightly better — but it still sends trucks to a dock it never checks.",
    code: `def assign_truck(truck, net, state):
    # take the next DC in the rotation, whoever is asking
    d = net["depots"][assign_truck.i % len(net["depots"])]
    assign_truck.i += 1
    return {"depot": d["id"]}`,
    make: net => { let i = 0; return () => ({depot: net.depots[i++ % net.depots.length].id}); },
  },
  {
    id: "nearest",
    label: "Nearest DC to me",
    short: "Nearest DC to me",
    tag: "myopic",
    blurb: "Classic greedy: drive to whatever DC is closest right now. Minimises the one number you can see — and ignores the dock queue you are about to join.",
    code: `def assign_truck(truck, net, state):
    # shortest empty leg, nothing else
    d = min(net["depots"], key=lambda d: dist(truck, d))
    return {"depot": d["id"]}`,
    make: net => truck => pick(net, d => -dist(truck, d)),
  },
  {
    id: "fastest",
    label: "Fastest belt",
    short: "Fastest belt",
    tag: "myopic",
    blurb: "Always load at an automated DC, because loading there takes minutes instead of hours. Four DCs never see a truck and three docks jam.",
    code: `def assign_truck(truck, net, state):
    # the quickest belt in the network, wherever it is
    d = max(net["depots"], key=lambda d: d["dispatch_rate"])
    return {"depot": d["id"]}`,
    make: net => () => pick(net, d => d.dispatch_rate),
  },
  {
    id: "freedock",
    label: "Whichever dock frees first",
    short: "Earliest free dock",
    tag: "reactive",
    blurb: "Look at the dock clocks and go where loading can start soonest. Reacts to congestion, but is blind to how long the load itself takes and to the sorters.",
    code: `def assign_truck(truck, net, state):
    # earliest possible start of loading
    def start(d):
        arrive = state["now"] + travel_min(truck, d, net["speed_empty"])
        return max(arrive, state["depot_free"][d["id"]])
    return {"depot": min(net["depots"], key=start)["id"]}`,
    make: net => (truck, _net, state) => pick(net, d => -Math.max(
      state.now + travelMin(truck, d, net.speed_empty), state.depot_free[d.id])),
  },
  {
    id: "evolved",
    label: "AlphaEvolve's dispatcher",
    short: "AlphaEvolve #26",
    tag: "evolved",
    blurb: "Forecast the entire cycle — drive, dock queue, load, run to the sooner-free sorter, sorter queue, unload — for all 7 DCs, price congestion, take the best parcels-per-minute.",
    code: `def assign_truck(truck, net, state):
    """Evolved dispatcher: score every DC on expected parcels-per-minute of the
    full forecast cycle, with congestion shadow prices on dock and sorter
    queues and dual-hub balancing."""
    hubs = net.get("hubs", [net["hub"]])
    now = state["now"]
    best, best_s = None, None
    for d in net["depots"]:
        arrive = now + travel_min(truck, d, net["speed_empty"])
        wait = max(0.0, state["depot_free"][d["id"]] - arrive)
        load = truck["capacity"] / d["dispatch_rate"]
        loaded_at = arrive + wait + load
        eta, hub_queue = None, None
        for h in hubs:
            at_hub = loaded_at + travel_min(d, h, net["speed_loaded"])
            start_sort = max(at_hub, state["hub_free_by_id"][h["id"]])
            done = start_sort + truck["capacity"] / h["sort_rate"]
            if eta is None or done < eta:
                eta, hub_queue = done, start_sort - at_hub
        effective = eta - now + 3.0 * wait + 1.2 * hub_queue
        score = truck["capacity"] / effective
        if best_s is None or score > best_s:
            best, best_s = d, score
    return {"depot": best["id"]}`,
    make: net => weighted(net, 3.0, 1.2, false),
  },
];

/** The evolved policy's shape, with its two shadow prices exposed. */
export function weighted(net, wq, wh, myopic) {
  return (truck, _net, state) => pick(net, d => {
    const f = forecast(truck, d, net, state);
    if (myopic) return truck.capacity / (f.drive + f.load + f.driveLoaded + f.unload);
    return truck.capacity / (f.cycle + wq * f.wait + wh * f.hubQueue);
  });
}

export const CUSTOM = {
  id: "custom",
  label: "Your dispatcher",
  short: "Your dispatcher",
  tag: "yours",
  blurb: "The evolved policy's shape with its two congestion shadow prices exposed. Turn them up and the fleet spreads out; turn them to zero and it chases whatever looks fastest.",
  make: (net, o) => weighted(net, o.wq, o.wh, o.myopic),
};

/* ------------------------------------------------------------------ *
 * A genome. The evolved dispatcher's shape with every term of the
 * forecast cycle priced separately, so a search can be run over the
 * numbers. `load` is pinned at 1.0 as the yardstick — multiplying all
 * six weights by the same constant leaves the ranking unchanged, so
 * only five are actually free.
 * ------------------------------------------------------------------ */
export const GENES = [
  {key: "drive",       label: "empty drive",  short: "drive"},
  {key: "driveLoaded", label: "loaded haul",  short: "haul"},
  {key: "unload",      label: "unload",       short: "tip"},
  {key: "wait",        label: "DC queue",     short: "dockQ"},
  {key: "hubQueue",    label: "sorter queue", short: "sortQ"},
];
export const GENE_MAX = 6;

/** Candidate #26 written in this genome: `cycle` already contains one unit of
 *  each term, so its 3.0×/1.2× shadow prices land at 4.0 and 2.2 here. */
export const EVOLVED_GENOME = [1, 1, 1, 4.0, 2.2];

export function genomePolicy(net, g) {
  const [wd, wl, wu, wq, wh] = g;
  return (truck, _net, state) => pick(net, d => {
    const f = forecast(truck, d, net, state);
    return truck.capacity /
      (wd * f.drive + f.load + wl * f.driveLoaded + wu * f.unload + wq * f.wait + wh * f.hubQueue);
  });
}

export const genomeCode = g => `def assign_truck(truck, net, state):
    # the template a human wrote. The search only picks the five numbers.
    def cost(d):
        f = forecast(truck, d, net, state)     # drive, load, haul, tip, queues
        return (${g[0].toFixed(2)} * f.drive        + 1.00 * f.load
                + ${g[1].toFixed(2)} * f.drive_loaded + ${g[2].toFixed(2)} * f.unload
                + ${g[3].toFixed(2)} * f.wait         + ${g[4].toFixed(2)} * f.hub_queue)
    best = max(net["depots"], key=lambda d: truck["capacity"] / cost(d))
    return {"depot": best["id"]}`;

export const customCode = o => o.myopic
  ? `def assign_truck(truck, net, state):
    # myopic: cost the cycle as if no queue existed anywhere
    def rate(d):
        cycle = (travel_min(truck, d, net["speed_empty"])
                 + truck["capacity"] / d["dispatch_rate"]
                 + travel_min(d, net["hub"], net["speed_loaded"])
                 + truck["capacity"] / net["hub"]["sort_rate"])
        return truck["capacity"] / cycle
    return {"depot": max(net["depots"], key=rate)["id"]}`
  : `def assign_truck(truck, net, state):
    # full-cycle forecast, dock queue priced at ${o.wq.toFixed(1)}x, sorter queue at ${o.wh.toFixed(1)}x
    ...
        effective = eta - now + ${o.wq.toFixed(1)} * wait + ${o.wh.toFixed(1)} * hub_queue
        score = truck["capacity"] / effective
    ...`;
