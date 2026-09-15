"""BirdAI NeuralBrain v0.2.6 (reconstructed v0.5.3 lineage).

Shadow-mode spiking motivation, affordance gating, temporal commitment and
basal-ganglia action competition for BirdAI. Godot remains the only actuator.

v0.2.6 is intentionally still a family-level brain: it decides *what kind* of
behaviour is currently most appropriate (eat, rest, explore, manipulate ...),
not the exact target object or motor sequence. It receives no utility score,
utility ranking or utility-selected action from Godot.
"""
from __future__ import annotations

import math
import hashlib
from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Optional, Sequence

import numpy as np

from temporal_commitment import TemporalCommitment

ACTIONS = ("FLEE", "DRINK", "EAT", "REST", "SOCIAL", "CARE", "EXPLORE", "MANIPULATE")
INPUT_KEYS = (
    "hunger", "thirst", "rest", "explore", "social", "safety", "comfort",
    "food", "water", "person", "rest_site", "care_site", "novelty",
    "manipulable", "motion", "open_space",
)
COGNITIVE_INPUT_KEYS = ("learned_food_access", "substrate_affordance")
ALL_INPUT_KEYS = INPUT_KEYS + COGNITIVE_INPUT_KEYS

INTEROCEPTIVE_DIMS = 7
BASE_INPUT_DIMS = len(INPUT_KEYS)
EXTEROCEPTIVE_DIMS = BASE_INPUT_DIMS - INTEROCEPTIVE_DIMS
COGNITIVE_AFFORDANCE_DIMS = len(COGNITIVE_INPUT_KEYS)

# Original 16 channels retain their exact positions. Cognitive predictions are
# appended and routed through separate populations rather than widening the old
# interoceptive/exteroceptive pathways.
HUNGER, THIRST, REST, EXPLORE, SOCIAL, SAFETY, COMFORT = range(7)
FOOD, WATER, PERSON, REST_SITE, CARE_SITE, NOVELTY, MANIPULABLE, MOTION, OPEN_SPACE = range(7, 16)
LEARNED_FOOD_ACCESS, SUBSTRATE_AFFORDANCE = range(16, 18)

# Stable named sub-seeds make anatomical populations reproducible. Adding a new
# circuit later must not silently re-randomize unrelated pathways or BG.
_SUBSEED_OFFSETS = {
    "interoception": 10, "exteroception": 11, "integrated_state": 12,
    "flee_ctx": 30, "drink_ctx": 31, "eat_ctx": 32, "rest_ctx": 33,
    "social_ctx": 34, "care_ctx": 35, "explore_base_ctx": 36,
    "hunger_search_ctx": 37, "thirst_search_ctx": 38, "explore_gate_ctx": 39,
    "manipulate_ctx": 40, "persistence": 50, "basal_ganglia": 60,
    "eval_flee": 101, "eval_drink": 102, "eval_eat": 103, "eval_rest": 104,
    "eval_social": 105, "eval_care": 106, "eval_explore_base": 107,
    "eval_hunger_search": 108, "eval_thirst_search": 109,
    "eval_explore_gate": 110, "eval_manipulate": 111,
    "manipulate_drive_ctx": 41, "manipulate_novelty_ctx": 42,
    "manipulate_motion_ctx": 43, "manipulate_gate_ctx": 44,
    "eval_manipulate_drive": 112, "eval_manipulate_novelty": 113,
    "eval_manipulate_motion": 114, "eval_manipulate_gate": 115,
    "cognitive_affordances": 45, "manipulate_learned_ctx": 46, "manipulate_substrate_ctx": 47,
    "eval_manipulate_learned": 116, "eval_manipulate_substrate": 117,
}

# Temporal commitment is deliberately short. It suppresses 5 Hz decision
# flicker but is weak enough for a newly dominant physiological opportunity to
# take over. Strong threat always bypasses it.
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
    """Live transport vector: original 16 inputs plus appended cognitive predictions."""
    return np.asarray([clamp01(values.get(key, 0.0)) for key in ALL_INPUT_KEYS], dtype=float)


