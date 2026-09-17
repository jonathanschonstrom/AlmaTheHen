from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_DEFAULT = Path(r"C:\AlmaTheHen")
EVIDENCE_ROOT = Path(r"C:\BirdAI_E1_evidence")
REGISTRATION_PATH = EVIDENCE_ROOT / "registrations" / "e1-e-h2-early-explore-predictor-v1.json"
REGISTRATION_SHA256 = "0311621fb4493338d5785753da0c27ce490128170dc84bb4eb096e9b79eb01f1"
SEED_MANIFEST_PATH = EVIDENCE_ROOT / "registrations" / "e1-e-h2-seed-manifest.json"
SEED_MANIFEST_SHA256 = "bb9e3108f382df25cc28f93b520662b9f110fdf70a9723220e5b79ace05f4e1f"
REGISTRATION_LOCK_PATH = EVIDENCE_ROOT / "registrations" / "e1-e-h2-registration-lock.json"
REGISTRATION_LOCK_SHA256 = "e0c7eb1518f601a2788a01e7e141c69882db77422583b416eef099626aba50a7"
SOURCE_SNAPSHOT = EVIDENCE_ROOT / "source-snapshots" / "e1-a1-bootstrap-ab186b5.json"
SOURCE_SNAPSHOT_SHA256 = "3b42d55fc595bc7312e932dc9615c08e1ce2abe72f0f2bcc0984e9818e47b218"
DENSITY_REGISTRATION_SHA256 = "b35a58950e1ba12f2e6006b817cbaa04d16926baca0d37272f04cbe8f0c0a88c"

EXPERIMENT_ID = "E1-E-H2-early-explore-predictor-v1"
STAGE = "E1-E"
HYPOTHESIS_ID = "H2"
PRIMARY_RESOURCE_ID = "o1"
PEER_RESOURCE_ID = "e1d_food_peer"
PRIMARY_POSITION = [-4.0, 0.0, 0.0]
PEER_POSITION = [4.0, 0.0, 0.0]
EARLY_WINDOW_SECONDS = 30.0
RUN_HORIZON_SECONDS = 180.0
LATE_WINDOW_SECONDS = RUN_HORIZON_SECONDS - EARLY_WINDOW_SECONDS
EXPECTED_SEEDS = [1654930625, 1323201516, 643721773, 1673661858, 795032547]
PRIOR_SEEDS = {20260910, 2095399255, 889499301, 1357519266, 1853072130}
PRIMARY_METRICS = [
    "time_to_first_valid_food_interaction_seconds",
    "total_distance_travelled_m",
    "selected_explore_proportion",
    "food_acquisition_rate_per_sim_minute",
]


