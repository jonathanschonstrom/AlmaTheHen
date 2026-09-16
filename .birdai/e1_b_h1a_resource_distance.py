from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STAGE = "E1-B-H1a"
RUNTIME_COMMIT = "2b7326823026cc4ba9d1f35570c6ecaa6873ca2d"
D3_HELPER_REL = ".birdai/e1_a1_d3_barrier_scheduling_diagnostic.py"
D3_HELPER_BLOB = "939fc43af6a37c4b00cdad44e8fb8ea96c27b218"
MAIN_REL = "scripts/main.gd"
MAIN_BLOB = "66daffb205d680e64d55b314a6c9a92bfe98a0c3"
BRIDGE_REL = "scripts/cognition/neural_brain_bridge.gd"
BRIDGE_BLOB = "b7fd20af2f92f9156d8db5d820e2592e8b62c9a0"
REGISTRATION_SHA256 = "febb899324126253c046b5828d47dd09a7cbc0bfb7c8112e587d68ec175cd1c5"

REGISTRATION_PATH = Path(
    os.environ.get(
        "BIRDAI_E1_H1A_REGISTRATION",
        r"C:\BirdAI_E1_evidence\registrations\e1-b-h1a-resource-distance-v1.json",
    )
)
SOURCE_SNAPSHOT = Path(
    os.environ.get(
        "BIRDAI_E1_SOURCE_SNAPSHOT",
        r"C:\BirdAI_E1_evidence\source-snapshots\e1-a1-bootstrap-ab186b5.json",
    )
)
EVIDENCE_ROOT = Path(
    os.environ.get("BIRDAI_E1_EVIDENCE_ROOT", r"C:\BirdAI_E1_evidence")
)

NEURAL_SEED = 20260910
SIM_DT = 1.0 / 60.0
RUN_HORIZON_SIM_SECONDS = 180.0
STOP_TICK = int(round(RUN_HORIZON_SIM_SECONDS / SIM_DT))
REQUEST_START_TICK = 240
REQUEST_INTERVAL_TICKS = 18
GATE_DELAY_TICKS = 12
WALL_TIMEOUT_SECONDS = 900

ACTIONS = ("FLEE", "DRINK", "EAT", "REST", "SOCIAL", "CARE", "EXPLORE", "MANIPULATE")


class ExperimentError(RuntimeError):
    pass


