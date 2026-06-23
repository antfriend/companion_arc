"""
games/wa30/dynamic.py — wa30 as a Dynamic (ARC-RFC-0001 §3, fourth port).

wa30 = pick-up-and-deliver. A 4×4 cursor (color-0 direction edge + color-14 body)
picks up color-4 items and carries them to a color-2 drop zone (ACTION5 =
pickup/drop). Multi-phase (approach → face → pickup → carry → drop).

PATTERN A — ONE closed-loop cooperative-delivery solver for every level (no level
gate, no fixed route, no plan-replay). Each frame: read cursor / items / drop-zone
slots / helper from the frame; fetch the farthest-from-helper undelivered item
(committed approach→face→pickup); deliver it to the nearest REACHABLE free slot,
routing the rigid cursor+item body around other items and the helper. L1 is the
DEGENERATE case — no helper, so the cursor delivers every item itself. On L2+ the
color-12 sprite `kdweefinfi` is NOT a lethal hazard but a DELIVERY HELPER that
autonomously carries items in (source: ynmgxjqkgh/cyjrduhzmz; ~4/5 on its own); the
cursor never dies on contact, the ONLY failure is the step TIMER (StepCounter=70).
So the cursor takes the items the helper is slowest to reach (farthest-first → least
competition) and together they finish inside the timer.

Three frame-mechanics the per-frame reader must respect (all found by driving the
real engine — see the wa30_* probes):
  * an item's color-4 border RECOLORS to color-3 when the cursor is adjacent (a
    "pickup-ready" highlight), so _item_cells scans {3,4} or a cursor-adjacent item
    silently drops out of detection and the planner routes into it (livelock);
  * the drop zone's color-2 interior SHRINKS as slots fill, so the full slot set is
    LATCHED on first sight (delivered items then read as filled slots = obstacles);
  * detect_state's cursor read is reliable only while NOT carrying (the hidden held
    item shifts it one cell), so the cursor is DEAD-RECKONED during carry — seeded
    from the frame at pickup, advanced by each commanded move. The item is held
    rigidly at the facing offset it was picked up from; DROP detaches it at cursor+off.
Anything uncertain → return None → defer to the floor (additive-safe).
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
    """EVERY item cell (delivered + undelivered + carried), snapped to the cursor's
    STEP lattice. Items have a color-4 border that the engine RECOLORS to color-3
    when the cursor is adjacent (a "pickup-ready" highlight) — so scan {3,4} or a
    cursor-adjacent item silently drops out and the planner routes into it (livelock).
    The detector's `items` also excludes drop-zone-bbox cells, so delivered items
    vanish from it — we re-scan here to track which slots are filled."""
    f = np.asarray(frame)[:63, :]
    px, py = cursor_game[0] % STEP, cursor_game[1] % STEP
    out = set()
    for r, c in np.argwhere((f == 4) | (f == 3)):
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
        # closed-loop cooperative-delivery state (one solver, every level)
        self._carry = False
        self._off = None            # (dx,dy) cell offset of carried item
        self._phase = "approach"    # approach | face | pickup | carry
        self._target = None         # current undelivered item being fetched
        self._footprint = None      # latched set of drop-zone slot cells (all slots, empty)
        self._dr = None             # dead-reckoned cursor cell (trusted during carry)

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

    # ----- unified closed-loop cooperative delivery -------------------------
    def _step(self, f, n_actions):
        st = W.detect_state(f)
        if not st:
            return None
        # detect_state's cursor reading is reliable ONLY while NOT carrying; the hidden
        # held item shifts the read by one cell during carry. So resync a dead-reckoned
        # cursor from the frame whenever not carrying, and trust dead-reckoning (advanced
        # by each commanded carry move) while carrying.
        cur_detect = (st["cursor_x"] // STEP, st["cursor_y"] // STEP)
        if not self._carry or self._dr is None:
            self._dr = cur_detect
        cur = self._dr
        dzbb = {(x // STEP, y // STEP) for (x, y) in st["dz_valid"]}
        # Latch ALL drop-zone slots on first sight, while every slot is still empty.
        # dz_valid is read from color-2 interior, which SHRINKS as slots fill with
        # items — so re-reading it each frame would lose filled slots and corrupt the
        # free/undelivered sets. Latch holds for any level (L1=3 slots, L2=6).
        if self._footprint is None and dzbb:
            self._footprint = set(dzbb)
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
            # The item is held IN FRONT of the cursor — at the facing direction it was
            # picked up from (here cur is adjacent to t, so t-cur is that unit facing).
            # DROP detaches the item at cursor+off, so this offset must be carried
            # through delivery exactly (it rides rigidly during the carry).
            self._off = (t[0] - cur[0], t[1] - cur[1])
            self._phase = "carry"
            return SolverStep(_PICKDROP, _expect_changed(f), "wa30 pickup")
        if self._phase == "face" or abs(t[0] - cur[0]) + abs(t[1] - cur[1]) == 1:
            self._phase = "pickup"
            fdx = max(-1, min(1, t[0] - cur[0])); fdy = max(-1, min(1, t[1] - cur[1]))
            return SolverStep(_ACT.get((fdx, fdy), _PICKDROP), lambda ff: True, "wa30 face")
        obst = (items - {t}) | helper
        adj = [(t[0] + dx, t[1] + dy) for dx, dy in _DIRS
               if _in_bounds((t[0] + dx, t[1] + dy)) and (t[0] + dx, t[1] + dy) not in obst]
        mv = _bfs(cur, adj, lambda c: _in_bounds(c) and c not in obst)
        if mv not in _ACT:
            return None
        return SolverStep(_ACT[mv], _expect_changed(f), f"wa30 approach {mv}")

    def _deliver(self, f, cur, items, helper, free):
        off = self._off
        obst = items | helper
        goals = [(s[0] - off[0], s[1] - off[1]) for s in free]
        # A drop position is only valid if BOTH the cursor cell AND the item-landing
        # cell are free. Checking only the item cell lets the cursor goal coincide with
        # an already-delivered item (a filled slot) → BFS routes into it and bumps.
        goals = [g for g in goals if _in_bounds(g) and _in_bounds((g[0] + off[0], g[1] + off[1]))
                 and g not in obst and (g[0] + off[0], g[1] + off[1]) not in obst]
        if cur in set(goals):
            self._carry = False; self._off = None
            self._target = None; self._phase = "approach"
            return SolverStep(_PICKDROP, _expect_changed(f), "wa30 drop")

        def passable_c(c):
            ic = (c[0] + off[0], c[1] + off[1])
            return _in_bounds(c) and _in_bounds(ic) and c not in obst and ic not in obst
        mv = _bfs(cur, goals, passable_c)
        if mv not in _ACT:
            return None
        self._dr = (cur[0] + mv[0], cur[1] + mv[1])   # advance dead-reckoned cursor
        return SolverStep(_ACT[mv], _expect_changed(f), f"wa30 carry {mv}")

    def next_action(self, frame, n_actions):
        # ONE closed-loop cooperative-delivery solver for every level (Pattern A): read
        # cursor / items / drop-zone slots / helper from the frame, fetch the farthest-
        # from-helper undelivered item, deliver it to the nearest reachable free slot.
        # L1 is the degenerate case with no helper (cursor delivers ALL items); a color-12
        # helper merely shares the load. No level gate, no fixed route, no plan-replay.
        return self._step(np.asarray(frame), n_actions)
