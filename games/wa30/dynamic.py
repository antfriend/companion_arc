"""
games/wa30/dynamic.py — wa30 as a Dynamic (ARC-RFC-0001 §3, fourth port).

wa30 = pick-up-and-deliver. A 4×4 cursor (color-0 direction edge + color-14 body)
picks up color-4 items and carries them to a color-2 drop zone (ACTION5 =
pickup/drop). Multi-phase (approach → face → pickup → carry → drop).

L1 (no adversary): PLAN ONCE per level — the detector's adaptive multi-item BFS
route (frame-derived, translation-robust), replayed one action at a time, each
guarded by a "board changed" expectation. A no-op step means the plan desynced and
the supervisor aborts back to the explorer.

L2+ (a color-12 patroller that KILLS on contact): the fixed plan would walk into the
patroller, and — crucially — wa30 has NO wait action (a no-op needs a wall), so the
agent must EVADE by detouring, not by pausing. So when an adversary is present the
dynamic switches to a CLOSED-LOOP hazard-aware delivery driven by the shared
space-time BFS organ (core/dynamics/hazard_nav.py): each frame it re-reads the
cursor + adversary, forecasts the patroller's short-horizon occupancy, and BFS-routes
the current delivery sub-goal around it. Phases (approach/face/pickup/carry/drop) are
tracked internally; carry-state can't be read cleanly from the frame (a carried item
still shows as a loose color-4), so it is latched. Anything uncertain → return None →
defer to the floor (additive-safe).
"""

import numpy as np

from core.dynamics.base import Dynamic, SolverStep
from core.dynamics.hazard_nav import (
    HazardTracker, predict_occupancy, spacetime_bfs, manhattan, WAIT,
)
from games.wa30 import detector as W

STEP = 4
_LO, _HI = 0, 15                       # 64/STEP = 16 cells per axis (0..15)
_HORIZON = 12
# (dx, dy) cell move → wa30 action index (0=UP,1=DOWN,2=LEFT,3=RIGHT)
_ACT = {(0, -1): 0, (0, 1): 1, (-1, 0): 2, (1, 0): 3}
_DIRS = [(0, -1), (0, 1), (-1, 0), (1, 0)]
_PICKDROP = 4


def _expect_changed(cur):
    b = cur.tobytes()
    return lambda f: np.asarray(f).tobytes() != b


