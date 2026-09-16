from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUNTIME_COMMIT = "aafc6f5f28fa3c6892775ed0125ae4798796dfe4"
MAIN_BLOB = "66daffb205d680e64d55b314a6c9a92bfe98a0c3"
BRIDGE_BLOB = "b7fd20af2f92f9156d8db5d820e2592e8b62c9a0"
BASE_HARNESS_BLOB = "8309b217f21b779bae5ae593e1cb91f3b980c695"

MAIN_REL = "scripts/main.gd"
BRIDGE_REL = "scripts/cognition/neural_brain_bridge.gd"
BASE_HARNESS_REL = ".birdai/e1_a1_replay_audit.py"

STAGE = "E1-A1-D3"
NEURAL_SEED = 20260910
GATE_DELAY_TICKS = 12
REQUEST_START_TICK = 240
REQUEST_INTERVAL_TICKS = 18
INTERVENTION_REQUEST_ID = 3
STOP_TICK = 480
ACCEPTED_E1_A1_SOURCE_SHA256 = "3b42d55fc595bc7312e932dc9615c08e1ce2abe72f0f2bcc0984e9818e47b218"
ACCEPTED_E1_A1_COMPARISON_SHA256 = "472f0a9db2a42fedabe22fd5e3883c18af41addf9c581a2ed66760f611592fb2"

SUPPORTED = "SUPPORTED — RESPONSE_APPLICATION_TICK_CAUSES_EMBODIED_DIVERGENCE"
FALSIFIED = "FALSIFIED — ONE_TICK_APPLICATION_SHIFT_NOT_SUFFICIENT"
BLOCKED_CONTROL = "BLOCKED — BARRIER_CONTROL_NONDETERMINISTIC"