def _coerce_transport_vector(values: Iterable[float]) -> np.ndarray:
    """Accept the historical 16D policy contract or the live 18D transport vector."""
    x = np.asarray(list(values), dtype=float)
    if x.shape[0] == len(INPUT_KEYS):
        x = np.concatenate([x, np.zeros(len(COGNITIVE_INPUT_KEYS), dtype=float)])
    elif x.shape[0] != len(ALL_INPUT_KEYS):
        raise ValueError(
            f"expected {len(INPUT_KEYS)} policy or {len(ALL_INPUT_KEYS)} transport inputs, got {x.shape[0]}"
        )
    return np.clip(x, 0.0, 1.0)


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


def _explore_base_value(x: Sequence[float]) -> float:
    """Curiosity/novelty contribution before physiological search and safety gating."""
    explore, novelty, open_space = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    return (
        0.018
        + explore * (0.20 + 0.30 * novelty + 0.10 * open_space)
        + 0.13 * novelty
    )


def _hunger_search_value(x: Sequence[float]) -> float:
    hunger, food = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    return (hunger ** 1.30) * (1.0 - food) * 0.45


def _thirst_search_value(x: Sequence[float]) -> float:
    thirst, water = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    return (thirst ** 1.30) * (1.0 - water) * 0.45


def _explore_safety_gate(x: Sequence[float]) -> float:
    subtotal = max(0.0, min(1.80, float(x[0])))
    safety = clamp01(float(x[1]))
    return subtotal * _suppress(safety)


def _explore_value(x: Sequence[float]) -> float:
    """Exact v0.2 exploration policy, written as factorized subterms.

    The analytical policy is unchanged. The spiking network in v0.2.6 mirrors
    this factorization so an eight-dimensional decoder no longer has to learn
    all curiosity, search and safety interactions in one population.
    """
    explore, novelty, open_space, hunger, food, thirst, water, safety = np.clip(
        np.asarray(x, dtype=float), 0.0, 1.0
    )
    subtotal = (
        _explore_base_value([explore, novelty, open_space])
        + _hunger_search_value([hunger, food])
        + _thirst_search_value([thirst, water])
    )
    return _explore_safety_gate([subtotal, safety])


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


def _manipulate_drive_value(x: Sequence[float]) -> float:
    explore, manipulable = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    return 0.012 + manipulable * (0.025 + 0.30 * explore)


def _manipulate_novelty_value(x: Sequence[float]) -> float:
    novelty, manipulable = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    return manipulable * 0.55 * novelty


def _manipulate_motion_value(x: Sequence[float]) -> float:
    motion, manipulable = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    return manipulable * 0.06 * motion

def _learned_food_manipulation_value(x: Sequence[float]) -> float:
    """Current hunger revalues a learned prediction of future food access."""
    hunger, learned_food_access, safety = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    return 1.80 * (hunger ** 1.15) * learned_food_access * _suppress(safety)


def _substrate_manipulation_value(x: Sequence[float]) -> float:
    """Hunger makes an unresolved loose-substrate affordance worth testing."""
    hunger, substrate_affordance, safety = np.clip(np.asarray(x, dtype=float), 0.0, 1.0)
    return 0.95 * (hunger ** 1.15) * substrate_affordance * _suppress(safety)


def _manipulate_safety_gate(x: Sequence[float]) -> float:
    # 0.947 is the algebraic maximum of the original pre-safety formula.
    subtotal = max(0.0, min(0.947, float(x[0])))
    return subtotal * _suppress(float(x[1]))


def affordance_vector(values: Iterable[float]) -> np.ndarray:
    """Observable opportunity gates for diagnostics and temporal commitment.

    These are not utility scores. They indicate whether the body can currently
    express an action family in the perceived context. EXPLORE remains broadly
    available because orienting/searching does not require a specific object.
    """
    x = _coerce_transport_vector(values)
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
        max(float(x[MANIPULABLE]), float(x[LEARNED_FOOD_ACCESS]), float(x[SUBSTRATE_AFFORDANCE])),
    ], dtype=float)


