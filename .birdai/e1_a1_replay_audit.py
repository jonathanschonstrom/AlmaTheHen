from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUNTIME_COMMIT = "ab186b5c9cbae6fa721c4b9a2ac6f30623507067"
BRIDGE_BLOB = "b7fd20af2f92f9156d8db5d820e2592e8b62c9a0"
MAIN_BLOB = "66daffb205d680e64d55b314a6c9a92bfe98a0c3"
AGENT_BLOB = "85ef6dcc094f81b016ec68c7e7fb4d98c7d10e2a"

STAGE = "E1-A1"
NEURAL_SEED = 20260910
PORT = 39393
ABS_TOL = 1e-9
REL_TOL = 1e-9
DEFAULT_DURATION = 15.0

BRIDGE_REL = "scripts/cognition/neural_brain_bridge.gd"
MAIN_REL = "scripts/main.gd"
AGENT_REL = "scripts/cognition/agent.gd"

PROVENANCE_ONLY_KEYS = {
    "experiment_id",
    "run_id",
    "request_sent_ticks_usec",
    "response_ticks_usec",
    "round_trip_ms",
    "saved_at",
    "wall_clock_start",
    "wall_clock_end",
    "wall_clock_elapsed_seconds",
}


class AuditError(RuntimeError):
    pass


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    return sha256_bytes(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def run(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
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
        raise AuditError(
            f"Command failed ({result.returncode}): {' '.join(args)}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def git_show(repo: Path, commit: str, rel: str) -> str:
    result = run(
        ["git", "show", f"{commit}:{rel}"],
        cwd=repo,
    )
    return result.stdout.replace("\r\n", "\n")


def git_blob(repo: Path, commit: str, rel: str) -> str:
    return run(
        ["git", "rev-parse", f"{commit}:{rel}"],
        cwd=repo,
    ).stdout.strip()


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise AuditError(
            f"{label}: expected exactly one pinned source fragment, found {count}."
        )
    return source.replace(old, new, 1)



def _source_lines(source: str) -> list[str]:
    return source.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _render_source(lines: list[str]) -> str:
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def _unique_exact_line(
    lines: list[str],
    exact: str,
    label: str,
    *,
    start: int = 0,
    end: int | None = None,
) -> int:
    stop = len(lines) if end is None else end
    matches = [
        index
        for index in range(start, stop)
        if lines[index] == exact
    ]
    if len(matches) != 1:
        raise AuditError(
            f"{label}: expected exactly one exact line {exact!r}, "
            f"found {len(matches)}."
        )
    return matches[0]


def _function_bounds(
    lines: list[str],
    signature: str,
    label: str,
) -> tuple[int, int]:
    start = _unique_exact_line(lines, signature, label)
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("func "):
            end = index
            break
    return start, end


def _insert_after_unique(
    lines: list[str],
    exact: str,
    additions: list[str],
    label: str,
    *,
    start: int = 0,
    end: int | None = None,
) -> None:
    index = _unique_exact_line(
        lines,
        exact,
        label,
        start=start,
        end=end,
    )
    lines[index + 1:index + 1] = additions


def _insert_before_unique(
    lines: list[str],
    exact: str,
    additions: list[str],
    label: str,
    *,
    start: int = 0,
    end: int | None = None,
) -> None:
    index = _unique_exact_line(
        lines,
        exact,
        label,
        start=start,
        end=end,
    )
    lines[index:index] = additions


def _replace_unique_line(
    lines: list[str],
    exact: str,
    replacements: list[str],
    label: str,
    *,
    start: int = 0,
    end: int | None = None,
) -> None:
    index = _unique_exact_line(
        lines,
        exact,
        label,
        start=start,
        end=end,
    )
    lines[index:index + 1] = replacements


def instrument_bridge(source: str) -> str:
    lines = _source_lines(source)

    _insert_after_unique(
        lines,
        'var mode := "control"',
        [
            'var experiment_id := ""',
            'var run_id := ""',
            'var neural_seed := 20260910',
            'var pending_sent_ticks_usec := 0',
            'var session_end_recorded := false',
        ],
        "bridge declarations",
    )

    start_begin, start_end = _function_bounds(
        lines,
        'func start(requested_mode: String = "control") -> void:',
        "bridge start function",
    )
    _insert_after_unique(
        lines,
        '\tmode = "shadow" if requested_mode == "shadow" else "control"',
        [
            '\texperiment_id = OS.get_environment("BIRDAI_E1_EXPERIMENT_ID")',
            '\trun_id = OS.get_environment("BIRDAI_E1_RUN_ID")',
            '\tvar configured_seed = OS.get_environment("BIRDAI_E1_NEURAL_SEED")',
            '\tneural_seed = int(configured_seed) if not configured_seed.is_empty() else 20260910',
        ],
        "bridge start environment",
        start=start_begin,
        end=start_end,
    )

    # Recalculate function bounds after insertions.
    start_begin, start_end = _function_bounds(
        lines,
        'func start(requested_mode: String = "control") -> void:',
        "bridge start function after environment insertion",
    )
    _replace_unique_line(
        lines,
        '\tlog_path = ProjectSettings.globalize_path("res://data/" + filename)',
        [
            '\tvar configured_log_path = OS.get_environment("BIRDAI_E1_TRACE_PATH")',
            '\tlog_path = configured_log_path if not configured_log_path.is_empty() else ProjectSettings.globalize_path("res://data/" + filename)',
        ],
        "bridge run-scoped log path",
        start=start_begin,
        end=start_end,
    )

    start_begin, start_end = _function_bounds(
        lines,
        'func start(requested_mode: String = "control") -> void:',
        "bridge start function before provenance",
    )
    _replace_unique_line(
        lines,
        '\t\t\t"port": PORT',
        [
            '\t\t\t"port": PORT,',
            '\t\t\t"experiment_id": experiment_id,',
            '\t\t\t"run_id": run_id,',
            '\t\t\t"neural_seed": neural_seed,',
            '\t\t\t"neural_start_mode": "cold",',
            '\t\t\t"update_interval": UPDATE_INTERVAL,',
            '\t\t\t"neural_seconds": 0.05',
        ],
        "bridge session provenance",
        start=start_begin,
        end=start_end,
    )

    find_begin, find_end = _function_bounds(
        lines,
        'func find_python() -> String:',
        "bridge find_python function",
    )
    lines[find_begin + 1:find_begin + 1] = [
        '\tvar configured = OS.get_environment("BIRDAI_PYTHON")',
        '\tif not configured.is_empty() and FileAccess.file_exists(configured):',
        '\t\treturn configured',
    ]

    start_begin, start_end = _function_bounds(
        lines,
        'func start(requested_mode: String = "control") -> void:',
        "bridge start function before process launch",
    )
    _replace_unique_line(
        lines,
        '\tprocess_id = OS.create_process(python_path, PackedStringArray([script, "--port", str(PORT)]), false)',
        [
            '\tprocess_id = OS.create_process(python_path, PackedStringArray([script, "--port", str(PORT), "--seed", str(neural_seed)]), false)'
        ],
        "bridge explicit neural seed",
        start=start_begin,
        end=start_end,
    )

    send_begin, send_end = _function_bounds(
        lines,
        'func send_snapshot(agent) -> void:',
        "bridge send_snapshot function",
    )
    _insert_after_unique(
        lines,
        '\t\tpending = true',
        ['\t\tpending_sent_ticks_usec = Time.get_ticks_usec()'],
        "bridge request timing",
        start=send_begin,
        end=send_end,
    )

    read_begin, read_end = _function_bounds(
        lines,
        'func read_available(agent) -> void:',
        "bridge read_available function",
    )
    _insert_before_unique(
        lines,
        '\t\t\t\tparsed["agent_action_before_apply"] = str(agent.current.get("action", ""))',
        [
            '\t\t\t\tparsed["event"] = "neural_decision"',
            '\t\t\t\tparsed["experiment_id"] = experiment_id',
            '\t\t\t\tparsed["run_id"] = run_id',
            '\t\t\t\tparsed["request_sent_ticks_usec"] = pending_sent_ticks_usec',
            '\t\t\t\tparsed["response_ticks_usec"] = Time.get_ticks_usec()',
            '\t\t\t\tparsed["round_trip_ms"] = float(parsed["response_ticks_usec"] - pending_sent_ticks_usec) / 1000.0 if pending_sent_ticks_usec > 0 else -1.0',
            '\t\t\t\tparsed["response_agent_age"] = agent.age',
        ],
        "bridge neural decision trace",
        start=read_begin,
        end=read_end,
    )

    read_begin, read_end = _function_bounds(
        lines,
        'func read_available(agent) -> void:',
        "bridge read_available function after decision insertion",
    )
    _insert_after_unique(
        lines,
        '\t\t\t\tparsed["agent_position"] = [agent.position.x, agent.position.y, agent.position.z]',
        [
            '\t\t\t\tparsed["agent_target_before_apply"] = str(agent.current.get("target", ""))',
            '\t\t\t\tparsed["agent_heading"] = [agent.heading.x, agent.heading.y, agent.heading.z]',
            '\t\t\t\tparsed["agent_state_at_response"] = agent.export_data()',
            '\t\t\t\tparsed["world_state_at_response"] = agent.world.export_data()',
        ],
        "bridge embodied/world trace",
        start=read_begin,
        end=read_end,
    )

    append_index = _unique_exact_line(
        lines,
        'func append_log(payload: Dictionary) -> void:',
        "bridge append_log function",
    )
    lines[append_index:append_index] = [
        'func record_session_end(agent, reason: String) -> void:',
        '\tif session_end_recorded or log_path.is_empty():',
        '\t\treturn',
        '\tsession_end_recorded = true',
        '\tappend_log({',
        '\t\t"event": "session_end",',
        '\t\t"experiment_id": experiment_id,',
        '\t\t"run_id": run_id,',
        '\t\t"termination_reason": reason,',
        '\t\t"control_mode": mode,',
        '\t\t"actuator_authority": "utility" if mode == "shadow" else "neural",',
        '\t\t"response_agent_age": agent.age,',
        '\t\t"agent_state_at_response": agent.export_data(),',
        '\t\t"agent_phase": agent.phase,',
        '\t\t"agent_action": str(agent.current.get("action", "")),',
        '\t\t"agent_target": str(agent.current.get("target", "")),',
        '\t\t"world_state_at_response": agent.world.export_data(),',
        '\t\t"last_neural_actuation": agent.neural_last_actuation.duplicate(true)',
        '\t})',
    ]

    result = _render_source(lines)
    required = [
        'var session_end_recorded := false',
        'OS.get_environment("BIRDAI_E1_TRACE_PATH")',
        '"--seed", str(neural_seed)',
        'parsed["event"] = "neural_decision"',
        'parsed["agent_state_at_response"] = agent.export_data()',
        'parsed["world_state_at_response"] = agent.world.export_data()',
        'func record_session_end(agent, reason: String) -> void:',
    ]
    missing = [item for item in required if item not in result]
    if missing:
        raise AuditError(
            f"bridge instrumentation postcondition failed: {missing}"
        )
    return result




def instrument_main(source: str) -> str:
    lines = _source_lines(source)
    process_begin, process_end = _function_bounds(
        lines,
        'func _process(dt: float) -> void:',
        "main _process function",
    )

    quit_index = _unique_exact_line(
        lines,
        '\tif quit_after > 0 and total_runtime >= quit_after:',
        "main bounded-run condition",
        start=process_begin,
        end=process_end,
    )
    shutdown_candidates = [
        index
        for index in range(quit_index + 1, process_end)
        if lines[index] == '\t\t\tneural.shutdown()'
    ]
    if len(shutdown_candidates) != 1:
        raise AuditError(
            "main bounded termination: expected exactly one neural.shutdown() "
            f"after quit_after condition, found {len(shutdown_candidates)}."
        )
    shutdown_index = shutdown_candidates[0]
    lines[shutdown_index:shutdown_index] = [
        '\t\t\tneural.record_session_end(agent, "quit_after")'
    ]

    result = _render_source(lines)
    if 'neural.record_session_end(agent, "quit_after")' not in result:
        raise AuditError("main instrumentation postcondition failed.")
    return result




def instrument_agent(source: str) -> str:
    lines = _source_lines(source)

    select_begin, select_end = _function_bounds(
        lines,
        'func select_action() -> void:',
        "agent select_action function",
    )
    target_line = '\tphase_time = 0'
    phase_matches = [
        index
        for index in range(select_begin, select_end)
        if lines[index] == target_line
    ]
    if len(phase_matches) != 1:
        raise AuditError(
            "agent select_action: expected exactly one phase_time = 0 line, "
            f"found {len(phase_matches)}."
        )
    actuation_index = phase_matches[0] + 1
    lines[actuation_index:actuation_index] = [
        '\te1_a1_append_event({',
        '\t\t"event": "actuation_resolved",',
        '\t\t"experiment_id": OS.get_environment("BIRDAI_E1_EXPERIMENT_ID"),',
        '\t\t"run_id": OS.get_environment("BIRDAI_E1_RUN_ID"),',
        '\t\t"request_id": neural_request_id,',
        '\t\t"family": neural_selected_family,',
        '\t\t"action": str(current.get("action", "")),',
        '\t\t"target": str(current.get("target", "")),',
        '\t\t"age": age,',
        '\t\t"phase": phase,',
        '\t\t"agent_state": export_data(),',
        '\t\t"world_state": world.export_data()',
        '\t})',
    ]

    finish_begin, finish_end = _function_bounds(
        lines,
        'func finish(result: Dictionary) -> void:',
        "agent finish function",
    )
    _insert_before_unique(
        lines,
        '\tthought = result.outcome',
        [
            '\te1_a1_append_event({',
            '\t\t"event": "action_outcome",',
            '\t\t"experiment_id": OS.get_environment("BIRDAI_E1_EXPERIMENT_ID"),',
            '\t\t"run_id": OS.get_environment("BIRDAI_E1_RUN_ID"),',
            '\t\t"request_id": int(current.get("neural_request_id", -1)),',
            '\t\t"age": age,',
            '\t\t"action": str(current.get("action", "")),',
            '\t\t"target": str(current.get("target", "")),',
            '\t\t"result": result.duplicate(true),',
            '\t\t"reward": reward,',
            '\t\t"prediction_error": learned.prediction_error,',
            '\t\t"phase": phase,',
            '\t\t"agent_state": export_data(),',
            '\t\t"world_state": world.export_data()',
            '\t})',
        ],
        "agent outcome event",
        start=finish_begin,
        end=finish_end,
    )

    setter_index = _unique_exact_line(
        lines,
        'func set_neural_control(enabled: bool) -> void:',
        "agent set_neural_control function",
    )
    lines[setter_index:setter_index] = [
        'func e1_a1_append_event(payload: Dictionary) -> void:',
        '\tvar audit_path = OS.get_environment("BIRDAI_E1_TRACE_PATH")',
        '\tif audit_path.is_empty():',
        '\t\treturn',
        '\tvar log = FileAccess.open(audit_path, FileAccess.READ_WRITE)',
        '\tif log == null:',
        '\t\treturn',
        '\tlog.seek_end()',
        '\tlog.store_line(JSON.stringify(payload))',
        '\tlog.close()',
    ]

    result = _render_source(lines)
    required = [
        '"event": "actuation_resolved"',
        '"event": "action_outcome"',
        'func e1_a1_append_event(payload: Dictionary) -> void:',
    ]
    missing = [item for item in required if item not in result]
    if missing:
        raise AuditError(
            f"agent instrumentation postcondition failed: {missing}"
        )
    return result




def validate_instrumentation_self_test() -> None:
    # Fixtures intentionally contain blank lines so the test protects against
    # the exact failure mode that triggered v2: pinned content with different
    # blank-line layout must not break line-local instrumentation.
    bridge_fixture = (
        'var log_path := ""\n'
        '\n'
        'var mode := "control"\n'
        '\n'
        'func start(requested_mode: String = "control") -> void:\n'
        '\tmode = "shadow" if requested_mode == "shadow" else "control"\n'
        '\tvar filename = "neural-shadow.jsonl" if mode == "shadow" else "neural-control.jsonl"\n'
        '\tlog_path = ProjectSettings.globalize_path("res://data/" + filename)\n'
        '\tvar log = FileAccess.open(log_path, FileAccess.WRITE)\n'
        '\t\t\t"port": PORT\n'
        '\tpython_path = find_python()\n'
        '\tprocess_id = OS.create_process(python_path, PackedStringArray([script, "--port", str(PORT)]), false)\n'
        '\n'
        'func find_python() -> String:\n'
        '\tfor relative in ["res://brain/.venv/Scripts/pythonw.exe", "res://brain/.venv/Scripts/python.exe", "res://tools/python/pythonw.exe", "res://tools/python/python.exe"]:\n'
        '\t\tpass\n'
        '\n'
        'func send_snapshot(agent) -> void:\n'
        '\tvar err = peer.put_data(bytes)\n'
        '\tif err == OK:\n'
        '\t\tpending = true\n'
        '\n'
        'func read_available(agent) -> void:\n'
        '\t\t\t\tparsed["agent_action_before_apply"] = str(agent.current.get("action", ""))\n'
        '\t\t\t\tparsed["agent_family_before_apply"] = agent.action_family(str(agent.current.get("action", "look"))) if not agent.current.is_empty() else ""\n'
        '\t\t\t\tparsed["agent_phase"] = agent.phase\n'
        '\t\t\t\tparsed["agent_position"] = [agent.position.x, agent.position.y, agent.position.z]\n'
        '\t\t\t\tparsed["last_neural_actuation"] = agent.neural_last_actuation.duplicate(true)\n'
        '\n'
        'func append_log(payload: Dictionary) -> void:\n'
        '\tpass\n'
    )

    main_fixture = (
        'func _process(dt: float) -> void:\n'
        '\tif quit_after > 0 and total_runtime >= quit_after:\n'
        '\t\tsave(false)\n'
        '\t\tprint("BirdAI smoke complete: ", agent.decision_count, " decisions; ", agent.memory.total_episodes, " episodes.")\n'
        '\t\tif neural != null:\n'
        '\t\t\tneural.shutdown()\n'
        '\t\tget_tree().quit()\n'
        '\n'
        'func save() -> void:\n'
        '\tpass\n'
    )

    agent_fixture = (
        'func select_action() -> void:\n'
        '\tphase = "approach"\n'
        '\tphase_time = 0\n'
        '\tif phase == "act":\n'
        '\t\tbegin_act()\n'
        '\n'
        'func finish(result: Dictionary) -> void:\n'
        '\tvar reward = 0.0\n'
        '\tvar learned = {"prediction_error": 0.0}\n'
        '\tthought = result.outcome\n'
        '\tcurrent = {}\n'
        '\n'
        'func touch() -> String:\n'
        '\treturn ""\n'
        '\n'
        'func set_neural_control(enabled: bool) -> void:\n'
        '\tpass\n'
    )

    bridge = instrument_bridge(bridge_fixture)
    main = instrument_main(main_fixture)
    agent = instrument_agent(agent_fixture)

    assert 'record_session_end' in bridge
    assert 'BIRDAI_E1_TRACE_PATH' in bridge
    assert '"--seed", str(neural_seed)' in bridge
    assert 'parsed["event"] = "neural_decision"' in bridge
    assert 'neural.record_session_end(agent, "quit_after")' in main
    assert '"event": "actuation_resolved"' in agent
    assert '"event": "action_outcome"' in agent
    assert 'func e1_a1_append_event' in agent



def decode_snapshot(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        outer = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AuditError(f"Invalid snapshot JSON: {path}: {exc}") from exc
    if not isinstance(outer, dict):
        raise AuditError(f"Snapshot envelope is not an object: {path}")
    payload = outer.get("payload")
    claimed = outer.get("sha256")
    if not isinstance(payload, str) or not isinstance(claimed, str):
        raise AuditError(f"Snapshot lacks payload/sha256 envelope: {path}")
    actual = sha256_bytes(payload.encode("utf-8"))
    if claimed != actual:
        raise AuditError(
            f"Snapshot envelope checksum mismatch: claimed={claimed}, actual={actual}"
        )
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise AuditError("Snapshot payload is not an object.")
    if not isinstance(data.get("agent"), dict):
        raise AuditError("Snapshot payload lacks agent state.")
    if not isinstance(data.get("world"), dict):
        raise AuditError("Snapshot payload lacks world state.")
    return outer, data


def project_name(repo: Path) -> str:
    text = (repo / "project.godot").read_text(encoding="utf-8", errors="replace")
    match = re.search(r'(?m)^config/name="([^"]+)"$', text)
    return match.group(1) if match else ""


def bootstrap_snapshot(repo: Path) -> Path:
    source_root = Path(r"C:\BirdAI_E1_evidence") / "source-snapshots"
    source_root.mkdir(parents=True, exist_ok=True)
    target = source_root / f"e1-a1-bootstrap-{RUNTIME_COMMIT[:7]}.json"

    if target.is_file():
        decode_snapshot(target)
        return target.resolve()

    sandbox = source_root / f"_bootstrap-{RUNTIME_COMMIT[:7]}-{os.getpid()}"
    if sandbox.exists():
        shutil.rmtree(sandbox, ignore_errors=True)

    run(
        ["git", "worktree", "add", "--detach", str(sandbox), RUNTIME_COMMIT],
        cwd=repo,
        timeout=120,
    )

    bootstrap_script = sandbox / "e1_a1_bootstrap_snapshot.gd"
    bootstrap_stdout = source_root / f"e1-a1-bootstrap-{RUNTIME_COMMIT[:7]}.stdout.txt"
    bootstrap_stderr = source_root / f"e1-a1-bootstrap-{RUNTIME_COMMIT[:7]}.stderr.txt"

    bootstrap_source = r"""extends SceneTree
const World = preload("res://scripts/world/world_state.gd")
const Agent = preload("res://scripts/cognition/agent.gd")
const Persistence = preload("res://scripts/persistence.gd")

func _initialize() -> void:
    var output_path = OS.get_environment("BIRDAI_E1_BOOTSTRAP_PATH")
    if output_path.is_empty():
        push_error("BIRDAI_E1_BOOTSTRAP_PATH is empty")
        quit(2)
        return

    var world = World.new()
    var agent = Agent.new(world, 20260910)
    agent.individual_id = "alma-e1-a1-bootstrap-20260910"

    var persistence = Persistence.new(output_path)
    if not persistence.save(agent, world):
        push_error("Could not save bootstrap snapshot: " + persistence.message)
        quit(3)
        return

    print("E1_A1_BOOTSTRAP_SNAPSHOT: ", output_path)
    quit(0)
"""

    try:
        bootstrap_script.write_text(
            bootstrap_source,
            encoding="utf-8",
            newline="\n",
        )

        godot = discover_godot(repo)
        env = os.environ.copy()
        env["BIRDAI_E1_BOOTSTRAP_PATH"] = str(target)

        result = run(
            [
                str(godot),
                "--headless",
                "--path",
                str(sandbox),
                "--script",
                str(bootstrap_script),
            ],
            cwd=sandbox,
            env=env,
            timeout=120,
            check=False,
        )
        bootstrap_stdout.write_text(result.stdout, encoding="utf-8")
        bootstrap_stderr.write_text(result.stderr, encoding="utf-8")

        if result.returncode != 0:
            raise AuditError(
                "Could not bootstrap a valid persistent E1-A1 source snapshot. "
                f"Godot exit code={result.returncode}. "
                f"See {bootstrap_stdout} and {bootstrap_stderr}."
            )
        if not target.is_file():
            raise AuditError(
                "Bootstrap Godot run completed but did not create "
                f"the expected snapshot: {target}"
            )

        _, data = decode_snapshot(target)
        if int(data.get("schema", 0)) not in (1, 2):
            raise AuditError(
                f"Bootstrap snapshot has unsupported schema: {data.get('schema')}"
            )

        return target.resolve()
    finally:
        remove_worktree(repo, sandbox)


def discover_snapshot(repo: Path) -> tuple[Path, list[str], str]:
    appdata = os.environ.get("APPDATA")
    candidates: list[Path] = []

    if appdata:
        root = Path(appdata) / "Godot" / "app_userdata"
        if root.is_dir():
            for path in root.glob("*/alma/individual.json"):
                try:
                    decode_snapshot(path)
                except Exception:
                    continue
                candidates.append(path.resolve())

        exact_name = project_name(repo)
        if exact_name:
            exact_path = (root / exact_name / "alma" / "individual.json").resolve()
            if exact_path in candidates:
                return (
                    exact_path,
                    [str(path) for path in candidates],
                    "existing-user-persistent-snapshot",
                )

    if candidates:
        candidates.sort(
            key=lambda path: (path.stat().st_mtime_ns, str(path)),
            reverse=True,
        )
        return (
            candidates[0],
            [str(path) for path in candidates],
            "existing-valid-persistent-snapshot",
        )

    bootstrapped = bootstrap_snapshot(repo)
    return (
        bootstrapped,
        [],
        "deterministic-bootstrap-via-pinned-runtime-persistence",
    )


def discover_python() -> Path:
    configured = os.environ.get("BIRDAI_PYTHON")
    candidates = [
        Path(configured) if configured else None,
        Path(r"C:\BirdAI_P1_env\Scripts\python.exe"),
    ]
    for candidate in candidates:
        if candidate is None or not candidate.is_file():
            continue
        probe = subprocess.run(
            [str(candidate), "-B", "-c", "import nengo,numpy; print('ok')"],
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        if probe.returncode == 0:
            return candidate.resolve()
    raise AuditError("Python with nengo+numpy not found; set BIRDAI_PYTHON.")


def discover_godot(repo: Path) -> Path:
    configured = os.environ.get("GODOT_EXE")
    if configured and Path(configured).is_file():
        return Path(configured).resolve()

    preferred = repo / "tools" / "Godot.exe"
    if preferred.is_file():
        return preferred.resolve()

    downloads = Path.home() / "Downloads"
    matches = sorted(downloads.rglob("Godot*_console.exe")) if downloads.is_dir() else []
    if matches:
        return matches[-1].resolve()

    raise AuditError("Godot executable not found; set GODOT_EXE.")


def version_metadata(repo: Path, godot: Path, python_exe: Path) -> dict[str, Any]:
    godot_version = run(
        [str(godot), "--version"],
        cwd=repo,
        timeout=30,
    ).stdout.strip()

    probe = run(
        [
            str(python_exe),
            "-B",
            "-c",
            (
                "import json,platform,nengo,numpy;"
                "\ntry:\n import scipy; sv=scipy.__version__"
                "\nexcept Exception:\n sv=None"
                "\nprint(json.dumps({"
                "'python':platform.python_version(),"
                "'nengo':nengo.__version__,"
                "'numpy':numpy.__version__,"
                "'scipy':sv}))"
            ),
        ],
        cwd=repo,
        timeout=30,
    )
    py = json.loads(probe.stdout.strip())

    project_text = (repo / "project.godot").read_text(encoding="utf-8", errors="replace")
    bird_match = re.search(r'config/name="([^"]+)"', project_text)
    bird_version = bird_match.group(1) if bird_match else "unknown"

    bridge_text = git_show(repo, RUNTIME_COMMIT, BRIDGE_REL)
    neural_match = re.search(r'"neural_brain": "([^"]+)"', bridge_text)
    neural_version = neural_match.group(1) if neural_match else "unknown"

    return {
        "birdai_version": bird_version,
        "neural_brain_version": neural_version,
        "godot_version": godot_version,
        "godot_sha256": sha256_file(godot),
        **py,
    }


def wait_port_free(timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", PORT)) != 0:
                return
        time.sleep(0.2)
    raise AuditError(
        f"TCP port {PORT} remained occupied; stop any existing NeuralBrain process."
    )


def remove_worktree(repo: Path, path: Path) -> None:
    run(
        ["git", "worktree", "remove", "--force", str(path)],
        cwd=repo,
        check=False,
        timeout=120,
    )
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    run(["git", "worktree", "prune"], cwd=repo, check=False)


def write_instrumented_runtime(repo: Path, sandbox: Path) -> dict[str, str]:
    actual = {
        BRIDGE_REL: git_blob(repo, RUNTIME_COMMIT, BRIDGE_REL),
        MAIN_REL: git_blob(repo, RUNTIME_COMMIT, MAIN_REL),
        AGENT_REL: git_blob(repo, RUNTIME_COMMIT, AGENT_REL),
    }
    expected = {
        BRIDGE_REL: BRIDGE_BLOB,
        MAIN_REL: MAIN_BLOB,
        AGENT_REL: AGENT_BLOB,
    }
    if actual != expected:
        raise AuditError(
            "Pinned runtime blobs changed; refusing to adapt instrumentation.\n"
            f"Expected: {expected}\nActual: {actual}"
        )

    transformed = {
        BRIDGE_REL: instrument_bridge(git_show(repo, RUNTIME_COMMIT, BRIDGE_REL)),
        MAIN_REL: instrument_main(git_show(repo, RUNTIME_COMMIT, MAIN_REL)),
        AGENT_REL: instrument_agent(git_show(repo, RUNTIME_COMMIT, AGENT_REL)),
    }
    hashes: dict[str, str] = {}
    for rel, content in transformed.items():
        path = sandbox / rel
        path.write_text(content, encoding="utf-8", newline="\n")
        hashes[rel] = sha256_bytes(content.encode("utf-8"))
    return hashes


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise AuditError(f"Trace missing: {path}")
    events: list[dict[str, Any]] = []
    for line_no, raw in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(),
        start=1,
    ):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except Exception as exc:
            raise AuditError(
                f"Invalid JSONL at {path}:{line_no}: {exc}"
            ) from exc
        if not isinstance(value, dict):
            raise AuditError(f"Trace event is not an object at line {line_no}.")
        events.append(value)
    if not events:
        raise AuditError(f"Trace is empty: {path}")
    return events


def winner(values: Any) -> str:
    if not isinstance(values, dict) or not values:
        return ""
    numeric: list[tuple[str, float]] = []
    for key, value in values.items():
        try:
            numeric.append((str(key), float(value)))
        except Exception:
            return ""
    return max(numeric, key=lambda item: item[1])[0]


def process_trace(
    raw_events: list[dict[str, Any]],
    processed_path: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    decisions = {
        int(event.get("request_id", -1)): event
        for event in raw_events
        if event.get("event") == "neural_decision"
        and int(event.get("request_id", -1)) >= 0
    }
    actuations = {
        int(event.get("request_id", -1)): event
        for event in raw_events
        if event.get("event") == "actuation_resolved"
        and int(event.get("request_id", -1)) >= 0
    }
    outcomes: dict[int, list[dict[str, Any]]] = {}
    for event in raw_events:
        if event.get("event") != "action_outcome":
            continue
        request_id = int(event.get("request_id", -1))
        if request_id >= 0:
            outcomes.setdefault(request_id, []).append(event)

    processed: list[dict[str, Any]] = []
    errors: list[str] = []

    for index, event in enumerate(raw_events):
        item = json.loads(json.dumps(event))
        item["trace_index"] = index

        if item.get("event") == "neural_decision":
            request_id = int(item.get("request_id", -1))
            item["competition_winner"] = winner(item.get("competition_values"))
            item["bg_winner"] = winner(item.get("basal_ganglia"))
            if request_id in actuations:
                actuation = actuations[request_id]
                item["resolution_status"] = "actuated"
                item["resolved_actuator_action"] = actuation.get("action", "")
                item["resolved_actuator_target"] = actuation.get("target", "")
                item["resolved_actuator_age"] = actuation.get("age")
            else:
                item["resolution_status"] = "not_actuated_within_observation_window"
                item["resolved_actuator_action"] = ""
                item["resolved_actuator_target"] = ""
                item["resolved_actuator_age"] = None
            item["outcomes_for_request"] = outcomes.get(request_id, [])

            required = (
                "request_id",
                "age",
                "inputs",
                "action_values",
                "competition_values",
                "basal_ganglia",
                "selected",
                "response_agent_age",
                "agent_state_at_response",
                "world_state_at_response",
                "agent_action_before_apply",
                "agent_target_before_apply",
            )
            missing = [field for field in required if field not in item]
            if missing:
                errors.append(
                    f"request {request_id}: missing trace fields {missing}"
                )

        processed.append(item)

    if not decisions:
        errors.append("trace contains no neural_decision events")
    if raw_events[0].get("event") != "session_start":
        errors.append("first event is not session_start")
    if raw_events[-1].get("event") != "session_end":
        errors.append("last event is not session_end")
    else:
        if raw_events[-1].get("termination_reason") != "quit_after":
            errors.append("session_end termination_reason is not quit_after")

    start = raw_events[0]
    if start.get("mode") != "control":
        errors.append("session_start mode is not control")
    if start.get("actuator_authority") != "neural":
        errors.append("session_start actuator authority is not neural")
    if int(start.get("neural_seed", -1)) != NEURAL_SEED:
        errors.append("session_start neural seed mismatch")
    if start.get("neural_start_mode") != "cold":
        errors.append("session_start neural start is not cold")

    for event in raw_events:
        authority = event.get("actuator_authority")
        if authority is not None and authority != "neural":
            errors.append(
                f"event {event.get('event')}: non-neural actuator authority {authority!r}"
            )

    with processed_path.open("w", encoding="utf-8", newline="\n") as handle:
        for event in processed:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    return processed, errors


def normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: normalize(item)
            for key, item in value.items()
            if key not in PROVENANCE_ONLY_KEYS
        }
    if isinstance(value, list):
        return [normalize(item) for item in value]
    return value


def compare_values(
    a: Any,
    b: Any,
    path: str = "$",
) -> dict[str, Any] | None:
    if isinstance(a, bool) or isinstance(b, bool):
        return None if a == b else {"field": path, "a": a, "b": b}

    if (
        isinstance(a, (int, float))
        and not isinstance(a, bool)
        and isinstance(b, (int, float))
        and not isinstance(b, bool)
    ):
        af = float(a)
        bf = float(b)
        if math.isclose(af, bf, abs_tol=ABS_TOL, rel_tol=REL_TOL):
            return None
        delta = abs(af - bf)
        denom = max(abs(af), abs(bf), ABS_TOL)
        return {
            "field": path,
            "a": a,
            "b": b,
            "absolute_delta": delta,
            "relative_delta": delta / denom,
        }

    if type(a) is not type(b):
        return {
            "field": path,
            "a": a,
            "b": b,
            "type_a": type(a).__name__,
            "type_b": type(b).__name__,
        }

    if isinstance(a, dict):
        if set(a) != set(b):
            return {
                "field": path,
                "missing_from_a": sorted(set(b) - set(a)),
                "missing_from_b": sorted(set(a) - set(b)),
            }
        for key in sorted(a):
            diff = compare_values(a[key], b[key], f"{path}.{key}")
            if diff is not None:
                return diff
        return None

    if isinstance(a, list):
        if len(a) != len(b):
            return {
                "field": path,
                "a_length": len(a),
                "b_length": len(b),
            }
        for index, (left, right) in enumerate(zip(a, b)):
            diff = compare_values(left, right, f"{path}[{index}]")
            if diff is not None:
                return diff
        return None

    return None if a == b else {"field": path, "a": a, "b": b}


def nearest_scheduling_context(
    events: list[dict[str, Any]],
    index: int,
) -> dict[str, Any] | None:
    for cursor in range(min(index, len(events) - 1), -1, -1):
        event = events[cursor]
        if event.get("event") == "neural_decision":
            return {
                "request_id": event.get("request_id"),
                "request_age": event.get("age"),
                "response_agent_age": event.get("response_agent_age"),
                "request_sent_ticks_usec": event.get("request_sent_ticks_usec"),
                "response_ticks_usec": event.get("response_ticks_usec"),
                "round_trip_ms": event.get("round_trip_ms"),
            }
    return None


def compare_traces(
    events_a: list[dict[str, Any]],
    events_b: list[dict[str, Any]],
) -> dict[str, Any]:
    count = min(len(events_a), len(events_b))
    last_match: dict[str, Any] | None = None

    for index in range(count):
        left = events_a[index]
        right = events_b[index]
        diff = compare_values(
            normalize(left),
            normalize(right),
            f"trace[{index}]",
        )
        if diff is not None:
            upstream = None
            if (
                left.get("event") == "neural_decision"
                and right.get("event") == "neural_decision"
            ):
                upstream = (
                    compare_values(
                        normalize(left.get("inputs", {})),
                        normalize(right.get("inputs", {})),
                        "inputs",
                    )
                    is not None
                )
            return {
                "equal": False,
                "last_matching_comparison_event": last_match,
                "first_diverging_event": {
                    "index": index,
                    "event_a": left.get("event"),
                    "event_b": right.get("event"),
                    "request_id_a": left.get("request_id"),
                    "request_id_b": right.get("request_id"),
                },
                "divergence": diff,
                "upstream_inputs_already_differed": upstream,
                "nearest_prior_scheduling_context": {
                    "a": nearest_scheduling_context(events_a, index),
                    "b": nearest_scheduling_context(events_b, index),
                },
            }
        last_match = {
            "index": index,
            "event": left.get("event"),
            "request_id": left.get("request_id"),
        }

    if len(events_a) != len(events_b):
        return {
            "equal": False,
            "last_matching_comparison_event": last_match,
            "first_diverging_event": {
                "index": count,
                "event_a": events_a[count].get("event") if count < len(events_a) else None,
                "event_b": events_b[count].get("event") if count < len(events_b) else None,
                "reason": "trace_event_count_mismatch",
            },
            "divergence": {
                "field": "trace_event_count",
                "a": len(events_a),
                "b": len(events_b),
            },
            "upstream_inputs_already_differed": None,
            "nearest_prior_scheduling_context": {
                "a": nearest_scheduling_context(events_a, count - 1),
                "b": nearest_scheduling_context(events_b, count - 1),
            },
        }

    return {
        "equal": True,
        "last_matching_comparison_event": last_match,
        "first_diverging_event": None,
        "divergence": None,
        "upstream_inputs_already_differed": False,
        "nearest_prior_scheduling_context": None,
    }


def run_one(
    *,
    repo: Path,
    evidence_root: Path,
    source: Path,
    source_hash: str,
    source_data: dict[str, Any],
    godot: Path,
    python_exe: Path,
    versions: dict[str, Any],
    experiment_id: str,
    run_id: str,
    duration: float,
) -> dict[str, Any]:
    run_dir = evidence_root / f"run_{run_id.lower()}"
    sandbox = evidence_root / f"sandbox_{run_id.lower()}"
    run_dir.mkdir(parents=True, exist_ok=False)

    save_path = run_dir / "individual.json"
    raw_trace_path = run_dir / "trace.raw.jsonl"
    processed_trace_path = run_dir / "trace.processed.jsonl"
    stdout_path = run_dir / "godot.stdout.txt"
    stderr_path = run_dir / "godot.stderr.txt"
    capsule_path = run_dir / "capsule.json"

    shutil.copy2(source, save_path)
    initial_copy_hash = sha256_file(save_path)
    if initial_copy_hash != source_hash:
        raise AuditError(
            f"Run {run_id}: run-local source copy is not byte-identical."
        )

    run(
        ["git", "worktree", "add", "--detach", str(sandbox), RUNTIME_COMMIT],
        cwd=repo,
        timeout=120,
    )

    try:
        instrumentation_hashes = write_instrumented_runtime(repo, sandbox)
        wait_port_free()

        env = os.environ.copy()
        env["BIRDAI_PYTHON"] = str(python_exe)
        env["BIRDAI_E1_EXPERIMENT_ID"] = experiment_id
        env["BIRDAI_E1_RUN_ID"] = run_id
        env["BIRDAI_E1_NEURAL_SEED"] = str(NEURAL_SEED)
        env["BIRDAI_E1_TRACE_PATH"] = str(raw_trace_path)

        command = [
            str(godot),
            "--headless",
            "--path",
            str(sandbox),
            "--",
            "--neural-control",
            f"--save-path={save_path}",
            f"--quit-after={duration}",
        ]

        wall_start = datetime.now(timezone.utc).isoformat()
        monotonic_start = time.monotonic()
        result = run(
            command,
            cwd=sandbox,
            env=env,
            timeout=max(150.0, duration + 120.0),
            check=False,
        )
        elapsed = time.monotonic() - monotonic_start
        wall_end = datetime.now(timezone.utc).isoformat()

        stdout_path.write_text(result.stdout, encoding="utf-8")
        stderr_path.write_text(result.stderr, encoding="utf-8")
        wait_port_free()

        if result.returncode != 0:
            raise AuditError(
                f"Run {run_id} Godot exit code {result.returncode}. "
                f"See {stdout_path} and {stderr_path}."
            )

        raw_events = load_jsonl(raw_trace_path)
        processed_events, trace_errors = process_trace(
            raw_events,
            processed_trace_path,
        )
        if trace_errors:
            raise AuditError(
                f"Run {run_id} trace invalid: " + "; ".join(trace_errors)
            )

        _, final_data = decode_snapshot(save_path)
        final_age = final_data["agent"].get("age")

        session_end = raw_events[-1]
        if session_end.get("termination_reason") != "quit_after":
            raise AuditError(
                f"Run {run_id} did not terminate via quit_after."
            )

        capsule = {
            "experiment_id": experiment_id,
            "stage": STAGE,
            "run_id": run_id,
            "git_commit_sha": RUNTIME_COMMIT,
            "harness_git_commit_sha": run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
            ).stdout.strip(),
            "birdai_version": versions["birdai_version"],
            "neural_brain_version": versions["neural_brain_version"],
            "godot_version": versions["godot_version"],
            "godot_sha256": versions["godot_sha256"],
            "python_version": versions["python"],
            "nengo_version": versions["nengo"],
            "numpy_version": versions["numpy"],
            "scipy_version": versions["scipy"],
            "source_snapshot_sha256": source_hash,
            "agent_state_sha256": canonical_hash(source_data["agent"]),
            "world_state_sha256": canonical_hash(source_data["world"]),
            "world_layout_version": source_data["world"].get("layout_version"),
            "agent_rng_seed": source_data["agent"].get("rng_seed"),
            "agent_rng_initial_state": source_data["agent"].get("rng_state"),
            "neural_seed": NEURAL_SEED,
            "neural_start_mode": "cold",
            "body_world_simulation_step_seconds": 1.0 / 60.0,
            "neural_request_interval_seconds": 0.20,
            "neural_step_seconds": 0.05,
            "control_mode": "control",
            "actuator_authority": "neural",
            "simulated_start_time": source_data["agent"].get("age"),
            "simulated_end_time": final_age,
            "wall_clock_start": wall_start,
            "wall_clock_end": wall_end,
            "wall_clock_elapsed_seconds": elapsed,
            "termination_reason": "quit_after",
            "raw_trace_path": str(raw_trace_path),
            "raw_trace_sha256": sha256_file(raw_trace_path),
            "processed_trace_path": str(processed_trace_path),
            "processed_trace_sha256": sha256_file(processed_trace_path),
            "result_comparison_path": None,
            "result_comparison_sha256": None,
            "sandbox_only_instrumentation": True,
            "instrumented_source_sha256": instrumentation_hashes,
            "run_local_initial_snapshot_sha256": initial_copy_hash,
            "run_local_final_snapshot_sha256": sha256_file(save_path),
            "command_configuration": {
                "headless": True,
                "neural_control": True,
                "quit_after_seconds": duration,
                "port": PORT,
            },
        }

        capsule_path.write_text(
            json.dumps(capsule, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        return {
            "capsule": capsule,
            "capsule_path": capsule_path,
            "processed_events": processed_events,
            "final_data": final_data,
        }
    finally:
        remove_worktree(repo, sandbox)


def self_test() -> None:
    validate_instrumentation_self_test()

    event_a = {
        "event": "neural_decision",
        "experiment_id": "X",
        "run_id": "A",
        "request_id": 1,
        "age": 10.0,
        "request_sent_ticks_usec": 100,
        "response_ticks_usec": 200,
        "round_trip_ms": 0.1,
        "inputs": {"hunger": 0.2},
        "selected": "EXPLORE",
    }
    event_b = {
        **event_a,
        "run_id": "B",
        "request_sent_ticks_usec": 500,
        "response_ticks_usec": 700,
        "round_trip_ms": 0.2,
    }
    assert compare_values(normalize(event_a), normalize(event_b)) is None

    changed = json.loads(json.dumps(event_b))
    changed["selected"] = "REST"
    result = compare_traces([event_a], [changed])
    assert result["equal"] is False
    assert result["divergence"]["field"].endswith(".selected")

    near = json.loads(json.dumps(event_b))
    near["age"] = 10.0 + 5e-10
    assert compare_values(normalize(event_a), normalize(near)) is None

    print("SELF_TEST: PASS")
    print("PINNED_SANDBOX_INSTRUMENTATION: PASS")
    print("FIRST_DIVERGENCE_COMPARATOR: PASS")
    print("FIXED_NUMERIC_TOLERANCE: 1e-9")
    print("WALL_CLOCK_SCHEDULING_FIELDS: PROVENANCE_ONLY")
    print("MISSING_USER_SNAPSHOT_FALLBACK: DETERMINISTIC_BOOTSTRAP")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="E1-A1 identical closed-loop replay audit."
    )
    parser.add_argument("--repo", default=r"C:\AlmaTheHen")
    parser.add_argument("--source-snapshot")
    parser.add_argument(
        "--evidence-root",
        default=r"C:\BirdAI_E1_evidence",
    )
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    if args.duration <= 0:
        raise AuditError("--duration must be positive.")

    repo = Path(args.repo).resolve()
    status = run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repo,
    ).stdout
    if status:
        raise AuditError(
            "Primary repository must be clean before audit:\n" + status
        )

    runtime_head = run(
        ["git", "rev-parse", "origin/main"],
        cwd=repo,
    ).stdout.strip()
    if runtime_head != RUNTIME_COMMIT:
        raise AuditError(
            f"origin/main moved after harness creation: "
            f"expected {RUNTIME_COMMIT}, got {runtime_head}."
        )

    if args.source_snapshot:
        source = Path(args.source_snapshot).resolve()
        candidates: list[str] = []
        source_origin = "explicit-source-snapshot"
    else:
        source, candidates, source_origin = discover_snapshot(repo)

    if not source.is_file():
        raise AuditError(f"Source snapshot not found: {source}")

    source_hash_before = sha256_file(source)
    _, source_data = decode_snapshot(source)

    python_exe = discover_python()
    godot = discover_godot(repo)
    versions = version_metadata(repo, godot, python_exe)

    experiment_id = f"e1-a1-{utc_stamp()}-{RUNTIME_COMMIT[:7]}"
    evidence_root = Path(args.evidence_root) / experiment_id
    evidence_root.mkdir(parents=True, exist_ok=False)

    config = {
        "experiment_id": experiment_id,
        "stage": STAGE,
        "runtime_git_commit": RUNTIME_COMMIT,
        "source_snapshot": str(source),
        "source_snapshot_origin": source_origin,
        "source_snapshot_candidates": candidates,
        "source_snapshot_sha256": source_hash_before,
        "neural_seed": NEURAL_SEED,
        "neural_start_mode": "cold",
        "duration_seconds": args.duration,
        "abs_tolerance": ABS_TOL,
        "rel_tolerance": REL_TOL,
        "run_order": ["A", "B"],
        "control_A_equals_control_B": True,
        "environment_override": None,
        "sandbox_only_diagnostic_instrumentation": True,
    }
    (evidence_root / "experiment-config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("========================================")
    print("E1-A1 IDENTICAL CLOSED-LOOP REPLAY")
    print(f"EXPERIMENT: {experiment_id}")
    print(f"RUNTIME_COMMIT: {RUNTIME_COMMIT}")
    print(f"SOURCE: {source}")
    print(f"SOURCE_ORIGIN: {source_origin}")
    print(f"SOURCE_SHA256: {source_hash_before}")
    print(f"EVIDENCE: {evidence_root}")
    print("CONTROL_A == CONTROL_B")
    print("PRODUCTION_RUNTIME_MUTATION: NONE")
    print("========================================")

    run_a = run_one(
        repo=repo,
        evidence_root=evidence_root,
        source=source,
        source_hash=source_hash_before,
        source_data=source_data,
        godot=godot,
        python_exe=python_exe,
        versions=versions,
        experiment_id=experiment_id,
        run_id="A",
        duration=args.duration,
    )
    run_b = run_one(
        repo=repo,
        evidence_root=evidence_root,
        source=source,
        source_hash=source_hash_before,
        source_data=source_data,
        godot=godot,
        python_exe=python_exe,
        versions=versions,
        experiment_id=experiment_id,
        run_id="B",
        duration=args.duration,
    )

    source_hash_after = sha256_file(source)
    validity_errors: list[str] = []
    if source_hash_after != source_hash_before:
        validity_errors.append("immutable source snapshot mutated")

    shared_capsule_fields = (
        "git_commit_sha",
        "birdai_version",
        "neural_brain_version",
        "godot_version",
        "godot_sha256",
        "python_version",
        "nengo_version",
        "numpy_version",
        "scipy_version",
        "source_snapshot_sha256",
        "agent_state_sha256",
        "world_state_sha256",
        "world_layout_version",
        "agent_rng_seed",
        "agent_rng_initial_state",
        "neural_seed",
        "neural_start_mode",
        "body_world_simulation_step_seconds",
        "neural_request_interval_seconds",
        "neural_step_seconds",
        "control_mode",
        "actuator_authority",
        "termination_reason",
        "sandbox_only_instrumentation",
        "instrumented_source_sha256",
        "run_local_initial_snapshot_sha256",
        "command_configuration",
    )
    for field in shared_capsule_fields:
        if run_a["capsule"].get(field) != run_b["capsule"].get(field):
            validity_errors.append(f"run capsule mismatch: {field}")

    comparison = None
    final_state_diff = None
    if not validity_errors:
        comparison = compare_traces(
            run_a["processed_events"],
            run_b["processed_events"],
        )
        final_state_diff = compare_values(
            normalize(run_a["final_data"]),
            normalize(run_b["final_data"]),
            "final_persistent_state",
        )
        equal = comparison["equal"] and final_state_diff is None
        verdict = (
            "PASS — IDENTICAL_CONTROL_REPLAY_REPRODUCIBLE"
            if equal
            else "BLOCKED — CLOSED_LOOP_RUNTIME_NONDETERMINISTIC"
        )
    else:
        verdict = "INVALID"

    result = {
        "experiment_id": experiment_id,
        "stage": STAGE,
        "valid": not validity_errors,
        "validity_errors": validity_errors,
        "verdict": verdict,
        "comparison_contract": {
            "discrete_fields": "exact",
            "continuous_abs_tolerance": ABS_TOL,
            "continuous_rel_tolerance": REL_TOL,
            "provenance_only_keys": sorted(PROVENANCE_ONLY_KEYS),
        },
        "source_snapshot_sha256_before": source_hash_before,
        "source_snapshot_sha256_after": source_hash_after,
        "trace_comparison": comparison,
        "final_state_equal": final_state_diff is None,
        "final_state_first_divergence": final_state_diff,
    }

    comparison_path = evidence_root / "comparison.json"
    comparison_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    comparison_hash = sha256_file(comparison_path)

    for run_result in (run_a, run_b):
        capsule = json.loads(
            run_result["capsule_path"].read_text(encoding="utf-8")
        )
        capsule["result_comparison_path"] = str(comparison_path)
        capsule["result_comparison_sha256"] = comparison_hash
        run_result["capsule_path"].write_text(
            json.dumps(capsule, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    primary_status = run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repo,
    ).stdout
    if primary_status:
        raise AuditError(
            "Primary repository changed during sandbox audit:\n" + primary_status
        )

    print("")
    print("========================================")
    print("STATUS: PASS" if verdict != "INVALID" else "STATUS: INVALID")
    print(f"E1_A1_VERDICT: {verdict}")
    print(f"SOURCE_IMMUTABLE: {source_hash_before == source_hash_after}")
    print(f"TRACE_EQUAL: {comparison['equal'] if comparison else False}")
    print(f"FINAL_STATE_EQUAL: {final_state_diff is None}")
    if comparison and not comparison["equal"]:
        print(
            "FIRST_DIVERGING_EVENT: "
            + json.dumps(
                comparison["first_diverging_event"],
                ensure_ascii=False,
            )
        )
        print(
            "DIVERGENCE: "
            + json.dumps(
                comparison["divergence"],
                ensure_ascii=False,
            )
        )
        print(
            "UPSTREAM_INPUTS_ALREADY_DIFFERED: "
            + str(comparison["upstream_inputs_already_differed"])
        )
        print(
            "NEAREST_PRIOR_SCHEDULING_CONTEXT: "
            + json.dumps(
                comparison["nearest_prior_scheduling_context"],
                ensure_ascii=False,
            )
        )
    if final_state_diff is not None:
        print(
            "FINAL_STATE_FIRST_DIVERGENCE: "
            + json.dumps(final_state_diff, ensure_ascii=False)
        )
    print(f"COMPARISON: {comparison_path}")
    print(f"EVIDENCE: {evidence_root}")
    print("PRIMARY_REPOSITORY_MUTATION: NONE")
    print("PRODUCTION_RUNTIME_MUTATION: NONE")
    print("========================================")

    return 2 if verdict == "INVALID" else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuditError as exc:
        print("STATUS: INVALID", file=sys.stderr)
        print(f"BLOCKER: {exc}", file=sys.stderr)
        raise SystemExit(2)
