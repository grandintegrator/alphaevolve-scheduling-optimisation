"""Run the real AlphaEvolve experiment for the Metro Parcel Network linehaul demo.

Wraps evaluate.evaluate() in the client-loop contract, records every candidate
to traces/candidates.jsonl as the run progresses, then post-processes into
traces/evolution_trace.json for the UI (linehaul flows recomputed for each new
best).

Usage:  python experiment/run_evolution.py
"""
import asyncio
import copy
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

import nest_asyncio
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiment"))
load_dotenv(ROOT / "experiment" / ".env")

from alpha_evolve.client import AlphaEvolveClient
from alpha_evolve.controller import run_controller_loop
from alpha_evolve.experiment import AlphaEvolveExperiment

from evaluate import evaluate, load_instances, simulate, FAIL_SCORE

logger = logging.getLogger("linehaul-run")

METRIC = "parcels_per_shift"
SEED_SOURCE = (ROOT / "experiment" / "program.py").read_text()
TRACE_JSONL = ROOT / "traces" / "candidates.jsonl"
TRACE_JSON = ROOT / "traces" / "evolution_trace.json"

_lock = threading.Lock()
_counter = {"n": 0}


def linehaul_evaluation_function(program_candidate: dict) -> dict:
    code = program_candidate["content"]["files"][0]["content"]
    result = evaluate(code)
    score = result[METRIC]
    ok = score > FAIL_SCORE
    with _lock:
        _counter["n"] += 1
        entry = {
            "idx": _counter["n"],
            "name": program_candidate.get("name", ""),
            "score": score if ok else None,
            "failed": not ok,
            "insight": result.get("insight"),
            "code": code,
            "t": time.time(),
        }
        with TRACE_JSONL.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    evaluation = {
        "scores": {"scores": [{"metric": METRIC, "score": score if ok else None}]}
    }
    if not ok:
        evaluation["insights"] = {
            "insights": [{"label": "Evaluation failure", "text": result.get("insight", "failed")}]
        }
    return evaluation


def primary_result(code: str):
    """Re-run a candidate on the primary network to get flows + stats for the UI."""
    ns = {}
    exec(code, ns)
    primary = load_instances()[0]
    return simulate(primary, ns["solve"](copy.deepcopy(primary)))


def postprocess(seed_score: float):
    entries = [json.loads(l) for l in TRACE_JSONL.read_text().splitlines() if l.strip()]
    entries.sort(key=lambda e: e["idx"])

    best_score = seed_score
    candidates = []
    for e in entries:
        is_best = e["score"] is not None and e["score"] > best_score
        cand = {
            "idx": e["idx"],
            "score": e["score"],
            "failed": e["failed"],
            "new_best": is_best,
        }
        if is_best:
            best_score = e["score"]
            try:
                cand["primary"] = primary_result(e["code"])
                cand["code"] = e["code"]
            except Exception as ex:  # candidate scored on mean but broke on rerun
                logger.warning("could not recompute flows for idx %s: %s", e["idx"], ex)
                cand["new_best"] = False
        candidates.append(cand)

    trace = {
        "source": "alphaevolve-real-run",
        "metric": METRIC,
        "model": os.getenv("MODEL", "unknown"),
        "baseline": {
            "score": seed_score,
            "primary": primary_result(SEED_SOURCE),
            "code": SEED_SOURCE,
        },
        "candidates": candidates,
    }
    TRACE_JSON.write_text(json.dumps(trace, indent=1))
    n_best = sum(1 for c in candidates if c["new_best"])
    final = max((c["score"] for c in candidates if c["score"] is not None),
                default=seed_score)
    final = max(final, seed_score)
    improvement = (final - seed_score) / seed_score * 100
    logger.info("trace written: %d candidates, %d improvements, "
                "score %.1f -> %.1f parcels/shift (+%.1f%%)",
                len(candidates), n_best, seed_score, final, improvement)


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s %(message)s")
    if TRACE_JSONL.exists():
        TRACE_JSONL.rename(TRACE_JSONL.with_suffix(f".jsonl.bak{int(time.time())}"))

    client = AlphaEvolveClient(
        project_id=os.environ["PROJECT_ID"],
        location=os.getenv("LOCATION", "global"),
        collection=os.getenv("COLLECTION", "default_collection"),
        engine=os.environ["GE_APP_ID"],
        assistant=os.getenv("ASSISTANT", "default_assistant"),
        base_url=os.getenv("BASE_URL", "discoveryengine.googleapis.com"),
    )
    experiment = AlphaEvolveExperiment(
        ae_client=client,
        evaluator_function=linehaul_evaluation_function,
        max_programs_evaluated=int(os.getenv("MAX_PROGRAMS_EVALUATED", "80")),
        parallel_evaluation=False,  # required: evaluator uses signal.alarm
    )

    problem_description = (ROOT / "experiment" / "instructions.md").read_text()
    experiment.create_experiment({
        "title": "Metro Parcel Network linehaul dispatch - parcels sorted maximisation",
        "problem_description": problem_description,
        "program_language": "python",
        "run_settings": {
            "max_programs": int(os.getenv("MAX_PROGRAMS_GENERATED", "100")),
            "concurrency": int(os.getenv("CONCURRENCY", "4")),
        },
        "generation_settings": {"models": [{"name": os.getenv("MODEL", "gemini-2.5-flash")}]},
    })

    seed_eval = evaluate(SEED_SOURCE)
    seed_score = seed_eval[METRIC]
    logger.info("seed score: %s", seed_score)
    experiment.create_initial_program({
        "content": {"files": [{"path": "main.py", "content": SEED_SOURCE}]},
        "evaluation": {"scores": {"scores": [{"metric": METRIC, "score": seed_score}]}},
    })
    experiment.start_experiment()
    logger.info("experiment started: %s", experiment.experiment_name)

    nest_asyncio.apply()
    asyncio.run(run_controller_loop(experiment))

    postprocess(seed_score)


if __name__ == "__main__":
    main()