def valuation(x: Iterable[float]) -> np.ndarray:
    """Analytical reference for v0.2 neural motivational evidence.

    The live Nengo model approximates each pathway independently; this function
    is retained only for self-test, replay diagnostics and decoder error metrics.
    """
    values = _coerce_transport_vector(x)

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
            (
                _manipulate_value([
                    values[EXPLORE], values[NOVELTY], values[MANIPULABLE], values[MOTION], values[SAFETY],
                ])
                + _learned_food_manipulation_value([
                    values[HUNGER], values[LEARNED_FOOD_ACCESS], values[SAFETY],
                ])
                + _substrate_manipulation_value([
                    values[HUNGER], values[SUBSTRATE_AFFORDANCE], values[SAFETY],
                ])
            ),
        ],
        dtype=float,
    )
    return np.clip(result, 0.0, 1.8)


@dataclass
class ShadowDecision:
    selected: str
    action_values: Dict[str, float]
    competition_values: Dict[str, float]
    competition_evidence: Dict[str, float]
    basal_ganglia_output: Dict[str, float]
    affordance_gates: Dict[str, float]
    explore_diagnostics: Dict[str, object]
    commitment: Dict[str, object]
    confidence: float
    sim_time: float


class NeuralBrain:
    """Persistent ~11.9k-neuron Nengo motivational action-competition model."""

    def __init__(self, seed: int = 20260910, dt: float = 0.001):
        import nengo

        self.nengo = nengo
        self.seed = int(seed)
        self.dt = float(dt)
        self.input_values = np.zeros(len(ALL_INPUT_KEYS), dtype=float)
        self.commitment_input_values = np.zeros(len(ACTIONS), dtype=float)
        self.temporal = TemporalCommitment(ACTIONS, COMMITMENT_STRENGTH, COMMITMENT_DURATION)
        self._internal_world_time = 0.0
        def sub_seed(name: str) -> int:
            offset = _SUBSEED_OFFSETS[name]
            value = int((self.seed + 100003 * int(offset)) % 2147483647)
            return value if value != 0 else 1

        def eval_points(name: str, dimensions: int, count: int = 2200) -> np.ndarray:
            # Broad 0..1 training only. No selftest coordinates are injected.
            rng = np.random.default_rng(sub_seed(name))
            points = rng.uniform(0.0, 1.0, size=(count, dimensions))
            anchors = np.vstack([
                np.zeros((1, dimensions)),
                np.ones((1, dimensions)),
                np.eye(dimensions),
            ])
            return np.vstack([points, anchors])

        def explore_gate_eval_points(count: int = 3000) -> np.ndarray:
            # Dimension 0 is the already-summed exploration subtotal (0..1.648);
            # dimension 1 is acute safety (0..1). These are structural domain
            # anchors, not behavior/selftest examples.
            rng = np.random.default_rng(sub_seed("eval_explore_gate"))
            points = np.column_stack([
                rng.uniform(0.0, 1.70, size=count),
                rng.uniform(0.0, 1.0, size=count),
            ])
            anchors = np.asarray([
                [0.0, 0.0], [0.0, 1.0], [1.70, 0.0], [1.70, 1.0],
                [0.20, 0.0], [0.60, 0.25], [1.00, 0.50], [1.40, 0.75],
            ], dtype=float)
            return np.vstack([points, anchors])

        with nengo.Network(label="BirdAI NeuralBrain v0.2.6 (reconstructed v0.5.3 lineage)", seed=self.seed) as model:
            input_node = nengo.Node(lambda _t: self.input_values, size_out=len(ALL_INPUT_KEYS), label="Embodied + cognitive input")
            commitment_node = nengo.Node(
                lambda _t: self.commitment_input_values,
                size_out=len(ACTIONS),
                label="Temporal commitment state",
            )

            interoception = nengo.Ensemble(
                n_neurons=500,
                dimensions=INTEROCEPTIVE_DIMS,
                radius=math.sqrt(INTEROCEPTIVE_DIMS),
                label="Interoception",
                seed=sub_seed("interoception"),
            )
            exteroception = nengo.Ensemble(
                n_neurons=650,
                dimensions=EXTEROCEPTIVE_DIMS,
                radius=math.sqrt(EXTEROCEPTIVE_DIMS),
                label="Perceptual context",
                seed=sub_seed("exteroception"),
            )
            integrated_state = nengo.Ensemble(
                n_neurons=1200,
                dimensions=BASE_INPUT_DIMS,
                radius=math.sqrt(BASE_INPUT_DIMS),
                label="Integrated state / NCL-like association",
                seed=sub_seed("integrated_state"),
            )
            cognitive_affordances = nengo.Ensemble(
                n_neurons=320,
                dimensions=COGNITIVE_AFFORDANCE_DIMS,
                radius=math.sqrt(COGNITIVE_AFFORDANCE_DIMS),
                label="Learned consequence / substrate affordances",
                seed=sub_seed("cognitive_affordances"),
            )
            action_values = nengo.Node(size_in=len(ACTIONS), label="Motivation + affordance evidence")
            # Both evidence and state projection are observable. The temporal
            # controller receives filtered neural evidence, never valuation().
            temporal_channels = nengo.Node(size_in=2 * len(ACTIONS), label="Neural evidence and premotor channels")
            competition_evidence = nengo.Node(
                lambda _t, x: x[:len(ACTIONS)] + x[len(ACTIONS):] * (self.commitment_input_values != 0.0),
                size_in=2 * len(ACTIONS), size_out=len(ACTIONS), label="Filtered evidence before hysteresis")
            competition_values = nengo.Node(
                lambda _t, x: self.temporal.project(x), size_in=len(ACTIONS),
                size_out=len(ACTIONS), label="Competition authorized by temporal state")

            nengo.Connection(input_node[:INTEROCEPTIVE_DIMS], interoception, synapse=0.01)
            nengo.Connection(input_node[INTEROCEPTIVE_DIMS:BASE_INPUT_DIMS], exteroception, synapse=0.01)
            nengo.Connection(input_node[BASE_INPUT_DIMS:], cognitive_affordances, synapse=0.01)
            nengo.Connection(interoception, integrated_state[:INTEROCEPTIVE_DIMS], synapse=0.015)
            nengo.Connection(exteroception, integrated_state[INTEROCEPTIVE_DIMS:BASE_INPUT_DIMS], synapse=0.015)

            # Dedicated low-dimensional action pathways. Each family sees only the
            # motivational and perceptual variables relevant to its affordance.
            flee_ctx = nengo.Ensemble(240, 2, radius=math.sqrt(2), label="Flee context", seed=sub_seed("flee_ctx"))
            drink_ctx = nengo.Ensemble(360, 3, radius=math.sqrt(3), label="Drink context", seed=sub_seed("drink_ctx"))
            eat_ctx = nengo.Ensemble(360, 3, radius=math.sqrt(3), label="Eat context", seed=sub_seed("eat_ctx"))
            rest_ctx = nengo.Ensemble(360, 3, radius=math.sqrt(3), label="Rest context", seed=sub_seed("rest_ctx"))
            social_ctx = nengo.Ensemble(360, 3, radius=math.sqrt(3), label="Social context", seed=sub_seed("social_ctx"))
            care_ctx = nengo.Ensemble(360, 3, radius=math.sqrt(3), label="Care context", seed=sub_seed("care_ctx"))
            # EXPLORE is factorized into low-dimensional spiking pathways. The
            # v0.5 robustness sweep showed a large positive decoder bias in the
            # former single 8D explore ensemble across seeds. These subcircuits
            # implement the same analytical policy without changing its weights.
            explore_base_ctx = nengo.Ensemble(500, 3, radius=math.sqrt(3), label="Explore curiosity context", seed=sub_seed("explore_base_ctx"))
            hunger_search_ctx = nengo.Ensemble(300, 2, radius=math.sqrt(2), label="Hunger search context", seed=sub_seed("hunger_search_ctx"))
            thirst_search_ctx = nengo.Ensemble(300, 2, radius=math.sqrt(2), label="Thirst search context", seed=sub_seed("thirst_search_ctx"))
            explore_pre = nengo.Node(size_in=1, label="Explore subtotal")
            explore_gate_ctx = nengo.Ensemble(400, 2, radius=2.10, label="Explore safety gate", seed=sub_seed("explore_gate_ctx"))
            # Separate 2D bilinear terms and safety gate preserve the exact
            # analytical MANIPULATE policy without a single 5D decoder.
            manipulate_drive_ctx = nengo.Ensemble(300, 2, radius=math.sqrt(2), label="Manipulate drive and affordance", seed=sub_seed("manipulate_drive_ctx"))
            manipulate_novelty_ctx = nengo.Ensemble(300, 2, radius=math.sqrt(2), label="Manipulate novelty and affordance", seed=sub_seed("manipulate_novelty_ctx"))
            manipulate_motion_ctx = nengo.Ensemble(200, 2, radius=math.sqrt(2), label="Manipulate motion and affordance", seed=sub_seed("manipulate_motion_ctx"))
            manipulate_pre = nengo.Node(size_in=1, label="Manipulate subtotal")
            manipulate_gate_ctx = nengo.Ensemble(400, 2, radius=math.sqrt(2), label="Manipulate safety gate", seed=sub_seed("manipulate_gate_ctx"))
            # Learned consequence and substrate-search evidence are separate from
            # the historical manipulate gate so its original 0..0.947 domain is unchanged.
            manipulate_learned_ctx = nengo.Ensemble(360, 3, radius=math.sqrt(3), label="Hunger x learned food-access", seed=sub_seed("manipulate_learned_ctx"))
            manipulate_substrate_ctx = nengo.Ensemble(360, 3, radius=math.sqrt(3), label="Hunger x loose-substrate affordance", seed=sub_seed("manipulate_substrate_ctx"))

            # Reconstructed v0.5.3: action contexts receive decoded intero/extero
            # signals, as in original v0.5. No raw-input context bypass.
            nengo.Connection(interoception[SAFETY], flee_ctx[0], synapse=0.008)
            nengo.Connection(exteroception[MOTION - INTEROCEPTIVE_DIMS], flee_ctx[1], synapse=0.008)

            for ctx, drive_idx, resource_idx in (
                (drink_ctx, THIRST, WATER),
                (eat_ctx, HUNGER, FOOD),
            ):
                nengo.Connection(interoception[drive_idx], ctx[0], synapse=0.008)
                nengo.Connection(exteroception[resource_idx - INTEROCEPTIVE_DIMS], ctx[1], synapse=0.008)
                nengo.Connection(interoception[SAFETY], ctx[2], synapse=0.008)

            for ctx, drive_idx, site_idx in (
                (rest_ctx, REST, REST_SITE),
                (social_ctx, SOCIAL, PERSON),
                (care_ctx, COMFORT, CARE_SITE),
            ):
                nengo.Connection(interoception[drive_idx], ctx[0], synapse=0.008)
                nengo.Connection(exteroception[site_idx - INTEROCEPTIVE_DIMS], ctx[1], synapse=0.008)
                nengo.Connection(interoception[SAFETY], ctx[2], synapse=0.008)

            explore_drive_in = nengo.Connection(interoception[EXPLORE], explore_base_ctx[0], synapse=0.008)
            explore_novelty_in = nengo.Connection(exteroception[NOVELTY - INTEROCEPTIVE_DIMS], explore_base_ctx[1], synapse=0.008)
            explore_open_space_in = nengo.Connection(exteroception[OPEN_SPACE - INTEROCEPTIVE_DIMS], explore_base_ctx[2], synapse=0.008)
            explore_hunger_in = nengo.Connection(interoception[HUNGER], hunger_search_ctx[0], synapse=0.008)
            explore_food_in = nengo.Connection(exteroception[FOOD - INTEROCEPTIVE_DIMS], hunger_search_ctx[1], synapse=0.008)
            explore_thirst_in = nengo.Connection(interoception[THIRST], thirst_search_ctx[0], synapse=0.008)
            explore_water_in = nengo.Connection(exteroception[WATER - INTEROCEPTIVE_DIMS], thirst_search_ctx[1], synapse=0.008)

            nengo.Connection(interoception[EXPLORE], manipulate_drive_ctx[0], synapse=0.008)
            nengo.Connection(exteroception[NOVELTY - INTEROCEPTIVE_DIMS], manipulate_novelty_ctx[0], synapse=0.008)
            nengo.Connection(exteroception[MOTION - INTEROCEPTIVE_DIMS], manipulate_motion_ctx[0], synapse=0.008)
            for ctx in (manipulate_drive_ctx, manipulate_novelty_ctx, manipulate_motion_ctx):
                nengo.Connection(exteroception[MANIPULABLE - INTEROCEPTIVE_DIMS], ctx[1], synapse=0.008)
            nengo.Connection(manipulate_pre, manipulate_gate_ctx[0], synapse=0.008)
            nengo.Connection(interoception[SAFETY], manipulate_gate_ctx[1], synapse=0.008)
            for ctx in (manipulate_learned_ctx, manipulate_substrate_ctx):
                nengo.Connection(interoception[HUNGER], ctx[0], synapse=0.008)
                nengo.Connection(interoception[SAFETY], ctx[2], synapse=0.008)
            nengo.Connection(cognitive_affordances[0], manipulate_learned_ctx[1], synapse=0.008)
            nengo.Connection(cognitive_affordances[1], manipulate_substrate_ctx[1], synapse=0.008)

            nengo.Connection(flee_ctx, action_values[0], function=_flee_value, synapse=0.010, eval_points=eval_points("eval_flee", 2))
            nengo.Connection(drink_ctx, action_values[1], function=_drink_value, synapse=0.010, eval_points=eval_points("eval_drink", 3))
            nengo.Connection(eat_ctx, action_values[2], function=_eat_value, synapse=0.010, eval_points=eval_points("eval_eat", 3))
            nengo.Connection(rest_ctx, action_values[3], function=_rest_value, synapse=0.010, eval_points=eval_points("eval_rest", 3))
            nengo.Connection(social_ctx, action_values[4], function=_social_value, synapse=0.010, eval_points=eval_points("eval_social", 3))
            nengo.Connection(care_ctx, action_values[5], function=_care_value, synapse=0.010, eval_points=eval_points("eval_care", 3))
            # These eval points are already expressed in the physical coordinates
            # represented by each ensemble. Do not scale them by ensemble radius.
            # v0.2.5 did so implicitly, over-weighting saturated regions of EXPLORE.
            explore_base_conn = nengo.Connection(
                explore_base_ctx, explore_pre, function=_explore_base_value,
                synapse=0.010, eval_points=eval_points("eval_explore_base", 3, 2800),
                scale_eval_points=False,
            )
            hunger_search_conn = nengo.Connection(
                hunger_search_ctx, explore_pre, function=_hunger_search_value,
                synapse=0.010, eval_points=eval_points("eval_hunger_search", 2, 2200),
                scale_eval_points=False,
            )
            thirst_search_conn = nengo.Connection(
                thirst_search_ctx, explore_pre, function=_thirst_search_value,
                synapse=0.010, eval_points=eval_points("eval_thirst_search", 2, 2200),
                scale_eval_points=False,
            )
            explore_subtotal_in = nengo.Connection(explore_pre, explore_gate_ctx[0], synapse=0.008)
            explore_safety_in = nengo.Connection(interoception[SAFETY], explore_gate_ctx[1], synapse=0.008)
            explore_gate_conn = nengo.Connection(
                explore_gate_ctx, action_values[6], function=_explore_safety_gate,
                synapse=0.010, eval_points=explore_gate_eval_points(3200),
                scale_eval_points=False,
            )
            for ctx, function, key in (
                (manipulate_drive_ctx, _manipulate_drive_value, "eval_manipulate_drive"),
                (manipulate_novelty_ctx, _manipulate_novelty_value, "eval_manipulate_novelty"),
                (manipulate_motion_ctx, _manipulate_motion_value, "eval_manipulate_motion"),
            ):
                # Points are in physical 0..1 coordinates, not radius-scaled.
                nengo.Connection(ctx, manipulate_pre, function=function, synapse=0.010,
                    eval_points=eval_points(key, 2), scale_eval_points=False, seed=sub_seed(key))
            nengo.Connection(manipulate_gate_ctx, action_values[7], function=_manipulate_safety_gate,
                synapse=0.010, eval_points=eval_points("eval_manipulate_gate", 2),
                scale_eval_points=False, seed=sub_seed("eval_manipulate_gate"))
            nengo.Connection(manipulate_learned_ctx, action_values[7], function=_learned_food_manipulation_value,
                synapse=0.010, eval_points=eval_points("eval_manipulate_learned", 3, 2800),
                scale_eval_points=False, seed=sub_seed("eval_manipulate_learned"))
            nengo.Connection(manipulate_substrate_ctx, action_values[7], function=_substrate_manipulation_value,
                synapse=0.010, eval_points=eval_points("eval_manipulate_substrate", 3, 2800),
                scale_eval_points=False, seed=sub_seed("eval_manipulate_substrate"))

            # Preserve the eight premotor spiking channels and original decay.
            # Mask inactive channels after filtering so stale activity cannot
            # recreate an expired or interrupted commitment.
            persistence = nengo.networks.EnsembleArray(
                n_neurons=100,
                n_ensembles=len(ACTIONS),
                ens_dimensions=1,
                radius=0.20,
                label="Premotor temporal commitment",
                seed=sub_seed("persistence"),
            )
            nengo.Connection(commitment_node, persistence.input, synapse=0.010)
            nengo.Connection(action_values, temporal_channels[:len(ACTIONS)], synapse=0.010)
            nengo.Connection(persistence.output, temporal_channels[len(ACTIONS):], synapse=0.012)
            # The same final low-pass evidence drives projection and diagnosis.
            # This moves the old 10 ms competition probe filter before the gate;
            # it does not introduce a tail-mean readout or change BG gain/bias.
            nengo.Connection(temporal_channels, competition_evidence, synapse=0.010)
            nengo.Connection(competition_evidence, competition_values, synapse=None)

            basal_ganglia = nengo.networks.BasalGanglia(
                dimensions=len(ACTIONS),
                n_neurons_per_ensemble=100,
                input_bias=0.0,
                label="Basal ganglia action competition",
                seed=sub_seed("basal_ganglia"),
            )
            nengo.Connection(competition_values, basal_ganglia.input, synapse=0.008)

            self.action_value_probe = nengo.Probe(action_values, synapse=0.01)
            self.competition_probe = nengo.Probe(competition_values, synapse=None)
            self.competition_evidence_probe = nengo.Probe(competition_evidence, synapse=None)
            self.bg_probe = nengo.Probe(basal_ganglia.output, synapse=0.01)
            self.state_probe = nengo.Probe(integrated_state, synapse=0.02)

            # EXPLORE trace probes are diagnostic only. Probing a Connection's
            # output reads the same weighted+filtered signal already delivered
            # to its post object; it does not add another policy pathway.
            self.explore_input_probes = {
                "explore": nengo.Probe(explore_drive_in, "output", synapse=None),
                "novelty": nengo.Probe(explore_novelty_in, "output", synapse=None),
                "open_space": nengo.Probe(explore_open_space_in, "output", synapse=None),
                "hunger": nengo.Probe(explore_hunger_in, "output", synapse=None),
                "food": nengo.Probe(explore_food_in, "output", synapse=None),
                "thirst": nengo.Probe(explore_thirst_in, "output", synapse=None),
                "water": nengo.Probe(explore_water_in, "output", synapse=None),
                "subtotal_to_gate": nengo.Probe(explore_subtotal_in, "output", synapse=None),
                "safety": nengo.Probe(explore_safety_in, "output", synapse=None),
            }
            self.explore_term_probes = {
                "base": nengo.Probe(explore_base_conn, "output", synapse=None),
                "hunger_search": nengo.Probe(hunger_search_conn, "output", synapse=None),
                "thirst_search": nengo.Probe(thirst_search_conn, "output", synapse=None),
                "gate": nengo.Probe(explore_gate_conn, "output", synapse=None),
            }
            self.explore_subtotal_probe = nengo.Probe(explore_pre, synapse=None)

        # Explicit semantic seeds for every top-level decoder, including the
        # identity decoders between intero/exteroception and action contexts.
        # Inserting another circuit cannot shift these random streams.
        decoder_names = set()
        for connection in model.connections:
            if not isinstance(connection.pre_obj, nengo.Ensemble):
                continue
            name = '|'.join((str(connection.pre_obj.label), str(connection.pre_slice),
                             str(connection.post_obj.label), str(connection.post_slice),
                             getattr(connection.function, '__name__', 'identity')))
            if name in decoder_names:
                raise ValueError('Duplicate anatomical decoder name: ' + name)
            decoder_names.add(name)
            if connection.seed is None:
                digest = hashlib.sha256(f'{self.seed}|{name}'.encode('utf-8')).digest()
                connection.seed = 1 + int.from_bytes(digest[:4], 'little') % 2147483646
        self.model = model
        self.sim = nengo.Simulator(self.model, dt=self.dt, progress_bar=False)

    @property
    def estimated_neuron_count(self) -> int:
        return sum(ensemble.n_neurons for ensemble in self.model.all_ensembles)

    def reset_temporal_state(self) -> None:
        """Reset behavioural commitment without resetting neural membranes."""
        self.temporal.reset()
        self.commitment_input_values[:] = 0.0

    def _resolve_world_time(self, seconds: float, world_time: Optional[float]) -> float:
        if world_time is None:
            self._internal_world_time += max(0.0, float(seconds))
        else:
            self._internal_world_time = float(world_time)
        return self._internal_world_time

    def step(self, values: Mapping[str, float], seconds: float = 0.05,
             world_time: Optional[float] = None) -> ShadowDecision:
        self.input_values[:] = vector_from_mapping(values)
        resolved_world_time = self._resolve_world_time(seconds, world_time)
        gates = affordance_vector(self.input_values)
        bias, _remaining = self.temporal.prepare(resolved_world_time, self.input_values[SAFETY], gates)
        self.commitment_input_values[:] = bias
        steps = max(1, int(round(float(seconds) / self.dt)))
        self.sim.run_steps(steps, progress_bar=False)
        action_values = np.asarray(self.sim.data[self.action_value_probe][-1], dtype=float)
        evidence = np.asarray(self.sim.data[self.competition_evidence_probe][-1], dtype=float)
        competition_values = np.asarray(self.sim.data[self.competition_probe][-1], dtype=float)
        bg_output = np.asarray(self.sim.data[self.bg_probe][-1], dtype=float)
        def probe_scalar(probe) -> float:
            return float(np.asarray(self.sim.data[probe][-1], dtype=float).reshape(-1)[0])
        explore_diagnostics = {
            "context_inputs": {name: probe_scalar(probe) for name, probe in self.explore_input_probes.items()},
            "decoded_terms": {name: probe_scalar(probe) for name, probe in self.explore_term_probes.items()},
            "subtotal": probe_scalar(self.explore_subtotal_probe),
            "final_action_value": float(action_values[ACTIONS.index("EXPLORE")]),
        }
        bg_winner = int(np.argmax(bg_output))
        winner, commitment = self.temporal.resolve(bg_winner, evidence, resolved_world_time)
        ordered = np.sort(competition_values)
        competition_margin = float(ordered[-1] - ordered[-2])
        commitment['competition_margin'] = competition_margin
        decision = ShadowDecision(
            selected=ACTIONS[winner],
            action_values={name: float(action_values[i]) for i, name in enumerate(ACTIONS)},
            competition_values={name: float(competition_values[i]) for i, name in enumerate(ACTIONS)},
            competition_evidence={name: float(evidence[i]) for i, name in enumerate(ACTIONS)},
            basal_ganglia_output={name: float(bg_output[i]) for i, name in enumerate(ACTIONS)},
            affordance_gates={name: float(gates[i]) for i, name in enumerate(ACTIONS)},
            explore_diagnostics=explore_diagnostics,
            commitment=commitment, confidence=clamp01(competition_margin / 0.40),
            sim_time=float(self.sim.time),
        )
        if hasattr(self.sim, 'clear_probes'):
            self.sim.clear_probes()
        return decision

    def close(self) -> None:
        self.sim.close()
