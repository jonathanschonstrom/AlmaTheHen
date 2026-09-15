"""Local line-delimited JSON server for BirdAI NeuralBrain v0.2.7 control/shadow mode."""
from __future__ import annotations

import argparse
import json
import socket
import sys
import traceback
from pathlib import Path

from neural_model import ACTIONS, INPUT_KEYS, NeuralBrain

HOST = "127.0.0.1"
DEFAULT_PORT = 39393


def send_line(connection: socket.socket, payload: dict) -> None:
    connection.sendall((json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))


def serve(port: int, seed: int) -> int:
    try:
        brain = NeuralBrain(seed=seed)
    except Exception as exc:
        print(f"NeuralBrain failed to initialize: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 2

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, int(port)))
        server.listen(1)
        print(f"BirdAI NeuralBrain listening on {HOST}:{port} | {brain.estimated_neuron_count} neurons", flush=True)
        running = True
        while running:
            connection, _address = server.accept()
            with connection:
                file = connection.makefile("r", encoding="utf-8", newline="\n")
                for line in file:
                    try:
                        request = json.loads(line)
                        command = request.get("command", "step")
                        if command == "ping":
                            send_line(connection, {
                                "ok": True,
                                "status": "ready",
                                "backend": "nengo",
                                "nengo_version": getattr(brain.nengo, "__version__", "unknown"),
                                "actions": list(ACTIONS),
                                "input_keys": list(INPUT_KEYS),
                                "neurons": brain.estimated_neuron_count,
                            })
                            continue
                        if command == "shutdown":
                            send_line(connection, {"ok": True, "status": "stopping"})
                            running = False
                            break
                        if command != "step":
                            send_line(connection, {"ok": False, "error": f"unknown command: {command}"})
                            continue

                        inputs = request.get("inputs", {})
                        decision = brain.step(
                            inputs,
                            float(request.get("neural_seconds", 0.05)),
                            world_time=float(request.get("age", 0.0)),
                        )
                        send_line(connection, {
                            "ok": True,
                            "request_id": int(request.get("request_id", 0)),
                            "age": float(request.get("age", 0.0)),
                            "backend": "nengo",
                            "inputs": {key: float(inputs.get(key, 0.0)) for key in INPUT_KEYS},
                            "selected": decision.selected,
                            "confidence": decision.confidence,
                            "action_values": decision.action_values,
                            "competition_values": decision.competition_values,
                            "competition_evidence": decision.competition_evidence,
                            "affordance_gates": decision.affordance_gates,
                            "explore_diagnostics": decision.explore_diagnostics,
                            "commitment": decision.commitment,
                            "basal_ganglia": decision.basal_ganglia_output,
                            "basal_ganglia_instantaneous": decision.basal_ganglia_instantaneous,
                            "basal_ganglia_readout_window_seconds": decision.basal_ganglia_readout_window_seconds,
                            "sim_time": decision.sim_time,
                            "neurons": brain.estimated_neuron_count,
                        })
                    except Exception as exc:
                        send_line(connection, {"ok": False, "error": str(exc)})
        brain.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--seed", type=int, default=20260910)
    args = parser.parse_args()
    return serve(args.port, args.seed)


if __name__ == "__main__":
    raise SystemExit(main())
