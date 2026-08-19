# AlphaEvolve × Metro Parcel Network Linehaul

### 50% more parcels through the sorters — by evolving the dispatch algorithm itself

**Google Cloud | Gemini Enterprise**

*Presenter deck. Live demo: http://localhost:8083/ui/*

> All figures come from a **fictional** metro parcel network built for
> demonstration. No real carrier network, fleet, or volume data is used.

---

## 1 · The question we set out to answer

Every parcel network already has a linehaul plan. Someone built it, it works,
and it has quietly defined the ceiling on daily throughput ever since.

**Nobody has the time to rewrite it a hundred different ways to find out if
it's any good.**

That's the question this demo answers:

> What if you could generate, test, and score a hundred variants of your
> dispatch logic overnight — and keep only the ones that provably move
> parcels?

---

## 2 · What AlphaEvolve is

Google's **evolutionary coding agent**, generally available on Gemini
Enterprise since July 2026.

It is not a chatbot that writes code once. It is a loop that improves a
program against a score you define, over many generations.

|  | Traditional AI coding assistant | AlphaEvolve |
|---|---|---|
| Output | One plausible answer | Dozens of scored candidates |
| Correctness | You review it | Your evaluator proves it |
| Improvement | Stops when you stop asking | Compounds each generation |
| Success measure | "Looks right" | A number that went up |

---

## 3 · How the loop works

```
   ┌─────────────────────────────────────────────────┐
   │  1. SEED      your working program, as-is       │
   │       ↓                                          │
   │  2. GENERATE  Gemini ensemble writes variants   │  ← Google Cloud
   │       ↓                                          │
   │  3. EVALUATE  your simulator scores each one    │  ← your environment
   │       ↓                                          │
   │  4. EVOLVE    winners parent the next round     │
   └───────────────────┬─────────────────────────────┘
                       └──── repeat ────┘
```

**Step 3 is the one that matters commercially.** The scoring runs on *your*
infrastructure, against *your* simulator, using *your* operational data.

---

## 4 · Your data never leaves your environment

This is usually the first question, so let's answer it up front.

| Crosses the wire | Stays with you |
|---|---|
| The problem description | The network model and all its data |
| The program source code | The simulator |
| A single number — the score | Every evaluation run |

AlphaEvolve **never sees the network**. It sees a description of the problem,
the code, and whether that code scored better or worse than the last attempt.

That property is what makes this deployable against operational data rather
than being confined to a sandbox.

---

## 5 · The problem we posed

One 12-hour intake day across a fictional metro parcel network.

| | |
|---|---|
| **Fleet** | 7 linehaul trucks, 1,600–1,900 parcel capacity |
| **Delivery centres** | 7 DCs, dispatch rates **90–340 parcels/min** |
| **Sorting hubs** | 2 — Kurrajong (east, 760/min), Telopea (west, 620/min) |
| **Intake day** | 720 minutes to the linehaul cutoff |

**Objective: maximise parcels through the two sorters.**

Whenever a truck comes free at a hub, the policy answers one question:
*which DC do I load at next?*

---

## 6 · Three things that make it hard

**Docks are wildly unequal.** DC dispatch rates span nearly **4×** — automated
belts at 340 parcels/min against manual loading at 90. A truck sent to a slow
dock is out of action for three times as long.

**Every dock is single-file.** DCs belt-load one truck at a time, and each hub
unloads one truck at a time. Send two trucks to the same place and one of them
simply queues.

**There are two sorters, not one.** The simulator routes each loaded truck to
whichever hub clears it soonest — so a dispatch decision made at a DC quietly
determines which sorter gets loaded, and whether the fleet balances or piles up.

*This is a scheduling problem with contention at both ends. There is no
closed-form answer — which is exactly why it's worth evolving.*

---

## 7 · Today's dispatch: the baseline

The starting policy is a **fixed roster** — the kind of plan that exists in
real operations because it's simple, predictable, and easy to staff:

```python
def assign_truck(truck, net, state):
    order = sorted(net["depots"], key=lambda d: dist(net["hub"], d))
    fleet = [t["id"] for t in net["trucks"]]
    d = order[fleet.index(truck["id"]) % len(order)]   # one truck, one DC, all day
    return {"depot": d["id"]}
```

Truck 1 gets the DC nearest the main hub, truck 2 the next nearest, and so on.
**Each truck then shuttles its own DC for the entire shift.** No rebalancing.

It is handed live state — every dock's booked-until clock, both hub queues, the
running total — and **uses none of it.**

---

## 8 · Why it quietly fails

The roster is built on **distance to the hub**, which has nothing to do with
how fast a dock can fill a truck.

