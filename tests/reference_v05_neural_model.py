"""Frozen v0.5 policy reference extracted verbatim from the verified portable package.
Original full-file SHA-256: 6dbe8211305b91c6bfb1b648fa6392efd29da2024ceabbe1a0b7c5b603121604
Only symbols consumed by brain/test_regressions_v026.py are retained.
"""
from __future__ import annotations

from typing import Iterable, Mapping, Sequence
import numpy as np

ACTIONS = ("FLEE", "DRINK", "EAT", "REST", "SOCIAL", "CARE", "EXPLORE", "MANIPULATE")

INPUT_KEYS = (
    "hunger", "thirst", "rest", "explore", "social", "safety", "comfort",
    "food", "water", "person", "rest_site", "care_site", "novelty",
    "manipulable", "motion", "open_space",
)

INTEROCEPTIVE_DIMS = 7

EXTEROCEPTIVE_DIMS = len(INPUT_KEYS) - INTEROCEPTIVE_DIMS

HUNGER, THIRST, REST, EXPLORE, SOCIAL, SAFETY, COMFORT = range(7)

FOOD, WATER, PERSON, REST_SITE, CARE_SITE, NOVELTY, MANIPULABLE, MOTION, OPEN_SPACE = range(7, 16)

COMMITMENT_STRENGTH = {
    "FLEE": 0.13,
    "DRINK": 0.10,
    "EAT": 0.10,
    "REST": 0.130,
    "SOCIAL": 0.085,
    "CARE": 0.085,
    "EXPLORE": 0.070,
    "MANIPULATE": 0.085,
}

COMMITMENT_DURATION = {
    "FLEE": 0.75,
    "DRINK": 0.90,
    "EAT": 0.90,
    "REST": 1.25,
    "SOCIAL": 0.85,
    "CARE": 0.85,
    "EXPLORE": 0.65,
    "MANIPULATE": 0.80,
}

def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def vector_from_mapping(values: Mapping[str, float]) -> np.ndarray:
    return np.asarray([clamp01(values.get(key, 0.0)) for key in INPUT_KEYS], dtype=float)


def _suppress(safety: float) -> float:
    """Reduce non-defensive actions as acute danger rises."""
    return 1.0 - 0.80 * clamp01(safety)


def _flee_value(x: Sequence[float]) -> float:
    safety, motion = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    return 0.015 + 1.55 * safety + 0.25 * safety * motion


def _drink_value(x: Sequence[float]) -> float:
    """Thirst only becomes a drinking opportunity when water is perceived."""
    thirst, water, safety = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    drive = thirst ** 1.55
    return (0.010 + water * (0.035 + 1.90 * drive)) * _suppress(safety)


def _eat_value(x: Sequence[float]) -> float:
    """Hunger only becomes direct feeding evidence when food is perceived."""
    hunger, food, safety = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    drive = hunger ** 1.55
    return (0.010 + food * (0.035 + 1.90 * drive)) * _suppress(safety)


def _rest_value(x: Sequence[float]) -> float:
    """A suitable rest affordance lowers the threshold for acting on sleep/fatigue."""
    rest, rest_site, safety = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    value = 0.012 + rest_site * (0.050 + 1.45 * (rest ** 1.05)) + 0.16 * rest * rest
    return value * (1.0 - 0.50 * safety)


def _social_value(x: Sequence[float]) -> float:
    social, person, safety = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    value = 0.012 + person * (0.035 + 1.15 * (social ** 1.25))
    return value * _suppress(safety)


def _care_value(x: Sequence[float]) -> float:
    comfort, care_site, safety = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    value = 0.012 + care_site * (0.030 + 1.05 * (comfort ** 1.20))
    return value * (1.0 - 0.55 * safety)


def _explore_value(x: Sequence[float]) -> float:
    """Exploration is a fallback/search mode, not a permanently high competitor.

    Hunger/thirst raise search pressure only when their matching resource is not
    currently available. Novelty can independently invite exploration, but a
    familiar open room no longer produces the ~0.43 floor seen in v0.1.1.
    """
    explore, novelty, open_space, hunger, food, thirst, water, safety = np.clip(
        np.asarray(x, dtype=float), 0.0, 1.0
    )
    hunger_search = (hunger ** 1.30) * (1.0 - food) * 0.45
    thirst_search = (thirst ** 1.30) * (1.0 - water) * 0.45
    value = (
        0.018
        + explore * (0.20 + 0.30 * novelty + 0.10 * open_space)
        + 0.13 * novelty
        + hunger_search
        + thirst_search
    )
    return value * _suppress(safety)


def _manipulate_value(x: Sequence[float]) -> float:
    """Manipulation requires a perceived manipulable affordance.

    Novelty is useful but not mandatory. A familiar object can still invite
    pecking/pushing/inspection when exploratory motivation remains active.
    """
    explore, novelty, manipulable, motion, safety = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    value = 0.012 + manipulable * (
        0.025 + 0.30 * explore + 0.55 * novelty + 0.06 * motion
    )
    return value * _suppress(safety)


def affordance_vector(values: Iterable[float]) -> np.ndarray:
    """Observable opportunity gates for diagnostics and temporal commitment.

    These are not utility scores. They indicate whether the body can currently
    express an action family in the perceived context. EXPLORE remains broadly
    available because orienting/searching does not require a specific object.
    """
    x = np.asarray(list(values), dtype=float)
    if x.shape[0] != len(INPUT_KEYS):
        raise ValueError(f"expected {len(INPUT_KEYS)} inputs, got {x.shape[0]}")
    x = np.clip(x, 0.0, 1.0)
    search_opportunity = max(
        0.35,
        float(x[OPEN_SPACE]),
        float(x[NOVELTY]),
        float(x[HUNGER] * (1.0 - x[FOOD])),
        float(x[THIRST] * (1.0 - x[WATER])),
    )
    return np.asarray([
        1.0,
        x[WATER],
        x[FOOD],
        x[REST_SITE],
        x[PERSON],
        x[CARE_SITE],
        search_opportunity,
        x[MANIPULABLE],
    ], dtype=float)


def valuation(x: Iterable[float]) -> np.ndarray:
    """Analytical reference for v0.2 neural motivational evidence.

    The live Nengo model approximates each pathway independently; this function
    is retained only for self-test, replay diagnostics and decoder error metrics.
    """
    values = np.asarray(list(x), dtype=float)
    if values.shape[0] != len(INPUT_KEYS):
        raise ValueError(f"expected {len(INPUT_KEYS)} inputs, got {values.shape[0]}")
    values = np.clip(values, 0.0, 1.0)

    result = np.asarray(
        [
            _flee_value([values[SAFETY], values[MOTION]]),
            _drink_value([values[THIRST], values[WATER], values[SAFETY]]),
            _eat_value([values[HUNGER], values[FOOD], values[SAFETY]]),
            _rest_value([values[REST], values[REST_SITE], values[SAFETY]]),
            _social_value([values[SOCIAL], values[PERSON], values[SAFETY]]),
            _care_value([values[COMFORT], values[CARE_SITE], values[SAFETY]]),
            _explore_value([
                values[EXPLORE], values[NOVELTY], values[OPEN_SPACE], values[HUNGER],
                values[FOOD], values[THIRST], values[WATER], values[SAFETY],
            ]),
            _manipulate_value([
                values[EXPLORE], values[NOVELTY], values[MANIPULABLE], values[MOTION], values[SAFETY],
            ]),
        ],
        dtype=float,
    )
    return np.clip(result, 0.0, 1.8)
