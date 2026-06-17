"""
games/ls20/dynamic.py — ls20 as a Dynamic (ARC-RFC-0001 §3).

ls20 is ONE "transform-and-deliver" mechanic at every level: a block carries (shape,
color, rotation); changer tiles cycle each; rings reset a move-timer; a target admits the
block only when all three attrs match; WIN = deliver to every target matching. Levels are
just configurations (L1 = +1 rotation visit; L2 = +3 + 2 ring resets), so ONE frame-driven
solver (games/ls20/solver.py) clears them — superseding the old per-level fixed routes.

Per level: read the spec from the frame, plan transform-and-deliver with timer-aware ring
interleaving, then emit the plan one action at a time. The plan assumes deterministic one-cell
moves, so it is GUARDED: before each step we verify the block reached the cell the previous
step predicted. A divergence means an unmodeled mechanic moved it — e.g. the PUSHER bars on L3
(a colour-1 `gbvqrjtaqo` bar) shove the block several cells, and on L3 the pusher cell is in
fact the only way out of the start pocket, so it MUST be used. Rather than model each such
mechanic, we RE-PLAN from the block's actual position whenever it diverges (closed-loop): one
push → one replan → finish. A small cap on replans (and read_spec/plan returning None) latches
back to the explorer floor, so a genuinely unsolvable layout can't spin. (L3 needs 1 replan.)

Recognition: ls20's SMALL color-12 block (≤50 px) — excludes sp80 where color-12 is the
~3500-px background.
"""

import numpy as np

from core.dynamics.base import Dynamic, SolverStep
from games.ls20 import solver as S


def _expect_changed(cur):
    b = np.asarray(cur).tobytes()
    return lambda f: np.asarray(f).tobytes() != b


class Ls20Dynamic(Dynamic):
    id = "ls20"
    MAX_REPLANS = 16          # closed-loop replans per level before latching to the floor

    def reset(self) -> None:
        self._route = None
        self._planned = False
        self._i = 0
        self._cells = None        # predicted block-cell after each planned action
        self._replans = 0
        self._aborted = False

    def recognize(self, frame) -> float:
        # PRECISION fingerprint: a SMALL color-12 block (≤50 px) — excludes sp80 where
        # color-12 is the background (~3500 px).
        f = np.asarray(frame)
        n12 = int(np.count_nonzero(f == S.BLOCK))
        return 1.0 if 0 < n12 <= 50 else 0.0

    def _plan_from(self, f):
        """(Re)plan from the current frame; precompute the predicted block-cell path."""
        spec = S.read_spec(f, getattr(self, "_level", 1))
        self._route = S.plan(spec) if spec is not None else None
        self._i = 0
        self._cells = None
        if self._route and spec is not None:
            cell, cells = spec["block"], []
            for a in self._route:
                dr, dc = S.DELTA[int(a)]; cell = (cell[0] + dr, cell[1] + dc); cells.append(cell)
            self._cells = cells

    def next_action(self, frame, n_actions):
        f = np.asarray(frame)
        if not self._planned:                      # plan once per level, from the frame
            self._planned = True
            self._plan_from(f)
        elif self._i > 0 and self._cells is not None and S.read_block_cell(f) != self._cells[self._i - 1]:
            # DIVERGENCE: an unmodeled mechanic moved the block (e.g. a pusher shove). Re-plan
            # closed-loop from where it actually is, up to a cap (then latch to the floor).
            self._replans += 1
            if self._replans > self.MAX_REPLANS:
                self._aborted = True
            else:
                self._plan_from(f)
        if self._aborted or not self._route or self._i >= len(self._route):
            return None                            # nothing to drive → defer to the floor
        a = int(self._route[self._i])              # solver is 1-indexed (1=UP..4=RIGHT)
        self._i += 1
        return SolverStep((a - 1) % n_actions, _expect_changed(f), f"ls20[{self._i - 1}]={a}")