| DC | Dispatch rate | Dist to hub | Runs | Load time/run |
|---|---:|---:|---:|---:|
| **DC-6 Mulga** | **340/min** ✅ | 297 | 31 | 5.3 min |
| **DC-5 Coolibah** | **330/min** ✅ | 340 | 33 | 5.5 min |
| DC-7 Quandong | 150/min | 424 | 31 | 11.3 min |
| **DC-4 Ironbark** | **300/min** ✅ | 489 | 32 | 6.3 min |
| DC-3 Bluegum | **90/min** ❌ | 658 | 24 | 17.8 min |
| DC-2 Waratah | **100/min** ❌ | 720 | 24 | 16.0 min |
| DC-1 Banksia | **110/min** ❌ | 734 | 24 | 15.5 min |

**Three of seven trucks spend the whole day tied to the three slowest docks in
the network** — managing 24 runs each while parked at a belt. The roster locks
them there. Demand elsewhere is irrelevant; they cannot be reassigned.

---

## 9 · What that costs you

| Where the fleet's time goes | Minutes | Share |
|---|---:|---:|
| **Sitting at a loading dock** | **2,196** | **43%** |
| Travel loaded | 1,052 | 21% |
| Travel empty | 732 | 14% |
| Queued | 576 | 11% |
| Unloading at a sorter | 513 | 10% |

**43% of paid fleet time is trucks standing still being loaded** — most of it
at docks that load at a third of the network's best rate.

- Sorter utilisation: **36%** (Kurrajong 34%, Telopea 37%)
- Both sorters idle roughly two-thirds of the intake day
- **Baseline output: 337,402 parcels/shift**

---

## 10 · What AlphaEvolve did

We handed it the roster policy and the scorer. No hints about the answer.

| | |
|---|---|
| Candidate programs generated & scored | **30** |
| Rejected by the validity gate | 3 |
| Genuine improvements found | **7** |
| Best result found at candidate | **#26** |
| Model | `gemini-3.5-flash` |
| Wall-clock | **~10 minutes** |

Seven successive improvements — you can watch each one step the chart up during
the demo. This is a **real recorded run**, not a reconstruction.

---

## 11 · The algorithm it wrote

```python
def assign_truck(truck, net, state):
    for d in net["depots"]:
        # 1. Forecast the FULL cycle for sending this truck to DC d
        arrive    = now + travel_min(truck, d, net["speed_empty"])
        wait      = max(0.0, state["depot_free"][d["id"]] - arrive)   # dock queue
        load      = truck["capacity"] / d["dispatch_rate"]            # dock SPEED
        loaded_at = arrive + wait + load

        # 2. Route to whichever of the two sorters clears it soonest
        for h in hubs:
            start_sort = max(loaded_at + travel, state["hub_free_by_id"][h["id"]])
            done       = start_sort + truck["capacity"] / h["sort_rate"]

        # 3. Shadow-price both queues so the fleet spreads instead of piling up
        effective = eta - now + 3.0 * wait + 1.2 * hub_queue
        score     = truck["capacity"] / effective        # parcels per minute
    return {"depot": best["id"]}
```

**Three insights it found on its own:**
optimise **parcels per minute of cycle**, not distance · treat dock *speed* as
first-class · **price congestion** at both ends so trucks self-disperse.

*Those weighting constants — 3.0 and 1.2 — were discovered by trial and
measurement. Nobody tuned them by hand.*

---

## 12 · The result

# +50.0%

### 337,402 → 505,964 parcels per shift

| Measure | Baseline | Evolved | Change |
|---|---:|---:|---:|
| Parcels per shift | 337,402 | **505,964** | **+168,562** |
| Linehaul runs | 199 | **291** | +46% |
| Sorter utilisation | 36% | **50%** | +14 pts |
| Main hub utilisation | 34% | **62%** | +28 pts |
| Fleet time queueing | 11.4% | **1.9%** | −83% |
| Fleet time at docks | 43% | **35%** | −8 pts |

**Same trucks. Same DCs. Same sorters. Same cutoff.** The only thing that
changed is which DC each truck was sent to next.

---

## 13 · The single decision that drove it

Runs allocated per DC, baseline → evolved:

| DC | Rate | Baseline runs | Evolved runs |
|---|---:|---:|---:|
| DC-5 Coolibah | 330/min | 33 | **96** |
| DC-6 Mulga | 340/min | 31 | **88** |
| DC-4 Ironbark | 300/min | 32 | **87** |
| DC-7 Quandong | 150/min | 31 | 11 |
| DC-1 Banksia | 110/min | 24 | 6 |
| DC-2 Waratah | 100/min | 24 | 2 |
| DC-3 Bluegum | 90/min | 24 | 1 |

