"""
core/goal_agent.py — additive-safe per-instance solving via goal-biased TIE-BREAKS.

Regime shift (2026-06-15): breadth is measurably exhausted at v1 (the coverage
proxy shows v2/dyn/click all flat). The next measurable gain needs per-instance
solving — read THIS frame, plan toward an inferred goal (@LAT25LON55). But
goal-seeking is directed commitment, the same shape as the detectors that scored
0.08. The reconciliation with the additive-only law (@LAT85LON55: "re-order among
already-safe actions, never displace an action that might have completed a level"):

  Do NOT plan. Only break v1's TIES.

GeneralAgent's policy has a top tier — untried-and-safe actions, or else the
least-visited-successor actions — and currently breaks ties by self._rng.choice.
This agent re-orders ONLY within that already-safe top tier: it never promotes a
lower tier and never displaces a more-novel action (which might be the lucky
completing one). When the controllable entity or the goal is unknown / low
confidence, the tie-break falls back to random -> byte-equivalent to its base
(general_dyn). So it is no-regression by construction, the same proof-shape that
made ClickExplorer safe. The only open question is whether biasing ties toward a
salient object raises the DEATH rate (steering into a trap); that is exactly what
the trap family of _test_solve_proxy.py measures, and why goal_mode is selectable.

Everything is inferred ONLINE from the frame — no canonical priors, no per-game
code (H-variant safe):
  * controllable-entity ID: the foreground color whose component keeps the same
    cell-count but whose centroid TRANSLATES when a move changes the board.
  * action->displacement: learned per action from how the entity centroid moved
    (so the agent discovers which action index is up/down/left/right by itself).
  * goal inference (goal_mode):
      "off"      no goal -> identical to general_dyn.
      "near"     nearest non-entity foreground object (aggressive; helps plain
                 goal-reaching, but will steer into a nearer trap -> regresses).
      "react"    only objects that previously REACTED (a board change the entity's
                 own translation does not explain — a key vanishing, a door
                 opening) and so are proven non-fatal. Safe; null on plain goal
                 worlds (nothing reacts until you win), helps affordance worlds.
      "frontier" push away from the mean of visited entity positions (object-free,
                 fully safe; spreads the budget-bound walk toward far regions).

STALL-GATE (the coverage-safety fix, 2026-06-15): biasing ties toward a goal
CONCENTRATES the walk and so REDUCES coverage — and coverage is the measured
driver of the 0.15->0.18 ladder (_test_proxy_curve.py caught near at -11% before
this gate). So goal-seeking is gated behind a movement-stall, exactly like
ClickExplorer: while novelty is still being found, ties are broken RANDOMLY
(byte-identical to general_dyn, coverage preserved). Only after _stall steps with
no never-seen signature — when coverage has saturated and directing the stuck
walk costs no coverage — does the goal tie-break engage. Additive on coverage too.
"""

import numpy as np

from core.general_agent_dyn import GeneralAgentDyn
from core.click_agent import _foreground_components

_MIN_ENTITY_VOTES = 3      # entity color trusted after this many consistent moves
_MIN_DISP_COUNT = 2        # action displacement trusted after this many samples
_REACT_MEMORY = 8          # how many recent reaction sites to keep


def _bg_color(a: np.ndarray) -> int:
    vals, counts = np.unique(a, return_counts=True)
    return int(vals[int(np.argmax(counts))])


def _centroid(mask: np.ndarray):
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return None
    return (float(ys.mean()), float(xs.mean()), int(ys.size))


