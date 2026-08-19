# Metro Parcel Network × AlphaEvolve — Demo

A very simple, self-contained demo showing how **Google AlphaEvolve** (the
evolutionary coding agent on Gemini Enterprise, GA July 2026) improves a
baseline parcel linehaul dispatch algorithm.

**The story in one line:** we gave AlphaEvolve a naive linehaul roster for a
fictional metro parcel network (7 delivery centres, 2 sorting
hubs, 7 trucks) and a local shift simulator that scores parcels through the
sorters — the dispatch policy then evolves over 30 candidate programs from
a rigid one-truck-per-DC roster into a full-cycle forecasting dispatcher
that lifts parcels sorted per shift by +50%.

## Run the demo (no cloud access needed)

```bash
./serve.sh            # then open http://localhost:8000/ui/
```

Press **▶ Play evolution**. The UI replays the recorded experiment: every dot
on the chart is one candidate dispatch program; whenever a candidate beats the
best so far, the linehaul flows on the network map switch to the new plan and
the parcel counters climb. Toggle **Baseline dispatch / Evolved dispatch** to
compare, and expand *"Optimised dispatcher"* to see the actual code AlphaEvolve
evolved (baseline policy vs best evolved policy).

Everything is static files — no network calls at demo time.

## The problem

One 12-hour parcel intake day. 7 linehaul trucks carry ~1,600–1,900 parcels
per load between 7 delivery centres and 2 parcel sorting facilities (the
big Kurrajong hub in the east, the smaller Telopea sorter in the west).
Whenever a truck finishes unloading, the dispatch policy answers one
question: **which delivery centre (DC) should it load at next?** DCs
belt-load one truck at a time and each hub unloads one truck at a time, so
queueing is everything; loaded trucks tip at whichever hub gets them
unloaded soonest. DCs differ enormously: three are fast automated sites,
four are older manual-load DCs with painfully slow belts.

The naive baseline is a fixed greedy roster: walk the fleet and pair each
truck with the nearest still-unclaimed DC, one truck per DC, for the whole
shift. It looks tidy — every DC is covered — but trucks rostered to the
slow manual DCs spend most of the day parked at a dock while the fast belts
sit under-used. The evolved dispatcher forecasts the full cycle for every
DC on every dispatch (travel + dock queue + load + run to the sooner-free
sorter), shadow-prices congestion, and balances both hubs — rotating each
truck across ~5 DCs over the shift instead of pinning it to one.

## What's in here

| Path | Purpose |
|---|---|
| `data/network.json` | Fictional metro parcel network: DCs, 2 sorting hubs, truck fleet (`data/make_network.py` regenerates it) |
| `experiment/program.py` | Seed program; only the code between `# EVOLVE-BLOCK-START/END` may be mutated |
| `experiment/evaluate.py` | Deterministic local evaluator: discrete-event shift simulator + validity gate, scored over 3 network variants. `python3 experiment/evaluate.py` self-tests |
| `experiment/instructions.md` | Problem description sent to AlphaEvolve |
| `experiment/run_evolution.py` | Drives the real experiment via the official client; records every candidate; writes `traces/evolution_trace.json` |
| `experiment/.env` | Project / engine / model / run-size settings |
| `scripts/setup_engine.sh` | One-time provisioning of the Discovery Engine engine + `default_assistant` |
| `scripts/build_demo_trace.py` | Builds the curated hill-climb trace the UI replays (see note below) |
| `scripts/simulate_trace.py` | Fallback trace generator (same schema, honestly labelled `simulated-fallback`; UI shows a badge) |
| `traces/evolution_trace.json` | The trace the UI replays |
| `ui/index.html` | The whole UI — single file, SVG network map + evolution chart |
| `vendor/alphaevolve/` | Clone of `github.com/Google-Cloud-AI/alphaevolve-on-googlecloud` (official Python client + examples) |

## How the AlphaEvolve loop works (what the demo re-tells)

1. **Seed program** — a working baseline (greedy one-truck-per-DC roster)
   with the policy inside an EVOLVE block.
2. **Generate** — AlphaEvolve's managed backend (Gemini model ensemble +
   program database) proposes mutated candidate programs.
3. **Evaluate locally** — our client loop (`run_controller_loop`) pulls
   candidates, runs `evaluate.py` *on our machine*, and submits scores back.
4. **Evolve** — high scorers seed the next generation; parcel throughput
   climbs.

## Reproduce the real run

```bash
scripts/setup_engine.sh          # one-time engine + assistant provisioning
python experiment/run_evolution.py
```

If cloud access is blocked, `python scripts/simulate_trace.py` regenerates a
fallback trace from a ladder of hand-written policies scored by the same
evaluator (the UI badges it as simulated).

**Note on the shipped trace:** for demo pacing, the replayed run is an
illustrative reconstruction built by `scripts/build_demo_trace.py` — the
candidate ordering and filler scores are curated into a smooth hill-climb.
The substance is real: every new-best plan is an actual dispatch policy
played through the simulator (the map animates its genuine schedule), and
the baseline and final scores are unmodified evaluator results, so the
headline improvement is a real evaluator outcome.

All data is fictional; no real facility, fleet, or production figures are
used. "Metro Parcel Network" is an invented operator, not a real carrier.
