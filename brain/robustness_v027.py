"""Extended multi-seed robustness runner for BirdAI NeuralBrain v0.2.7."""
from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path

import numpy as np

from neural_model import ACTIONS
from selftest import run_seed

SEEDS = (20260910, 42, 1701, 7, 2026, 31337, 271828, 314159, 8675309, 123456789)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/neural-robustness-v0.2.7.json")
    args = parser.parse_args()

    import nengo
    try:
        import scipy
        scipy_version = scipy.__version__
    except Exception:
        scipy_version = None

    runs = [run_seed(seed) for seed in SEEDS]
    neural_matches = 0
    neural_total = 0
    bg_matches = 0
    bg_total = 0
    mixed_traces = []

    for run in runs:
        for item in run["results"]:
            neural_total += 1
            neural_matches += int(item["neural_value_pick"] == item["analytical_pick"])
            bg_total += 1
            bg_matches += int(item["bg_pick"] == item["competition_value_pick"])
            if item["scenario"] == "mixed_manipulate":
                mixed_traces.append({
                    "seed": run["seed"],
                    "selected": item["selected"],
                    "analytical_pick": item["analytical_pick"],
                    "neural_pick": item["neural_value_pick"],
                    "competition_pick": item["competition_value_pick"],
                    "bg_pick": item["bg_pick"],
                    "analytical_explore": item["analytical_values"]["EXPLORE"],
                    "neural_explore": item["action_values"]["EXPLORE"],
                    "analytical_manipulate": item["analytical_values"]["MANIPULATE"],
                    "neural_manipulate": item["action_values"]["MANIPULATE"],
                    "explore_trace": item["explore_trace"],
                })

    failures = [f"seed={run['seed']}: {failure}" for run in runs for failure in run["failures"]]
    all_pass = not failures
    qualified = all_pass and neural_matches == neural_total and bg_matches == bg_total
    report = {
        "diagnostic": "BirdAI v0.5.8 NeuralBrain v0.2.7 BG readout robustness",
        "status": "PASS" if qualified else "FAIL",
        "qualified": qualified,
        "candidate_change": "30 ms mean readout of the existing 10 ms-filtered BG output; valuation, competition, BG100 weights/bias/gain, commitment and actuator authority unchanged",
        "seeds": list(SEEDS),
        "checks_per_seed": 21,
        "behavior_checks": 21 * len(SEEDS),
        "behavior_passed": sum(run["passed"] for run in runs),
        "behavior_total": sum(run["checks"] for run in runs),
        "neural_analytical_match_count": neural_matches,
        "neural_analytical_match_total": neural_total,
        "bg_competition_match_count": bg_matches,
        "bg_competition_match_total": bg_total,
        "failures": failures,
        "mixed_manipulate_traces": mixed_traces,
        "environment": {
            "python": platform.python_version(),
            "nengo": nengo.__version__,
            "numpy": np.__version__,
            "scipy": scipy_version,
        },
        "runs": runs,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"NeuralBrain v0.2.7 extended robustness: {report['status']}")
    print(f"  behavior: {report['behavior_passed']}/{report['behavior_total']}")
    print(f"  neural vs analytical: {neural_matches}/{neural_total}")
    print(f"  BG vs competition: {bg_matches}/{bg_total}")
    for run in runs:
        print(f"  seed={run['seed']}: {run['passed']}/{run['checks']}")
        for failure in run["failures"]:
            print(f"    - {failure}")
    print(f"Resultat: {out}")
    return 0 if qualified else 1


if __name__ == "__main__":
    raise SystemExit(main())
