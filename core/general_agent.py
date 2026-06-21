"""
core/general_agent.py — ONE general agent for all games. No per-game code.

Motivation: a fixed per-game route drives unknown instances into early
GAME_OVER (the board it was recorded on is not the board it now faces), so it
clears fewer levels than even uniform-random play. The fix is an agent that:
  - re-decides every frame (never commits to a killable plan),
  - wastes no budget on no-op actions (moves blocked by walls),
  - explores via count-based novelty (cover more distinct states than random),
  - identifies the controllable entity online but never hard-codes a goal.

This is a tabular count-based explorer. It maintains, per level:
  visit[sig]              how many times a board-signature was seen
  trans[(sig, action)]    the signature that action produced from sig
  noop[(sig, action)]     action produced no board change from sig (wall/blocked)

Policy from the current signature s:
  1. untried actions from s  → take one (max novelty), skipping known no-ops
  2. else                    → take the action whose known successor is least
                               visited (pull toward unexplored region),
                               skipping no-ops; ties broken randomly

The signature ignores the outer UI rows/cols (timer/step bars animate every
frame and would otherwise make every state look novel).
"""

import random
from typing import Optional

import numpy as np


def board_signature(frame: np.ndarray) -> bytes:
    """Hashable signature of the play area, excluding animated UI borders."""
    a = np.asarray(frame)
    if a.shape[0] >= 3 and a.shape[1] >= 2:
        core = a[1:-1, :-1]          # drop top+bottom rows and last col (UI bars)
    else:
        core = a
    return core.tobytes()


class GeneralAgent:
    def __init__(self, n_actions: int, seed: Optional[int] = None) -> None:
        self.n = max(1, n_actions)
        self._rng = random.Random(seed)
        self.reset_level()

    def reset_level(self) -> None:
        self.visit: dict = {}
        self.trans: dict = {}      # (sig, action) -> next_sig
        self.noop: set = set()     # (sig, action) with no board change
        self._prev_sig: Optional[bytes] = None
        self._prev_action: Optional[int] = None
        self._cur_sig: Optional[bytes] = None   # this step's signature (observe→propose→commit)

    def set_n_actions(self, n: int) -> None:
        self.n = max(1, n)

    def _sig(self, frame: np.ndarray) -> bytes:
        """Signature seam — overridable by subclasses. Default is the static
        board_signature (the v1 floor)."""
        return board_signature(frame)

    # -- observe / propose / commit ----------------------------------------
    # Split so a supervisor (core/solve_agent.py) can keep the explorer warm
    # while a solver drives: observe(frame) every step, propose() when the
    # explorer is in control, commit(frame, executed_action) with whatever
    # action was ACTUALLY taken (solver or explorer). choose() composes the
    # three so standalone behavior is byte-identical to the old single method.

    def observe(self, frame: np.ndarray) -> bytes:
        """Ingest a frame: compute its signature (once — _sig may mutate state),
        count the visit, and learn the effect of the previously executed action."""
        sig = self._sig(frame)
        self._cur_sig = sig
        self.visit[sig] = self.visit.get(sig, 0) + 1
        if self._prev_sig is not None and self._prev_action is not None:
            key = (self._prev_sig, self._prev_action)
            self.trans[key] = sig
            if sig == self._prev_sig:
                self.noop.add(key)
        return sig

    def propose(self, frame: Optional[np.ndarray] = None) -> int:
        """The explorer's action for this step's observed signature."""
        return self._policy(self._cur_sig)

    def commit(self, frame: Optional[np.ndarray], action: int) -> None:
        """Record the action that was ACTUALLY executed (for next-step learning)."""
        self._prev_sig, self._prev_action = self._cur_sig, action

    def mark_discontinuity(self) -> None:
        """Forget the last executed action so the NEXT observe learns no transition
        across a control gap. Used by the supervisor (core/solve_agent.py) when the
        explorer resumes after a solver drove off-policy steps: the resumed frame is
        NOT the successor of the last floor action, so trans[(prev_sig, prev_action)]
        must not be written. This keeps the floor's model identical to one that
        simply skipped the off-policy frames (the additive law, ARC-RFC-0001 §7)."""
        self._prev_sig, self._prev_action = None, None

    def choose(self, frame: np.ndarray) -> int:
        self.observe(frame)
        action = self.propose(frame)
        self.commit(frame, action)
        return action

    def _policy(self, sig: bytes) -> int:
        all_actions = list(range(self.n))
        tried = [a for a in all_actions if (sig, a) in self.trans]
        untried = [a for a in all_actions if a not in tried]

        # 1) Prefer untried actions (highest novelty), skipping known no-ops.
        cand = [a for a in untried if (sig, a) not in self.noop]
        if cand:
            return self._rng.choice(cand)
        if untried:  # all untried are no-ops here; still try one (cheap)
            return self._rng.choice(untried)

        # 2) All actions tried: go toward the least-visited known successor,
        #    skipping no-ops (they waste a step).
        live = [a for a in all_actions if (sig, a) not in self.noop]
        pool = live or all_actions
        best, best_v = [], None
        for a in pool:
            nsig = self.trans.get((sig, a))
            v = self.visit.get(nsig, 0) if nsig is not None else 0
            if best_v is None or v < best_v:
                best_v, best = v, [a]
            elif v == best_v:
                best.append(a)
        return self._rng.choice(best)
