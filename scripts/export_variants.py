#!/usr/bin/env python3
"""Export the three network instances evaluate.py scores every candidate on.

The two variants are produced by seeded Python RNG inside evaluate.load_instances(),
which the browser cannot reproduce — so the scheduling explainer (/scheduling/)
reads them from data/variants.json instead and gets numbers identical to the
real experiment.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiment"))

import evaluate  # noqa: E402

LABELS = ["Primary network", "Variant A (seed 7)", "Variant B (seed 13)"]


def main():
    instances = evaluate.load_instances()
    out = ROOT / "data" / "variants.json"
    out.write_text(json.dumps({
        "note": "The 3 network instances evaluate.py scores every candidate on "
                "(primary + 2 deterministic perturbations). Regenerate with "
                "scripts/export_variants.py.",
        "labels": LABELS,
        "instances": instances,
    }, indent=1) + "\n")
    print(f"wrote {out.relative_to(ROOT)} — {len(instances)} instances")


if __name__ == "__main__":
    main()
