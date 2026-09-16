from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_DEFAULT = Path(os.environ.get("BIRDAI_REPO", r"C:\AlmaTheHen"))
STAGE = "E1-C-H1a"
REGISTRATION_PATH = Path(os.environ.get(
    "BIRDAI_E1_C_REGISTRATION",
    r"C:\BirdAI_E1_evidence\registrations\e1-c-h1a-seed-replication-v1.json",
))
REGISTRATION_SHA256 = "948c0453748bd110384a513cb21d9c10684fde410721103c9e86c449ce2dfecb"
H1A_HELPER_REL = ".birdai/e1_b_h1a_resource_distance.py"
SOURCE_SNAPSHOT = Path(os.environ.get(
    "BIRDAI_E1_SOURCE_SNAPSHOT",
    r"C:\BirdAI_E1_evidence\source-snapshots\e1-a1-bootstrap-ab186b5.json",
))
EVIDENCE_ROOT = Path(os.environ.get(
    "BIRDAI_E1_EVIDENCE_ROOT", r"C:\BirdAI_E1_evidence"
))
PRIMARY_METRICS = (
    "time_to_first_valid_food_interaction_seconds",
    "total_distance_travelled_m",
    "selected_explore_proportion",
    "food_acquisition_rate_per_sim_minute",
)

