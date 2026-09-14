"""Frozen v0.2.5 EXPLORE analytical reference.
Original full-file SHA-256: 47d4ea08e80ee450ee815cc4e7edbabf1e6ef5233bb05c05e098fa989e9ca401
Only functions consumed by brain/test_regressions_v026.py are retained.
"""

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

    The analytical policy is unchanged. The spiking network in v0.2.5 mirrors
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
