"""
games/wa30/dynamic.py — wa30 as a Dynamic (ARC-RFC-0001 §3, fourth port).

wa30 = pick-up-and-deliver. A 4×4 cursor (color-0 direction edge + color-14 body)
picks up color-4 items and carries them to a color-2 drop zone (ACTION5 =
pickup/drop). Multi-phase (approach → face → pickup → carry → drop).

L1 (no adversary): PLAN ONCE per level — the detector's adaptive multi-item BFS
route (frame-derived, translation-robust), replayed one action at a time, each
guarded by a "board changed" expectation. A no-op step means the plan desynced and
the supervisor aborts back to the explorer.

L2+ (a color-12 sprite appears): the color-12 sprite `kdweefinfi` is NOT a lethal
hazard — it is a DELIVERY HELPER that autonomously carries items into the drop zone
(source: ynmgxjqkgh/cyjrduhzmz; it delivers ~4/5 on its own). The cursor never dies
on contact; the ONLY failure is the step TIMER (StepCounter=70 on L2). So L2 is a
COOPERATIVE delivery, not an evasion problem (the earlier hazard-nav evasion branch
solved a non-existent threat and could not win). The cursor delivers the items the
helper is slowest to reach (FARTHEST-from-helper first → least competition) while it
delivers the rest; together they finish 5/5 inside the timer. Each frame:
  * read cursor / items / drop-zone slots / helper from the frame,
  * track filled slots by scanning color-4 within the latched drop-zone footprint
    (the detector's dz_valid is a bbox fill that mis-reads delivered slots as empty),
  * fetch the farthest-from-helper undelivered item (committed approach→face→pickup,
    never re-targeting mid-pickup — a one-frame dropout flickers the item out),
  * deliver to the nearest REACHABLE free slot, routing the rigid cursor+item body
    around other items and the moving helper.
Carry-state can't be read cleanly (a carried item still shows as a loose color-4) so
it is latched. Anything uncertain → return None → defer to the floor (additive-safe).
"""

from collections import deque

import numpy as np

from core.dynamics.base import Dynamic, SolverStep
from games.wa30 import detector as W

STEP = 4
_LO, _HI = 0, 15                       # 64/STEP = 16 cells per axis (0..15)
# (dx, dy) cell move → wa30 action index (0=UP,1=DOWN,2=LEFT,3=RIGHT)
_ACT = {(0, -1): 0, (0, 1): 1, (-1, 0): 2, (1, 0): 3}
_DIRS = [(0, -1), (0, 1), (-1, 0), (1, 0)]
_PICKDROP = 4


def _expect_changed(cur):
    b = cur.tobytes()
    return lambda f: np.asarray(f).tobytes() != b


def _in_bounds(c):
    return _LO <= c[0] <= _HI and _LO <= c[1] <= _HI