class ReplicationError(RuntimeError):
    pass

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReplicationError(f"Missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReplicationError(f"Invalid JSON {path}: {exc}") from exc

def load_h1a_helper(repo: Path):
    path = repo / H1A_HELPER_REL
    if not path.is_file():
        raise ReplicationError(f"Missing accepted H1a helper: {path}")
    spec = importlib.util.spec_from_file_location("e1_b_h1a_helper", path)
    if spec is None or spec.loader is None:
        raise ReplicationError("Could not import E1-B/H1a helper.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def git_output(helper, repo: Path, args: list[str]) -> str:
    return helper.run(args, cwd=repo).stdout.strip()

def validate_registration(reg: dict[str, Any]) -> tuple[list[int], dict[str, dict[str, Any]], str]:
    if reg.get("experiment") != "E1-C-H1a-seed-replication-v1":
        raise ReplicationError(f"Unexpected experiment: {reg.get('experiment')!r}")
    if reg.get("stage") != "E1-C":
        raise ReplicationError(f"Unexpected stage: {reg.get('stage')!r}")
    if reg.get("manipulated_variable") != "world.objects.o1.position":
        raise ReplicationError("Manipulated variable changed from E1-B.")
    if reg.get("allowed_environment_difference") != ["world.objects.o1.position"]:
        raise ReplicationError("Allowed environment difference is not exact.")
    seeds = reg.get("seed_set")
    if (
        not isinstance(seeds, list)
        or len(seeds) != 5
        or len(set(seeds)) != 5
        or not all(isinstance(seed, int) and 0 < seed < 2**31 for seed in seeds)
    ):
        raise ReplicationError(f"Invalid predeclared seed set: {seeds!r}")
    arms = reg.get("arms")
    if not isinstance(arms, list) or len(arms) != 2:
        raise ReplicationError("Registration must contain exactly two arms.")
    indexed = {str(arm.get("arm_id")): arm for arm in arms if isinstance(arm, dict)}
    if set(indexed) != {"baseline", "far"}:
        raise ReplicationError(f"Invalid arm IDs: {sorted(indexed)}")
    runtime_commit = str(reg.get("runtime_commit_at_registration", ""))
    if len(runtime_commit) != 40:
        raise ReplicationError("Missing/invalid runtime_commit_at_registration.")
    if float(reg.get("run_horizon_sim_seconds", -1)) != 180.0:
        raise ReplicationError("E1-C horizon must remain 180 simulated seconds.")
    source_h1a = reg.get("source_h1a_registration", {})
    if source_h1a.get("sha256") != "febb899324126253c046b5828d47dd09a7cbc0bfb7c8112e587d68ec175cd1c5":
        raise ReplicationError("Source E1-B registration hash changed.")
    return list(seeds), indexed, runtime_commit

def configure_helper(helper, repo: Path, runtime_commit: str, seed: int) -> None:
    helper.STAGE = STAGE
    helper.RUNTIME_COMMIT = runtime_commit
    helper.REGISTRATION_SHA256 = REGISTRATION_SHA256
    helper.NEURAL_SEED = seed
    helper.MAIN_BLOB = git_output(helper, repo, ["git", "rev-parse", f"{runtime_commit}:{helper.MAIN_REL}"])
    helper.BRIDGE_BLOB = git_output(helper, repo, ["git", "rev-parse", f"{runtime_commit}:{helper.BRIDGE_REL}"])
    helper.D3_HELPER_BLOB = git_output(helper, repo, ["git", "rev-parse", f"{runtime_commit}:{helper.D3_HELPER_REL}"])

def pair_direction_summary(directions: dict[str, str]) -> dict[str, Any]:
    predicted = sum(v == "predicted" for v in directions.values())
    opposite = sum(v == "opposite" for v in directions.values())
    neutral = sum(v == "neutral" for v in directions.values())
    return {
        "predicted_metric_count": predicted,
        "opposite_metric_count": opposite,
        "neutral_metric_count": neutral,
        "has_predicted": predicted > 0,
        "has_opposite": opposite > 0,
    }

def replication_result(pair_results: list[dict[str, Any]], stage_validity: str):
    summaries = [
        pair_direction_summary(pair["primary_metric_directions"])
        for pair in pair_results
        if pair.get("pair_validity") == "PASS"
    ]
    support_count = sum(bool(x["has_predicted"]) for x in summaries)
    opposite_count = sum(bool(x["has_opposite"]) for x in summaries)
    neutral_count = sum(
        not bool(x["has_predicted"]) and not bool(x["has_opposite"])
        for x in summaries
    )
    counts = {
        "valid_pair_count": len(summaries),
        "support_count": support_count,
        "opposite_count": opposite_count,
        "neutral_pair_count": neutral_count,
        "seed_sensitivity": support_count > 0 and opposite_count > 0,
    }
    if stage_validity != "PASS":
        return None, counts
    if opposite_count == 0 and support_count >= 4:
        return "ROBUST", counts
    if support_count > 0 and opposite_count > 0:
        return "SEED_SENSITIVE", counts
    if support_count < 3:
        return "NOT_REPLICATED", counts
    return "INCONCLUSIVE", counts

def aggregate_numeric(pair_results: list[dict[str, Any]], arm_id: str, metric: str):
    values: list[float] = []
    censored = 0
    for pair in pair_results:
        arm = pair.get(arm_id)
        if not isinstance(arm, dict) or arm.get("status") != "PASS":
            continue
        value = arm["metrics"].get(metric)
        if value is None:
            censored += 1
        elif isinstance(value, (int, float)) and math.isfinite(float(value)):
            values.append(float(value))
    return {
        "observed_values": values,
        "observed_count": len(values),
        "censored_count": censored,
        "mean": statistics.mean(values) if values else None,
        "sample_standard_deviation": statistics.stdev(values) if len(values) >= 2 else None,
    }

def self_test() -> None:
    robust = [
        {
            "pair_validity": "PASS",
            "primary_metric_directions": {metric: "predicted" for metric in PRIMARY_METRICS},
        }
        for _ in range(5)
    ]
    result, counts = replication_result(robust, "PASS")
    assert result == "ROBUST"
    assert counts["support_count"] == 5

    mixed = json.loads(json.dumps(robust))
    mixed[-1]["primary_metric_directions"][PRIMARY_METRICS[0]] = "opposite"
    result, counts = replication_result(mixed, "PASS")
    assert result == "SEED_SENSITIVE"
    assert counts["seed_sensitivity"] is True

    weak = []
    for i in range(5):
        weak.append({
            "pair_validity": "PASS",
            "primary_metric_directions": {
                metric: ("predicted" if i < 2 and metric == PRIMARY_METRICS[0] else "neutral")
                for metric in PRIMARY_METRICS
            },
        })
    result, counts = replication_result(weak, "PASS")
    assert result == "NOT_REPLICATED"
    assert counts["support_count"] == 2

    print("SELF_TEST: PASS")
    print("STAGE: E1-C")
    print("PAIR_COUNT: 5")
    print("RUN_COUNT: 10")
    print("INVALID_PAIR_POLICY: retained; stage INVALID")
    print("RESULTS: ROBUST | SEED_SENSITIVE | NOT_REPLICATED | INCONCLUSIVE")
    print("PRODUCTION_RUNTIME_MUTATION: NONE")

def run_arm_safe(helper, **kwargs):
    try:
        item = helper.run_arm(**kwargs)
        return {
            "status": "PASS",
            "metrics": item["metrics"],
            "initial_invariant_hash": helper.canonical_hash(
                helper.environment_without_o1_position(item["initial"])
            ),
            "capsule_path": str(item["capsule_path"]),
        }
    except Exception as exc:
        return {
            "status": "INVALID",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=str(REPO_DEFAULT))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0

    self_test()
    repo = Path(args.repo).resolve()

    if not REGISTRATION_PATH.is_file():
        raise ReplicationError(f"Missing registration: {REGISTRATION_PATH}")
    actual_sha = sha256_file(REGISTRATION_PATH)
    if actual_sha != REGISTRATION_SHA256:
        raise ReplicationError(f"Registration SHA mismatch: {actual_sha} != {REGISTRATION_SHA256}")

    registration = load_json(REGISTRATION_PATH)
    seeds, arms, runtime_commit = validate_registration(registration)

    if not SOURCE_SNAPSHOT.is_file():
        raise ReplicationError(f"Missing source snapshot: {SOURCE_SNAPSHOT}")
    source_sha = sha256_file(SOURCE_SNAPSHOT)
    if source_sha != str(registration["shared_agent_snapshot"]["sha256"]):
        raise ReplicationError("Source snapshot hash mismatch.")

    helper = load_h1a_helper(repo)
    if git_output(helper, repo, ["git", "cat-file", "-t", runtime_commit]) != "commit":
        raise ReplicationError(f"Registered runtime commit unavailable: {runtime_commit}")

    godot = helper.discover_godot(repo)
    python_exe = helper.discover_python()
    d3 = helper.load_d3_helper(repo)

    experiment_id = (
        f"e1-c-h1a-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{runtime_commit[:7]}"
    )
    root = EVIDENCE_ROOT / experiment_id
    root.mkdir(parents=True, exist_ok=False)

    config = {
        "stage": STAGE,
        "experiment_id": experiment_id,
        "registration_sha256": REGISTRATION_SHA256,
        "runtime_commit": runtime_commit,
        "source_snapshot_sha256": source_sha,
        "seed_set": seeds,
        "pair_count": 5,
        "run_count": 10,
        "allowed_environment_difference": ["world.objects.o1.position"],
    }
    (root / "experiment-config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=" * 72, flush=True)
    print("E1-C H1a PAIRED SEED REPLICATION", flush=True)
    print(f"EVIDENCE: {root}", flush=True)
    print(f"RUNTIME_COMMIT: {runtime_commit}", flush=True)
    print("SEEDS: " + ",".join(map(str, seeds)), flush=True)
    print("=" * 72, flush=True)

    pairs: list[dict[str, Any]] = []
    for index, seed in enumerate(seeds, 1):
        configure_helper(helper, repo, runtime_commit, seed)
        pair_root = root / f"seed_{seed}"
        pair_root.mkdir(parents=True, exist_ok=False)
        print(f"PAIR {index}/5 — SEED {seed}", flush=True)

        baseline = run_arm_safe(
            helper,
            repo=repo,
            d3=d3,
            experiment_root=pair_root,
            source=SOURCE_SNAPSHOT,
            source_sha=source_sha,
            arm=arms["baseline"],
            godot=godot,
            python_exe=python_exe,
        )
        print(f"  BASELINE: {baseline['status']}", flush=True)

        far = run_arm_safe(
            helper,
            repo=repo,
            d3=d3,
            experiment_root=pair_root,
            source=SOURCE_SNAPSHOT,
            source_sha=source_sha,
            arm=arms["far"],
            godot=godot,
            python_exe=python_exe,
        )
        print(f"  FAR: {far['status']}", flush=True)

        validity = "PASS"
        reasons: list[str] = []
        directions: dict[str, str] = {}

        if baseline["status"] != "PASS":
            validity = "INVALID"
            reasons.append("baseline run invalid")
        if far["status"] != "PASS":
            validity = "INVALID"
            reasons.append("far run invalid")
        if validity == "PASS" and baseline["initial_invariant_hash"] != far["initial_invariant_hash"]:
            validity = "INVALID"
            reasons.append("start state differs outside o1.position")
        if validity == "PASS" and not baseline["metrics"]["neural_authority_integrity"]:
            validity = "INVALID"
            reasons.append("baseline neural authority integrity failed")
        if validity == "PASS" and not far["metrics"]["neural_authority_integrity"]:
            validity = "INVALID"
            reasons.append("far neural authority integrity failed")
        if validity == "PASS":
            directions = helper.metric_direction(baseline["metrics"], far["metrics"])

        pair = {
            "seed": seed,
            "pair_index": index,
            "pair_validity": validity,
            "validity_reasons": reasons,
            "baseline": baseline,
            "far": far,
            "primary_metric_directions": directions,
        }
        pair_path = pair_root / "pair-comparison.json"
        pair_path.write_text(
            json.dumps(pair, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        pair["pair_comparison_path"] = str(pair_path)
        pair["pair_comparison_sha256"] = sha256_file(pair_path)
        pairs.append(pair)
        print(f"  PAIR_VALIDITY: {validity}", flush=True)

    stage_validity = (
        "PASS"
        if len(pairs) == 5 and all(pair["pair_validity"] == "PASS" for pair in pairs)
        else "INVALID"
    )
    result, counts = replication_result(pairs, stage_validity)
    aggregates = {
        metric: {
            "baseline": aggregate_numeric(pairs, "baseline", metric),
            "far": aggregate_numeric(pairs, "far", metric),
        }
        for metric in PRIMARY_METRICS
    }

    summary = {
        "stage": STAGE,
        "experiment_id": experiment_id,
        "runtime_commit": runtime_commit,
        "registration_sha256": REGISTRATION_SHA256,
        "source_snapshot_sha256": source_sha,
        "stage_validity": stage_validity,
        "replication_result": result,
        "seed_set": seeds,
        "pair_count_declared": 5,
        "pair_count_completed": len(pairs),
        "run_count_declared": 10,
        "pairs": pairs,
        "replication_counts": counts,
        "aggregates": aggregates,
        "allowed_environment_difference": ["world.objects.o1.position"],
        "new_environment_variables": "none",
        "production_runtime_mutation": "none",
        "neural_policy_change": "none",
        "learning_rule_change": "none",
    }
    summary_path = root / "replication-summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary_sha = sha256_file(summary_path)

    print("=" * 72, flush=True)
    print("STATUS: PASS" if stage_validity == "PASS" else "STATUS: INVALID", flush=True)
    print(f"STAGE_VALIDITY: {stage_validity}", flush=True)
    print(f"REPLICATION_RESULT: {result}", flush=True)
    print("REPLICATION_COUNTS: " + json.dumps(counts, sort_keys=True), flush=True)
    print(f"SUMMARY: {summary_path}", flush=True)
    print(f"SUMMARY_SHA256: {summary_sha}", flush=True)
    print(f"EVIDENCE: {root}", flush=True)
    print("PRODUCTION_RUNTIME_MUTATION: NONE", flush=True)
    print("=" * 72, flush=True)
    return 0 if stage_validity == "PASS" else 2

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ReplicationError as exc:
        print("STATUS: BLOCKED", file=sys.stderr)
        print(f"BLOCKER: {exc}", file=sys.stderr)
        raise SystemExit(2)
    except Exception as exc:
        print("STATUS: BLOCKED", file=sys.stderr)
        print(f"BLOCKER: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