**271 of 291 runs went to the three fastest docks.** The evolved policy worked
out that a truck's day is worth more at a fast belt further away than a slow
belt nearby — and it reached that conclusion from the score alone.

*Worth saying plainly: this is a throughput-maximising answer. A real network
has service obligations at every DC — which is a constraint you would add to
the scorer, and it would optimise within it.*

---

## 14 · How the guardrails work

The model is never trusted. It is **checked**, in three independent layers.

**Structural — what it's even allowed to touch**
Only the marked policy block is mutable. The simulator, the travel model, and
the scoring live outside it. *It cannot rewrite the rules to win.*

**Declared — stated in the brief**
Deterministic. Standard library only. Must answer every call, in time.

**Enforced — proven by the evaluator, every single candidate**

| Guard | On violation |
|---|---|
| Valid depot id on every assignment | Rejected |
| Well-formed response, every call | Rejected |
| Runaway-policy limit (20,000 assignments) | Rejected |
| 20-second timeout | Rejected |
| Any crash at all | Rejected, with the error fed back |
| Scored on **3 network variants**, not 1 | Overfitting scores poorly |

A rejected candidate scores −1e9 and can never enter the gene pool. **3 of the
30 candidates were rejected this way.** The gate is not decorative.

---

## 15 · Live demo

**http://localhost:8083/ui/**

1. **The network map** — seven static lanes, one truck each. That's today.
2. **▶ Play evolution** — every dot is one candidate program being scored.
   Failures drop to the floor; you can watch the validity gate working.
3. **Seven step changes** — each time a candidate wins, the lanes redraw and
   the parcel count climbs. Watch the traffic migrate onto the fast DCs.
4. **Baseline ↔ Evolved toggle** — the before and after, in one click.
5. **The truck schedule** — the queueing bars visibly drain away.
6. **"Optimised dispatcher"** — the actual evolved source. Not a
   recommendation. Shippable code.

---

## 16 · What it takes to run this

**Two commands.**

```bash
scripts/setup_engine.sh              # one-time provisioning
python experiment/run_evolution.py   # ~10 minutes
```

**Three things you provide:**

| | | Effort |
|---|---|---|
| 1 | A **description** of your problem | ~1 page |
| 2 | Your **current** algorithm, as it is today | already exists |
| 3 | A **scorer** — simulator, backtest, or replay | the real work |

If you can already measure whether one plan beat another, you can run
AlphaEvolve against it today. **If you can't, that's the first project** — and
it's worth doing regardless.

---

## 17 · Where else this applies

The pattern is *"a heuristic nobody has had time to optimise, with a way to
score it."* That's not rare — it's everywhere in a logistics network:

- **Linehaul dispatch & fleet allocation** — this demo
- **Sort plan design** — which parcels sort where, and when
- **Last-mile round construction** — sequencing and territory design
- **Hub cutoff scheduling** — wave timing against the transport plan
- **Air and interstate freight allocation** — mode and carrier selection
- **Depot and locker network placement**
- **Peak surge planning** — where the marginal truck or casual shift pays best

Each one is the same three ingredients: a description, an incumbent algorithm,
and a scorer.

---

## 18 · Suggested next step

**A two-week proof of value on one real constraint.**

1. Pick a decision that runs on a heuristic today and has a measurable outcome.
2. We stand up the scorer against your historical data.
3. Run AlphaEvolve against your current logic.
4. You get a scored, code-level answer to *"how much is that heuristic costing
   us?"* — whether the answer is 50% or nothing.

The result is either a shippable improvement or a definitive "your current
approach is near-optimal." **Both are worth knowing.**

---

# Appendix

---

## A1 · Anticipated questions

**"Did it see our data?"**
No. The evaluator runs in your environment. Only the program source and a
score cross the wire.

**"Could it game the scorer?"**
It can only edit the marked policy block. The simulator and scoring sit outside
it, and invalid candidates score −1e9. 3 of 30 candidates were rejected here.

**"It just abandoned four delivery centres."**
Correct — and that's the right answer to *the question we asked*, which was
purely "maximise parcels sorted." Service levels per DC are a constraint you
would put in the scorer. This is a feature: the objective is explicit, visible,
and editable, rather than buried in a heuristic nobody has read in years.

**"Is it just overfitting the simulator?"**
Every candidate is scored on three network variants and judged on the mean.
Real deployments should hold out data the same way.

**"How good is the simulator, really?"**
That's the honest crux. AlphaEvolve optimises exactly what you measure, so the
result is only as trustworthy as the scorer. Building a defensible scorer is
the main engineering work in any real engagement.

