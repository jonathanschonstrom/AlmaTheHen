"""Signed learned-consequence adapter for the learned-affordance experiment.

This module deliberately leaves the v0.2.6 / learned-affordance graph topology
unchanged.  It changes the semantics of the existing learned-food cognitive
channel from an unsigned 0..1 bonus to a centred signal:

    0.0  strongly extinguished / negative evidence
    0.5  neutral or unknown
    1.0  strongly positive predicted food access

The live Nengo decoder performs the state-dependent revaluation.  Godot never
multiplies the learned consequence by hunger.
"""
from __future__ import annotations

from typing import Iterable, Mapping

import numpy as np

import neural_model as _base

ACTIONS = _base.ACTIONS
INPUT_KEYS = _base.INPUT_KEYS
COGNITIVE_INPUT_KEYS = _base.COGNITIVE_INPUT_KEYS
ALL_INPUT_KEYS = _base.ALL_INPUT_KEYS
NEUTRAL_LEARNED_FOOD = 0.5


def vector_from_mapping(values: Mapping[str, float]) -> np.ndarray:
    """Build the existing 18D transport vector with a neutral learned default."""
    result = []
    for key in ALL_INPUT_KEYS:
        default = NEUTRAL_LEARNED_FOOD if key == "learned_food_access" else 0.0
        result.append(_base.clamp01(values.get(key, default)))
    return np.asarray(result, dtype=float)


def _coerce_transport_vector(values: Iterable[float]) -> np.ndarray:
    """Preserve the historical 16D contract while centring learned valence."""
    x = np.asarray(list(values), dtype=float)
    if x.shape[0] == len(INPUT_KEYS):
        x = np.concatenate([x, np.asarray([NEUTRAL_LEARNED_FOOD, 0.0], dtype=float)])
    elif x.shape[0] != len(ALL_INPUT_KEYS):
        raise ValueError(
            f"expected {len(INPUT_KEYS)} policy or {len(ALL_INPUT_KEYS)} transport inputs, got {x.shape[0]}"
        )
    return np.clip(x, 0.0, 1.0)


def _signed_learned_food_manipulation_value(x):
    """Revalue signed target/action/context food evidence inside NeuralBrain."""
    hunger, encoded_prediction, safety = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    signed_prediction = (float(encoded_prediction) - NEUTRAL_LEARNED_FOOD) * 2.0
    return 1.80 * (float(hunger) ** 1.15) * signed_prediction * _base._suppress(float(safety))


def affordance_vector(values: Iterable[float]) -> np.ndarray:
    """Use only the positive half of the signed memory as an opportunity gate."""
    x = _coerce_transport_vector(values)
    search_opportunity = max(
        0.35,
        float(x[_base.OPEN_SPACE]),
        float(x[_base.NOVELTY]),
        float(x[_base.HUNGER] * (1.0 - x[_base.FOOD])),
        float(x[_base.THIRST] * (1.0 - x[_base.WATER])),
    )
    learned_positive = max(0.0, (float(x[_base.LEARNED_FOOD_ACCESS]) - 0.5) * 2.0)
    return np.asarray([
        1.0,
        x[_base.WATER],
        x[_base.FOOD],
        x[_base.REST_SITE],
        x[_base.PERSON],
        x[_base.CARE_SITE],
        search_opportunity,
        max(float(x[_base.MANIPULABLE]), learned_positive, float(x[_base.SUBSTRATE_AFFORDANCE])),
    ], dtype=float)


# NeuralBrain's methods resolve these names through the neural_model module at
# runtime.  Replacing them before construction changes the decoder semantics
# without duplicating or silently re-randomising the established graph.
_base.vector_from_mapping = vector_from_mapping
_base._coerce_transport_vector = _coerce_transport_vector
_base._learned_food_manipulation_value = _signed_learned_food_manipulation_value
_base.affordance_vector = affordance_vector

NeuralBrain = _base.NeuralBrain
valuation = _base.valuation
