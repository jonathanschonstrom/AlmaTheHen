from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_DEFAULT = Path(os.environ.get("BIRDAI_REPO", r"C:\AlmaTheHen"))
STAGE = "E1-D-H1b"
REGISTRATION_PATH = Path(
    os.environ.get(
        "BIRDAI_E1_D_REGISTRATION",
        r"C:\BirdAI_E1_evidence\registrations\e1-d-h1b-resource-density-v1.json",
    )
)
REGISTRATION_SHA256 = "b35a58950e1ba12f2e6006b817cbaa04d16926baca0d37272f04cbe8f0c0a88c"
SOURCE_SNAPSHOT = Path(
    os.environ.get(
        "BIRDAI_E1_SOURCE_SNAPSHOT",
        r"C:\BirdAI_E1_evidence\source-snapshots\e1-a1-bootstrap-ab186b5.json",
    )
)
SOURCE_SNAPSHOT_SHA256 = "3b42d55fc595bc7312e932dc9615c08e1ce2abe72f0f2bcc0984e9818e47b218"
EVIDENCE_ROOT = Path(
    os.environ.get("BIRDAI_E1_EVIDENCE_ROOT", r"C:\BirdAI_E1_evidence")
)

H1A_HELPER_REL = ".birdai/e1_b_h1a_resource_distance.py"
WORLD_REL = "scripts/world/world_state.gd"
TESTED_RESOURCE_ID = "o1"
PEER_RESOURCE_ID = "e1d_food_peer"
PRIMARY_POSITION = [-4.0, 0.0, 0.0]
PEER_POSITION = [4.0, 0.0, 0.0]
PRIMARY_METRICS = (
    "time_to_first_valid_food_interaction_seconds",
    "total_distance_travelled_m",
    "selected_explore_proportion",
    "food_acquisition_rate_per_sim_minute",
)