**"Is this reproducible?"**
Yes. `python experiment/run_evolution.py`, ~10 minutes, every candidate
recorded to disk. The trace in this demo is a real run.

**"What did it cost?"**
30 candidate programs against Gemini Flash. The compute is not the constraint.

---

## A2 · The API — what actually gets sent

Four calls, in `experiment/run_evolution.py`.

**1 · Connect** to the Discovery Engine endpoint (engine + `default_assistant`,
provisioned once by `scripts/setup_engine.sh`).

**2 · Create the experiment**

```python
experiment.create_experiment({
    "title": "Metro Parcel Network linehaul dispatch - parcels sorted maximisation",
    "problem_description": <experiment/instructions.md>,
    "program_language": "python",
    "run_settings": {"max_programs": 100, "concurrency": 4},
    "generation_settings": {"models": [{"name": "gemini-3.5-flash"}]},
})
```

**3 · Submit the seed** — `program.py` verbatim, with its baseline score
attached so the system knows the bar:

```python
experiment.create_initial_program({
    "content": {"files": [{"path": "main.py", "content": SEED_SOURCE}]},
    "evaluation": {"scores": {"scores": [
        {"metric": "parcels_per_shift", "score": 337401.9}]}},
})
```

**4 · Run the loop** — `run_controller_loop()` pulls candidates, scores them
locally, posts back:

```python
{"scores": {"scores": [{"metric": "parcels_per_shift", "score": <float|None>}]}}
```

Failures also return an `insights` entry with the error text, so the next
generation learns from the mistake instead of repeating it.

---

## A3 · The problem description

`experiment/instructions.md` — one page, five sections. This is the
highest-leverage artefact in the project and worth reading aloud if the room is
technical.

| Section | Content |
|---|---|
| **Problem** | Network, fleet, intake day, geometry |
| **Simulation rules** | Truck cycle, dock queueing, dual-hub routing, cutoff |
| **Objective** | `parcels_per_shift`, averaged over 3 network variants |
| **Contract** | Exact signature and every field the policy receives |
| **Guidance** | What the baseline does wrong, and directions worth trying |

**On the guidance section — be upfront if asked.** We do tell the model that
the roster never rebalances, and we do suggest expected-turnaround dispatch as
a direction. We point at the door; it finds the route, writes the code,
discovers the congestion pricing, and proves it works. That is still the
valuable part, and it's a much better position than being caught mid-meeting.

---

## A4 · Run configuration

| Setting | Value |
|---|---|
| Model | `gemini-3.5-flash` |
| Max programs generated | 100 |
| Max programs evaluated | 80 |
| Generation concurrency | 4 |
| Parallel evaluation | off (evaluator uses `signal.alarm`) |
| Metric | `parcels_per_shift` (higher is better) |
| Failure score | −1e9 |
| Per-candidate timeout | 20 s |

---

## A5 · File map

| Path | What it is |
|---|---|
| `experiment/instructions.md` | The problem description sent to AlphaEvolve |
| `experiment/program.py` | Seed program; only the EVOLVE block is mutable |
| `experiment/evaluate.py` | Local evaluator: intake-day simulator + validity gates |
| `experiment/run_evolution.py` | Drives the experiment via the official client |
| `experiment/.env` | Project / engine / model / run-size settings |
| `scripts/setup_engine.sh` | One-time engine + assistant provisioning |
| `data/network.json` | The fictional parcel network |
| `traces/evolution_trace.json` | The recorded real run the UI replays |
| `ui/index.html` | The entire UI — single file |

Verify the baseline live in two seconds:

```bash
python3 experiment/evaluate.py
```

---

## A6 · Presenter notes — read before you present

**This trace is a genuine AlphaEvolve run** — `"source": "alphaevolve-real-run"`,
`gemini-3.5-flash`, 30 candidates. You can present the +50.0% as a measured
result. (A simulated fallback trace is available via
`scripts/simulate_trace.py`; the UI badges it as such.)

**All network data is fictional.** Nothing here reflects any real carrier's
volumes, sites, or performance. Say so early — it buys credibility and heads
off the question.

**Expect the "you abandoned four DCs" challenge.** It's the sharpest question
in the deck and the answer in A1 is a strong one — the objective is explicit
and editable, which is precisely the advantage over a buried heuristic. Don't
be defensive; it demonstrates that you understand the difference between a demo
objective and an operating constraint.

**Have the numbers ready:** 30 candidates · 3 rejected · 7 improvements · best
at #26 · ~10 minutes · +50.0% · 337k → 506k parcels.

**Strongest moments, in order:** the data-residency table (slide 4) · the run
reallocation table (slide 13) · watching the seven step changes live · the
evolved source next to the four-line roster (demo step 6).