def _adv_cells(frame):
    """Color-12 adversary sprite centroid(s) → cell coords. Returns [] if none."""
    pos = np.argwhere(np.asarray(frame) == 12)
    if len(pos) == 0:
        return []
    # one compact 4×4 sprite per adversary; cluster by 8-connectivity
    rem = {(int(r), int(c)) for r, c in pos}
    out = []
    while rem:
        seed = next(iter(rem)); stack = [seed]; cl = []
        while stack:
            cur = stack.pop()
            if cur not in rem:
                continue
            rem.discard(cur); cl.append(cur); r, c = cur
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if (r + dr, c + dc) in rem:
                        stack.append((r + dr, c + dc))
        mr = sum(r for r, _ in cl) / len(cl)
        mc = sum(c for _, c in cl) / len(cl)
        out.append((int(round(mc)) // STEP, int(round(mr)) // STEP))   # (x,y) cell
    return out


class Wa30Dynamic(Dynamic):
    id = "wa30"

    def reset(self) -> None:
        self._route = None          # L1 plan-once route
        self._i = 0
        # L2 closed-loop state
        self._tracker = HazardTracker()
        self._carrying = False
        self._item_off = None       # (dx,dy) cell offset of carried item
        self._phase = "approach"    # approach|face|pickup|carry|drop
        self._target = None         # current item cell being fetched

    def recognize(self, frame) -> float:
        # PRECISION fingerprint: small color-0 cursor edge + color-14 body + a
        # color-2 drop zone, AND the detector finds both items and a drop zone.
        # The color-2 cap is generous enough for L2's larger drop zone; precision
        # comes from the STRUCTURAL detect_state (cursor edge + items + dz), not
        # the raw count (see _test_falsefire.py).
        f = np.asarray(frame)
        p0 = np.count_nonzero(f == 0)
        p2 = np.count_nonzero(f == 2)
        p14 = np.count_nonzero(f == 14)
        if not (0 < p0 <= 40 and 0 < p2 <= 80 and 0 < p14 <= 40):
            return 0.0
        # The drop zone is a COMPACT rectangle (L1 ~2×10, L2 ~10×6). This — not the
        # raw count — is what excludes sk48's frame-spanning color-2 band (bbox up to
        # 46×64, 200+ phased cells) that the old p2<=40 cap happened to filter. The
        # p2 cap had to widen for L2's larger drop zone, so gate on SHAPE instead.
        pos2 = np.argwhere(f == 2)
        h = int(pos2[:, 0].max() - pos2[:, 0].min()) + 1
        w = int(pos2[:, 1].max() - pos2[:, 1].min()) + 1
        if max(h, w) > 16:
            return 0.0
        st = W.detect_state(f)
        if not st or not st.get("items") or not st.get("dz_valid"):
            return 0.0
        if len(st["dz_valid"]) > 12:        # a real drop zone has a handful of slots
            return 0.0
        return 1.0

    # ----- L2 closed-loop hazard-aware delivery -----------------------------
    def _l2_step(self, f, n_actions):
        st = W.detect_state(f)
        if not st:
            return None
        cursor = (st["cursor_x"] // STEP, st["cursor_y"] // STEP)
        dz = {(x // STEP, y // STEP) for (x, y) in st["dz_valid"]}
        items = [(x // STEP, y // STEP) for (x, y) in st["items"]]

        # Carried item reads as a loose color-4; drop it from the to-fetch list.
        carried_cell = None
        if self._carrying and self._item_off is not None:
            carried_cell = (cursor[0] + self._item_off[0], cursor[1] + self._item_off[1])
            items = [it for it in items if it != carried_cell]

        # Undelivered = items not already sitting on a drop cell.
        undelivered = [it for it in items if it not in dz]

        # Hazard forecast (re-derived every frame → short horizon suffices).
        adv = self._tracker.update(_adv_cells(f))
        occ = predict_occupancy(adv, _HORIZON, radius=1, bounds=(_LO, _LO, _HI, _HI))

        def in_bounds(c):
            return _LO <= c[0] <= _HI and _LO <= c[1] <= _HI

        # ----- not carrying: fetch the nearest item -----
        if not self._carrying:
            if not undelivered:
                return None                      # nothing left → hand back
            # Only (re)pick a target while approaching; once we are face/pickup we
            # commit, so a one-frame detection dropout can't reset the phase.
            if self._phase == "approach" and self._target not in undelivered:
                self._target = min(undelivered, key=lambda it: manhattan(it, cursor))
            if self._target is None:
                self._target = min(undelivered, key=lambda it: manhattan(it, cursor))
            item = self._target
            others = set(undelivered) - {item}

            def passable(c):
                return in_bounds(c) and c not in others and c != item

            adj = [(item[0] + dx, item[1] + dy) for dx, dy in _DIRS]
            adj = [a for a in adj if passable(a)]
            if not adj:
                return None

            if cursor in adj or self._phase in ("face", "pickup"):
                # adjacent: face the item then pick it up (2 no-op frames). Guard:
                # only do so if staying put is safe next tick; else flee one step.
                if cursor in occ[1] if len(occ) > 1 else False:
                    mv = spacetime_bfs(cursor, item, passable, occ, _HORIZON)
                    if mv in (None, WAIT):
                        return None
                    return SolverStep(_ACT[mv], _expect_changed(f), "wa30L2 flee")
                if self._phase != "pickup":
                    self._phase = "pickup"
                    fdx, fdy = item[0] - cursor[0], item[1] - cursor[1]
                    fdx = max(-1, min(1, fdx)); fdy = max(-1, min(1, fdy))
                    return SolverStep(_ACT[(fdx, fdy)], lambda ff: True, "wa30L2 face")
                # pickup
                self._carrying = True
                self._item_off = (item[0] - cursor[0], item[1] - cursor[1])
                self._phase = "carry"
                return SolverStep(_PICKDROP, _expect_changed(f), "wa30L2 pickup")

            # approach: BFS one step toward ANY adjacent cell, avoiding the patroller
            mv = spacetime_bfs(cursor, adj, passable, occ, _HORIZON)
            if mv is None or mv == WAIT:
                return None                      # no realizable wait in wa30 → defer
            return SolverStep(_ACT[mv], _expect_changed(f), f"wa30L2 approach {mv}")

        # ----- carrying: deliver to a free drop cell -----
        off = self._item_off
        free_dz = [d for d in dz if d not in items]    # drop cells not yet filled
        if not free_dz:
            free_dz = list(dz)
        # cursor cells that land the item on a drop cell
        goals = [(d[0] - off[0], d[1] - off[1]) for d in free_dz]
        goals = [g for g in goals if in_bounds(g) and in_bounds((g[0] + off[0], g[1] + off[1]))]
        if not goals:
            return None
        others = set(undelivered)

        def passable_c(c):
            ic = (c[0] + off[0], c[1] + off[1])
            return (in_bounds(c) and in_bounds(ic)
                    and c not in others and ic not in others)

        # forbid cursor cells whose carried item would enter a lethal cell, too
        occ_c = [s | {(cc[0] - off[0], cc[1] - off[1]) for cc in s} for s in occ]

        if cursor in set(goals):
            self._carrying = False
            self._item_off = None
            self._target = None
            self._phase = "approach"
            return SolverStep(_PICKDROP, _expect_changed(f), "wa30L2 drop")

        mv = spacetime_bfs(cursor, goals, passable_c, occ_c, _HORIZON)
        if mv is None or mv == WAIT:
            return None
        return SolverStep(_ACT[mv], _expect_changed(f), f"wa30L2 carry {mv}")

    def next_action(self, frame, n_actions):
        f = np.asarray(frame)
        # L2+: a color-12 patroller is present → closed-loop hazard-aware delivery.
        if len(_adv_cells(f)) > 0:
            return self._l2_step(f, n_actions)

        # L1: plan once, replay (byte-identical to the shipped behaviour).
        if self._route is None:
            st = W.detect_state(f)
            if not st:
                return None
            self._route = W.compute_route(st, 1)
            self._i = 0
        if self._i >= len(self._route):
            return None
        a = int(self._route[self._i])
        self._i += 1
        return SolverStep(a, _expect_changed(f), f"wa30[{self._i - 1}]={a}")
