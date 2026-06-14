"""
core/meta_agent.py — cross-game meta-explorer (dream spark @LAT30LON55).

The 25-game rerun is ONE process. Every prior build resets all learned state per
game, treating the games as independent. But if the hidden set is an H-variant
FAMILY (@LAT79LON55), the action SEMANTICS are shared even when the games differ:
across ARC-AGI-3, action ids 1-4 tend to be directional, 5/7 primary/secondary,
6 a click. So a prior keyed by ACTION ID (not by board signature, not by game)
can be learned on the first games of a rerun and primed into the later ones.

What transfers (dense, always available):
  change-rate[id]   P(the board changed | action id was taken), pooled over all
                    games so far — actions that tend to DO something are tried
                    first in a new game, before that game's own data exists.
What transfers (sparse, high-value):
  complete[id]      times an action id was in the window just before a level
                    completion — the gold signal, credited on completion.

Additive-only law (@LAT85LON55): the prior must only RE-ORDER exploration, never
commit. So it biases WHICH untried/safe action is sampled (soft weighted choice),
and never overrides the never-commit, re-decide-every-frame stochasticity. On a
new game with no relevant prior it degrades gracefully to general_agent v1.

Per-level model (visit/trans/noop) is identical to v1 and is reset per level;
the cross-game prior (g_*) persists across new_game() and level_completed().
"""

import random
from collections import deque
from typing import Optional

import numpy as np

from core.general_agent import board_signature

_COMPLETE_WEIGHT = 3.0   # how strongly a completion-associated id is preferred
_CREDIT_WINDOW = 5       # actions before a completion that get completion credit


class MetaExplorer:
    def __init__(self, seed: Optional[int] = None,
                 credit_window: int = _CREDIT_WINDOW) -> None:
        self._rng = random.Random(seed)
        self._credit_window = credit_window
        # Cross-game prior, keyed by action id — persists across games/levels.
        self.g_tries: dict = {}
        self.g_change: dict = {}
        self.g_complete: dict = {}
        self.action_ids: list = []
        self.reset_level()

    # -- lifecycle ---------------------------------------------------------

    def new_game(self, action_ids) -> None:
        """Start a new game. Per-level model clears; cross-game prior persists."""
        self.action_ids = list(action_ids)
        self.reset_level()

    def reset_level(self) -> None:
        self.visit: dict = {}
        self.trans: dict = {}
        self.noop: set = set()
        self._prev_sig: Optional[bytes] = None
        self._prev_id: Optional[int] = None
        self._recent: deque = deque(maxlen=self._credit_window)

    def level_completed(self) -> None:
        """Credit the recent actions for the completion, then reset the level."""
        for aid in self._recent:
            self.g_complete[aid] = self.g_complete.get(aid, 0) + 1
        self.reset_level()

    # -- prior -------------------------------------------------------------

    def _prior(self, aid: int) -> float:
        tries = self.g_tries.get(aid, 0)
        change_rate = (self.g_change.get(aid, 0) + 1) / (tries + 2)   # Laplace
        comp_rate = self.g_complete.get(aid, 0) / (tries + 1)
        return change_rate + _COMPLETE_WEIGHT * comp_rate

    def _weighted(self, ids):
        weights = [max(1e-3, self._prior(i)) for i in ids]
        return self._rng.choices(ids, weights=weights, k=1)[0]

    # -- step --------------------------------------------------------------

    def choose(self, frame: np.ndarray) -> int:
        sig = board_signature(frame)
        self.visit[sig] = self.visit.get(sig, 0) + 1

        # Learn the previous action's effect, both per-level and cross-game.
        if self._prev_sig is not None and self._prev_id is not None:
            key = (self._prev_sig, self._prev_id)
            self.trans[key] = sig
            changed = sig != self._prev_sig
            if not changed:
                self.noop.add(key)
            self.g_tries[self._prev_id] = self.g_tries.get(self._prev_id, 0) + 1
            if changed:
                self.g_change[self._prev_id] = self.g_change.get(self._prev_id, 0) + 1

        aid = self._policy(sig)
        self._recent.append(aid)
        self._prev_sig, self._prev_id = sig, aid
        return aid

    def _policy(self, sig: bytes) -> int:
        ids = self.action_ids or [0]
        tried = [i for i in ids if (sig, i) in self.trans]
        untried = [i for i in ids if i not in tried]

        cand = [i for i in untried if (sig, i) not in self.noop]
        pool = cand or untried
        if pool:
            return self._weighted(pool)  # prior orders the novelty frontier

        # All tried: head for the least-visited known successor; the prior only
        # breaks ties (additive-only — it never overrides exploration value).
        live = [i for i in ids if (sig, i) not in self.noop] or ids
        best, best_v = [], None
        for i in live:
            nsig = self.trans.get((sig, i))
            v = self.visit.get(nsig, 0) if nsig is not None else 0
            if best_v is None or v < best_v:
                best_v, best = v, [i]
            elif v == best_v:
                best.append(i)
        return self._weighted(best)
