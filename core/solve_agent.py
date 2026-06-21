"""
core/solve_agent.py — SupervisedAgent (ARC-RFC-0001 §5).

An additive, recognition-gated, abortable solver layer OVER the general explorer.

Invariant: the explorer floor is never displaced except under a unique
high-confidence dynamic recognition, and any divergence from the solver's plan
aborts back to the floor within ABORT_K frames. So:
  - empty library / nothing recognized / aborted  → byte-identical to the floor
    (no regression by construction),
  - upside = whole games solved when a dynamic confidently matches.

The explorer learns ONLY from steps IT chose (the additive law, §7): while a solver
drives, the explorer is frozen (no observe/commit), so its model is identical to one
that skipped those off-policy frames. On abort it resumes from clean pre-takeover
state — never from a model polluted by moves it did not pick. This makes the layer
additive by construction: floor+dynamics >= floor on every game, firing or not.

(Superseded the prior "keep warm every step" design, which committed the executed
action regardless of who drove — teaching the floor off-policy edges and breaking
the additive invariant. The floor-freeze restores it.)
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
    additive, so the floor is what carries every game we cannot yet recognize.

    "v1"    = GeneralAgent (static signature) — the movement floor.
    "click" = ClickExplorer (ACTION6-capable) — for games that expose a click.
    """
    if floor == "click":
        # ACTION6-capable floor: count-based novelty over moves + foreground
        # clicks (movement-stall gates clicks on). For movement games it never
        # stalls so it never clicks — reduces to v1-style novelty; for click
        # games it can actually win instead of doing nothing. Use when 6 in avail.
        from core.click_agent import ClickExplorer
        return ClickExplorer(n_actions, allow_click=True, seed=seed)
    from core.general_agent import GeneralAgent       # default "v1" movement floor
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
        # Side-channel action SPEC for the executed step, in ClickExplorer's format:
        #   ("m", i)        → movement action index i
        #   ("c", x, y)     → ACTION6 click at frame cell (x, y)
        # Harnesses translate it via core.click_agent.spec_to_action_input. It is set
        # on every choose(); a click is emitted ONLY when a solver returns one, so for
        # non-firing / movement steps this is always ("m", action) and behaviour is
        # byte-identical to the int return (the additive invariant is untouched).
        self.spec = ("m", 0)

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
            a = step.action % self.n
            if step.click is not None:                # ACTION6 click-select
                self.spec = ("c", int(step.click[0]), int(step.click[1]))
            else:
                self.spec = ("m", a)
            return a

        # 4) Floor drives — a real explorer step it chose itself, so learn from it.
        #    On the first floor step after solver control, cut the transition gap so
        #    the floor doesn't learn a bogus edge from its last action to this frame.
        if self._solver_drove_last:
            self.explorer.mark_discontinuity()
            self._solver_drove_last = False
        self.explorer.observe(frame)
        proposal = self.explorer.propose(frame)
        self.explorer.commit(frame, proposal)
        # A click floor proposes a SPEC tuple (("m",i) / ("c",x,y)); the movement
        # floor proposes a bare int. Normalise to (spec, int) so the int return
        # stays valid for legacy `% n` callers and self.spec drives clicks.
        if isinstance(proposal, tuple):
            self.spec = proposal
            return (proposal[1] % self.n) if proposal[0] == "m" else 0
        self.spec = ("m", proposal)
        return proposal