class DensityError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DensityError(f"Missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DensityError(f"Invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DensityError(f"JSON root is not an object: {path}")
    return value


def load_h1a_helper(repo: Path):
    path = repo / H1A_HELPER_REL
    if not path.is_file():
        raise DensityError(f"Missing accepted H1a helper: {path}")
    spec = importlib.util.spec_from_file_location("e1_b_h1a_helper_for_e1d", path)
    if spec is None or spec.loader is None:
        raise DensityError("Could not import accepted H1a helper.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def git_output(helper, repo: Path, args: list[str]) -> str:
    return helper.run(args, cwd=repo).stdout.strip()


def normalize_position(value: Any, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise DensityError(f"{label} must be [x,y,z], got {value!r}")
    try:
        result = [float(x) for x in value]
    except (TypeError, ValueError) as exc:
        raise DensityError(f"{label} contains non-numeric values: {value!r}") from exc
    if not all(math.isfinite(x) for x in result):
        raise DensityError(f"{label} contains non-finite values: {value!r}")
    return result


def validate_registration(reg: dict[str, Any]) -> tuple[list[int], str]:
    if reg.get("experiment") != "E1-D-H1b-resource-density-v1":
        raise DensityError(f"Unexpected experiment id: {reg.get('experiment')!r}")
    if reg.get("stage") != "E1-D":
        raise DensityError(f"Unexpected stage: {reg.get('stage')!r}")
    if reg.get("hypothesis_id") != "H1b":
        raise DensityError(f"Unexpected hypothesis id: {reg.get('hypothesis_id')!r}")

    runtime_commit = str(reg.get("runtime_commit_at_registration", ""))
    if len(runtime_commit) != 40:
        raise DensityError("Invalid runtime_commit_at_registration.")

    seeds = reg.get("seed_set")
    if (
        not isinstance(seeds, list)
        or len(seeds) != 5
        or len(set(seeds)) != 5
        or not all(isinstance(seed, int) and 0 < seed < 2**31 for seed in seeds)
    ):
        raise DensityError(f"Invalid seed set: {seeds!r}")

    iv = reg.get("independent_variable", {})
    if iv.get("name") != "tested_food_resource_count_density":
        raise DensityError("Independent variable does not match registered H1b.")
    if iv.get("allowed_environment_differences") != [
        f"world.objects.{PEER_RESOURCE_ID} presence"
    ]:
        raise DensityError("Allowed environment difference is not exact.")

    geometry = reg.get("geometry", {})
    if normalize_position(
        geometry.get("primary_tested_resource_position"),
        "geometry.primary_tested_resource_position",
    ) != PRIMARY_POSITION:
        raise DensityError("Primary tested resource position changed.")
    if normalize_position(
        geometry.get("peer_resource_position"),
        "geometry.peer_resource_position",
    ) != PEER_POSITION:
        raise DensityError("Peer resource position changed.")
    if not bool(geometry.get("distance_constant_across_arms")):
        raise DensityError("Registration does not hold distance constant.")

    arms = reg.get("arms")
    if not isinstance(arms, list) or len(arms) != 2:
        raise DensityError("Registration must contain exactly rich and sparse arms.")
    by_id = {str(arm.get("arm_id")): arm for arm in arms if isinstance(arm, dict)}
    if set(by_id) != {"rich", "sparse"}:
        raise DensityError(f"Invalid density arm IDs: {sorted(by_id)}")
    if int(by_id["rich"].get("tested_resource_count", -1)) != 2:
        raise DensityError("Rich arm tested resource count is not 2.")
    if int(by_id["sparse"].get("tested_resource_count", -1)) != 1:
        raise DensityError("Sparse arm tested resource count is not 1.")

    if float(reg.get("run_horizon_sim_seconds", -1.0)) != 180.0:
        raise DensityError("Run horizon changed from 180 seconds.")

    source = reg.get("source_snapshot", {})
    if source.get("sha256") != SOURCE_SNAPSHOT_SHA256:
        raise DensityError("Registration source snapshot SHA mismatch.")

    return list(seeds), runtime_commit


def configure_helper(helper, repo: Path, runtime_commit: str, seed: int) -> None:
    helper.STAGE = STAGE
    helper.RUNTIME_COMMIT = runtime_commit
    helper.REGISTRATION_SHA256 = REGISTRATION_SHA256
    helper.NEURAL_SEED = seed
    helper.MAIN_BLOB = git_output(
        helper, repo, ["git", "rev-parse", f"{runtime_commit}:{helper.MAIN_REL}"]
    )
    helper.BRIDGE_BLOB = git_output(
        helper, repo, ["git", "rev-parse", f"{runtime_commit}:{helper.BRIDGE_REL}"]
    )
    helper.D3_HELPER_BLOB = git_output(
        helper, repo, ["git", "rev-parse", f"{runtime_commit}:{helper.D3_HELPER_REL}"]
    )


def mask_identity_and_position(resource: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(resource)
    clone["position"] = "__POSITION__"
    for key in ("id", "object_id", "uid", "name"):
        if key in clone:
            clone[key] = "__IDENTITY__"
    return clone


def make_peer_from_o1(o1: dict[str, Any]) -> dict[str, Any]:
    peer = copy.deepcopy(o1)
    peer["position"] = list(PEER_POSITION)
    for key in ("id", "object_id", "uid", "name"):
        if key in peer and str(peer[key]) == TESTED_RESOURCE_ID:
            peer[key] = PEER_RESOURCE_ID
    if mask_identity_and_position(peer) != mask_identity_and_position(o1):
        raise DensityError("Rich peer differs from o1 in tested resource properties.")
    return peer


def derive_arm_sources(helper, source: Path, root: Path) -> tuple[Path, Path]:
    _env, data = helper.decode_snapshot(source)
    objects = data.get("world", {}).get("objects")
    if not isinstance(objects, dict):
        raise DensityError("Source payload lacks world.objects mapping.")
    if TESTED_RESOURCE_ID not in objects:
        raise DensityError("Source payload lacks o1.")
    if PEER_RESOURCE_ID in objects:
        raise DensityError(f"Source unexpectedly already contains {PEER_RESOURCE_ID}.")

    o1 = objects[TESTED_RESOURCE_ID]
    if not isinstance(o1, dict):
        raise DensityError("o1 is not an object.")
    if normalize_position(o1.get("position"), "source o1.position") != PRIMARY_POSITION:
        raise DensityError("Source o1 position no longer matches registration.")

    sparse = copy.deepcopy(data)
    rich = copy.deepcopy(data)
    rich["world"]["objects"][PEER_RESOURCE_ID] = make_peer_from_o1(
        rich["world"]["objects"][TESTED_RESOURCE_ID]
    )

    sources = root / "derived_sources"
    sources.mkdir(parents=True, exist_ok=False)
    rich_path = sources / "rich.json"
    sparse_path = sources / "sparse.json"
    helper.write_snapshot(rich_path, rich)
    helper.write_snapshot(sparse_path, sparse)

    rich_written = helper.decode_snapshot(rich_path)[1]
    sparse_written = helper.decode_snapshot(sparse_path)[1]
    if PEER_RESOURCE_ID not in rich_written["world"]["objects"]:
        raise DensityError("Rich source lost the registered peer resource.")
    if PEER_RESOURCE_ID in sparse_written["world"]["objects"]:
        raise DensityError("Sparse source unexpectedly contains peer resource.")

    rich_masked = copy.deepcopy(rich_written)
    del rich_masked["world"]["objects"][PEER_RESOURCE_ID]
    if helper.canonical_hash(rich_masked) != helper.canonical_hash(sparse_written):
        raise DensityError(
            "Rich/sparse derived sources differ outside peer-resource presence."
        )

    return rich_path, sparse_path


def inject_peer_world_runtime(source: str) -> str:
    if PEER_RESOURCE_ID in source:
        raise DensityError(
            f"Throwaway world runtime unexpectedly already contains {PEER_RESOURCE_ID}."
        )
    anchor = "\tobjects.o1.stock = BOWL_CAPACITY\n"
    if source.count(anchor) != 1:
        raise DensityError(
            "Could not locate the pinned o1 initialization anchor in world_state.gd."
        )
    addition = (
        anchor
        + '\tobjects["e1d_food_peer"] = objects.o1.duplicate(true)\n'
        + '\tobjects["e1d_food_peer"]["id"] = "e1d_food_peer"\n'
        + '\tobjects["e1d_food_peer"]["position"] = Vector3(4.0, 0.0, 0.0)\n'
    )
    return source.replace(anchor, addition, 1)


def density_lightweight_bridge_state(instrumented: str) -> str:
    start_marker = "func e1_d3_state(agent) -> Dictionary:\n"
    end_marker = "func should_pause_simulation() -> bool:\n"
    start = instrumented.find(start_marker)
    end = instrumented.find(end_marker, start)
    if start < 0 or end < 0:
        raise DensityError(
            "Could not locate D3 state function for E1-D density instrumentation."
        )

    replacement = """func e1_d3_state(agent) -> Dictionary:
\tvar peer_present: bool = bool(agent.world.objects.has("e1d_food_peer"))
\tvar peer_stock: float = -1.0
\tvar peer_active: bool = false
\tif peer_present:
\t\tpeer_stock = float(agent.world.objects["e1d_food_peer"]["stock"])
\t\tpeer_active = bool(agent.world.objects["e1d_food_peer"]["active"])
\treturn {
\t\t"agent": {
\t\t\t"age": agent.age,
\t\t\t"position": [agent.position.x, agent.position.y, agent.position.z],
\t\t\t"distance_walked": agent.distance_walked,
\t\t\t"decision_count": agent.decision_count,
\t\t\t"last_causal_outcome": agent.last_causal_outcome.duplicate(true)
\t\t},
\t\t"world": {
\t\t\t"now": agent.world.now,
\t\t\t"o1_position": [
\t\t\t\tagent.world.objects.o1.position.x,
\t\t\t\tagent.world.objects.o1.position.y,
\t\t\t\tagent.world.objects.o1.position.z
\t\t\t],
\t\t\t"o1_stock": agent.world.objects.o1.stock,
\t\t\t"o1_active": agent.world.objects.o1.active,
\t\t\t"e1d_peer_present": peer_present,
\t\t\t"e1d_peer_stock": peer_stock,
\t\t\t"e1d_peer_active": peer_active
\t\t},
\t\t"phase": agent.phase,
\t\t"current_action": str(agent.current.get("action", "")),
\t\t"current_target": str(agent.current.get("target", "")),
\t\t"neural_selected_family": agent.neural_selected_family,
\t\t"neural_request_id": agent.neural_request_id
\t}
"""
    return instrumented[:start] + replacement + instrumented[end:]


def tested_stock(data: dict[str, Any]) -> tuple[float, dict[str, float]]:
    objects = data["world"]["objects"]
    stocks = {TESTED_RESOURCE_ID: float(objects[TESTED_RESOURCE_ID]["stock"])}
    if PEER_RESOURCE_ID in objects:
        stocks[PEER_RESOURCE_ID] = float(objects[PEER_RESOURCE_ID]["stock"])
    return sum(stocks.values()), stocks


def install_density_metrics(helper) -> None:
    original = helper.metrics_for_run
    original_write_instrumented_runtime = helper.write_instrumented_runtime

    def write_instrumented_runtime(repo: Path, sandbox: Path, d3):
        hashes = original_write_instrumented_runtime(repo, sandbox, d3)
        arm_id = str(getattr(helper, "_e1d_current_arm", ""))
        world_path = sandbox / WORLD_REL
        if arm_id == "rich":
            world_source = world_path.read_text(encoding="utf-8")
            patched_world = inject_peer_world_runtime(world_source)
            world_path.write_text(patched_world, encoding="utf-8", newline="\n")
            hashes[WORLD_REL] = sha256_file(world_path)
        elif arm_id == "sparse":
            if PEER_RESOURCE_ID in world_path.read_text(encoding="utf-8"):
                raise DensityError(
                    "Sparse throwaway runtime unexpectedly contains the E1-D peer."
                )
        else:
            raise DensityError(
                f"E1-D apparatus arm context is missing or invalid: {arm_id!r}"
            )
        return hashes

    def metrics_for_run(*, events, initial, final):
        base = original(events=events, initial=initial, final=final)
        initial_total, initial_stocks = tested_stock(initial)
        final_total, final_stocks = tested_stock(final)
        acquired = max(0.0, initial_total - final_total)

        first_tick = None
        initial_peer = initial_stocks.get(PEER_RESOURCE_ID)
        for event in events:
            if event.get("event") != "sim_state":
                continue
            world = event.get("state", {}).get("world", {})
            total = float(world["o1_stock"])
            if initial_peer is not None:
                if not bool(world.get("e1d_peer_present", False)):
                    raise DensityError(
                        "Rich trace lost registered e1d peer during simulation."
                    )
                total += float(world["e1d_peer_stock"])
            if total < initial_total - 1e-9:
                first_tick = int(event["sim_tick"])
                break

        base["time_to_first_valid_food_interaction_seconds"] = (
            None if first_tick is None else first_tick * helper.SIM_DT
        )
        base["first_food_acquisition_tick"] = first_tick
        base["food_acquisitions"] = acquired
        base["food_acquisition_rate_per_sim_minute"] = (
            acquired / (helper.RUN_HORIZON_SIM_SECONDS / 60.0)
        )
        base["tested_resource_initial_stocks"] = initial_stocks
        base["tested_resource_final_stocks"] = final_stocks
        base["tested_resource_initial_stock_total"] = initial_total
        base["tested_resource_final_stock_total"] = final_total
        return base

    helper.metrics_for_run = metrics_for_run
    helper.lightweight_bridge_state = density_lightweight_bridge_state
    helper.write_instrumented_runtime = write_instrumented_runtime


def mask_peer_presence(data: dict[str, Any]) -> dict[str, Any]:
    clone = copy.deepcopy(data)
    clone["world"]["objects"].pop(PEER_RESOURCE_ID, None)
    return clone


def run_one_arm(
    helper,
    *,
    repo: Path,
    d3,
    pair_root: Path,
    source: Path,
    source_sha: str,
    arm_id: str,
    godot: Path,
    python_exe: Path,
) -> dict[str, Any]:
    helper._e1d_current_arm = arm_id
    try:
        item = helper.run_arm(
            repo=repo,
            d3=d3,
            experiment_root=pair_root,
            source=source,
            source_sha=source_sha,
            arm={"arm_id": arm_id, "food_position": list(PRIMARY_POSITION)},
            godot=godot,
            python_exe=python_exe,
        )
    finally:
        helper._e1d_current_arm = ""
    return {
        "status": "PASS",
        "metrics": item["metrics"],
        "initial": item["initial"],
        "final": item["final"],
        "capsule_path": str(item["capsule_path"]),
        "capsule_sha256": sha256_file(item["capsule_path"]),
    }


def run_arm_safe(*args, **kwargs) -> dict[str, Any]:
    try:
        return run_one_arm(*args, **kwargs)
    except Exception as exc:
        return {
            "status": "INVALID",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def pair_direction_summary(directions: dict[str, str]) -> dict[str, Any]:
    predicted = sum(value == "predicted" for value in directions.values())
    opposite = sum(value == "opposite" for value in directions.values())
    neutral = sum(value == "neutral" for value in directions.values())
    return {
        "predicted_metric_count": predicted,
        "opposite_metric_count": opposite,
        "neutral_metric_count": neutral,
        "has_predicted": predicted > 0,
        "has_opposite": opposite > 0,
    }


def stage_hypothesis_result(
    pairs: list[dict[str, Any]],
    stage_validity: str,
) -> tuple[str | None, dict[str, Any]]:
    summaries = [
        pair_direction_summary(pair["primary_metric_directions"])
        for pair in pairs
        if pair.get("pair_validity") == "PASS"
    ]
    support_count = sum(bool(item["has_predicted"]) for item in summaries)
    opposite_count = sum(bool(item["has_opposite"]) for item in summaries)
    neutral_count = sum(
        not bool(item["has_predicted"]) and not bool(item["has_opposite"])
        for item in summaries
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
        return "SUPPORTED", counts
    if support_count > 0 and opposite_count > 0:
        return "SEED_SENSITIVE", counts
    if support_count < 3:
        return "NOT_SUPPORTED", counts
    return "INCONCLUSIVE", counts


def aggregate_numeric(
    pairs: list[dict[str, Any]],
    arm_id: str,
    metric: str,
) -> dict[str, Any]:
    values: list[float] = []
    censored = 0
    for pair in pairs:
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
        "sample_standard_deviation": (
            statistics.stdev(values) if len(values) >= 2 else None
        ),
    }


def self_test() -> None:
    sample_o1 = {
        "kind": "food",
        "position": list(PRIMARY_POSITION),
        "stock": 12.0,
        "active": True,
    }
    peer = make_peer_from_o1(sample_o1)
    assert peer["position"] == PEER_POSITION
    assert mask_identity_and_position(peer) == mask_identity_and_position(sample_o1)

    supported_pairs = [
        {
            "pair_validity": "PASS",
            "primary_metric_directions": {
                metric: "predicted" for metric in PRIMARY_METRICS
            },
        }
        for _ in range(5)
    ]
    result, counts = stage_hypothesis_result(supported_pairs, "PASS")
    assert result == "SUPPORTED"
    assert counts["support_count"] == 5

    sensitive = copy.deepcopy(supported_pairs)
    sensitive[-1]["primary_metric_directions"][PRIMARY_METRICS[0]] = "opposite"
    result, counts = stage_hypothesis_result(sensitive, "PASS")
    assert result == "SEED_SENSITIVE"
    assert counts["opposite_count"] == 1

    synthetic_bridge = (
        "func e1_d3_state(agent) -> Dictionary:\n"
        "\treturn {}\n"
        "func should_pause_simulation() -> bool:\n"
        "\treturn false\n"
    )
    bridge = density_lightweight_bridge_state(synthetic_bridge)
    assert "var peer_present: bool = bool(" in bridge
    assert "var peer_stock: float = -1.0" in bridge
    assert "var peer_active: bool = false" in bridge
    assert "peer_present :=" not in bridge

    synthetic_world = (
        "func _init() -> void:\n"
        "\tobjects.o1.stock = BOWL_CAPACITY\n"
    )
    rich_world = inject_peer_world_runtime(synthetic_world)
    assert 'objects["e1d_food_peer"] = objects.o1.duplicate(true)' in rich_world
    assert 'objects["e1d_food_peer"]["position"] = Vector3(4.0, 0.0, 0.0)' in rich_world

    print("SELF_TEST: PASS")
    print("STAGE: E1-D")
    print("HYPOTHESIS: H1b resource density")
    print("PAIR_COUNT: 5")
    print("RUN_COUNT: 10")
    print("RICH_RESOURCE_COUNT: 2")
    print("SPARSE_RESOURCE_COUNT: 1")
    print("PRIMARY_RESOURCE_DISTANCE_M: 4.0 in both arms")
    print("RESULTS: SUPPORTED | SEED_SENSITIVE | NOT_SUPPORTED | INCONCLUSIVE")
    print("INVALID_PAIR_POLICY: retained; stage INVALID")
    print("PRODUCTION_RUNTIME_MUTATION: NONE")


def apparatus_preflight(repo: Path) -> int:
    if not REGISTRATION_PATH.is_file():
        raise DensityError(f"Missing registration: {REGISTRATION_PATH}")
    if sha256_file(REGISTRATION_PATH) != REGISTRATION_SHA256:
        raise DensityError("Registration SHA mismatch during apparatus preflight.")

    registration = load_json(REGISTRATION_PATH)
    seeds, runtime_commit = validate_registration(registration)
    helper = load_h1a_helper(repo)
    configure_helper(helper, repo, runtime_commit, int(seeds[0]))
    install_density_metrics(helper)
    d3 = helper.load_d3_helper(repo)
    godot = helper.discover_godot(repo)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = EVIDENCE_ROOT / f"e1-d-apparatus-preflight-{stamp}-{runtime_commit[:7]}"
    root.mkdir(parents=True, exist_ok=False)
    results: dict[str, Any] = {}

    for arm_id in ("rich", "sparse"):
        sandbox = root / f"sandbox_{arm_id}"
        save_path = root / f"{arm_id}.json"
        stdout_path = root / f"{arm_id}.stdout.txt"
        stderr_path = root / f"{arm_id}.stderr.txt"

        helper.arm_snapshot(
            SOURCE_SNAPSHOT,
            save_path,
            list(PRIMARY_POSITION),
        )
        helper.run(
            ["git", "worktree", "add", "--detach", str(sandbox), runtime_commit],
            cwd=repo,
            timeout=120,
        )
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
                raise DensityError(
                    f"{arm_id} apparatus compile/startup preflight {status}; "
                    f"see {stderr_path}"
                )
        finally:
            helper._e1d_current_arm = ""
            helper.remove_worktree(repo, sandbox)

    report = {
        "stage": STAGE,
        "purpose": "apparatus compile/startup preflight only",
        "runtime_commit": runtime_commit,
        "registration_sha256": REGISTRATION_SHA256,
        "results": results,
        "scientific_result": None,
        "production_runtime_mutation": "none",
    }
    report_path = root / "preflight-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=" * 72)
    print("E1-D APPARATUS PREFLIGHT: PASS")
    print(f"EVIDENCE: {root}")
    print("RICH_COMPILE_STARTUP: PASS")
    print("SPARSE_COMPILE_STARTUP: PASS")
    print("RICH_PEER_RUNTIME_MATERIALIZATION: ENABLED_IN_THROWAWAY_RUNTIME")
    print("SCIENTIFIC_RESULT: NONE")
    print("PRODUCTION_RUNTIME_MUTATION: NONE")
    print(f"REPORT: {report_path}")
    print("=" * 72)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="E1-D H1b paired resource-density harness.")
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

    if not REGISTRATION_PATH.is_file():
        raise DensityError(f"Missing registration: {REGISTRATION_PATH}")
    actual_registration_sha = sha256_file(REGISTRATION_PATH)
    if actual_registration_sha != REGISTRATION_SHA256:
        raise DensityError(
            f"Registration SHA mismatch: {actual_registration_sha} != {REGISTRATION_SHA256}"
        )

    registration = load_json(REGISTRATION_PATH)
    seeds, runtime_commit = validate_registration(registration)

    if not SOURCE_SNAPSHOT.is_file():
        raise DensityError(f"Missing source snapshot: {SOURCE_SNAPSHOT}")
    if sha256_file(SOURCE_SNAPSHOT) != SOURCE_SNAPSHOT_SHA256:
        raise DensityError("Accepted source snapshot SHA mismatch.")

    helper = load_h1a_helper(repo)
    if git_output(helper, repo, ["git", "cat-file", "-t", runtime_commit]) != "commit":
        raise DensityError(f"Registered runtime commit unavailable: {runtime_commit}")

    install_density_metrics(helper)
    godot = helper.discover_godot(repo)
    python_exe = helper.discover_python()
    d3 = helper.load_d3_helper(repo)

    experiment_id = (
        f"e1-d-h1b-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{runtime_commit[:7]}"
    )
    root = EVIDENCE_ROOT / experiment_id
    root.mkdir(parents=True, exist_ok=False)

    rich_source, sparse_source = derive_arm_sources(helper, SOURCE_SNAPSHOT, root)
    rich_source_sha = sha256_file(rich_source)
    sparse_source_sha = sha256_file(sparse_source)

    config = {
        "stage": STAGE,
        "experiment_id": experiment_id,
        "registration_path": str(REGISTRATION_PATH),
        "registration_sha256": REGISTRATION_SHA256,
        "runtime_commit": runtime_commit,
        "accepted_source_snapshot": str(SOURCE_SNAPSHOT),
        "accepted_source_snapshot_sha256": SOURCE_SNAPSHOT_SHA256,
        "rich_source_sha256": rich_source_sha,
        "sparse_source_sha256": sparse_source_sha,
        "seed_set": seeds,
        "pair_count": 5,
        "run_count": 10,
        "independent_variable": "tested_food_resource_count_density",
        "rich_resource_count": 2,
        "sparse_resource_count": 1,
        "primary_resource_position": PRIMARY_POSITION,
        "peer_resource_position": PEER_POSITION,
        "production_runtime_mutation": "none",
    }
    (root / "experiment-config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=" * 72, flush=True)
    print("E1-D H1b PAIRED RESOURCE-DENSITY EXPERIMENT", flush=True)
    print(f"EVIDENCE: {root}", flush=True)
    print(f"RUNTIME_COMMIT: {runtime_commit}", flush=True)
    print("SEEDS: " + ",".join(map(str, seeds)), flush=True)
    print("PAIR_COUNT: 5", flush=True)
    print("RUN_COUNT: 10", flush=True)
    print("=" * 72, flush=True)

    pairs: list[dict[str, Any]] = []

    for index, seed in enumerate(seeds, 1):
        configure_helper(helper, repo, runtime_commit, seed)
        pair_root = root / f"seed_{seed}"
        pair_root.mkdir(parents=True, exist_ok=False)
        print(f"PAIR {index}/5 — SEED {seed}", flush=True)

        rich = run_arm_safe(
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

        sparse = run_arm_safe(
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

        pair_validity = "PASS"
        reasons: list[str] = []
        directions: dict[str, str] = {}

        if rich["status"] != "PASS":
            pair_validity = "INVALID"
            reasons.append("rich run invalid")
        if sparse["status"] != "PASS":
            pair_validity = "INVALID"
            reasons.append("sparse run invalid")

        if pair_validity == "PASS":
            rich_masked = mask_peer_presence(rich["initial"])
            sparse_masked = mask_peer_presence(sparse["initial"])
            if helper.canonical_hash(rich_masked) != helper.canonical_hash(sparse_masked):
                pair_validity = "INVALID"
                reasons.append("arm start states differ outside peer-resource presence")

        if pair_validity == "PASS":
            rich_objects = rich["initial"]["world"]["objects"]
            sparse_objects = sparse["initial"]["world"]["objects"]
            if PEER_RESOURCE_ID not in rich_objects:
                pair_validity = "INVALID"
                reasons.append("rich arm lacks peer resource")
            if PEER_RESOURCE_ID in sparse_objects:
                pair_validity = "INVALID"
                reasons.append("sparse arm unexpectedly contains peer resource")

        if pair_validity == "PASS":
            if not rich["metrics"]["neural_authority_integrity"]:
                pair_validity = "INVALID"
                reasons.append("rich neural authority integrity failed")
            if not sparse["metrics"]["neural_authority_integrity"]:
                pair_validity = "INVALID"
                reasons.append("sparse neural authority integrity failed")

        if pair_validity == "PASS":
            directions = helper.metric_direction(rich["metrics"], sparse["metrics"])

        pair = {
            "seed": seed,
            "pair_index": index,
            "pair_validity": pair_validity,
            "validity_reasons": reasons,
            "rich": rich,
            "sparse": sparse,
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
        print(f"  PAIR_VALIDITY: {pair_validity}", flush=True)

    stage_validity = (
        "PASS"
        if len(pairs) == 5
        and all(pair["pair_validity"] == "PASS" for pair in pairs)
        else "INVALID"
    )
    hypothesis_result, counts = stage_hypothesis_result(pairs, stage_validity)

    aggregates = {
        metric: {
            "rich": aggregate_numeric(pairs, "rich", metric),
            "sparse": aggregate_numeric(pairs, "sparse", metric),
        }
        for metric in PRIMARY_METRICS
    }

    summary = {
        "stage": STAGE,
        "experiment_id": experiment_id,
        "runtime_commit": runtime_commit,
        "registration_sha256": REGISTRATION_SHA256,
        "accepted_source_snapshot_sha256": SOURCE_SNAPSHOT_SHA256,
        "stage_validity": stage_validity,
        "hypothesis_result": hypothesis_result,
        "seed_set": seeds,
        "pair_count_declared": 5,
        "pair_count_completed": len(pairs),
        "run_count_declared": 10,
        "pairs": pairs,
        "hypothesis_counts": counts,
        "aggregates": aggregates,
        "independent_variable": "tested_food_resource_count_density",
        "rich_resource_count": 2,
        "sparse_resource_count": 1,
        "primary_resource_distance_m": 4.0,
        "peer_resource_distance_m": 4.0,
        "new_independent_variables": "resource count/density only",
        "production_runtime_mutation": "none",
        "neural_policy_change": "none",
        "learning_rule_change": "none",
    }
    summary_path = root / "density-summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
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
    except DensityError as exc:
        print("STATUS: BLOCKED", file=sys.stderr)
        print(f"BLOCKER: {exc}", file=sys.stderr)
        raise SystemExit(2)
    except Exception as exc:
        print("STATUS: BLOCKED", file=sys.stderr)
        print(f"BLOCKER: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
