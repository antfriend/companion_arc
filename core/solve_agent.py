"""
core/solve_agent.py — SupervisedAgent (ARC-RFC-0001 §5).

An additive, recognition-gated, abortable solver layer OVER the general explorer.

Invariant: the explorer floor (GoalSeekAgent) is never displaced except under a
unique high-confidence dynamic recognition, and any divergence from the solver's
plan aborts back to the floor within ABORT_K frames. So:
  - empty library / nothing recognized / aborted  → byte-identical to `goal`
    (no regression by construction),
  - upside = whole games solved when a dynamic confidently matches.

The explorer is kept WARM every step (observe + commit the executed action), so
after an abort it already holds this level's transition table — no cold start.
"""

from typing import List, Optional

import numpy as np

from core.dynamics.base import Dynamic
from core.dynamics.registry import dispatch, DYNAMICS

# Frames of plan-vs-reality divergence tolerated before latching back to the
# explorer floor for the rest of the level (ARC-RFC-0001 §5/§7).
_ABORT_K = 3


def _make_floor(floor: str, n_actions: int, seed):
    """The undirected explorer used on unrecognized games. The dynamics layer is
    additive, so the floor DOMINATES the score → use the measured-best explorer.

    "v1"  = GeneralAgent (static signature) — leaderboard 0.18, the standing best.
    "dyn" = GeneralAgentDyn (HUD-immune signature).
    "goal"= GoalSeekAgent (goal tie-break) — leaderboard 0.10; NOT recommended as a
            floor (its directed tie-break is redundant once dynamics drive solving,
            and it scored below v1). The 2026-06-16 solve submission used this floor
            by mistake → 0.13 (= goal 0.10 + dynamics +0.03); v1 floor should ≈0.21.
    """
    if floor == "dyn":
        from core.general_agent_dyn import GeneralAgentDyn
        return GeneralAgentDyn(n_actions, seed=seed)
    if floor == "goal":
        from core.goal_agent import GoalSeekAgent
        return GoalSeekAgent(n_actions, seed=seed, goal_mode="near")
    from core.general_agent import GeneralAgent       # default "v1" — the 0.18 floor
    return GeneralAgent(n_actions, seed=seed)


class SupervisedAgent:
    def __init__(self, n_actions: int, seed: Optional[int] = None,
                 floor: str = "v1",
                 dynamics: Optional[List[Dynamic]] = None) -> None:
        self.n = max(1, n_actions)
        self.explorer = _make_floor(floor, n_actions, seed)
        # None → use the global registry; [] → empty (must == the floor); list → inject.
        self.dynamics = DYNAMICS if dynamics is None else dynamics
        self.reset_level()

    def reset_level(self, level: int = 1) -> None:
        self.explorer.reset_level()
        for d in self.dynamics:
            d.set_level(level)          # level-aware solvers plan the right route
            d.reset()
        self._active: Optional[Dynamic] = None
        self._expect = None
        self._aborted = False
        self._diverge = 0

    def set_n_actions(self, n: int) -> None:
        self.n = max(1, n)
        self.explorer.set_n_actions(n)

    def choose(self, frame) -> int:
        frame = np.asarray(frame)
        # 1) Keep the floor warm REGARDLESS of who drives.
        self.explorer.observe(frame)
        explorer_action = self.explorer.propose(frame)

        # 2) Consistency check: did the last solver step's expectation hold?
        if self._active is not None and self._expect is not None:
            if self._expect(frame):
                self._diverge = 0
            else:
                self._diverge += 1
                if self._diverge >= _ABORT_K:        # latch back to floor for the level
                    self._aborted = True
                    self._active = None
                    self._expect = None

        # 3) Solver pre-empts ONLY on a unique confident match (and not aborted).
        action = explorer_action
        if not self._aborted:
            d = self._active or dispatch(frame, self.dynamics)
            step = d.next_action(frame, self.n) if d is not None else None
            if step is not None:
                self._active = d
                self._expect = step.expect
                action = step.action % self.n

        # 4) Tell the explorer what was ACTUALLY executed (warm handoff).
        self.explorer.commit(frame, action)
        return action