def _adv_cells(frame):
    """Color-12 sprite centroid(s) → (x, y) cell coords. Returns [] if none.

    On L2+ this is the kdweefinfi delivery HELPER (one compact 4×4 sprite); its mere
    presence is the L2 trigger. Centroid clustering tolerates the helper carrying an
    item (the color-12 body stays a single component)."""
    pos = np.argwhere(np.asarray(frame) == 12)
    if len(pos) == 0:
        return []
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
        out.append((int(round(mc)) // STEP, int(round(mr)) // STEP))
    return out


def _item_cells(frame, cursor_game):
    """EVERY color-4 item cell (delivered + undelivered + carried), snapped to the
    cursor's STEP lattice. The detector's `items` excludes drop-zone-bbox cells, so
    delivered items vanish from it — we re-scan to track which slots are filled."""
    f = np.asarray(frame)[:63, :]
    px, py = cursor_game[0] % STEP, cursor_game[1] % STEP
    out = set()
    for r, c in np.argwhere(f == 4):
        out.add(((int(c) - px) // STEP, (int(r) - py) // STEP))
    return out


def _bfs(start, goals, passable):
    """First move (dx,dy) on a shortest path from start to any goal cell, or None."""
    goals = set(goals)
    if not goals or start in goals:
        return None
    q = deque([(start, None)]); seen = {start}
    while q:
        cell, first = q.popleft()
        for dx, dy in _DIRS:
            nc = (cell[0] + dx, cell[1] + dy)
            fm = first if first is not None else (dx, dy)
            if nc in goals:
                return fm
            if nc not in seen and passable(nc):
                seen.add(nc); q.append((nc, fm))
    return None


class Wa30Dynamic(Dynamic):
    id = "wa30"

    def reset(self) -> None:
        self._route = None          # L1 plan-once route
        self._i = 0
        # L2 cooperative-delivery state
        self._carry = False
        self._off = None            # (dx,dy) cell offset of carried item
        self._phase = "approach"    # approach | face | pickup | carry
        self._target = None         # current undelivered item being fetched
        self._footprint = None      # latched set of drop-zone slot cells (all 6, empty)

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

    # ----- L2 cooperative delivery ------------------------------------------
    def _l2_step(self, f, n_actions):
        st = W.detect_state(f)
        if not st:
            return None
        cur = (st["cursor_x"] // STEP, st["cursor_y"] // STEP)
        dzbb = {(x // STEP, y // STEP) for (x, y) in st["dz_valid"]}
        if self._footprint is None and len(dzbb) >= 5:
            self._footprint = set(dzbb)                 # latch all slots while empty
        fp = self._footprint or dzbb
        if not fp:
            return None
        all4 = _item_cells(f, (st["cursor_x"], st["cursor_y"]))
        helper = set(_adv_cells(f))
        carried = (cur[0] + self._off[0], cur[1] + self._off[1]) if (self._carry and self._off) else None
        items = {it for it in all4 if it != carried}
        undelivered = [it for it in items if it not in fp]
        free = [s for s in fp if s not in items]

        if self._carry:
            return self._deliver(f, cur, items, helper, free)

        # (re)select a target ONLY while approaching — committing protects the pickup
        # from a one-frame detector dropout that flickers the item out of `undelivered`.
        if self._phase == "approach" and (self._target is None or self._target not in undelivered):
            if not undelivered:
                return None                             # nothing left for us → defer
            hc = next(iter(helper)) if helper else cur
            self._target = max(undelivered, key=lambda it: abs(it[0] - hc[0]) + abs(it[1] - hc[1]))
        if self._target is None:
            return None
        return self._fetch(f, cur, items, helper)

    def _fetch(self, f, cur, items, helper):
        t = self._target
        if self._phase == "pickup":
            self._carry = True
            self._off = (t[0] - cur[0], t[1] - cur[1])
            self._phase = "carry"
            return SolverStep(_PICKDROP, _expect_changed(f), "wa30L2 pickup")
        if self._phase == "face" or abs(t[0] - cur[0]) + abs(t[1] - cur[1]) == 1:
            self._phase = "pickup"
            fdx = max(-1, min(1, t[0] - cur[0])); fdy = max(-1, min(1, t[1] - cur[1]))
            return SolverStep(_ACT.get((fdx, fdy), _PICKDROP), lambda ff: True, "wa30L2 face")
        obst = (items - {t}) | helper
        adj = [(t[0] + dx, t[1] + dy) for dx, dy in _DIRS
               if _in_bounds((t[0] + dx, t[1] + dy)) and (t[0] + dx, t[1] + dy) not in (items - {t})]
        mv = _bfs(cur, adj, lambda c: _in_bounds(c) and c not in obst)
        if mv not in _ACT:
            return None
        return SolverStep(_ACT[mv], _expect_changed(f), f"wa30L2 approach {mv}")

    def _deliver(self, f, cur, items, helper, free):
        off = self._off
        obst = items | helper
        goals = [(s[0] - off[0], s[1] - off[1]) for s in free]
        goals = [g for g in goals if _in_bounds(g) and _in_bounds((g[0] + off[0], g[1] + off[1]))
                 and (g[0] + off[0], g[1] + off[1]) not in obst]
        if cur in set(goals):
            self._carry = False; self._off = None
            self._target = None; self._phase = "approach"
            return SolverStep(_PICKDROP, _expect_changed(f), "wa30L2 drop")

        def passable_c(c):
            ic = (c[0] + off[0], c[1] + off[1])
            return _in_bounds(c) and _in_bounds(ic) and c not in obst and ic not in obst
        mv = _bfs(cur, goals, passable_c)
        if mv not in _ACT:
            return None
        return SolverStep(_ACT[mv], _expect_changed(f), f"wa30L2 carry {mv}")

    def next_action(self, frame, n_actions):
        f = np.asarray(frame)
        # L2+: a color-12 helper is present → cooperative delivery.
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
