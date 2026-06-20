"""
core/solve_agent.py — SupervisedAgent (ARC-RFC-0001 §5).

An additive, recognition-gated, abortable solver layer OVER the general explorer.

Invariant: the explorer floor (GoalSeekAgent) is never displaced except under a
unique high-confidence dynamic recognition, and any divergence from the solver's
plan aborts back to the floor within ABORT_K frames. So:
  - empty library / nothing recognized / aborted  → byte-identical to `goal`
    (no regression by construction),
  - upside = whole games solved when a dynamic confidently matches.

The explorer learns ONLY from steps IT chose (the additive law, §7): while a solver
drives, the explorer is frozen (no observe/commit), so its model is identical to one
that skipped those off-policy frames. On abort it resumes from clean pre-takeover
state — never from a model polluted by moves it did not pick. This makes the layer
additive by construction: floor+dynamics >= floor on every game, firing or not.

(Superseded the prior "keep warm every step" design, which committed the executed
action regardless of who drove — teaching the floor off-policy edges and dropping
every dynamics build BELOW plain v1 on the leaderboard; see @BELIEF:LAT92LON62.)
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
        self._solver_drove_last = False

    def set_n_actions(self, n: int) -> None:
        self.n = max(1, n)
        self.explorer.set_n_actions(n)

    def choose(self, frame) -> int:
        frame = np.asarray(frame)

        # 1) Consistency check: did the last solver step's expectation hold?
        if self._active is not None and self._expect is not None:
            if self._expect(frame):
                self._diverge = 0
            else:
                self._diverge += 1
                if self._diverge >= _ABORT_K:        # latch back to floor for the level
                    self._aborted = True
                    self._active = None
                    self._expect = None

        # 2) Decide who drives. Solver pre-empts ONLY on a unique confident match
        #    (and not aborted) that yields a concrete next step.
        step = None
        if not self._aborted:
            d = self._active or dispatch(frame, self.dynamics)
            if d is not None:
                step = d.next_action(frame, self.n)
                if step is not None:
                    self._active = d

        # 3) THE ADDITIVE LAW (ARC-RFC-0001 §7): never teach the floor a step it did
        #    not choose. While the solver drives, the explorer is FROZEN — no observe,
        #    no commit — so its model is byte-identical to one that skipped these
        #    off-policy frames. The floor thus resumes from clean pre-takeover state
        #    on abort, and floor+dynamics >= floor by construction (no pollution).
        if step is not None:
            self._expect = step.expect
            self._solver_drove_last = True
            return step.action % self.n

        # 4) Floor drives — a real explorer step it chose itself, so learn from it.
        #    On the first floor step after solver control, cut the transition gap so
        #    the floor doesn't learn a bogus edge from its last action to this frame.
        if self._solver_drove_last:
            self.explorer.mark_discontinuity()
            self._solver_drove_last = False
        self.explorer.observe(frame)
        action = self.explorer.propose(frame)
        self.explorer.commit(frame, action)
        return action
