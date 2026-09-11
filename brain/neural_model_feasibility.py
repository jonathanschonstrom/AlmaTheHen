"""Executable-affordance gate for learned-extinction v4.

v4 correctly learned positive/negative target-action-context consequences, but a
live run exposed a closed-loop liveness mismatch: the historical generic
``manipulable`` channel could keep MANIPULATE dominant after the resolver had no
concrete action left to execute.

This adapter keeps the 18D transport contract and the 12,930-neuron topology.
For live 18D inputs only, it gates the *historical generic manipulable cue* by
an executable opportunity encoded by the existing cognitive channels:

- learned_food_access > neutral + the resolver's positive threshold, or
- substrate_affordance > the resolver's experiment threshold.

``substrate_affordance`` therefore remains the wire name for compatibility, but
in v5 its live semantics are the current manipulation-experiment opportunity
(substrate or classic object). Signed learned consequence remains separate and
is never multiplied by current hunger in Godot.

Historical 16D callers retain the old policy/affordance semantics exactly.
"""
from __future__ import annotations

from typing import Iterable, Mapping

import numpy as np

import neural_model as _base
import neural_model_extinction as _ext

ACTIONS = _base.ACTIONS
INPUT_KEYS = _base.INPUT_KEYS
COGNITIVE_INPUT_KEYS = _base.COGNITIVE_INPUT_KEYS
ALL_INPUT_KEYS = _base.ALL_INPUT_KEYS
NEUTRAL_LEARNED_FOOD = _ext.NEUTRAL_LEARNED_FOOD

# Must match the resolver's evidence thresholds. These are contract thresholds,
# not new utility weights. EPSILON prevents binary-float reconstruction of an
# exactly encoded boundary (e.g. 0.52 -> 0.040000000000000036) from making
# Python executable while GDScript's original signed evidence remains at 0.04.
POSITIVE_FOOD_THRESHOLD = 0.04
EXPERIMENT_THRESHOLD = 0.08
THRESHOLD_EPSILON = 1e-9


def _live_feasibility_from_transport(values: Iterable[float]) -> float:
    """Return graded executable MANIPULATE opportunity for an 18D vector."""
    x = _ext._coerce_transport_vector(values)
    signed_food = (float(x[_base.LEARNED_FOOD_ACCESS]) - NEUTRAL_LEARNED_FOOD) * 2.0
    learned = signed_food if signed_food > POSITIVE_FOOD_THRESHOLD + THRESHOLD_EPSILON else 0.0
    experiment = float(x[_base.SUBSTRATE_AFFORDANCE])
    experiment = experiment if experiment > EXPERIMENT_THRESHOLD + THRESHOLD_EPSILON else 0.0
    return _base.clamp01(max(learned, experiment))


def manipulation_feasibility_from_mapping(values: Mapping[str, float]) -> float:
    """Diagnostic counterpart of the live gate, without physiological scoring."""
    encoded = _base.clamp01(values.get("learned_food_access", NEUTRAL_LEARNED_FOOD))
    signed_food = (encoded - NEUTRAL_LEARNED_FOOD) * 2.0
    learned = signed_food if signed_food > POSITIVE_FOOD_THRESHOLD + THRESHOLD_EPSILON else 0.0
    experiment = _base.clamp01(values.get("substrate_affordance", 0.0))
    experiment = experiment if experiment > EXPERIMENT_THRESHOLD + THRESHOLD_EPSILON else 0.0
    return _base.clamp01(max(learned, experiment))


def vector_from_mapping(values: Mapping[str, float]) -> np.ndarray:
    """Build live input while preventing generic no-target MANIPULATE evidence."""
    x = _ext.vector_from_mapping(values)
    # Compatibility: callers that genuinely provide only the historical 16D
    # semantic contract must remain unchanged. Live Godot always supplies the
    # appended cognitive keys.
    live_cognitive_contract = any(key in values for key in COGNITIVE_INPUT_KEYS)
    if live_cognitive_contract:
        x[_base.MANIPULABLE] *= _live_feasibility_from_transport(x)
    return x


def affordance_vector(values: Iterable[float]) -> np.ndarray:
    """Temporal gate mirrors executable feasibility for live 18D inputs."""
    raw = np.asarray(list(values), dtype=float)
    if raw.shape[0] == len(INPUT_KEYS):
        # Exact historical semantics for pure 16D regressions/callers.
        return _ext.affordance_vector(raw)
    x = _ext._coerce_transport_vector(raw)
    gates = _ext.affordance_vector(x)
    gates[ACTIONS.index("MANIPULATE")] = _live_feasibility_from_transport(x)
    return gates


# NeuralBrain resolves these functions through neural_model globals at runtime.
# Gate the live semantic transport and temporal affordance without changing the
# established Nengo topology or signed extinction decoder.
_base.vector_from_mapping = vector_from_mapping
_base.affordance_vector = affordance_vector

NeuralBrain = _base.NeuralBrain
valuation = _base.valuation