class PredictorError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PredictorError(f"Missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PredictorError(f"Invalid JSON {path}: {exc}") from exc


def load_density_helper(repo: Path):
    path = repo / ".birdai" / "e1_d_h1b_resource_density.py"
    spec = importlib.util.spec_from_file_location("e1e_density_apparatus", path)
    if spec is None or spec.loader is None:
        raise PredictorError(f"Cannot import density apparatus: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def normalize_position(value: Any, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise PredictorError(f"{label} must be a 3-vector.")
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise PredictorError(f"{label} contains a non-numeric value.") from exc


def validate_registration(reg: dict[str, Any]) -> tuple[list[int], str]:
    if reg.get("experiment") != EXPERIMENT_ID:
        raise PredictorError(f"Unexpected experiment id: {reg.get('experiment')!r}")
    if reg.get("stage") != STAGE:
        raise PredictorError(f"Unexpected stage: {reg.get('stage')!r}")
    if reg.get("hypothesis_id") != HYPOTHESIS_ID:
        raise PredictorError(f"Unexpected hypothesis id: {reg.get('hypothesis_id')!r}")
    if reg.get("status") != "FINAL_FROZEN_BEFORE_EXECUTION":
        raise PredictorError("Registration is not final/frozen.")

    lock = reg.get("registration_lock", {})
    if lock.get("final") is not True or lock.get("human_approved") is not True:
        raise PredictorError("Registration human/final lock is missing.")
    if lock.get("execution_started") is not False:
        raise PredictorError("Registration says execution already started.")

    seeds = reg.get("seed_set")
    if seeds != EXPECTED_SEEDS:
        raise PredictorError(f"Seed set changed: {seeds!r}")
    if set(seeds) & PRIOR_SEEDS:
        raise PredictorError("Fresh seed set overlaps E1-C/E1-D seeds.")

    seed_manifest = reg.get("seed_manifest", {})
    if seed_manifest.get("sha256") != SEED_MANIFEST_SHA256:
        raise PredictorError("Seed manifest SHA mismatch in registration.")

    apparatus = reg.get("apparatus", {})
    if normalize_position(apparatus.get("alma_start_position"), "Alma start") != [0.0, 0.0, 0.0]:
        raise PredictorError("Alma start position changed.")
    if normalize_position(apparatus.get("primary_tested_resource_position"), "primary position") != PRIMARY_POSITION:
        raise PredictorError("Primary resource position changed.")
    if normalize_position(apparatus.get("peer_resource_position"), "peer position") != PEER_POSITION:
        raise PredictorError("Peer resource position changed.")
    if float(apparatus.get("nearest_tested_resource_distance_m", -1.0)) != 4.0:
        raise PredictorError("Nearest tested-resource distance changed.")
    if apparatus.get("distance_constant_across_arms") is not True:
        raise PredictorError("Distance is not registered constant across arms.")
    if int(apparatus.get("rich_tested_resource_count", -1)) != 2:
        raise PredictorError("Rich resource count changed.")
    if int(apparatus.get("sparse_tested_resource_count", -1)) != 1:
        raise PredictorError("Sparse resource count changed.")
    if float(apparatus.get("run_horizon_sim_seconds", -1.0)) != RUN_HORIZON_SECONDS:
        raise PredictorError("Run horizon changed.")

    protected = apparatus.get("protected_changes", {})
    for key in ("production_runtime_mutation", "neural_policy_change", "bg_retuning", "learning_rule_change"):
        if str(protected.get(key, "")).lower() != "none":
            raise PredictorError(f"Protected change is not NONE: {key}")

    predictor = reg.get("early_predictor", {})
    if predictor.get("metric") != "selected_explore_proportion":
        raise PredictorError("Early predictor metric changed.")
    if predictor.get("window_sim_seconds") != [0.0, 30.0]:
        raise PredictorError("Early predictor window changed.")
    if predictor.get("arm_contrast") != "sparse_minus_rich":
        raise PredictorError("Early predictor contrast changed.")
    if predictor.get("label_rule") != {
        "delta_gt_0": "predicted",
        "delta_lt_0": "opposite",
        "delta_eq_0": "neutral",
    }:
        raise PredictorError("Early predictor label rule changed.")

    late = reg.get("late_outcome", {})
    if late.get("window_sim_seconds") != [30.0, 180.0]:
        raise PredictorError("Late outcome window changed.")
    if late.get("predictor_window_excluded") is not True:
        raise PredictorError("Predictor-window exclusion is not locked.")
    if set(late.get("metric_directions", {})) != set(PRIMARY_METRICS):
        raise PredictorError("Late primary metric set changed.")

    result = reg.get("hypothesis_result", {})
    if result.get("values") != ["SUPPORTED", "NOT_SUPPORTED", "INCONCLUSIVE"]:
        raise PredictorError("Hypothesis result vocabulary changed.")
    required_order = [
        "If stage validity is not PASS: no scientific result.",
        "If any early or late pair label is neutral: INCONCLUSIVE.",
        "If late labels do not contain at least one predicted and at least one opposite pair: INCONCLUSIVE.",
        "If all 5 early labels match their corresponding late labels: SUPPORTED.",
        "If at most 3 of 5 early labels match their corresponding late labels: NOT_SUPPORTED.",
        "If exactly 4 of 5 early labels match their corresponding late labels: INCONCLUSIVE.",
    ]
    if result.get("classification_order") != required_order:
        raise PredictorError("Hypothesis classification order changed.")

    provenance = reg.get("provenance", {})
    snapshot = provenance.get("source_snapshot", {})
    if snapshot.get("sha256") != SOURCE_SNAPSHOT_SHA256:
        raise PredictorError("Source snapshot SHA changed.")
    source_density = provenance.get("source_e1_d_registration", {})
    if source_density.get("sha256") != DENSITY_REGISTRATION_SHA256:
        raise PredictorError("E1-D apparatus provenance SHA changed.")
    runtime_commit = str(provenance.get("scientific_runtime_reference", ""))
    if len(runtime_commit) != 40 or any(ch not in "0123456789abcdef" for ch in runtime_commit.lower()):
        raise PredictorError("Invalid scientific_runtime_reference.")

    return list(seeds), runtime_commit


def response_apply_tick(event: dict[str, Any]) -> int:
    if "target_apply_tick" not in event:
        raise PredictorError("Successful neural response lacks target_apply_tick.")
    return int(event["target_apply_tick"])


def sign_label(delta: float) -> str:
    if delta > 0.0:
        return "predicted"
    if delta < 0.0:
        return "opposite"
    return "neutral"


def tested_total_from_state(world: dict[str, Any], rich: bool) -> float:
    total = float(world["o1_stock"])
    if rich:
        if not bool(world.get("e1d_peer_present", False)):
            raise PredictorError("Rich trace lost e1d peer.")
        total += float(world["e1d_peer_stock"])
    return total


def compute_windowed_metrics(
    *,
    events: list[dict[str, Any]],
    initial: dict[str, Any],
    final: dict[str, Any],
    sim_dt: float,
    stop_tick: int,
) -> dict[str, Any]:
    boundary_tick = int(round(EARLY_WINDOW_SECONDS / sim_dt))
    if boundary_tick <= 0 or boundary_tick >= stop_tick:
        raise PredictorError("Early boundary tick is outside the run.")

    sim_events = [event for event in events if event.get("event") == "sim_state"]
    by_tick = {int(event["sim_tick"]): event for event in sim_events}
    if len(sim_events) != stop_tick or set(by_tick) != set(range(1, stop_tick + 1)):
        raise PredictorError("Simulation trace is not complete for windowed metrics.")

    boundary = by_tick[boundary_tick]
    boundary_state = boundary.get("state", {})
    boundary_world = boundary_state.get("world", {})
    boundary_agent = boundary_state.get("agent", {})

    initial_objects = initial.get("world", {}).get("objects", {})
    rich = PEER_RESOURCE_ID in initial_objects
    boundary_stock = tested_total_from_state(boundary_world, rich)
    final_objects = final.get("world", {}).get("objects", {})
    final_stock = float(final_objects[PRIMARY_RESOURCE_ID]["stock"])
    if rich:
        if PEER_RESOURCE_ID not in final_objects:
            raise PredictorError("Rich final snapshot lost peer resource.")
        final_stock += float(final_objects[PEER_RESOURCE_ID]["stock"])

    first_late_tick = None
    for tick in range(boundary_tick + 1, stop_tick + 1):
        state = by_tick[tick].get("state", {})
        total = tested_total_from_state(state.get("world", {}), rich)
        if total < boundary_stock - 1e-9:
            first_late_tick = tick
            break

    boundary_distance = float(boundary_agent["distance_walked"])
    final_distance = float(final.get("agent", {}).get("distance_walked", boundary_distance))
    late_distance = max(0.0, final_distance - boundary_distance)
    late_acquired = max(0.0, boundary_stock - final_stock)

    responses = [
        event for event in events
        if event.get("event") == "response_received" and bool(event.get("ok", False))
    ]
    early_responses = [event for event in responses if response_apply_tick(event) <= boundary_tick]
    late_responses = [
        event for event in responses
        if boundary_tick < response_apply_tick(event) <= stop_tick
    ]
    if not early_responses:
        raise PredictorError("No successful neural responses in early predictor window.")
    if not late_responses:
        raise PredictorError("No successful neural responses in late outcome window.")

    def explore_summary(items: list[dict[str, Any]]) -> tuple[int, int, float]:
        values = [str(event.get("selected", "")).upper() for event in items]
        count = sum(value == "EXPLORE" for value in values)
        return count, len(values), count / len(values)

    early_explore, early_count, early_prop = explore_summary(early_responses)
    late_explore, late_count, late_prop = explore_summary(late_responses)

    late_first_seconds = (
        None
        if first_late_tick is None
        else (first_late_tick - boundary_tick) * sim_dt
    )

    return {
        "boundary_tick": boundary_tick,
        "early": {
            "window_sim_seconds": [0.0, EARLY_WINDOW_SECONDS],
            "selected_explore_count": early_explore,
            "neural_response_count": early_count,
            "selected_explore_proportion": early_prop,
        },
        "late": {
            "window_sim_seconds": [EARLY_WINDOW_SECONDS, RUN_HORIZON_SECONDS],
            "time_to_first_valid_food_interaction_seconds": late_first_seconds,
            "first_food_acquisition_tick_after_boundary": first_late_tick,
            "total_distance_travelled_m": late_distance,
            "selected_explore_count": late_explore,
            "neural_response_count": late_count,
            "selected_explore_proportion": late_prop,
            "food_acquisitions": late_acquired,
            "food_acquisition_rate_per_sim_minute": late_acquired / (LATE_WINDOW_SECONDS / 60.0),
            "tested_resource_stock_at_30s": boundary_stock,
            "tested_resource_final_stock_total": final_stock,
        },
    }


def install_predictor_metrics(density, helper) -> None:
    density.install_density_metrics(helper)
    density_metrics = helper.metrics_for_run

    def metrics_for_run(*, events, initial, final):
        base = density_metrics(events=events, initial=initial, final=final)
        windows = compute_windowed_metrics(
            events=events,
            initial=initial,
            final=final,
            sim_dt=float(helper.SIM_DT),
            stop_tick=int(helper.STOP_TICK),
        )
        base["e1e_early"] = windows["early"]
        base["e1e_late"] = windows["late"]
        base["e1e_boundary_tick"] = windows["boundary_tick"]
        return base

    helper.metrics_for_run = metrics_for_run


def early_prediction(rich_metrics: dict[str, Any], sparse_metrics: dict[str, Any]) -> dict[str, Any]:
    rich_value = float(rich_metrics["e1e_early"]["selected_explore_proportion"])
    sparse_value = float(sparse_metrics["e1e_early"]["selected_explore_proportion"])
    delta = sparse_value - rich_value
    return {
        "metric": "selected_explore_proportion",
        "window_sim_seconds": [0.0, EARLY_WINDOW_SECONDS],
        "rich": rich_value,
        "sparse": sparse_value,
        "delta_sparse_minus_rich": delta,
        "label": sign_label(delta),
    }


def late_metric_directions(
    rich_metrics: dict[str, Any],
    sparse_metrics: dict[str, Any],
) -> dict[str, str]:
    rich = rich_metrics["e1e_late"]
    sparse = sparse_metrics["e1e_late"]
    result: dict[str, str] = {}

    r_time = rich["time_to_first_valid_food_interaction_seconds"]
    s_time = sparse["time_to_first_valid_food_interaction_seconds"]
    if r_time is None and s_time is None:
        result["time_to_first_valid_food_interaction_seconds"] = "neutral"
    elif r_time is not None and s_time is None:
        result["time_to_first_valid_food_interaction_seconds"] = "predicted"
    elif r_time is None and s_time is not None:
        result["time_to_first_valid_food_interaction_seconds"] = "opposite"
    else:
        result["time_to_first_valid_food_interaction_seconds"] = sign_label(float(s_time) - float(r_time))

    result["total_distance_travelled_m"] = sign_label(
        float(sparse["total_distance_travelled_m"])
        - float(rich["total_distance_travelled_m"])
    )
    result["selected_explore_proportion"] = sign_label(
        float(sparse["selected_explore_proportion"])
        - float(rich["selected_explore_proportion"])
    )

    rate_delta = (
        float(rich["food_acquisition_rate_per_sim_minute"])
        - float(sparse["food_acquisition_rate_per_sim_minute"])
    )
    result["food_acquisition_rate_per_sim_minute"] = sign_label(rate_delta)
    return result


def late_pair_label(directions: dict[str, str]) -> dict[str, Any]:
    predicted = sum(value == "predicted" for value in directions.values())
    opposite = sum(value == "opposite" for value in directions.values())
    neutral = sum(value == "neutral" for value in directions.values())
    score = predicted - opposite
    return {
        "predicted_metric_count": predicted,
        "opposite_metric_count": opposite,
        "neutral_metric_count": neutral,
        "score": score,
        "label": "predicted" if score > 0 else "opposite" if score < 0 else "neutral",
    }


def classify_stage(
    pairs: list[dict[str, Any]],
    stage_validity: str,
) -> tuple[str | None, dict[str, Any]]:
    valid = [pair for pair in pairs if pair.get("pair_validity") == "PASS"]
    labels = [pair.get("late_pair_label") for pair in valid]
    early = [pair.get("early_prediction", {}).get("label") for pair in valid]
    matches = [bool(pair.get("prediction_match")) for pair in valid]

    late_predicted = sum(label == "predicted" for label in labels)
    late_opposite = sum(label == "opposite" for label in labels)
    late_neutral = sum(label == "neutral" for label in labels)
    early_neutral = sum(label == "neutral" for label in early)
    match_count = sum(matches)

    counts = {
        "valid_pair_count": len(valid),
        "match_count": match_count,
        "mismatch_count": len(valid) - match_count,
        "late_predicted_count": late_predicted,
        "late_opposite_count": late_opposite,
        "late_neutral_count": late_neutral,
        "early_neutral_count": early_neutral,
        "both_non_neutral_late_classes_present": late_predicted > 0 and late_opposite > 0,
    }

    if stage_validity != "PASS":
        return None, counts
    if early_neutral > 0 or late_neutral > 0:
        return "INCONCLUSIVE", counts
    if not counts["both_non_neutral_late_classes_present"]:
        return "INCONCLUSIVE", counts
    if match_count == 5:
        return "SUPPORTED", counts
    if match_count <= 3:
        return "NOT_SUPPORTED", counts
    return "INCONCLUSIVE", counts


def configure_density_for_e1e(density) -> None:
    density.STAGE = STAGE
    density.REGISTRATION_SHA256 = REGISTRATION_SHA256
    density.SOURCE_SNAPSHOT = SOURCE_SNAPSHOT
    density.SOURCE_SNAPSHOT_SHA256 = SOURCE_SNAPSHOT_SHA256


def self_test() -> None:
    assert sign_label(1.0) == "predicted"
    assert sign_label(-1.0) == "opposite"
    assert sign_label(0.0) == "neutral"

    directions = {
        PRIMARY_METRICS[0]: "predicted",
        PRIMARY_METRICS[1]: "predicted",
        PRIMARY_METRICS[2]: "opposite",
        PRIMARY_METRICS[3]: "neutral",
    }
    summary = late_pair_label(directions)
    assert summary["score"] == 1
    assert summary["label"] == "predicted"

    supported = [
        {
            "pair_validity": "PASS",
            "early_prediction": {"label": label},
            "late_pair_label": label,
            "prediction_match": True,
        }
        for label in ["predicted", "opposite", "predicted", "opposite", "predicted"]
    ]
    result, counts = classify_stage(supported, "PASS")
    assert result == "SUPPORTED"
    assert counts["match_count"] == 5

    four = copy.deepcopy(supported)
    four[-1]["early_prediction"]["label"] = "opposite"
    four[-1]["prediction_match"] = False
    result, counts = classify_stage(four, "PASS")
    assert result == "INCONCLUSIVE"
    assert counts["match_count"] == 4

    three = copy.deepcopy(supported)
    for index in (-1, -2):
        three[index]["early_prediction"]["label"] = (
            "opposite" if three[index]["late_pair_label"] == "predicted" else "predicted"
        )
        three[index]["prediction_match"] = False
    result, counts = classify_stage(three, "PASS")
    assert result == "NOT_SUPPORTED"
    assert counts["match_count"] == 3

    print("SELF_TEST: PASS")
    print("STAGE: E1-E")
    print("HYPOTHESIS: H2 early EXPLORE predictor")
    print("EARLY_WINDOW_SECONDS: 0-30")
    print("LATE_WINDOW_SECONDS: >30-180")
    print("PAIR_COUNT: 5")
    print("RUN_COUNT: 10")
    print("SCIENTIFIC_RESULTS: SUPPORTED | NOT_SUPPORTED | INCONCLUSIVE")
    print("INVALID_STAGE_RESULT: NONE")
    print("PRODUCTION_RUNTIME_MUTATION: NONE")


def apparatus_preflight(repo: Path) -> int:
    if not REGISTRATION_PATH.is_file():
        raise PredictorError(f"Missing registration: {REGISTRATION_PATH}")
    if sha256_file(REGISTRATION_PATH) != REGISTRATION_SHA256:
        raise PredictorError("Registration SHA mismatch.")
    if not SEED_MANIFEST_PATH.is_file() or sha256_file(SEED_MANIFEST_PATH) != SEED_MANIFEST_SHA256:
        raise PredictorError("Seed manifest missing or hash mismatch.")
    if not REGISTRATION_LOCK_PATH.is_file() or sha256_file(REGISTRATION_LOCK_PATH) != REGISTRATION_LOCK_SHA256:
        raise PredictorError("Registration lock missing or hash mismatch.")

    reg = load_json(REGISTRATION_PATH)
    seeds, runtime_commit = validate_registration(reg)

    density = load_density_helper(repo)
    configure_density_for_e1e(density)
    helper = density.load_h1a_helper(repo)
    density.configure_helper(helper, repo, runtime_commit, seeds[0])
    install_predictor_metrics(density, helper)

    # Compile/startup-only preflight inherited from E1-D; no 180 s scientific run.
    d3 = helper.load_d3_helper(repo)
    godot = helper.discover_godot(repo)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = EVIDENCE_ROOT / f"e1-e-apparatus-preflight-{stamp}-{runtime_commit[:7]}"
    root.mkdir(parents=True, exist_ok=False)

    results: dict[str, Any] = {}
    for arm_id in ("rich", "sparse"):
        sandbox = root / f"sandbox_{arm_id}"
        save_path = root / f"{arm_id}.json"
        stdout_path = root / f"{arm_id}.stdout.txt"
        stderr_path = root / f"{arm_id}.stderr.txt"
        helper.arm_snapshot(SOURCE_SNAPSHOT, save_path, list(PRIMARY_POSITION))
        helper.run(["git", "worktree", "add", "--detach", str(sandbox), runtime_commit], cwd=repo, timeout=120)
        try:
            helper._e1d_current_arm = arm_id
            hashes = helper.write_instrumented_runtime(repo, sandbox, d3)
            command = [
                str(godot),
                "--headless",
                "--path", str(sandbox),
                "--",
                "--smoke",
                f"--save-path={save_path}",
                "--quit-after=2",
            ]
            try:
                cp = subprocess.run(
                    command,
                    cwd=sandbox,
                    text=True,
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                )
                stdout_path.write_text(cp.stdout, encoding="utf-8")
                stderr_path.write_text(cp.stderr, encoding="utf-8")
                status = "PASS" if cp.returncode == 0 else "FAIL"
                returncode = cp.returncode
            except subprocess.TimeoutExpired as exc:
                stdout = exc.stdout or ""
                stderr = exc.stderr or ""
                if isinstance(stdout, bytes):
                    stdout = stdout.decode("utf-8", errors="replace")
                if isinstance(stderr, bytes):
                    stderr = stderr.decode("utf-8", errors="replace")
                stdout_path.write_text(str(stdout), encoding="utf-8")
                stderr_path.write_text(str(stderr), encoding="utf-8")
                status = "TIMEOUT"
                returncode = None

            results[arm_id] = {
                "status": status,
                "returncode": returncode,
                "instrumented_runtime_sha256": hashes,
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
            }
            if status != "PASS":
                raise PredictorError(
                    f"{arm_id} apparatus compile/startup preflight {status}; see {stderr_path}"
                )
        finally:
            helper._e1d_current_arm = ""
            helper.remove_worktree(repo, sandbox)

    report = {
        "stage": STAGE,
        "purpose": "apparatus instrumentation materialization preflight only; no scientific run",
        "runtime_commit": runtime_commit,
        "registration_sha256": REGISTRATION_SHA256,
        "results": results,
        "scientific_result": None,
        "execution_started": False,
        "production_runtime_mutation": "none",
    }
    report_path = root / "preflight-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("=" * 72)
    print("E1-E APPARATUS PREFLIGHT: PASS")
    print(f"EVIDENCE: {root}")
    print("RICH_COMPILE_STARTUP: PASS")
    print("SPARSE_COMPILE_STARTUP: PASS")
    print("SCIENTIFIC_RUN: NOT PERFORMED")
    print("SCIENTIFIC_RESULT: NONE")
    print(f"REPORT: {report_path}")
    print("=" * 72)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="E1-E H2 prospective early-EXPLORE predictor harness.")
    parser.add_argument("--repo", default=str(REPO_DEFAULT))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--apparatus-preflight", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    self_test()
    repo = Path(args.repo).resolve()

    if args.apparatus_preflight:
        return apparatus_preflight(repo)

    for path, expected, label in (
        (REGISTRATION_PATH, REGISTRATION_SHA256, "registration"),
        (SEED_MANIFEST_PATH, SEED_MANIFEST_SHA256, "seed manifest"),
        (REGISTRATION_LOCK_PATH, REGISTRATION_LOCK_SHA256, "registration lock"),
        (SOURCE_SNAPSHOT, SOURCE_SNAPSHOT_SHA256, "source snapshot"),
    ):
        if not path.is_file():
            raise PredictorError(f"Missing {label}: {path}")
        if sha256_file(path) != expected:
            raise PredictorError(f"{label} SHA mismatch.")

    reg = load_json(REGISTRATION_PATH)
    seeds, runtime_commit = validate_registration(reg)

    density = load_density_helper(repo)
    configure_density_for_e1e(density)
    helper = density.load_h1a_helper(repo)
    if density.git_output(helper, repo, ["git", "cat-file", "-t", runtime_commit]) != "commit":
        raise PredictorError(f"Registered runtime commit unavailable: {runtime_commit}")

    install_predictor_metrics(density, helper)
    godot = helper.discover_godot(repo)
    python_exe = helper.discover_python()
    d3 = helper.load_d3_helper(repo)

    experiment_name = (
        f"e1-e-h2-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{runtime_commit[:7]}"
    )
    root = EVIDENCE_ROOT / experiment_name
    root.mkdir(parents=True, exist_ok=False)

    rich_source, sparse_source = density.derive_arm_sources(helper, SOURCE_SNAPSHOT, root)
    rich_source_sha = sha256_file(rich_source)
    sparse_source_sha = sha256_file(sparse_source)

    config = {
        "stage": STAGE,
        "experiment_id": experiment_name,
        "registration_path": str(REGISTRATION_PATH),
        "registration_sha256": REGISTRATION_SHA256,
        "seed_manifest_sha256": SEED_MANIFEST_SHA256,
        "registration_lock_sha256": REGISTRATION_LOCK_SHA256,
        "runtime_commit": runtime_commit,
        "accepted_source_snapshot_sha256": SOURCE_SNAPSHOT_SHA256,
        "seed_set": seeds,
        "pair_count": 5,
        "run_count": 10,
        "early_window_sim_seconds": [0.0, 30.0],
        "late_window_sim_seconds": [30.0, 180.0],
        "predictor_metric": "selected_explore_proportion",
        "predictor_contrast": "sparse_minus_rich",
        "rich_source_sha256": rich_source_sha,
        "sparse_source_sha256": sparse_source_sha,
        "production_runtime_mutation": "none",
        "neural_policy_change": "none",
        "learning_rule_change": "none",
    }
    (root / "experiment-config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=" * 72, flush=True)
    print("E1-E H2 PROSPECTIVE EARLY-EXPLORE PREDICTOR", flush=True)
    print(f"EVIDENCE: {root}", flush=True)
    print(f"RUNTIME_COMMIT: {runtime_commit}", flush=True)
    print("SEEDS: " + ",".join(map(str, seeds)), flush=True)
    print("EARLY_WINDOW: 0-30 s", flush=True)
    print("LATE_WINDOW: >30-180 s", flush=True)
    print("=" * 72, flush=True)

    pairs: list[dict[str, Any]] = []
    for index, seed in enumerate(seeds, 1):
        density.configure_helper(helper, repo, runtime_commit, seed)
        pair_root = root / f"seed_{seed}"
        pair_root.mkdir(parents=True, exist_ok=False)
        print(f"PAIR {index}/5 — SEED {seed}", flush=True)

        rich = density.run_arm_safe(
            helper,
            repo=repo,
            d3=d3,
            pair_root=pair_root,
            source=rich_source,
            source_sha=rich_source_sha,
            arm_id="rich",
            godot=godot,
            python_exe=python_exe,
        )
        print(f"  RICH: {rich['status']}", flush=True)

        sparse = density.run_arm_safe(
            helper,
            repo=repo,
            d3=d3,
            pair_root=pair_root,
            source=sparse_source,
            source_sha=sparse_source_sha,
            arm_id="sparse",
            godot=godot,
            python_exe=python_exe,
        )
        print(f"  SPARSE: {sparse['status']}", flush=True)

        validity = "PASS"
        reasons: list[str] = []
        if rich["status"] != "PASS":
            validity = "INVALID"
            reasons.append("rich run invalid")
        if sparse["status"] != "PASS":
            validity = "INVALID"
            reasons.append("sparse run invalid")

        if validity == "PASS":
            rich_masked = density.mask_peer_presence(rich["initial"])
            sparse_masked = density.mask_peer_presence(sparse["initial"])
            if helper.canonical_hash(rich_masked) != helper.canonical_hash(sparse_masked):
                validity = "INVALID"
                reasons.append("arm start states differ outside peer-resource presence")

        if validity == "PASS":
            if not rich["metrics"]["neural_authority_integrity"]:
                validity = "INVALID"
                reasons.append("rich neural authority integrity failed")
            if not sparse["metrics"]["neural_authority_integrity"]:
                validity = "INVALID"
                reasons.append("sparse neural authority integrity failed")

        early = None
        directions: dict[str, str] = {}
        late_summary = None
        match = False
        if validity == "PASS":
            early = early_prediction(rich["metrics"], sparse["metrics"])
            directions = late_metric_directions(rich["metrics"], sparse["metrics"])
            late_summary = late_pair_label(directions)
            match = (
                early["label"] != "neutral"
                and late_summary["label"] != "neutral"
                and early["label"] == late_summary["label"]
            )

        pair = {
            "seed": seed,
            "pair_index": index,
            "pair_validity": validity,
            "validity_reasons": reasons,
            "rich": rich,
            "sparse": sparse,
            "early_prediction": early,
            "late_primary_metric_directions": directions,
            "late_pair_summary": late_summary,
            "late_pair_label": None if late_summary is None else late_summary["label"],
            "prediction_match": match,
        }
        pair_path = pair_root / "pair-comparison.json"
        pair_path.write_text(json.dumps(pair, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        pair["pair_comparison_path"] = str(pair_path)
        pair["pair_comparison_sha256"] = sha256_file(pair_path)
        pairs.append(pair)
        print(f"  PAIR_VALIDITY: {validity}", flush=True)

    stage_validity = (
        "PASS"
        if len(pairs) == 5 and all(pair["pair_validity"] == "PASS" for pair in pairs)
        else "INVALID"
    )
    hypothesis_result, counts = classify_stage(pairs, stage_validity)

    summary = {
        "stage": STAGE,
        "experiment_id": experiment_name,
        "runtime_commit": runtime_commit,
        "registration_sha256": REGISTRATION_SHA256,
        "seed_manifest_sha256": SEED_MANIFEST_SHA256,
        "registration_lock_sha256": REGISTRATION_LOCK_SHA256,
        "accepted_source_snapshot_sha256": SOURCE_SNAPSHOT_SHA256,
        "stage_validity": stage_validity,
        "hypothesis_result": hypothesis_result,
        "seed_set": seeds,
        "pair_count_declared": 5,
        "pair_count_completed": len(pairs),
        "run_count_declared": 10,
        "pairs": pairs,
        "hypothesis_counts": counts,
        "early_predictor": {
            "metric": "selected_explore_proportion",
            "window_sim_seconds": [0.0, 30.0],
            "contrast": "sparse_minus_rich",
        },
        "late_outcome_window_sim_seconds": [30.0, 180.0],
        "production_runtime_mutation": "none",
        "neural_policy_change": "none",
        "learning_rule_change": "none",
    }
    summary_path = root / "early-predictor-summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_sha = sha256_file(summary_path)

    print("=" * 72, flush=True)
    print("STATUS: PASS" if stage_validity == "PASS" else "STATUS: INVALID", flush=True)
    print(f"STAGE_VALIDITY: {stage_validity}", flush=True)
    print(f"HYPOTHESIS_RESULT: {hypothesis_result}", flush=True)
    print("HYPOTHESIS_COUNTS: " + json.dumps(counts, sort_keys=True), flush=True)
    print(f"SUMMARY: {summary_path}", flush=True)
    print(f"SUMMARY_SHA256: {summary_sha}", flush=True)
    print(f"EVIDENCE: {root}", flush=True)
    print("PRODUCTION_RUNTIME_MUTATION: NONE", flush=True)
    print("NEURAL_POLICY_CHANGE: NONE", flush=True)
    print("LEARNING_RULE_CHANGE: NONE", flush=True)
    print("=" * 72, flush=True)
    return 0 if stage_validity == "PASS" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PredictorError as exc:
        print("STATUS: BLOCKED", file=sys.stderr)
        print(f"BLOCKER: {exc}", file=sys.stderr)
        raise SystemExit(2)
