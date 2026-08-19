"""Export the program family tree of the recorded AlphaEvolve run.

Lists every alphaEvolveProgram of the experiment referenced in
traces/candidates.jsonl (the API keeps parentPrograms lineage server-side),
joins each program with the locally recorded evaluation (score, insight,
code, eval order), and writes traces/lineage.json for ui/tree.html.

Usage:  .venv/bin/python scripts/export_lineage.py
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiment"))

from dotenv import load_dotenv

load_dotenv(ROOT / "experiment" / ".env")

from alpha_evolve.client import AlphaEvolveClient

CANDIDATES = ROOT / "traces" / "candidates.jsonl"
OUT = ROOT / "traces" / "lineage.json"


def api_score(prog: dict):
    scores = (prog.get("evaluation") or {}).get("scores", {}).get("scores", [])
    return scores[0].get("score") if scores else None


def api_code(prog: dict):
    files = (prog.get("content") or {}).get("files", [])
    return files[0].get("content") if files else None


def main():
    local = {}
    for line in CANDIDATES.read_text().splitlines():
        if line.strip():
            e = json.loads(line)
            local[e["name"]] = e

    experiment = next(iter(local)).rsplit("/alphaEvolvePrograms/", 1)[0]
    client = AlphaEvolveClient(
        project_id=os.environ["PROJECT_ID"],
        location=os.getenv("LOCATION", "global"),
        collection=os.getenv("COLLECTION", "default_collection"),
        engine=os.environ["GE_APP_ID"],
        assistant=os.getenv("ASSISTANT", "default_assistant"),
        base_url=os.getenv("BASE_URL", "discoveryengine.googleapis.com"),
    )
    resp = client.list_alpha_evolve_programs(experiment) or {}
    programs = resp.get("alphaEvolvePrograms", [])
    if resp.get("nextPageToken"):
        raise SystemExit("pagination not handled: more than one page of programs")
    if not programs:
        raise SystemExit("no programs returned from the API")

    programs.sort(key=lambda p: (p.get("createTime", ""), p["name"]))
    nodes = []
    for prog in programs:
        name = prog["name"]
        rec = local.get(name, {})
        parents = prog.get("parentPrograms") or []
        score = rec.get("score")
        if score is None and not rec.get("failed"):
            score = api_score(prog)
        nodes.append({
            "id": name.rsplit("/", 1)[1],
            "parent": parents[0].rsplit("/", 1)[1] if parents else None,
            "idx": rec.get("idx"),          # local evaluation order, None if never scored here
            "score": score,
            "failed": bool(rec.get("failed")),
            "state": prog.get("state"),
            "create_time": prog.get("createTime"),
            "insight": rec.get("insight"),
            "code": rec.get("code") or api_code(prog),
        })

    # flag the running-best chain in evaluation order (root = seed baseline)
    best = next((n["score"] for n in nodes if n["parent"] is None), None)
    evaluated = sorted((n for n in nodes if n["parent"] and n["idx"] is not None),
                       key=lambda n: n["idx"])
    for n in evaluated:
        if n["score"] is not None and (best is None or n["score"] > best):
            n["new_best"] = True
            best = n["score"]

    ids = {n["id"] for n in nodes}
    orphans = [n["id"] for n in nodes if n["parent"] and n["parent"] not in ids]
    if orphans:
        print(f"warning: {len(orphans)} nodes reference parents outside the list: {orphans}")

    OUT.write_text(json.dumps({
        "source": "alphaevolve-real-run",
        "experiment": experiment,
        "metric": "parcels_per_shift",
        "nodes": nodes,
    }, indent=1))
    roots = sum(1 for n in nodes if n["parent"] is None)
    stars = sum(1 for n in nodes if n.get("new_best"))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(nodes)} programs, "
          f"{roots} root(s), {stars} new-best, "
          f"{sum(1 for n in nodes if n['failed'])} failed, "
          f"{sum(1 for n in nodes if n['idx'] is None)} never evaluated locally")


if __name__ == "__main__":
    main()