class GoalSeekAgent(GeneralAgentDyn):
    def __init__(self, n_actions, seed=None, goal_mode: str = "near"):
        self.goal_mode = goal_mode
        super().__init__(n_actions, seed)
        self._stall = max(8, 2 * self.n)

    def set_n_actions(self, n: int) -> None:
        super().set_n_actions(n)
        self._stall = max(8, 2 * self.n)

    def reset_level(self) -> None:
        # Extra per-level state, set before the parent reset (which __init__ also
        # calls). Parent creates _dynsig then GeneralAgent tables.
        self._prev_frame = None
        self._cur_frame = None
        self._entity_color = None
        self._entity_votes: dict = {}
        self._action_disp: dict = {}     # action -> [sum_dy, sum_dx, count]
        self._visited = set()            # entity cells seen (for "near" reached-test)
        self._reactions: list = []       # recent (y, x) reaction sites
        self._since_new = 0              # steps since a never-seen signature (stall-gate)
        self._seek_on = False            # latches once movement stalls (this level)
        super().reset_level()

    # -- online perception -------------------------------------------------
    def choose(self, frame):
        self._cur_frame = np.asarray(frame)
        self._update_perception(self._cur_frame)
        action = super().choose(frame)   # dispatches to our _policy (tie-break)
        self._prev_frame = self._cur_frame
        return action

    def _update_perception(self, cur: np.ndarray) -> None:
        prev = self._prev_frame
        if prev is None or prev.shape != cur.shape:
            return
        changed = cur != prev
        if not changed.any():
            return                        # no-op step: nothing to learn

        bg = _bg_color(cur)
        colors = [c for c in np.unique(cur) if c != bg]

        # Entity = a color present in both frames, same cell-count, centroid moved
        # by a small integer step. Vote across moves; pick the consistent winner.
        moved_color, moved_disp = None, None
        for c in colors:
            pc = _centroid(prev == c)
            cc = _centroid(cur == c)
            if pc is None or cc is None or pc[2] != cc[2]:
                continue
            dy, dx = cc[0] - pc[0], cc[1] - pc[1]
            if 0 < abs(dy) + abs(dx) <= 2.0:      # translated a little
                self._entity_votes[int(c)] = self._entity_votes.get(int(c), 0) + 1
                if moved_color is None:
                    moved_color, moved_disp = int(c), (dy, dx)
        if self._entity_votes:
            self._entity_color = max(self._entity_votes, key=self._entity_votes.get)

        # Learn action->displacement from the entity's own motion last step.
        if (moved_color is not None and moved_color == self._entity_color
                and self._prev_action is not None):
            dy, dx = moved_disp
            d = self._action_disp.setdefault(self._prev_action, [0.0, 0.0, 0])
            d[0] += dy; d[1] += dx; d[2] += 1

        # Record where the entity now is (reached-object test for "near").
        ec = self._entity_centroid(cur)
        if ec is not None:
            self._visited.add((round(ec[0]), round(ec[1])))

        # Reaction = changed cells NOT belonging to the entity in either frame
        # (something else in the world changed -> an affordance fired). Proven
        # non-fatal because we are still alive to observe it.
        if self._entity_color is not None:
            ent = (cur == self._entity_color) | (prev == self._entity_color)
            react_mask = changed & ~ent
            rc = _centroid(react_mask)
            if rc is not None and rc[2] <= max(4, cur.size // 64):
                self._reactions.append((rc[0], rc[1]))
                self._reactions[:] = self._reactions[-_REACT_MEMORY:]

    def _entity_centroid(self, frame: np.ndarray):
        if self._entity_color is None:
            return None
        return _centroid(frame == self._entity_color)

    # -- goal inference ----------------------------------------------------
    def _goal(self):
        """Return a (gy, gx) goal centroid, or None when not confidently inferred."""
        if self.goal_mode == "off":
            return None
        e = self._entity_centroid(self._cur_frame)
        if e is None or sum(self._entity_votes.values()) < _MIN_ENTITY_VOTES:
            return None
        ey, ex = e[0], e[1]

        if self.goal_mode == "frontier":
            if not self._visited:
                return None
            vy = sum(p[0] for p in self._visited) / len(self._visited)
            vx = sum(p[1] for p in self._visited) / len(self._visited)
            # push away from the visited mean (toward unexplored regions)
            return (ey + (ey - vy), ex + (ex - vx))

        if self.goal_mode == "react":
            if not self._reactions:
                return None
            return min(self._reactions, key=lambda r: (r[0] - ey) ** 2 + (r[1] - ex) ** 2)

        if self.goal_mode == "near":
            comps = _foreground_components(self._cur_frame)   # (gx, gy) list
            best, best_d = None, None
            for gx, gy in comps:
                if abs(gy - ey) + abs(gx - ex) < 1.5:         # the entity itself
                    continue
                if (round(gy), round(gx)) in self._visited:    # already reached
                    continue
                d = (gy - ey) ** 2 + (gx - ex) ** 2
                if best_d is None or d < best_d:
                    best_d, best = d, (gy, gx)
            return best
        return None

    # -- tie-break ---------------------------------------------------------
    def _tiebreak(self, pool, sig):
        if len(pool) == 1:
            return pool[0]
        # Stall-gate (LATCHED): until movement novelty dries up, break ties
        # RANDOMLY so coverage is preserved (identical to general_dyn). Once the
        # walk has stalled once, goal-seeking latches ON for the rest of the
        # level — directed progress would otherwise reset the stall and disable
        # itself (self-defeating). Latching mirrors ClickExplorer's _clicks_on.
        if not self._seek_on:
            return self._rng.choice(pool)
        goal = self._goal()
        e = self._entity_centroid(self._cur_frame)
        if goal is None or e is None:
            return self._rng.choice(pool)
        gy, gx = goal
        ey, ex = e[0], e[1]
        best, best_d = [], None
        for a in pool:
            d = self._action_disp.get(a)
            if d is None or d[2] < _MIN_DISP_COUNT:
                continue                  # unknown effect -> don't bias toward it
            ny, nx = ey + d[0] / d[2], ex + d[1] / d[2]
            dist = (ny - gy) ** 2 + (nx - gx) ** 2
            if best_d is None or dist < best_d:
                best_d, best = dist, [a]
            elif dist == best_d:
                best.append(a)
        if not best:                      # no candidate has a known displacement
            return self._rng.choice(pool)
        return self._rng.choice(best)

    # -- policy: v1 structure, ties routed through _tiebreak ---------------
    def _policy(self, sig: bytes) -> int:
        # Track movement-stall on the agent's own signature (visit was just
        # incremented by GeneralAgent.choose, so ==1 means this sig is new).
        if self.visit.get(sig, 0) <= 1:
            self._since_new = 0
        else:
            self._since_new += 1
            if self._since_new >= self._stall:
                self._seek_on = True      # LATCH: stays on for the rest of the level

        all_actions = list(range(self.n))
        tried = [a for a in all_actions if (sig, a) in self.trans]
        untried = [a for a in all_actions if a not in tried]

        cand = [a for a in untried if (sig, a) not in self.noop]
        if cand:
            return self._tiebreak(cand, sig)
        if untried:
            return self._rng.choice(untried)

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
        return self._tiebreak(best, sig)
