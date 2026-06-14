"""
core/general_agent_v2.py — frontier-directed explorer (next increment, NOT shipped).

v1 (general_agent.py) explores by 1-step novelty: prefer untried actions, else
the action whose immediate successor is least-visited. That is myopic — once the
local successors are all visited it dithers near-randomly, and it has no notion
of "this whole region is exhausted, leave it."

v2 keeps v1's learned model (visit / trans / noop) but replaces the policy with
a lightweight value iteration over the learned transition graph. Define a
"frontier" as any (sig, action) we have not yet tried (and is not a known
no-op). We back up a frontier reward through the known graph so every state
gets a value = discounted proximity to the nearest reachable unexplored action.
The policy then walks the shortest known path toward the nearest frontier.

Consequences vs v1:
  - Directed pathing to the frontier instead of myopic least-visited (fewer
    wasted steps crossing already-mapped corridors).
  - Automatic subtree pruning: a fully-explored region has no reachable
    frontier, so its value decays to 0 and the agent stops returning there.
  - Same first-choice behavior at a fresh state (untried non-noop = max value),
    so it never regresses below v1 locally; it only improves the "what now?"
    case where v1 went near-random.

Interface is identical to v1 (GeneralAgent): __init__(n_actions, seed=None),
reset_level(), set_n_actions(n), choose(frame) -> int. So launch_competition.py
can swap the import with no other change.
"""

import random
from typing import Optional

import numpy as np

from core.general_agent import board_signature

# Value-iteration constants.
_R_FRONTIER = 1.0    # reward for reaching a state with an untried, non-noop action
_GAMMA = 0.85        # discount: nearer frontiers strongly preferred over far ones
_MAX_SWEEPS = 100    # value-iteration cap (breaks early on convergence)
_CONVERGED = 1e-3


class GeneralAgentV2:
    def __init__(self, n_actions: int, seed: Optional[int] = None) -> None:
        self.n = max(1, n_actions)
        self._rng = random.Random(seed)
        self.reset_level()

    def reset_level(self) -> None:
        self.visit: dict = {}
        self.trans: dict = {}          # (sig, action) -> next_sig
        self.noop: set = set()         # (sig, action) with no board change
        self._prev_sig: Optional[bytes] = None
        self._prev_action: Optional[int] = None
        self._V: dict = {}             # sig -> backed-up frontier value
        self._dirty = True             # graph changed since last value iteration

    def set_n_actions(self, n: int) -> None:
        if n != self.n:
            self.n = max(1, n)
            self._dirty = True

    def choose(self, frame: np.ndarray) -> int:
        sig = board_signature(frame)
        if sig not in self.visit:
            self._dirty = True
        self.visit[sig] = self.visit.get(sig, 0) + 1

        # Learn the effect of the previous action.
        if self._prev_sig is not None and self._prev_action is not None:
            key = (self._prev_sig, self._prev_action)
            if key not in self.trans or self.trans[key] != sig:
                self._dirty = True
            self.trans[key] = sig
            if sig == self._prev_sig:
                if key not in self.noop:
                    self._dirty = True
                self.noop.add(key)

        action = self._policy(sig)
        self._prev_sig, self._prev_action = sig, action
        return action

    # -- value iteration over the learned graph ----------------------------

    def _q(self, sig: bytes, a: int) -> Optional[float]:
        """Action value, or None if this action is a known no-op (skip it)."""
        key = (sig, a)
        if key in self.noop:
            return None
        if key not in self.trans:
            return _R_FRONTIER  # untried, non-noop → directly at the frontier
        return _GAMMA * self._V.get(self.trans[key], 0.0)

    def _recompute_values(self) -> None:
        for _ in range(_MAX_SWEEPS):
            delta = 0.0
            for s in self.visit:
                best = 0.0
                for a in range(self.n):
                    q = self._q(s, a)
                    if q is not None and q > best:
                        best = q
                prev = self._V.get(s, 0.0)
                if abs(prev - best) > delta:
                    delta = abs(prev - best)
                self._V[s] = best
            if delta < _CONVERGED:
                break
        self._dirty = False

    def _policy(self, sig: bytes) -> int:
        if self._dirty:
            self._recompute_values()

        # Score each non-noop action; prefer untried (direct frontier), then
        # higher backed-up value, then a less-visited successor, then random.
        best_score = None
        best: list[int] = []
        forced: list[int] = []  # all-noop fallback
        for a in range(self.n):
            key = (sig, a)
            forced.append(a)
            q = self._q(sig, a)
            if q is None:
                continue
            untried = key not in self.trans
            succ_visits = 0 if untried else self.visit.get(self.trans[key], 0)
            # Sort key: maximize value, prefer untried, then fewer successor visits.
            score = (round(q, 6), 1 if untried else 0, -succ_visits)
            if best_score is None or score > best_score:
                best_score, best = score, [a]
            elif score == best_score:
                best.append(a)

        pool = best or forced  # if every action is a known no-op, still act
        return self._rng.choice(pool)


# Alias so callers can import a stable name regardless of version.
GeneralAgent = GeneralAgentV2