def run(args, *, cwd, env=None, timeout=None, check=True):
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if check and result.returncode != 0:
        raise ExperimentError(
            f"Command failed ({result.returncode}): {' '.join(map(str, args))}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def git_blob(repo: Path, commit: str, rel: str) -> str:
    result = run(
        ["git", "rev-parse", f"{commit}:{rel}"],
        cwd=repo,
        check=False,
    )
    if result.returncode != 0:
        raise ExperimentError(
            f"Cannot resolve git blob {commit}:{rel}: {result.stderr}"
        )
    return result.stdout.strip()


def git_show(repo: Path, commit: str, rel: str) -> str:
    result = run(
        ["git", "show", f"{commit}:{rel}"],
        cwd=repo,
        check=False,
    )
    if result.returncode != 0:
        raise ExperimentError(
            f"Cannot read {commit}:{rel}: {result.stderr}"
        )
    return result.stdout.replace("\r\n", "\n").replace("\r", "\n")


def load_d3_helper(repo: Path):
    path = repo / D3_HELPER_REL
    if not path.is_file():
        raise ExperimentError(f"Missing accepted D3 helper: {path}")
    actual_blob = git_blob(repo, RUNTIME_COMMIT, D3_HELPER_REL)
    if actual_blob != D3_HELPER_BLOB:
        raise ExperimentError(
            f"D3 helper blob mismatch: {actual_blob} != {D3_HELPER_BLOB}"
        )
    spec = importlib.util.spec_from_file_location("e1_a1_d3_helper", path)
    if spec is None or spec.loader is None:
        raise ExperimentError("Could not import accepted D3 helper.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def discover_godot(repo: Path) -> Path:
    candidates = []
    if os.environ.get("GODOT_EXE"):
        candidates.append(Path(os.environ["GODOT_EXE"]))
    candidates += [
        repo / "tools" / "Godot.exe",
        repo / "tools" / "Godot_console.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ExperimentError("Godot executable not found; expected tools\\Godot.exe or GODOT_EXE.")


def discover_python() -> Path:
    candidates = []
    if os.environ.get("BIRDAI_PYTHON"):
        candidates.append(Path(os.environ["BIRDAI_PYTHON"]))
    candidates.append(Path(r"C:\BirdAI_P1_env\Scripts\python.exe"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ExperimentError("Canonical BirdAI Python executable not found.")


def wait_port_free(port: int = 39393, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.25)
        try:
            code = sock.connect_ex(("127.0.0.1", port))
        finally:
            sock.close()
        if code != 0:
            return
        time.sleep(0.1)
    raise ExperimentError(f"TCP port {port} remained occupied.")


def remove_worktree(repo: Path, worktree: Path) -> None:
    run(
        ["git", "worktree", "remove", "--force", str(worktree)],
        cwd=repo,
        check=False,
        timeout=120,
    )
    if worktree.exists():
        shutil.rmtree(worktree, ignore_errors=True)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ExperimentError(f"Missing JSONL trace: {path}")
    events = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ExperimentError(f"Invalid JSONL {path}:{line_no}: {exc}") from exc
        if not isinstance(value, dict):
            raise ExperimentError(f"Non-object JSONL event at {path}:{line_no}")
        events.append(value)
    if not events:
        raise ExperimentError(f"Empty trace: {path}")
    return events


def decode_snapshot(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("payload"), str):
        raise ExperimentError(f"Snapshot is not a persistence envelope: {path}")
    payload_text = raw["payload"]
    payload_sha = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
    if payload_sha != str(raw.get("sha256", "")):
        raise ExperimentError(f"Snapshot payload checksum mismatch: {path}")
    data = json.loads(payload_text)
    if not isinstance(data, dict):
        raise ExperimentError(f"Snapshot payload root is not an object: {path}")
    return raw, data


def write_snapshot(path: Path, data: dict[str, Any]) -> None:
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    envelope = {
        "payload": payload,
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }
    path.write_text(
        json.dumps(envelope, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def normalize_position(value: Any, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ExperimentError(f"{label} must be [x,y,z], got {value!r}")
    return [float(value[0]), float(value[1]), float(value[2])]


def environment_without_o1_position(data: dict[str, Any]) -> dict[str, Any]:
    cloned = copy.deepcopy(data)
    try:
        cloned["world"]["objects"]["o1"]["position"] = "__REGISTERED_VARIABLE__"
    except Exception as exc:
        raise ExperimentError("Snapshot lacks world.objects.o1.position") from exc
    return cloned


def arm_snapshot(
    source: Path,
    destination: Path,
    registered_position: list[float],
) -> dict[str, Any]:
    _envelope, data = decode_snapshot(source)
    data = copy.deepcopy(data)
    data["world"]["objects"]["o1"]["position"] = list(registered_position)
    write_snapshot(destination, data)
    _written_envelope, written = decode_snapshot(destination)
    actual = normalize_position(
        written["world"]["objects"]["o1"]["position"],
        "derived world.objects.o1.position",
    )
    if actual != [float(x) for x in registered_position]:
        raise ExperimentError(
            f"Derived arm position mismatch: {actual} != {registered_position}"
        )
    return written


def lightweight_bridge_state(instrumented: str) -> str:
    start_marker = "func e1_d3_state(agent) -> Dictionary:\n"
    end_marker = "func should_pause_simulation() -> bool:\n"
    start = instrumented.find(start_marker)
    end = instrumented.find(end_marker, start)
    if start < 0 or end < 0:
        raise ExperimentError("Could not locate D3 state function for lightweight H1a trace.")

    replacement = '''func e1_d3_state(agent) -> Dictionary:
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
\t\t\t"o1_active": agent.world.objects.o1.active
\t\t},
\t\t"phase": agent.phase,
\t\t"current_action": str(agent.current.get("action", "")),
\t\t"current_target": str(agent.current.get("target", "")),
\t\t"neural_selected_family": agent.neural_selected_family,
\t\t"neural_request_id": agent.neural_request_id
\t}

'''
    return instrumented[:start] + replacement + instrumented[end:]


def write_instrumented_runtime(repo: Path, sandbox: Path, d3) -> dict[str, str]:
    main_blob = git_blob(repo, RUNTIME_COMMIT, MAIN_REL)
    bridge_blob = git_blob(repo, RUNTIME_COMMIT, BRIDGE_REL)
    if main_blob != MAIN_BLOB:
        raise ExperimentError(f"{MAIN_REL} blob mismatch: {main_blob} != {MAIN_BLOB}")
    if bridge_blob != BRIDGE_BLOB:
        raise ExperimentError(f"{BRIDGE_REL} blob mismatch: {bridge_blob} != {BRIDGE_BLOB}")

    main_source = git_show(repo, RUNTIME_COMMIT, MAIN_REL)
    bridge_source = git_show(repo, RUNTIME_COMMIT, BRIDGE_REL)

    instrumented_main = d3.instrument_main(main_source)
    instrumented_bridge = lightweight_bridge_state(d3.instrument_bridge(bridge_source))

    main_path = sandbox / MAIN_REL
    bridge_path = sandbox / BRIDGE_REL
    main_path.write_text(instrumented_main, encoding="utf-8", newline="\n")
    bridge_path.write_text(instrumented_bridge, encoding="utf-8", newline="\n")

    return {
        MAIN_REL: sha256_file(main_path),
        BRIDGE_REL: sha256_file(bridge_path),
    }


def new_episodes(initial: dict[str, Any], final: dict[str, Any]) -> list[dict[str, Any]]:
    initial_eps = initial.get("agent", {}).get("memory", {}).get("episodes", [])
    final_eps = final.get("agent", {}).get("memory", {}).get("episodes", [])
    if not isinstance(initial_eps, list) or not isinstance(final_eps, list):
        raise ExperimentError("Agent memory episodes are not lists.")
    if len(final_eps) < len(initial_eps):
        raise ExperimentError("Final episode count is smaller than initial episode count.")
    return [
        episode
        for episode in final_eps[len(initial_eps):]
        if isinstance(episode, dict)
    ]


def argmax_mapping(values: Any) -> str:
    if not isinstance(values, dict) or not values:
        return ""
    candidates = [
        (str(name), float(value))
        for name, value in values.items()
        if str(name) in ACTIONS
    ]
    if not candidates:
        return ""
    return max(candidates, key=lambda item: item[1])[0]


def metrics_for_run(
    *,
    events: list[dict[str, Any]],
    initial: dict[str, Any],
    final: dict[str, Any],
) -> dict[str, Any]:
    sim_events = [event for event in events if event.get("event") == "sim_state"]
    if len(sim_events) != STOP_TICK:
        raise ExperimentError(
            f"Expected {STOP_TICK} sim_state events, found {len(sim_events)}."
        )
    ticks = [int(event["sim_tick"]) for event in sim_events]
    if ticks != list(range(1, STOP_TICK + 1)):
        raise ExperimentError("Simulation trace tick sequence is not complete.")

    initial_stock = float(initial["world"]["objects"]["o1"]["stock"])
    final_stock = float(final["world"]["objects"]["o1"]["stock"])
    acquired = max(0.0, initial_stock - final_stock)

    first_acquisition_tick = None
    for event in sim_events:
        stock = float(event["state"]["world"]["o1_stock"])
        if stock < initial_stock - 1e-9:
            first_acquisition_tick = int(event["sim_tick"])
            break

    start_distance_walked = float(initial["agent"].get("distance_walked", 0.0))
    final_distance_walked = float(final["agent"].get("distance_walked", 0.0))
    travelled = max(0.0, final_distance_walked - start_distance_walked)

    responses = [
        event for event in events
        if event.get("event") == "response_received"
        and bool(event.get("ok", False))
    ]
    if not responses:
        raise ExperimentError("Run produced no successful NeuralBrain responses.")

    selected = [str(event.get("selected", "")).upper() for event in responses]
    explore_count = sum(1 for value in selected if value == "EXPLORE")
    explore_proportion = explore_count / len(selected)

    disagreements = 0
    comparable_bg = 0
    for event in responses:
        competition_winner = argmax_mapping(event.get("competition_values"))
        bg_winner = argmax_mapping(event.get("basal_ganglia"))
        if competition_winner and bg_winner:
            comparable_bg += 1
            if competition_winner != bg_winner:
                disagreements += 1

    authority_ok = all(
        str(event.get("control_mode", "")) == "control"
        and str(event.get("actuator_authority", "")) == "neural"
        for event in responses
    )

    episodes = new_episodes(initial, final)
    causal_episodes = [
        episode for episode in episodes
        if isinstance(episode.get("causal"), dict)
    ]
    execution_failures = 0
    for episode in causal_episodes:
        causal = episode["causal"]
        if (
            str(causal.get("resolution", "")) == "no_target"
            or str(causal.get("execution", "")) == "failed"
            or str(causal.get("interaction", "")) == "not_executed"
        ):
            execution_failures += 1

    first_time = (
        None
        if first_acquisition_tick is None
        else first_acquisition_tick * SIM_DT
    )

    return {
        "time_to_first_valid_food_interaction_seconds": first_time,
        "first_food_acquisition_tick": first_acquisition_tick,
        "total_distance_travelled_m": travelled,
        "selected_explore_proportion": explore_proportion,
        "food_acquisitions": acquired,
        "food_acquisition_rate_per_sim_minute": acquired / (RUN_HORIZON_SIM_SECONDS / 60.0),
        "neural_response_count": len(responses),
        "selected_explore_count": explore_count,
        "bg_vs_competition_comparable_samples": comparable_bg,
        "bg_vs_competition_disagreements": disagreements,
        "bg_vs_competition_disagreement_rate": (
            disagreements / comparable_bg if comparable_bg else None
        ),
        "new_episode_count": len(episodes),
        "causal_episode_count": len(causal_episodes),
        "execution_failure_count": execution_failures,
        "execution_failure_rate": (
            execution_failures / len(causal_episodes)
            if causal_episodes else 0.0
        ),
        "neural_authority_integrity": authority_ok,
        "initial_o1_stock": initial_stock,
        "final_o1_stock": final_stock,
    }


def run_arm(
    *,
    repo: Path,
    d3,
    experiment_root: Path,
    source: Path,
    source_sha: str,
    arm: dict[str, Any],
    godot: Path,
    python_exe: Path,
) -> dict[str, Any]:
    arm_id = str(arm["arm_id"])
    arm_position = normalize_position(arm["food_position"], f"{arm_id}.food_position")

    run_dir = experiment_root / f"run_{arm_id}"
    sandbox = experiment_root / f"sandbox_{arm_id}"
    run_dir.mkdir(parents=True, exist_ok=False)

    save_path = run_dir / "individual.json"
    trace_path = run_dir / "trace.jsonl"
    stdout_path = run_dir / "godot.stdout.txt"
    stderr_path = run_dir / "godot.stderr.txt"
    capsule_path = run_dir / "capsule.json"

    initial = arm_snapshot(source, save_path, arm_position)
    derived_source_hash = sha256_file(save_path)
    source_data = decode_snapshot(source)[1]

    if canonical_hash(environment_without_o1_position(initial)) != canonical_hash(
        environment_without_o1_position(source_data)
    ):
        raise ExperimentError(
            f"{arm_id}: derived snapshot differs from source outside o1.position."
        )

    run(
        ["git", "worktree", "add", "--detach", str(sandbox), RUNTIME_COMMIT],
        cwd=repo,
        timeout=120,
    )

    try:
        instrumented_hashes = write_instrumented_runtime(repo, sandbox, d3)
        wait_port_free()

        env = os.environ.copy()
        env["BIRDAI_PYTHON"] = str(python_exe)
        env["BIRDAI_E1_D3_RUN_ID"] = arm_id.upper()
        env["BIRDAI_E1_D3_TRACE_PATH"] = str(trace_path)
        env["BIRDAI_E1_D3_GATE_DELAY_TICKS"] = str(GATE_DELAY_TICKS)
        env["BIRDAI_E1_D3_REQUEST_START_TICK"] = str(REQUEST_START_TICK)
        env["BIRDAI_E1_D3_REQUEST_INTERVAL_TICKS"] = str(REQUEST_INTERVAL_TICKS)
        env["BIRDAI_E1_D3_LATE_REQUEST_ID"] = "-1"
        env["BIRDAI_E1_D3_NEURAL_SEED"] = str(NEURAL_SEED)
        env["BIRDAI_E1_D3_STOP_TICK"] = str(STOP_TICK)

        command = [
            str(godot),
            "--headless",
            "--path", str(sandbox),
            "--",
            "--neural-control",
            f"--save-path={save_path}",
            "--quit-after=600",
        ]

        wall_started = datetime.now(timezone.utc).isoformat()
        started = time.monotonic()
        result = run(
            command,
            cwd=sandbox,
            env=env,
            timeout=WALL_TIMEOUT_SECONDS,
            check=False,
        )
        elapsed = time.monotonic() - started
        wall_finished = datetime.now(timezone.utc).isoformat()

        stdout_path.write_text(result.stdout, encoding="utf-8")
        stderr_path.write_text(result.stderr, encoding="utf-8")
        wait_port_free()

        if result.returncode != 0:
            raise ExperimentError(
                f"{arm_id}: Godot exit code {result.returncode}; see {stderr_path}"
            )

        events = load_jsonl(trace_path)
        first = events[0]
        last = events[-1]
        if first.get("event") != "session_start":
            raise ExperimentError(f"{arm_id}: trace lacks session_start.")
        if last.get("event") != "session_end":
            raise ExperimentError(f"{arm_id}: trace lacks session_end.")
        if last.get("termination_reason") != "diagnostic_stop_tick":
            raise ExperimentError(
                f"{arm_id}: unexpected termination {last.get('termination_reason')!r}"
            )
        if int(last.get("deadline_misses", -1)) != 0:
            raise ExperimentError(
                f"{arm_id}: response application deadline misses={last.get('deadline_misses')}"
            )
        if int(last.get("request_schedule_misses", -1)) != 0:
            raise ExperimentError(
                f"{arm_id}: request schedule misses={last.get('request_schedule_misses')}"
            )
        if bool(last.get("queued_response_remaining")) or bool(last.get("pending")):
            raise ExperimentError(
                f"{arm_id}: neural request/response remained pending at termination."
            )

        _final_envelope, final = decode_snapshot(save_path)
        metrics = metrics_for_run(events=events, initial=initial, final=final)

        if not metrics["neural_authority_integrity"]:
            raise ExperimentError(
                f"{arm_id}: neural authority integrity failed."
            )

        capsule = {
            "stage": STAGE,
            "arm_id": arm_id,
            "runtime_commit": RUNTIME_COMMIT,
            "registration_sha256": REGISTRATION_SHA256,
            "source_snapshot_sha256": source_sha,
            "derived_start_snapshot_sha256": derived_source_hash,
            "food_position": arm_position,
            "neural_seed": NEURAL_SEED,
            "simulation_dt": SIM_DT,
            "stop_tick": STOP_TICK,
            "run_horizon_sim_seconds": RUN_HORIZON_SIM_SECONDS,
            "request_start_tick": REQUEST_START_TICK,
            "request_interval_ticks": REQUEST_INTERVAL_TICKS,
            "gate_delay_ticks": GATE_DELAY_TICKS,
            "wall_clock_start": wall_started,
            "wall_clock_end": wall_finished,
            "wall_clock_elapsed_seconds": elapsed,
            "trace_path": str(trace_path),
            "trace_sha256": sha256_file(trace_path),
            "final_snapshot_sha256": sha256_file(save_path),
            "instrumented_runtime_sha256": instrumented_hashes,
            "metrics": metrics,
            "production_runtime_mutation": "none",
            "instrumentation": "throwaway worktree only",
        }
        capsule_path.write_text(
            json.dumps(capsule, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        return {
            "arm": arm,
            "initial": initial,
            "final": final,
            "events": events,
            "metrics": metrics,
            "capsule": capsule,
            "capsule_path": capsule_path,
        }
    finally:
        remove_worktree(repo, sandbox)


def metric_direction(
    baseline: dict[str, Any],
    far: dict[str, Any],
) -> dict[str, str]:
    result = {}

    b_time = baseline["time_to_first_valid_food_interaction_seconds"]
    f_time = far["time_to_first_valid_food_interaction_seconds"]
    if b_time is None and f_time is None:
        result["time_to_first_valid_food_interaction_seconds"] = "neutral"
    elif b_time is not None and f_time is None:
        result["time_to_first_valid_food_interaction_seconds"] = "predicted"
    elif b_time is None and f_time is not None:
        result["time_to_first_valid_food_interaction_seconds"] = "opposite"
    else:
        delta = float(f_time) - float(b_time)
        result["time_to_first_valid_food_interaction_seconds"] = (
            "predicted" if delta > 1e-9 else
            "opposite" if delta < -1e-9 else
            "neutral"
        )

    delta_distance = (
        float(far["total_distance_travelled_m"])
        - float(baseline["total_distance_travelled_m"])
    )
    result["total_distance_travelled_m"] = (
        "predicted" if delta_distance > 1e-9 else
        "opposite" if delta_distance < -1e-9 else
        "neutral"
    )

    delta_explore = (
        float(far["selected_explore_proportion"])
        - float(baseline["selected_explore_proportion"])
    )
    result["selected_explore_proportion"] = (
        "predicted" if delta_explore > 1e-9 else
        "opposite" if delta_explore < -1e-9 else
        "neutral"
    )

    delta_rate = (
        float(baseline["food_acquisition_rate_per_sim_minute"])
        - float(far["food_acquisition_rate_per_sim_minute"])
    )
    result["food_acquisition_rate_per_sim_minute"] = (
        "predicted" if delta_rate > 1e-9 else
        "opposite" if delta_rate < -1e-9 else
        "neutral"
    )
    return result


def hypothesis_result(directions: dict[str, str]) -> str:
    predicted = sum(1 for value in directions.values() if value == "predicted")
    opposite = sum(1 for value in directions.values() if value == "opposite")
    if predicted and opposite:
        return "INCONCLUSIVE"
    if predicted:
        return "SUPPORTED"
    return "NOT_SUPPORTED"


def validate_registration(reg: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if reg.get("experiment") != "E1-B-H1a-resource-distance-v1":
        raise ExperimentError(f"Unexpected registration experiment: {reg.get('experiment')!r}")
    if reg.get("manipulated_variable") != "world.objects.o1.position":
        raise ExperimentError("Registration manipulated_variable is not world.objects.o1.position.")
    if reg.get("allowed_difference") != ["world.objects.o1.position"]:
        raise ExperimentError("Registration allowed_difference is not exact.")
    arms = reg.get("arms")
    if not isinstance(arms, list) or len(arms) != 2:
        raise ExperimentError("Registration must contain exactly two arms.")
    indexed = {str(arm.get("arm_id")): arm for arm in arms if isinstance(arm, dict)}
    if set(indexed) != {"baseline", "far"}:
        raise ExperimentError(f"Registration arm IDs invalid: {sorted(indexed)}")
    horizon = float(reg.get("run_horizon_sim_seconds", -1))
    if not math.isclose(horizon, RUN_HORIZON_SIM_SECONDS, abs_tol=1e-9):
        raise ExperimentError(
            f"Registration horizon {horizon} != harness horizon {RUN_HORIZON_SIM_SECONDS}"
        )
    return indexed["baseline"], indexed["far"]


def self_test() -> None:
    baseline = {
        "time_to_first_valid_food_interaction_seconds": 20.0,
        "total_distance_travelled_m": 8.0,
        "selected_explore_proportion": 0.30,
        "food_acquisition_rate_per_sim_minute": 1.0,
    }
    far = {
        "time_to_first_valid_food_interaction_seconds": 30.0,
        "total_distance_travelled_m": 9.0,
        "selected_explore_proportion": 0.35,
        "food_acquisition_rate_per_sim_minute": 0.5,
    }
    directions = metric_direction(baseline, far)
    assert set(directions.values()) == {"predicted"}
    assert hypothesis_result(directions) == "SUPPORTED"

    mixed = dict(far)
    mixed["total_distance_travelled_m"] = 7.0
    assert hypothesis_result(metric_direction(baseline, mixed)) == "INCONCLUSIVE"

    same = dict(baseline)
    assert hypothesis_result(metric_direction(baseline, same)) == "NOT_SUPPORTED"

    sample = {
        "schema": 2,
        "agent": {"position": [0, 0, 0]},
        "world": {
            "objects": {
                "o1": {
                    "position": [-4, 0, 0],
                    "kind": "food",
                    "stock": 12.0,
                }
            }
        },
    }
    other = copy.deepcopy(sample)
    other["world"]["objects"]["o1"]["position"] = [-5, 0, 0]
    assert canonical_hash(environment_without_o1_position(sample)) == canonical_hash(
        environment_without_o1_position(other)
    )

    print("SELF_TEST: PASS")
    print("ARM_COUNT: 2")
    print(f"STOP_TICK: {STOP_TICK}")
    print("SCHEDULING_CONTROL: accepted E1-A1-D3 barrier apparatus")
    print("ALLOWED_ENVIRONMENT_DIFFERENCE: world.objects.o1.position only")
    print("PRIMARY_METRICS: first_food, distance, EXPLORE proportion, acquisition rate")
    print("VALIDITY_AND_HYPOTHESIS: separate")
    print("REPLICATION_ACROSS_SEEDS: deferred to E1-C")
    print("PRODUCTION_RUNTIME_MUTATION: NONE")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.environ.get("BIRDAI_REPO", r"C:\AlmaTheHen"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    self_test()
    repo = Path(args.repo).resolve()

    head = run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    if head == RUNTIME_COMMIT:
        raise ExperimentError(
            "Run the H1a harness from its committed experiment branch, not directly from main."
        )
    parent = run(["git", "rev-parse", "HEAD^"], cwd=repo).stdout.strip()
    if parent != RUNTIME_COMMIT:
        raise ExperimentError(
            f"Harness branch parent mismatch: {parent} != {RUNTIME_COMMIT}"
        )

    if git_blob(repo, RUNTIME_COMMIT, MAIN_REL) != MAIN_BLOB:
        raise ExperimentError("Pinned main.gd blob mismatch.")
    if git_blob(repo, RUNTIME_COMMIT, BRIDGE_REL) != BRIDGE_BLOB:
        raise ExperimentError("Pinned neural bridge blob mismatch.")

    if not REGISTRATION_PATH.is_file():
        raise ExperimentError(f"Missing registration: {REGISTRATION_PATH}")
    if sha256_file(REGISTRATION_PATH) != REGISTRATION_SHA256:
        raise ExperimentError(
            "Registration file SHA-256 does not match the harness-pinned registration."
        )

    registration = json.loads(REGISTRATION_PATH.read_text(encoding="utf-8"))
    baseline_arm, far_arm = validate_registration(registration)

    if not SOURCE_SNAPSHOT.is_file():
        raise ExperimentError(f"Missing accepted source snapshot: {SOURCE_SNAPSHOT}")
    source_sha = sha256_file(SOURCE_SNAPSHOT)
    registered_source_sha = str(
        registration.get("shared_agent_snapshot", {}).get("sha256", "")
    )
    if source_sha != registered_source_sha:
        raise ExperimentError(
            f"Source snapshot hash mismatch: {source_sha} != {registered_source_sha}"
        )

    source_data = decode_snapshot(SOURCE_SNAPSHOT)[1]
    registered_baseline = normalize_position(
        baseline_arm["food_position"], "baseline.food_position"
    )
    source_baseline = normalize_position(
        source_data["world"]["objects"]["o1"]["position"],
        "source world.objects.o1.position",
    )
    if source_baseline != registered_baseline:
        raise ExperimentError(
            f"Source baseline position {source_baseline} != registered {registered_baseline}"
        )

    d3 = load_d3_helper(repo)
    godot = discover_godot(repo)
    python_exe = discover_python()

    experiment_id = f"e1-b-h1a-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{RUNTIME_COMMIT[:7]}"
    experiment_root = EVIDENCE_ROOT / experiment_id
    experiment_root.mkdir(parents=True, exist_ok=False)

    config = {
        "stage": STAGE,
        "experiment_id": experiment_id,
        "runtime_commit": RUNTIME_COMMIT,
        "registration_path": str(REGISTRATION_PATH),
        "registration_sha256": REGISTRATION_SHA256,
        "source_snapshot": str(SOURCE_SNAPSHOT),
        "source_snapshot_sha256": source_sha,
        "neural_seed": NEURAL_SEED,
        "simulation_dt": SIM_DT,
        "run_horizon_sim_seconds": RUN_HORIZON_SIM_SECONDS,
        "stop_tick": STOP_TICK,
        "request_start_tick": REQUEST_START_TICK,
        "request_interval_ticks": REQUEST_INTERVAL_TICKS,
        "gate_delay_ticks": GATE_DELAY_TICKS,
        "scheduling_control": "accepted E1-A1-D3 barrier apparatus",
        "production_runtime_mutation": "none",
        "allowed_environment_difference": ["world.objects.o1.position"],
    }
    config_path = experiment_root / "experiment-config.json"
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=" * 72)
    print("E1-B H1a REGISTERED RESOURCE-DISTANCE EXPERIMENT")
    print(f"EXPERIMENT: {experiment_id}")
    print(f"RUNTIME_COMMIT: {RUNTIME_COMMIT}")
    print(f"REGISTRATION_SHA256: {REGISTRATION_SHA256}")
    print(f"SOURCE_SHA256: {source_sha}")
    print(f"STOP_TICK: {STOP_TICK}")
    print(f"EVIDENCE: {experiment_root}")
    print("PRODUCTION_RUNTIME_MUTATION: NONE")
    print("=" * 72)

    baseline = run_arm(
        repo=repo,
        d3=d3,
        experiment_root=experiment_root,
        source=SOURCE_SNAPSHOT,
        source_sha=source_sha,
        arm=baseline_arm,
        godot=godot,
        python_exe=python_exe,
    )
    far = run_arm(
        repo=repo,
        d3=d3,
        experiment_root=experiment_root,
        source=SOURCE_SNAPSHOT,
        source_sha=source_sha,
        arm=far_arm,
        godot=godot,
        python_exe=python_exe,
    )

    baseline_invariant = canonical_hash(
        environment_without_o1_position(baseline["initial"])
    )
    far_invariant = canonical_hash(
        environment_without_o1_position(far["initial"])
    )
    environment_integrity = baseline_invariant == far_invariant

    validity_reasons = []
    if not environment_integrity:
        validity_reasons.append("arm start states differ outside world.objects.o1.position")
    if not baseline["metrics"]["neural_authority_integrity"]:
        validity_reasons.append("baseline neural authority integrity failed")
    if not far["metrics"]["neural_authority_integrity"]:
        validity_reasons.append("far neural authority integrity failed")

    validity = "PASS" if not validity_reasons else "INVALID"
    directions = metric_direction(baseline["metrics"], far["metrics"])
    result = hypothesis_result(directions) if validity == "PASS" else None

    comparison = {
        "stage": STAGE,
        "experiment_id": experiment_id,
        "runtime_commit": RUNTIME_COMMIT,
        "registration_sha256": REGISTRATION_SHA256,
        "source_snapshot_sha256": source_sha,
        "experiment_validity": validity,
        "validity_reasons": validity_reasons,
        "hypothesis_result": result,
        "allowed_environment_difference": ["world.objects.o1.position"],
        "environment_integrity": environment_integrity,
        "baseline_invariant_hash_without_o1_position": baseline_invariant,
        "far_invariant_hash_without_o1_position": far_invariant,
        "baseline": {
            "registered_arm": baseline_arm,
            "metrics": baseline["metrics"],
        },
        "far": {
            "registered_arm": far_arm,
            "metrics": far["metrics"],
        },
        "primary_metric_directions": directions,
        "interpretation_rule": {
            "SUPPORTED": "one or more predicted directions and no opposite primary direction",
            "NOT_SUPPORTED": "no predicted direction",
            "INCONCLUSIVE": "mixed predicted and opposite primary directions",
        },
        "replication_scope": "single paired E1-B perturbation; seed replication deferred to E1-C",
        "production_runtime_mutation": "none",
    }
    comparison_path = experiment_root / "comparison.json"
    comparison_path.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    comparison_sha = sha256_file(comparison_path)

    for item in (baseline, far):
        capsule = item["capsule"]
        capsule["comparison_path"] = str(comparison_path)
        capsule["comparison_sha256"] = comparison_sha
        item["capsule_path"].write_text(
            json.dumps(capsule, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print("")
    print("=" * 72)
    print("STATUS: PASS" if validity == "PASS" else "STATUS: INVALID")
    print(f"EXPERIMENT_VALIDITY: {validity}")
    print(f"HYPOTHESIS_RESULT: {result}")
    print("BASELINE_METRICS: " + json.dumps(baseline["metrics"], ensure_ascii=True, sort_keys=True))
    print("FAR_METRICS: " + json.dumps(far["metrics"], ensure_ascii=True, sort_keys=True))
    print("PRIMARY_METRIC_DIRECTIONS: " + json.dumps(directions, ensure_ascii=True, sort_keys=True))
    print(f"ENVIRONMENT_INTEGRITY: {environment_integrity}")
    print(f"COMPARISON: {comparison_path}")
    print(f"COMPARISON_SHA256: {comparison_sha}")
    print(f"EVIDENCE: {experiment_root}")
    print("PRODUCTION_RUNTIME_MUTATION: NONE")
    print("NEURAL_POLICY_CHANGE: NONE")
    print("LEARNING_RULE_CHANGE: NONE")
    print("ENVIRONMENT_CODE_CHANGE: NONE")
    print("=" * 72)

    if validity != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ExperimentError as exc:
        print("STATUS: INVALID", file=sys.stderr)
        print(f"BLOCKER: {exc}", file=sys.stderr)
        raise SystemExit(2)
    except Exception as exc:
        print("STATUS: INVALID", file=sys.stderr)
        print(f"BLOCKER: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
