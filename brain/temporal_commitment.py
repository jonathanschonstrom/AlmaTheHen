"""Explicit short-lived hysteresis over neural competition evidence.

No analytical valuation, utility ranking or selftest coordinates enter this
controller. BG proposes an action. A valid HOLD state authorizes the incumbent
until a challenger exceeds the switch margin, the opportunity disappears, the
duration expires, or acute threat releases the non-defensive latch.
"""
from __future__ import annotations

import numpy as np

INIT_MARGIN = 0.040
SWITCH_MARGIN = 0.080
STRONG_EVIDENCE_MARGIN = 0.120
THREAT_THRESHOLD = 0.55
MIN_AFFORDANCE = 0.16


class TemporalCommitment:
    def __init__(self, actions, strengths, durations):
        self.actions = tuple(actions)
        self.strengths = dict(strengths)
        self.durations = dict(durations)
        self.current = None
        self.started = None
        self.world_time = None
        self.threat = False
        self.gates = np.ones(len(actions))
        self.remaining = 0.0
        self.bias = np.zeros(len(actions))
        self.release_reason = 'none'
        self.prior_action = ''

    def reset(self, reason='reset'):
        self.current = None
        self.started = None
        self.remaining = 0.0
        self.bias[:] = 0.0
        self.release_reason = reason

    def _eligible(self, index):
        action = self.actions[index]
        if self.threat and action != 'FLEE':
            return False
        return action in ('FLEE', 'EXPLORE') or self.gates[index] >= MIN_AFFORDANCE

    def prepare(self, world_time, safety, gates):
        """Advance organism-time validity once per request, never per spike."""
        self.prior_action = '' if self.current is None else self.actions[self.current]
        self.release_reason = 'none'
        self.gates = np.asarray(gates, dtype=float).copy()
        self.threat = float(safety) >= THREAT_THRESHOLD
        if self.world_time is not None and world_time < self.world_time:
            self.reset('clock_rewound')
        self.world_time = float(world_time)
        if self.current is not None:
            action = self.actions[self.current]
            if self.threat and action != 'FLEE':
                self.reset('threat_interrupt')
            elif not self._eligible(self.current):
                self.reset('affordance_lost')
            elif world_time - self.started >= self.durations[action]:
                self.reset('expired')
        self.bias[:] = 0.0
        self.remaining = 0.0
        if self.current is not None:
            action = self.actions[self.current]
            elapsed = max(0.0, world_time - self.started)
            self.remaining = 1.0 - elapsed / self.durations[action]
            strength = self.strengths[action] * self.remaining ** 0.60
            if action not in ('FLEE', 'EXPLORE'):
                strength *= 0.35 + 0.65 * self.gates[self.current]
            self.bias[self.current] = strength
        return self.bias.copy(), self.remaining

    def challenger(self, evidence):
        values = np.asarray(evidence, dtype=float)
        if values.shape != (len(self.actions),) or not np.isfinite(values).all():
            raise ValueError('Competition evidence must contain one finite value per action')
        if self.current is None:
            winner = int(np.argmax(values))
            second = float(np.max(np.delete(values, winner)))
            return winner, float(values[winner] - second)
        others = values.copy()
        others[self.current] = -np.inf
        challenger = int(np.argmax(others))
        return challenger, float(values[challenger] - values[self.current])

    def should_hold(self, evidence):
        _, advantage = self.challenger(evidence)
        # Equality belongs to HOLD. The tiny tolerance only handles floating
        # point subtraction at the exact boundary; it is not a fitted margin.
        return self.current is not None and advantage <= SWITCH_MARGIN + 1e-12

    def project(self, evidence):
        """Create the actual BG input; preserve the raw vector separately.

        HOLD guarantees the incumbent is the competition winner. The projection
        is conditional on the explicit switch comparison, not a larger decaying
        bias that may or may not suffice. Strong challengers pass unchanged.
        """
        effective = np.asarray(evidence, dtype=float).copy()
        challenger, _ = self.challenger(effective)
        if self.should_hold(effective):
            effective[self.current] = max(
                effective[self.current], effective[challenger] + SWITCH_MARGIN)
        return effective

    def resolve(self, bg_winner, evidence, world_time):
        """Resolve a frame from the same filtered evidence used by project()."""
        evidence = np.asarray(evidence, dtype=float)
        applied_bias = float(np.max(self.bias))
        applied_remaining = float(self.remaining)
        challenger, advantage = self.challenger(evidence)
        held = self.should_hold(evidence)
        reason = self.release_reason
        selection_source = 'bg'
        if held:
            selected = self.current
            reason = 'hold_within_switch_margin'
            selection_source = 'commitment_hold'
            # Never refresh onset while holding: a latch must actually expire.
        else:
            selected = int(bg_winner)
            if self.current is not None:
                self.reset('challenger_exceeds_switch_margin')
                reason = 'challenger_exceeds_switch_margin'
            candidate = int(np.argmax(evidence))
            margin = float(evidence[candidate] - np.max(np.delete(evidence, candidate)))
            supported = ((candidate == bg_winner and margin >= INIT_MARGIN)
                         or margin >= STRONG_EVIDENCE_MARGIN)
            if supported and self._eligible(candidate):
                self.current = candidate
                self.started = float(world_time)
                if reason == 'none':
                    reason = 'acquire_supported_evidence'
        return selected, {
            'prior_action': self.prior_action,
            'bias': applied_bias,
            'remaining': applied_remaining,
            'selected_action': self.actions[selected],
            'latched_action': '' if self.current is None else self.actions[self.current],
            'update_reason': reason,
            'state': 'HOLD' if held else ('LATCHED' if self.current is not None else 'FREE'),
            'switch_margin': SWITCH_MARGIN,
            'challenger_action': self.actions[challenger],
            'challenger_advantage': advantage,
            'bg_selected_action': self.actions[int(bg_winner)],
            'selection_source': selection_source,
            'bg_matches_selected': int(bg_winner) == selected,
            'release_reason': self.release_reason,
        }