class DiagnosticError(RuntimeError):
    pass


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def git_blob(repo: Path, commit: str, rel: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", f"{commit}:{rel}"],
        cwd=repo,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise DiagnosticError(
            f"git blob lookup failed for {commit}:{rel}: {result.stderr}"
        )
    return result.stdout.strip()


def git_show(repo: Path, commit: str, rel: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{commit}:{rel}"],
        cwd=repo,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise DiagnosticError(
            f"git show failed for {commit}:{rel}: {result.stderr}"
        )
    return result.stdout.replace("\r\n", "\n").replace("\r", "\n")


def load_base(repo: Path):
    path = repo / BASE_HARNESS_REL
    if not path.is_file():
        raise DiagnosticError(f"Missing accepted E1-A1 harness: {path}")

    runtime_blob = git_blob(repo, RUNTIME_COMMIT, BASE_HARNESS_REL)
    if runtime_blob != BASE_HARNESS_BLOB:
        raise DiagnosticError(
            "Accepted E1-A1 harness blob changed at pinned runtime. "
            f"Expected {BASE_HARNESS_BLOB}, got {runtime_blob}."
        )

    spec = importlib.util.spec_from_file_location("e1_a1_base", path)
    if spec is None or spec.loader is None:
        raise DiagnosticError("Could not load E1-A1 harness module.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_lines(source: str) -> list[str]:
    return source.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def render_source(lines: list[str]) -> str:
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def unique_line(
    lines: list[str],
    exact: str,
    label: str,
    *,
    start: int = 0,
    end: int | None = None,
) -> int:
    stop = len(lines) if end is None else end
    matches = [i for i in range(start, stop) if lines[i] == exact]
    if len(matches) != 1:
        raise DiagnosticError(
            f"{label}: expected one exact line {exact!r}, found {len(matches)}."
        )
    return matches[0]


def function_bounds(
    lines: list[str],
    signature: str,
    label: str,
) -> tuple[int, int]:
    start = unique_line(lines, signature, label)
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("func "):
            end = i
            break
    return start, end


def insert_after(
    lines: list[str],
    exact: str,
    additions: list[str],
    label: str,
    *,
    start: int = 0,
    end: int | None = None,
) -> None:
    i = unique_line(lines, exact, label, start=start, end=end)
    lines[i + 1:i + 1] = additions


def insert_before(
    lines: list[str],
    exact: str,
    additions: list[str],
    label: str,
    *,
    start: int = 0,
    end: int | None = None,
) -> None:
    i = unique_line(lines, exact, label, start=start, end=end)
    lines[i:i] = additions


def replace_line(
    lines: list[str],
    exact: str,
    replacements: list[str],
    label: str,
    *,
    start: int = 0,
    end: int | None = None,
) -> None:
    i = unique_line(lines, exact, label, start=start, end=end)
    lines[i:i + 1] = replacements


def instrument_bridge(source: str) -> str:
    lines = source_lines(source)

    insert_after(
        lines,
        'var mode := "control"',
        [
            'var e1_d3_run_id := ""',
            'var e1_d3_trace_path := ""',
            'var e1_d3_sim_tick := 0',
            'var e1_d3_gate_delay_ticks := 12',
            'var e1_d3_request_start_tick := 240',
            'var e1_d3_request_interval_ticks := 18',
            'var e1_d3_request_schedule_misses := 0',
            'var e1_d3_last_schedule_miss_tick := -1',
            'var e1_d3_late_request_id := -1',
            'var e1_d3_stop_tick := -1',
            'var e1_d3_neural_seed := 20260910',
            'var e1_d3_pending_request_tick := -1',
            'var e1_d3_target_apply_tick := -1',
            'var e1_d3_sent_ticks_usec := 0',
            'var e1_d3_queued_response := {}',
            'var e1_d3_deadline_misses := 0',
            'var e1_d3_session_end_recorded := false',
        ],
        "bridge declarations",
    )

    begin, end = function_bounds(
        lines,
        'func start(requested_mode: String = "control") -> void:',
        "bridge start",
    )
    insert_after(
        lines,
        '\tmode = "shadow" if requested_mode == "shadow" else "control"',
        [
            '\te1_d3_run_id = OS.get_environment("BIRDAI_E1_D3_RUN_ID")',
            '\te1_d3_trace_path = OS.get_environment("BIRDAI_E1_D3_TRACE_PATH")',
            '\tvar configured_gate = OS.get_environment("BIRDAI_E1_D3_GATE_DELAY_TICKS")',
            '\tif not configured_gate.is_empty():',
            '\t\te1_d3_gate_delay_ticks = int(configured_gate)',
            '\tvar configured_start = OS.get_environment("BIRDAI_E1_D3_REQUEST_START_TICK")',
            '\tif not configured_start.is_empty():',
            '\t\te1_d3_request_start_tick = int(configured_start)',
            '\tvar configured_interval = OS.get_environment("BIRDAI_E1_D3_REQUEST_INTERVAL_TICKS")',
            '\tif not configured_interval.is_empty():',
            '\t\te1_d3_request_interval_ticks = int(configured_interval)',
            '\tvar configured_late = OS.get_environment("BIRDAI_E1_D3_LATE_REQUEST_ID")',
            '\tif not configured_late.is_empty():',
            '\t\te1_d3_late_request_id = int(configured_late)',
            '\tvar configured_stop = OS.get_environment("BIRDAI_E1_D3_STOP_TICK")',
            '\tif not configured_stop.is_empty():',
            '\t\te1_d3_stop_tick = int(configured_stop)',
            '\tvar configured_seed = OS.get_environment("BIRDAI_E1_D3_NEURAL_SEED")',
            '\tif not configured_seed.is_empty():',
            '\t\te1_d3_neural_seed = int(configured_seed)',
        ],
        "bridge diagnostic environment",
        start=begin,
        end=end,
    )

    begin, end = function_bounds(
        lines,
        'func start(requested_mode: String = "control") -> void:',
        "bridge start after env",
    )
    replace_line(
        lines,
        '\tlog_path = ProjectSettings.globalize_path("res://data/" + filename)',
        [
            '\tlog_path = e1_d3_trace_path if not e1_d3_trace_path.is_empty() else ProjectSettings.globalize_path("res://data/" + filename)'
        ],
        "bridge run trace path",
        start=begin,
        end=end,
    )

    begin, end = function_bounds(
        lines,
        'func start(requested_mode: String = "control") -> void:',
        "bridge start before provenance",
    )
    replace_line(
        lines,
        '\t\t\t"port": PORT',
        [
            '\t\t\t"port": PORT,',
            '\t\t\t"diagnostic_stage": "E1-A1-D3",',
            '\t\t\t"run_id": e1_d3_run_id,',
            '\t\t\t"gate_delay_ticks": e1_d3_gate_delay_ticks,',
            '\t\t\t"request_scheduler": "per_simulation_step_with_async_response_barrier",',
            '\t\t\t"request_start_tick": e1_d3_request_start_tick,',
            '\t\t\t"request_interval_ticks": e1_d3_request_interval_ticks,',
            '\t\t\t"late_request_id": e1_d3_late_request_id,',
            '\t\t\t"stop_tick": e1_d3_stop_tick,',
            '\t\t\t"tail_request_policy": "reserve_worst_case_plus_one_tick_with_barrier",',
            '\t\t\t"neural_seed": e1_d3_neural_seed',
        ],
        "bridge session provenance",
        start=begin,
        end=end,
    )

    begin, end = function_bounds(
        lines,
        'func find_python() -> String:',
        "bridge find_python",
    )
    lines[begin + 1:begin + 1] = [
        '\tvar configured = OS.get_environment("BIRDAI_PYTHON")',
        '\tif not configured.is_empty() and FileAccess.file_exists(configured):',
        '\t\treturn configured',
    ]

    begin, end = function_bounds(
        lines,
        'func start(requested_mode: String = "control") -> void:',
        "bridge start process",
    )
    replace_line(
        lines,
        '\tprocess_id = OS.create_process(python_path, PackedStringArray([script, "--port", str(PORT)]), false)',
        [
            '\tprocess_id = OS.create_process(python_path, PackedStringArray([script, "--port", str(PORT), "--seed", str(e1_d3_neural_seed)]), false)'
        ],
        "bridge explicit seed",
        start=begin,
        end=end,
    )

    begin, end = function_bounds(
        lines,
        'func tick(dt: float, agent) -> void:',
        "bridge tick",
    )
    schedule_if = unique_line(
        lines,
        '\tif not pending and clock >= UPDATE_INTERVAL:',
        "bridge wall-clock request scheduler",
        start=begin,
        end=end,
    )
    expected_schedule = [
        '\tif not pending and clock >= UPDATE_INTERVAL:',
        '\t\tclock = 0.0',
        '\t\tsend_snapshot(agent)',
    ]
    if lines[schedule_if:schedule_if + 3] != expected_schedule:
        raise DiagnosticError(
            "bridge wall-clock request scheduler shape changed; "
            "refusing adaptive instrumentation."
        )
    lines[schedule_if:schedule_if + 3] = [
        '\t# E1-A1-D3: request emission is driven from record_sim_state(),',
        '\t# once per fixed simulation step, never from frame dt.',
    ]

    begin, end = function_bounds(
        lines,
        'func send_snapshot(agent) -> void:',
        "bridge send_snapshot",
    )
    lines[begin + 1:begin + 1] = [
        '\t# Reserve one extra tick so all arms share the same request cutoff.',
        '\t# LATE3 delays request #3 by exactly one tick; controls use the same',
        '\t# worst-case cutoff to keep the request schedule symmetric.',
        '\tvar e1_d3_worst_case_target = e1_d3_sim_tick + e1_d3_gate_delay_ticks + 1',
        '\tif e1_d3_stop_tick > 0 and e1_d3_worst_case_target > e1_d3_stop_tick:',
        '\t\treturn',
    ]

    begin, end = function_bounds(
        lines,
        'func send_snapshot(agent) -> void:',
        "bridge send_snapshot after tail cutoff",
    )
    insert_after(
        lines,
        '\t\tpending = true',
        [
            '\t\te1_d3_pending_request_tick = e1_d3_sim_tick',
            '\t\te1_d3_target_apply_tick = e1_d3_pending_request_tick + e1_d3_gate_delay_ticks + (1 if request_id == e1_d3_late_request_id else 0)',
            '\t\te1_d3_sent_ticks_usec = Time.get_ticks_usec()',
            '\t\tappend_log({',
            '\t\t\t"event": "request_sent",',
            '\t\t\t"run_id": e1_d3_run_id,',
            '\t\t\t"request_id": request_id,',
            '\t\t\t"request_sim_tick": e1_d3_pending_request_tick,',
            '\t\t\t"target_apply_tick": e1_d3_target_apply_tick,',
            '\t\t\t"age": agent.age,',
            '\t\t\t"inputs": payload.inputs.duplicate(true),',
            '\t\t\t"neural_seconds": payload.neural_seconds',
            '\t\t})',
        ],
        "bridge request scheduling",
        start=begin,
        end=end,
    )

    begin, end = function_bounds(
        lines,
        'func read_available(agent) -> void:',
        "bridge read_available",
    )
    parsed_if = unique_line(
        lines,
        '\t\tif parsed is Dictionary:',
        "bridge parsed response branch",
        start=begin,
        end=end,
    )
    if (
        parsed_if + 1 >= len(lines)
        or lines[parsed_if + 1] != '\t\t\tpending = false'
    ):
        raise DiagnosticError(
            "bridge parsed response branch no longer begins with pending=false."
        )
    lines[parsed_if + 1] = '\t\t\tpending = true'

    begin, end = function_bounds(
        lines,
        'func read_available(agent) -> void:',
        "bridge read_available response",
    )
    accept_matches = [
        i
        for i in range(begin + 1, end - 2)
        if lines[i] == '\t\t\t\t\tagent.accept_neural_decision(parsed)'
        and lines[i - 1] == '\t\t\t\tif mode == "control":'
        and lines[i + 1] == '\t\t\t\tagent.neural_shadow = parsed.duplicate(true)'
        and lines[i + 2] == '\t\t\t\tappend_log(parsed)'
    ]
    if len(accept_matches) != 1:
        raise DiagnosticError(
            "bridge response application block: expected exactly one "
            f"accept/apply sequence, found {len(accept_matches)}"
        )
    accept_index = accept_matches[0]
    block_start = accept_index - 1
    block_end = accept_index + 3
    lines[block_start:block_end] = [
        '\t\t\t\tparsed["event"] = "response_received"',
        '\t\t\t\tparsed["run_id"] = e1_d3_run_id',
        '\t\t\t\tparsed["receive_sim_tick"] = e1_d3_sim_tick',
        '\t\t\t\tparsed["target_apply_tick"] = e1_d3_target_apply_tick',
        '\t\t\t\tparsed["request_sent_ticks_usec"] = e1_d3_sent_ticks_usec',
        '\t\t\t\tparsed["response_ticks_usec"] = Time.get_ticks_usec()',
        '\t\t\t\tparsed["round_trip_ms"] = float(parsed["response_ticks_usec"] - e1_d3_sent_ticks_usec) / 1000.0',
        '\t\t\t\tparsed["receipt_state"] = e1_d3_state(agent)',
        '\t\t\t\te1_d3_queued_response = parsed.duplicate(true)',
        '\t\t\t\tagent.neural_shadow = parsed.duplicate(true)',
        '\t\t\t\tappend_log(parsed)',
    ]

    begin, end = function_bounds(
        lines,
        'func read_available(agent) -> void:',
        "bridge read_available error branch",
    )
    insert_before(
        lines,
        '\t\t\t\tstatus = "hjärnfel"',
        ['\t\t\t\tpending = false'],
        "bridge error releases pending",
        start=begin,
        end=end,
    )

    append_index = unique_line(
        lines,
        'func append_log(payload: Dictionary) -> void:',
        "bridge append_log",
    )
    methods = [
        'func set_sim_tick(tick_value: int) -> void:',
        '\te1_d3_sim_tick = tick_value',
        '',
        'func e1_d3_state(agent) -> Dictionary:',
        '\treturn {',
        '\t\t"agent": agent.export_data(),',
        '\t\t"world": agent.world.export_data(),',
        '\t\t"phase": agent.phase,',
        '\t\t"phase_time": agent.phase_time,',
        '\t\t"current": agent.current.duplicate(true),',
        '\t\t"thought": agent.thought,',
        '\t\t"neural_selection_ready": agent.neural_selection_ready,',
        '\t\t"neural_selected_family": agent.neural_selected_family,',
        '\t\t"neural_request_id": agent.neural_request_id,',
        '\t\t"neural_decision_age": agent.neural_decision_age,',
        '\t\t"last_neural_actuation": agent.neural_last_actuation.duplicate(true)',
        '\t}',
        '',
        'func should_pause_simulation() -> bool:',
        '\treturn pending and e1_d3_queued_response.is_empty()',
        '',
        'func record_sim_state(agent, tick_value: int) -> void:',
        '\te1_d3_sim_tick = tick_value',
        '\tappend_log({',
        '\t\t"event": "sim_state",',
        '\t\t"run_id": e1_d3_run_id,',
        '\t\t"sim_tick": tick_value,',
        '\t\t"state": e1_d3_state(agent)',
        '\t})',
        '\tvar e1_d3_due_tick = e1_d3_request_start_tick + request_id * e1_d3_request_interval_ticks',
        '\tvar e1_d3_worst_case_apply_tick = e1_d3_due_tick + e1_d3_gate_delay_ticks + 1',
        '\tif e1_d3_worst_case_apply_tick > e1_d3_stop_tick:',
        '\t\treturn',
        '\tif tick_value != e1_d3_due_tick:',
        '\t\treturn',
        '\tif pending:',
        '\t\te1_d3_request_schedule_misses += 1',
        '\t\te1_d3_last_schedule_miss_tick = e1_d3_due_tick',
        '\t\tappend_log({',
        '\t\t\t"event": "request_schedule_miss",',
        '\t\t\t"run_id": e1_d3_run_id,',
        '\t\t\t"request_id": request_id + 1,',
        '\t\t\t"due_tick": e1_d3_due_tick,',
        '\t\t\t"observed_tick": tick_value,',
        '\t\t\t"reason": "previous_request_still_pending"',
        '\t\t})',
        '\t\treturn',
        '\tsend_snapshot(agent)',
        '',
        'func before_simulation_step(agent, tick_value: int) -> void:',
        '\te1_d3_sim_tick = tick_value',
        '\tif e1_d3_queued_response.is_empty():',
        '\t\treturn',
        '\tif tick_value < e1_d3_target_apply_tick:',
        '\t\treturn',
        '\tvar deadline_miss = tick_value > e1_d3_target_apply_tick',
        '\tif deadline_miss:',
        '\t\te1_d3_deadline_misses += 1',
        '\tvar decision = e1_d3_queued_response.duplicate(true)',
        '\tappend_log({',
        '\t\t"event": "response_apply_pre",',
        '\t\t"run_id": e1_d3_run_id,',
        '\t\t"request_id": int(decision.get("request_id", -1)),',
        '\t\t"apply_sim_tick": tick_value,',
        '\t\t"target_apply_tick": e1_d3_target_apply_tick,',
        '\t\t"deadline_miss": deadline_miss,',
        '\t\t"state": e1_d3_state(agent)',
        '\t})',
        '\tif mode == "control":',
        '\t\tagent.accept_neural_decision(decision)',
        '\tagent.neural_shadow = decision.duplicate(true)',
        '\tappend_log({',
        '\t\t"event": "response_apply_post",',
        '\t\t"run_id": e1_d3_run_id,',
        '\t\t"request_id": int(decision.get("request_id", -1)),',
        '\t\t"apply_sim_tick": tick_value,',
        '\t\t"target_apply_tick": e1_d3_target_apply_tick,',
        '\t\t"deadline_miss": deadline_miss,',
        '\t\t"state": e1_d3_state(agent)',
        '\t})',
        '\te1_d3_queued_response = {}',
        '\te1_d3_target_apply_tick = -1',
        '\te1_d3_pending_request_tick = -1',
        '\tpending = false',
        '',
        'func record_session_end(agent, reason: String) -> void:',
        '\tif e1_d3_session_end_recorded:',
        '\t\treturn',
        '\te1_d3_session_end_recorded = true',
        '\tappend_log({',
        '\t\t"event": "session_end",',
        '\t\t"run_id": e1_d3_run_id,',
        '\t\t"termination_reason": reason,',
        '\t\t"sim_tick": e1_d3_sim_tick,',
        '\t\t"deadline_misses": e1_d3_deadline_misses,',
        '\t\t"request_schedule_misses": e1_d3_request_schedule_misses,',
        '\t\t"last_schedule_miss_tick": e1_d3_last_schedule_miss_tick,',
        '\t\t"pending": pending,',
        '\t\t"pending_request_tick": e1_d3_pending_request_tick,',
        '\t\t"target_apply_tick": e1_d3_target_apply_tick,',
        '\t\t"queued_response_remaining": not e1_d3_queued_response.is_empty(),',
        '\t\t"queued_request_id": int(e1_d3_queued_response.get("request_id", -1)) if not e1_d3_queued_response.is_empty() else -1,',
        '\t\t"state": e1_d3_state(agent)',
        '\t})',
        '',
    ]
    lines[append_index:append_index] = methods

    result = render_source(lines)
    required = [
        'func before_simulation_step(agent, tick_value: int) -> void:',
        '"event": "request_sent"',
        'parsed["event"] = "response_received"',
        '"event": "response_apply_pre"',
        '"event": "sim_state"',
        'e1_d3_late_request_id',
        '"--seed", str(e1_d3_neural_seed)',
    ]
    missing = [item for item in required if item not in result]
    if missing:
        raise DiagnosticError(f"bridge instrumentation missing {missing}")
    return result


def instrument_main(source: str) -> str:
    lines = source_lines(source)
    insert_after(
        lines,
        'var neural_mode = "control"',
        [
            'var e1_d3_sim_tick := 0',
            'var e1_d3_stop_tick := -1',
        ],
        "main declarations",
    )

    begin, end = function_bounds(
        lines,
        'func _ready() -> void:',
        "main ready",
    )
    insert_after(
        lines,
        '\tget_tree().auto_accept_quit = false',
        [
            '\tvar configured_stop_tick = OS.get_environment("BIRDAI_E1_D3_STOP_TICK")',
            '\tif not configured_stop_tick.is_empty():',
            '\t\te1_d3_stop_tick = int(configured_stop_tick)',
        ],
        "main stop tick",
        start=begin,
        end=end,
    )

    begin, end = function_bounds(
        lines,
        'func _process(dt: float) -> void:',
        "main process",
    )
    replace_line(
        lines,
        '\t\twhile accumulator >= 1.0 / 60:',
        [
            '\t\twhile accumulator >= 1.0 / 60 and (e1_d3_stop_tick < 0 or e1_d3_sim_tick < e1_d3_stop_tick):',
            '\t\t\tif neural != null and not smoke_mode and neural.should_pause_simulation():',
            '\t\t\t\tbreak',
        ],
        "main bounded deterministic step loop with async-response barrier",
        start=begin,
        end=end,
    )

    begin, end = function_bounds(
        lines,
        'func _process(dt: float) -> void:',
        "main process after while",
    )
    replace_line(
        lines,
        '\t\t\tagent.step(1.0 / 60)',
        [
            '\t\t\te1_d3_sim_tick += 1',
            '\t\t\tif neural != null and not smoke_mode:',
            '\t\t\t\tneural.before_simulation_step(agent, e1_d3_sim_tick)',
            '\t\t\tagent.step(1.0 / 60)',
            '\t\t\tif neural != null and not smoke_mode:',
            '\t\t\t\tneural.record_sim_state(agent, e1_d3_sim_tick)',
        ],
        "main per-step diagnostic boundary",
        start=begin,
        end=end,
    )

    begin, end = function_bounds(
        lines,
        'func _process(dt: float) -> void:',
        "main process neural tick",
    )
    insert_before(
        lines,
        '\t\tneural.tick(dt, agent)',
        [
            '\t\tif neural.should_pause_simulation():',
            '\t\t\taccumulator = minf(accumulator, 1.0 / 60)',
            '\t\tneural.set_sim_tick(e1_d3_sim_tick)',
        ],
        "main publish current sim tick and suppress barrier backlog",
        start=begin,
        end=end,
    )

    begin, end = function_bounds(
        lines,
        'func _process(dt: float) -> void:',
        "main deterministic termination",
    )
    neural_tick_index = unique_line(
        lines,
        '\t\tneural.tick(dt, agent)',
        "main neural tick after instrumentation",
        start=begin,
        end=end,
    )
    deterministic_stop = [
        '\tif e1_d3_stop_tick > 0 and e1_d3_sim_tick >= e1_d3_stop_tick:',
        '\t\tsave(false)',
        '\t\tif neural != null:',
        '\t\t\tneural.record_session_end(agent, "diagnostic_stop_tick")',
        '\t\t\tneural.shutdown()',
        '\t\tget_tree().quit()',
        '\t\treturn',
    ]
    lines[neural_tick_index + 1:neural_tick_index + 1] = deterministic_stop

    result = render_source(lines)
    required = [
        'var e1_d3_sim_tick := 0',
        'neural.before_simulation_step(agent, e1_d3_sim_tick)',
        'neural.record_sim_state(agent, e1_d3_sim_tick)',
        'neural.record_session_end(agent, "diagnostic_stop_tick")',
    ]
    missing = [item for item in required if item not in result]
    if missing:
        raise DiagnosticError(f"main instrumentation missing {missing}")
    return result


def self_test_instrumentation() -> None:
    bridge_fixture = (
        'var mode := "control"\n'
        'func start(requested_mode: String = "control") -> void:\n'
        '\tmode = "shadow" if requested_mode == "shadow" else "control"\n'
        '\tvar filename = "neural-control.jsonl"\n'
        '\tlog_path = ProjectSettings.globalize_path("res://data/" + filename)\n'
        '\tvar log = FileAccess.open(log_path, FileAccess.WRITE)\n'
        '\tif log != null:\n'
        '\t\tlog.store_line(JSON.stringify({\n'
        '\t\t\t"event": "session_start",\n'
        '\t\t\t"mode": mode,\n'
        '\t\t\t"port": PORT\n'
        '\t\t}))\n'
        '\tpython_path = find_python()\n'
        '\tvar script = "brain_server.py"\n'
        '\tprocess_id = OS.create_process(python_path, PackedStringArray([script, "--port", str(PORT)]), false)\n'
        'func find_python() -> String:\n'
        '\treturn ""\n'
        'func tick(dt: float, agent) -> void:\n'
        '\tagent.neural_shadow["bridge_status"] = status\n'
        '\tclock += dt\n'
        '\treconnect_clock += dt\n'
        '\tpoll_connection(agent)\n'
        '\tif peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:\n'
        '\t\treturn\n'
        '\tif not pending and clock >= UPDATE_INTERVAL:\n'
        '\t\tclock = 0.0\n'
        '\t\tsend_snapshot(agent)\n'
        'func send_snapshot(agent) -> void:\n'
        '\trequest_id += 1\n'
        '\tvar payload = {"request_id": request_id, "age": agent.age, "neural_seconds": 0.05, "inputs": {}}\n'
        '\tvar bytes = (JSON.stringify(payload) + "\\n").to_utf8_buffer()\n'
        '\tvar err = peer.put_data(bytes)\n'
        '\tif err == OK:\n'
        '\t\tpending = true\n'
        'func read_available(agent) -> void:\n'
        '\twhile true:\n'
        '\t\tif peer.get_available_bytes() < 0:\n'
        '\t\t\tpending = false\n'
        '\t\tvar parsed = {}\n'
        '\t\tif parsed is Dictionary:\n'
        '\t\t\tpending = false\n'
        '\t\t\tif parsed.get("ok", false):\n'
        '\t\t\t\tvar utility_family = pending_utility_family\n'
        '\t\t\t\tpending_utility_family = ""\n'
        '\t\t\t\tparsed["utility_family"] = utility_family\n'
        '\t\t\t\tif mode == "control":\n'
        '\t\t\t\t\tagent.accept_neural_decision(parsed)\n'
        '\t\t\t\tagent.neural_shadow = parsed.duplicate(true)\n'
        '\t\t\t\tappend_log(parsed)\n'
        '\t\t\telse:\n'
        '\t\t\t\tpending_utility_family = ""\n'
        '\t\t\t\tstatus = "hjärnfel"\n'
        '\t\t\t\tif mode == "control":\n'
        '\t\t\t\t\tagent.neural_bridge_unavailable(last_error)\n'
        'func append_log(payload: Dictionary) -> void:\n'
        '\tpass\n'
    )
    main_fixture = (
        'var neural_mode = "control"\n'
        'func _ready() -> void:\n'
        '\tget_tree().auto_accept_quit = false\n'
        '\tvar save_path = ""\n'
        'func _process(dt: float) -> void:\n'
        '\ttotal_runtime += dt\n'
        '\tif not paused:\n'
        '\t\taccumulator += minf(dt, 0.15) * speed\n'
        '\t\twhile accumulator >= 1.0 / 60:\n'
        '\t\t\tagent.step(1.0 / 60)\n'
        '\t\t\taccumulator -= 1.0 / 60\n'
        '\tif neural != null and not smoke_mode:\n'
        '\t\tneural.tick(dt, agent)\n'
        '\tif quit_after > 0 and total_runtime >= quit_after:\n'
        '\t\tsave(false)\n'
    )
    bridge = instrument_bridge(bridge_fixture)
    main = instrument_main(main_fixture)
    assert '"event": "request_sent"' in bridge
    assert '"event": "response_apply_pre"' in bridge
    assert 'parsed["event"] = "response_received"' in bridge
    assert 'if false and mode == "control":' not in bridge
    assert 'neural.before_simulation_step' in main
    assert 'e1_d3_stop_tick' in main
    assert 'e1_d3_worst_case_target' in bridge
    assert 'tail_request_policy' in bridge
    assert 'e1_d3_due_tick = e1_d3_request_start_tick + request_id * e1_d3_request_interval_ticks' in bridge
    assert 'func should_pause_simulation() -> bool:' in bridge
    assert 'return pending and e1_d3_queued_response.is_empty()' in bridge
    assert '"event": "request_schedule_miss"' in bridge
    assert 'neural.should_pause_simulation()' in main
    assert 'accumulator = minf(accumulator, 1.0 / 60)' in main


def find_accepted_source(base) -> Path:
    root = Path(r"C:\BirdAI_E1_evidence")
    candidates = [
        root / "source-snapshots" / "e1-a1-bootstrap-ab186b5.json",
    ]
    for config in root.glob("e1-a1-*/experiment-config.json"):
        try:
            payload = json.loads(config.read_text(encoding="utf-8"))
            source = payload.get("source_snapshot")
            if source:
                candidates.append(Path(str(source)))
        except Exception:
            pass

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if not candidate.is_file():
            continue
        if base.sha256_file(candidate) != ACCEPTED_E1_A1_SOURCE_SHA256:
            continue
        base.decode_snapshot(candidate)
        return candidate.resolve()

    raise DiagnosticError(
        "Accepted E1-A1 immutable source snapshot not found with expected SHA-256 "
        f"{ACCEPTED_E1_A1_SOURCE_SHA256}."
    )


def write_instrumented_runtime(repo: Path, sandbox: Path) -> dict[str, str]:
    actual_main = git_blob(repo, RUNTIME_COMMIT, MAIN_REL)
    actual_bridge = git_blob(repo, RUNTIME_COMMIT, BRIDGE_REL)
    if actual_main != MAIN_BLOB or actual_bridge != BRIDGE_BLOB:
        raise DiagnosticError(
            "Pinned production runtime blobs changed; refusing adaptive instrumentation. "
            f"main={actual_main}, bridge={actual_bridge}"
        )

    transformed = {
        MAIN_REL: instrument_main(git_show(repo, RUNTIME_COMMIT, MAIN_REL)),
        BRIDGE_REL: instrument_bridge(git_show(repo, RUNTIME_COMMIT, BRIDGE_REL)),
    }
    hashes: dict[str, str] = {}
    for rel, content in transformed.items():
        path = sandbox / rel
        path.write_text(content, encoding="utf-8", newline="\n")
        hashes[rel] = base_sha256_bytes(content.encode("utf-8"))
    return hashes


def base_sha256_bytes(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def semantic_response(event: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "ok",
        "request_id",
        "age",
        "backend",
        "inputs",
        "selected",
        "confidence",
        "action_values",
        "competition_values",
        "competition_evidence",
        "affordance_gates",
        "explore_diagnostics",
        "commitment",
        "basal_ganglia",
        "sim_time",
        "neurons",
    )
    return {key: event.get(key) for key in keys}


def event_for(
    events: list[dict[str, Any]],
    event_name: str,
    request_id: int,
) -> dict[str, Any]:
    matches = [
        event for event in events
        if event.get("event") == event_name
        and int(event.get("request_id", -1)) == request_id
    ]
    if len(matches) != 1:
        raise DiagnosticError(
            f"Expected exactly one {event_name} for request {request_id}, "
            f"found {len(matches)}."
        )
    return matches[0]


def sim_states(events: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    result = {
        int(event["sim_tick"]): event["state"]
        for event in events
        if event.get("event") == "sim_state"
    }
    if len(result) != STOP_TICK:
        raise DiagnosticError(
            f"Expected {STOP_TICK} sim_state ticks, found {len(result)}."
        )
    if set(result) != set(range(1, STOP_TICK + 1)):
        raise DiagnosticError("sim_state tick sequence is incomplete.")
    return result


def compare_state_series(
    base,
    a: dict[int, dict[str, Any]],
    b: dict[int, dict[str, Any]],
    *,
    embodied_only: bool,
) -> dict[str, Any] | None:
    for tick in range(1, STOP_TICK + 1):
        left = a[tick]
        right = b[tick]
        if embodied_only:
            left = {"agent": left["agent"], "world": left["world"]}
            right = {"agent": right["agent"], "world": right["world"]}
        diff = base.compare_values(left, right, f"tick[{tick}]")
        if diff is not None:
            return {"tick": tick, "divergence": diff}
    return None


def run_one(
    *,
    base,
    repo: Path,
    evidence_root: Path,
    source: Path,
    source_hash: str,
    godot: Path,
    python_exe: Path,
    run_id: str,
    late_request_id: int,
) -> dict[str, Any]:
    run_dir = evidence_root / f"run_{run_id.lower()}"
    sandbox = evidence_root / f"sandbox_{run_id.lower()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    save_path = run_dir / "individual.json"
    trace_path = run_dir / "trace.jsonl"
    stdout_path = run_dir / "godot.stdout.txt"
    stderr_path = run_dir / "godot.stderr.txt"
    capsule_path = run_dir / "capsule.json"

    shutil.copy2(source, save_path)
    if base.sha256_file(save_path) != source_hash:
        raise DiagnosticError(f"Run {run_id}: source copy hash mismatch.")

    base.run(
        ["git", "worktree", "add", "--detach", str(sandbox), RUNTIME_COMMIT],
        cwd=repo,
        timeout=120,
    )

    try:
        hashes = write_instrumented_runtime(repo, sandbox)
        base.wait_port_free()

        env = os.environ.copy()
        env["BIRDAI_PYTHON"] = str(python_exe)
        env["BIRDAI_E1_D3_RUN_ID"] = run_id
        env["BIRDAI_E1_D3_TRACE_PATH"] = str(trace_path)
        env["BIRDAI_E1_D3_GATE_DELAY_TICKS"] = str(GATE_DELAY_TICKS)
        env["BIRDAI_E1_D3_REQUEST_START_TICK"] = str(REQUEST_START_TICK)
        env["BIRDAI_E1_D3_REQUEST_INTERVAL_TICKS"] = str(REQUEST_INTERVAL_TICKS)
        env["BIRDAI_E1_D3_LATE_REQUEST_ID"] = str(late_request_id)
        env["BIRDAI_E1_D3_NEURAL_SEED"] = str(NEURAL_SEED)
        env["BIRDAI_E1_D3_STOP_TICK"] = str(STOP_TICK)

        command = [
            str(godot),
            "--headless",
            "--path",
            str(sandbox),
            "--",
            "--neural-control",
            f"--save-path={save_path}",
            "--quit-after=30",
        ]

        wall_start = datetime.now(timezone.utc).isoformat()
        start = time.monotonic()
        result = base.run(
            command,
            cwd=sandbox,
            env=env,
            timeout=150,
            check=False,
        )
        elapsed = time.monotonic() - start
        wall_end = datetime.now(timezone.utc).isoformat()
        stdout_path.write_text(result.stdout, encoding="utf-8")
        stderr_path.write_text(result.stderr, encoding="utf-8")
        base.wait_port_free()

        if result.returncode != 0:
            raise DiagnosticError(
                f"Run {run_id}: Godot exit code {result.returncode}; "
                f"see {stderr_path}."
            )

        events = base.load_jsonl(trace_path)
        if events[0].get("event") != "session_start":
            raise DiagnosticError(f"Run {run_id}: trace lacks session_start.")
        if events[-1].get("event") != "session_end":
            raise DiagnosticError(f"Run {run_id}: trace lacks session_end.")
        if events[-1].get("termination_reason") != "diagnostic_stop_tick":
            raise DiagnosticError(
                f"Run {run_id}: unexpected termination "
                f"{events[-1].get('termination_reason')!r}."
            )
        if int(events[-1].get("deadline_misses", -1)) != 0:
            raise DiagnosticError(
                f"Run {run_id}: deterministic gate deadline miss count="
                f"{events[-1].get('deadline_misses')}; increase gate only in a "
                "new reviewed diagnostic revision."
            )
        if int(events[-1].get("request_schedule_misses", -1)) != 0:
            raise DiagnosticError(
                f"Run {run_id}: fixed request scheduler missed "
                f"{events[-1].get('request_schedule_misses')} due tick(s); "
                f"last_schedule_miss_tick={events[-1].get('last_schedule_miss_tick')}. "
                "This run is invalid because request emission was not controlled."
            )
        if events[-1].get("queued_response_remaining"):
            raise DiagnosticError(
                f"Run {run_id}: response remained queued at end; "
                f"request_id={events[-1].get('queued_request_id')}, "
                f"pending_request_tick={events[-1].get('pending_request_tick')}, "
                f"target_apply_tick={events[-1].get('target_apply_tick')}, "
                f"stop_tick={STOP_TICK}. "
                "If target_apply_tick <= stop_tick, the fixed gate was missed; "
                "do not extend the simulation window silently."
            )

        if events[-1].get("pending"):
            raise DiagnosticError(
                f"Run {run_id}: neural request still pending at end; "
                f"pending_request_tick={events[-1].get('pending_request_tick')}, "
                f"target_apply_tick={events[-1].get('target_apply_tick')}, "
                f"stop_tick={STOP_TICK}."
            )

        states = sim_states(events)
        _, final_data = base.decode_snapshot(save_path)
        capsule = {
            "stage": STAGE,
            "run_id": run_id,
            "runtime_commit": RUNTIME_COMMIT,
            "source_snapshot_sha256": source_hash,
            "neural_seed": NEURAL_SEED,
            "gate_delay_ticks": GATE_DELAY_TICKS,
            "request_start_tick": REQUEST_START_TICK,
            "request_interval_ticks": REQUEST_INTERVAL_TICKS,
            "late_request_id": late_request_id,
            "stop_tick": STOP_TICK,
            "wall_clock_start": wall_start,
            "wall_clock_end": wall_end,
            "wall_clock_elapsed_seconds": elapsed,
            "raw_trace_path": str(trace_path),
            "raw_trace_sha256": base.sha256_file(trace_path),
            "final_snapshot_sha256": base.sha256_file(save_path),
            "final_agent_state_sha256": base.canonical_hash(final_data["agent"]),
            "final_world_state_sha256": base.canonical_hash(final_data["world"]),
            "instrumented_source_sha256": hashes,
            "sandbox_only_instrumentation": True,
        }
        capsule_path.write_text(
            json.dumps(capsule, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return {
            "events": events,
            "states": states,
            "capsule": capsule,
            "capsule_path": capsule_path,
            "final_data": final_data,
        }
    finally:
        base.remove_worktree(repo, sandbox)


def analyze(base, control_a, control_b, late3) -> dict[str, Any]:
    control_runtime_diff = compare_state_series(
        base,
        control_a["states"],
        control_b["states"],
        embodied_only=False,
    )
    control_embodied_diff = compare_state_series(
        base,
        control_a["states"],
        control_b["states"],
        embodied_only=True,
    )

    if control_runtime_diff is not None or control_embodied_diff is not None:
        return {
            "valid": True,
            "verdict": BLOCKED_CONTROL,
            "control_runtime_divergence": control_runtime_diff,
            "control_embodied_divergence": control_embodied_diff,
            "causal_test_performed": False,
        }

    req_a = event_for(
        control_a["events"], "request_sent", INTERVENTION_REQUEST_ID
    )
    req_late = event_for(
        late3["events"], "request_sent", INTERVENTION_REQUEST_ID
    )
    request_diff = base.compare_values(
        {
            "request_id": req_a.get("request_id"),
            "age": req_a.get("age"),
            "inputs": req_a.get("inputs"),
            "neural_seconds": req_a.get("neural_seconds"),
            "request_sim_tick": req_a.get("request_sim_tick"),
        },
        {
            "request_id": req_late.get("request_id"),
            "age": req_late.get("age"),
            "inputs": req_late.get("inputs"),
            "neural_seconds": req_late.get("neural_seconds"),
            "request_sim_tick": req_late.get("request_sim_tick"),
        },
        "request3",
    )
    if request_diff is not None:
        raise DiagnosticError(
            "Counterfactual request #3 was not upstream-identical before the "
            f"application-tick intervention: {request_diff}"
        )

    response_a = event_for(
        control_a["events"], "response_received", INTERVENTION_REQUEST_ID
    )
    response_late = event_for(
        late3["events"], "response_received", INTERVENTION_REQUEST_ID
    )
    response_diff = base.compare_values(
        semantic_response(response_a),
        semantic_response(response_late),
        "response3",
    )
    if response_diff is not None:
        raise DiagnosticError(
            "Counterfactual NeuralBrain response #3 changed before application; "
            f"cannot isolate scheduler: {response_diff}"
        )

    apply_a = event_for(
        control_a["events"], "response_apply_pre", INTERVENTION_REQUEST_ID
    )
    apply_late = event_for(
        late3["events"], "response_apply_pre", INTERVENTION_REQUEST_ID
    )
    apply_tick_a = int(apply_a["apply_sim_tick"])
    apply_tick_late = int(apply_late["apply_sim_tick"])
    if apply_tick_late != apply_tick_a + 1:
        raise DiagnosticError(
            "Counterfactual application intervention was not exactly one tick: "
            f"{apply_tick_a} -> {apply_tick_late}."
        )

    runtime_diff = compare_state_series(
        base,
        control_a["states"],
        late3["states"],
        embodied_only=False,
    )
    embodied_diff = compare_state_series(
        base,
        control_a["states"],
        late3["states"],
        embodied_only=True,
    )

    if runtime_diff is not None and runtime_diff["tick"] < apply_tick_a:
        raise DiagnosticError(
            "Runtime diverged before the scheduled intervention boundary: "
            f"{runtime_diff}"
        )
    if embodied_diff is not None and embodied_diff["tick"] < apply_tick_a:
        raise DiagnosticError(
            "Embodied state diverged before the scheduled intervention boundary: "
            f"{embodied_diff}"
        )

    if embodied_diff is None:
        verdict = FALSIFIED
    else:
        verdict = SUPPORTED

    final_diff = base.compare_values(
        {
            "agent": control_a["final_data"]["agent"],
            "world": control_a["final_data"]["world"],
        },
        {
            "agent": late3["final_data"]["agent"],
            "world": late3["final_data"]["world"],
        },
        "final_state",
    )

    return {
        "valid": True,
        "verdict": verdict,
        "causal_test_performed": True,
        "control_gate_replay_equal": True,
        "intervention_request_id": INTERVENTION_REQUEST_ID,
        "request3_upstream_equal": True,
        "response3_semantic_equal": True,
        "baseline_apply_tick": apply_tick_a,
        "counterfactual_apply_tick": apply_tick_late,
        "application_tick_delta": 1,
        "baseline_receive_tick": int(response_a.get("receive_sim_tick", -1)),
        "counterfactual_receive_tick": int(
            response_late.get("receive_sim_tick", -1)
        ),
        "baseline_round_trip_ms": response_a.get("round_trip_ms"),
        "counterfactual_round_trip_ms": response_late.get("round_trip_ms"),
        "first_runtime_divergence": runtime_diff,
        "first_embodied_divergence": embodied_diff,
        "final_state_divergence": final_diff,
    }


def self_test() -> None:
    self_test_instrumentation()

    class FakeBase:
        @staticmethod
        def compare_values(a, b, path="$"):
            if a == b:
                return None
            return {"field": path, "a": a, "b": b}

    states_a = {
        tick: {"agent": {"x": tick}, "world": {"x": 1}, "phase": "idle"}
        for tick in range(1, STOP_TICK + 1)
    }
    states_b = {
        tick: {
            "agent": dict(value["agent"]),
            "world": dict(value["world"]),
            "phase": value["phase"],
        }
        for tick, value in states_a.items()
    }
    states_b[4]["agent"]["x"] = 999

    assert compare_state_series(
        FakeBase, states_a, states_a, embodied_only=True
    ) is None
    diff = compare_state_series(
        FakeBase, states_a, states_b, embodied_only=True
    )
    assert diff["tick"] == 4

    print("SELF_TEST: PASS")
    print("CONTROLLED_REQUEST_AND_GATE_A_B: REQUIRED")
    print(f"REQUEST_START_TICK: {REQUEST_START_TICK}")
    print(f"REQUEST_INTERVAL_TICKS: {REQUEST_INTERVAL_TICKS}")
    print("WALL_CLOCK_REQUEST_SCHEDULER: DISABLED_IN_SANDBOX")
    print("ASYNC_RESPONSE_BARRIER: ENABLED_IN_SANDBOX")
    print("SIMULATION_ADVANCE_WHILE_RESPONSE_IN_FLIGHT: DISABLED")
    print("COUNTERFACTUAL_REQUEST: 3")
    print("COUNTERFACTUAL_SHIFT_TICKS: +1")
    print("SIMULATION_TICK_ALIGNMENT: REQUIRED")
    print("UPSTREAM_REQUEST_EQUALITY: REQUIRED")
    print("NEURAL_RESPONSE_EQUALITY: REQUIRED")
    print("AMBIGUOUS_PENDING_FALSE_TARGETING: PASS")
    print("TAIL_REQUEST_CUTOFF: WORST_CASE_TARGET_WITHIN_STOP_TICK")
    print("FIXED_480_TICK_COMPARISON_WINDOW: PRESERVED")
    print("SANDBOX_ONLY_RUNTIME_INSTRUMENTATION: PASS")


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
    base = load_base(repo)

    head = base.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
    ).stdout.strip()
    if head == RUNTIME_COMMIT:
        raise DiagnosticError(
            "Run this diagnostic from its committed harness branch, not directly "
            "from the runtime parent commit."
        )

    runtime_parent = base.run(
        ["git", "rev-parse", "HEAD^"],
        cwd=repo,
    ).stdout.strip()
    if runtime_parent != RUNTIME_COMMIT:
        raise DiagnosticError(
            f"Harness branch parent mismatch: {runtime_parent} != {RUNTIME_COMMIT}"
        )

    source = find_accepted_source(base)
    source_hash = base.sha256_file(source)
    godot = base.discover_godot(repo)
    python_exe = base.discover_python()

    experiment_id = (
        f"e1-a1-d3-{utc_stamp()}-{RUNTIME_COMMIT[:7]}"
    )
    evidence_root = Path(r"C:\BirdAI_E1_evidence") / experiment_id
    evidence_root.mkdir(parents=True, exist_ok=False)

    config = {
        "stage": STAGE,
        "experiment_id": experiment_id,
        "runtime_commit": RUNTIME_COMMIT,
        "accepted_e1_a1_source_sha256": ACCEPTED_E1_A1_SOURCE_SHA256,
        "accepted_e1_a1_comparison_sha256": ACCEPTED_E1_A1_COMPARISON_SHA256,
        "source_snapshot": str(source),
        "source_snapshot_sha256": source_hash,
        "neural_seed": NEURAL_SEED,
        "gate_delay_ticks": GATE_DELAY_TICKS,
        "request_start_tick": REQUEST_START_TICK,
        "request_interval_ticks": REQUEST_INTERVAL_TICKS,
        "intervention_request_id": INTERVENTION_REQUEST_ID,
        "counterfactual_shift_ticks": 1,
        "stop_tick": STOP_TICK,
        "simulation_step_seconds": 1.0 / 60.0,
        "production_runtime_mutation": "none",
        "diagnostic_instrumentation": "throwaway-worktrees-only",
    }
    (evidence_root / "experiment-config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=" * 72)
    print("E1-A1-D3 BARRIER-CONTROLLED REQUEST + RESPONSE-APPLICATION DIAGNOSTIC")
    print(f"EXPERIMENT: {experiment_id}")
    print(f"RUNTIME_COMMIT: {RUNTIME_COMMIT}")
    print(f"SOURCE: {source}")
    print(f"SOURCE_SHA256: {source_hash}")
    print(f"GATE_DELAY_TICKS: {GATE_DELAY_TICKS}")
    print(f"REQUEST_START_TICK: {REQUEST_START_TICK}")
    print(f"REQUEST_INTERVAL_TICKS: {REQUEST_INTERVAL_TICKS}")
    print(f"INTERVENTION: request {INTERVENTION_REQUEST_ID} +1 application tick")
    print(f"EVIDENCE: {evidence_root}")
    print("PRODUCTION_RUNTIME_MUTATION: NONE")
    print("=" * 72)

    control_a = run_one(
        base=base,
        repo=repo,
        evidence_root=evidence_root,
        source=source,
        source_hash=source_hash,
        godot=godot,
        python_exe=python_exe,
        run_id="CONTROL_A",
        late_request_id=-1,
    )
    control_b = run_one(
        base=base,
        repo=repo,
        evidence_root=evidence_root,
        source=source,
        source_hash=source_hash,
        godot=godot,
        python_exe=python_exe,
        run_id="CONTROL_B",
        late_request_id=-1,
    )
    late3 = run_one(
        base=base,
        repo=repo,
        evidence_root=evidence_root,
        source=source,
        source_hash=source_hash,
        godot=godot,
        python_exe=python_exe,
        run_id="LATE3",
        late_request_id=INTERVENTION_REQUEST_ID,
    )

    comparison = analyze(base, control_a, control_b, late3)
    comparison["stage"] = STAGE
    comparison["experiment_id"] = experiment_id
    comparison["runtime_commit"] = RUNTIME_COMMIT
    comparison["source_snapshot_sha256"] = source_hash
    comparison_path = evidence_root / "comparison.json"
    comparison_path.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    comparison_sha = base.sha256_file(comparison_path)
    for run_result in (control_a, control_b, late3):
        capsule = run_result["capsule"]
        capsule["comparison_path"] = str(comparison_path)
        capsule["comparison_sha256"] = comparison_sha
        run_result["capsule_path"].write_text(
            json.dumps(capsule, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print("")
    print("=" * 72)
    print("STATUS: PASS")
    print(f"E1_A1_D3_VERDICT: {comparison['verdict']}")
    print(f"BARRIER_CONTROL_A_B_EQUAL: {comparison.get('control_gate_replay_equal')}")
    print(f"REQUEST3_UPSTREAM_EQUAL: {comparison.get('request3_upstream_equal')}")
    print(f"RESPONSE3_SEMANTIC_EQUAL: {comparison.get('response3_semantic_equal')}")
    print(f"BASELINE_APPLY_TICK: {comparison.get('baseline_apply_tick')}")
    print(f"COUNTERFACTUAL_APPLY_TICK: {comparison.get('counterfactual_apply_tick')}")
    print(
        "FIRST_RUNTIME_DIVERGENCE: "
        + json.dumps(
            comparison.get("first_runtime_divergence"),
            ensure_ascii=True,
        )
    )
    print(
        "FIRST_EMBODIED_DIVERGENCE: "
        + json.dumps(
            comparison.get("first_embodied_divergence"),
            ensure_ascii=True,
        )
    )
    print(f"COMPARISON: {comparison_path}")
    print(f"COMPARISON_SHA256: {comparison_sha}")
    print(f"EVIDENCE: {evidence_root}")
    print("PRODUCTION_RUNTIME_MUTATION: NONE")
    print("NEURAL_POLICY_CHANGE: NONE")
    print("ENVIRONMENT_CHANGE: NONE")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DiagnosticError as exc:
        print("STATUS: INVALID", file=sys.stderr)
        print(f"BLOCKER: {exc}", file=sys.stderr)
        raise SystemExit(2)
    except Exception as exc:
        print("STATUS: INVALID", file=sys.stderr)
        print(f"BLOCKER: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2)
