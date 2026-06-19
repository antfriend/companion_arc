"""Coordinated cooperative wa30 L2 solver prototype.

The kdweefinfi sprite is a HELPER (delivers ~4/5 alone). The cursor cooperates:
 - targets the undelivered item FARTHEST from the helper (least competition),
 - occupancy-aware BFS approach (avoids items + the moving helper, no stalling),
 - faces + picks up, then delivers to the nearest REACHABLE free drop slot,
 - optional: after `park_after` deliveries, parks at a clear cell out of the
   helper's lane so it stops interfering.

Usage: python _probe_wa30_l2_coop2.py [park_after] [park_x] [park_y]
"""
import importlib.util, io, sys
from collections import deque
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction

from core.solve_agent import SupervisedAgent
from games.wa30.dynamic import Wa30Dynamic
from games.wa30 import detector as W

ENV = Path(__file__).parent / "environment_files"
ACT = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3, GameAction.ACTION4, GameAction.ACTION5]
END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")
STEP = 4
LO, HI = 0, 15
_ACT = {(0, -1): 0, (0, 1): 1, (-1, 0): 2, (1, 0): 3}
_DIRS = [(0, -1), (0, 1), (-1, 0), (1, 0)]


def load():
    inst = next((ENV / "wa30").iterdir())
    spec = importlib.util.spec_from_file_location("c2_wa30", inst / "wa30.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values()
               if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def helper_cells(frame):
    pos = np.argwhere(np.asarray(frame) == 12)
    if not len(pos):
        return set()
    rem = {(int(r), int(c)) for r, c in pos}; out = set()
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
        mr = sum(r for r, _ in cl) / len(cl); mc = sum(c for _, c in cl) / len(cl)
        out.add((int(round(mc)) // STEP, int(round(mr)) // STEP))
    return out


def item_cells(frame, cur_game):
    """ALL color-4 item cells (delivered + undelivered + carried), snapped to the
    cursor's STEP lattice. The detector's `items` excludes drop-zone-bbox cells, so
    delivered items vanish from it — we need every item to track filled slots."""
    f = np.asarray(frame)[:63, :]
    px, py = cur_game[0] % STEP, cur_game[1] % STEP
    out = set()
    for r, c in np.argwhere(f == 4):
        out.add((((int(c) - px) // STEP), ((int(r) - py) // STEP)))
    return out


def in_b(c):
    return LO <= c[0] <= HI and LO <= c[1] <= HI


def bfs(start, goals, passable):
    goals = set(goals)
    if start in goals:
        return "AT"
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


class Coop:
    def __init__(self, park_after, park, debug=False):
        self.carry = False; self.off = None; self.phase = "approach"
        self.target = None; self.drops = 0; self.footprint = None
        self.park_after = park_after; self.park = park; self.debug = debug; self.s = -1

    def act(self, f):
        self.s += 1
        st = W.detect_state(f)
        if not st:
            return 4
        cur = (st["cursor_x"] // STEP, st["cursor_y"] // STEP)
        dzbb = {(x // STEP, y // STEP) for (x, y) in st["dz_valid"]}    # dz bbox cells (== 6 when empty)
        if self.footprint is None and len(dzbb) >= 5:
            self.footprint = set(dzbb)                                  # latch all 6 at empty start
        fp = self.footprint or dzbb
        all4 = item_cells(f, (st["cursor_x"], st["cursor_y"]))          # EVERY color-4 item cell
        helper = helper_cells(f)
        carried = (cur[0] + self.off[0], cur[1] + self.off[1]) if (self.carry and self.off) else None
        items = [it for it in all4 if it != carried]                   # obstacles = all real items
        undelivered = [it for it in items if it not in fp]             # outside the drop zone
        free = [s for s in fp if s not in items]                       # footprint slots with no item

        if self.debug:
            print(f"    dbg s={self.s} cur={cur} carry={int(self.carry)} off={self.off} phase={self.phase} "
                  f"tgt={self.target} undel={sorted(undelivered)} free={sorted(free)} helper={helper}")

        if self.carry:
            return self._deliver(cur, items, helper, free)
        if self.park_after is not None and self.drops >= self.park_after:
            return self._goto(cur, [self.park], set(items), helper)
        # (re)select a target ONLY while approaching — never mid-pickup (a one-frame
        # detector dropout flickers the item out of `undelivered`; committing protects it).
        if self.phase == "approach" and (self.target is None or self.target not in undelivered):
            if not undelivered:
                return 4
            hc = next(iter(helper)) if helper else cur
            self.target = max(undelivered, key=lambda it: abs(it[0]-hc[0])+abs(it[1]-hc[1]))
        if self.target is None:
            return 4
        return self._fetch(cur, items, helper)

    def _fetch(self, cur, items, helper):
        t = self.target
        adj_cell = abs(t[0]-cur[0]) + abs(t[1]-cur[1]) == 1     # cursor adjacent to item?
        if self.phase == "pickup":
            self.carry = True; self.off = (t[0]-cur[0], t[1]-cur[1]); self.phase = "carry"
            return 4
        if self.phase == "face" or adj_cell:
            self.phase = "pickup"
            fdx = max(-1, min(1, t[0]-cur[0])); fdy = max(-1, min(1, t[1]-cur[1]))
            return _ACT.get((fdx, fdy), 4)                       # face the item (blocked move)
        obst = (set(items) - {t}) | helper
        adj = [(t[0]+dx, t[1]+dy) for dx, dy in _DIRS
               if in_b((t[0]+dx, t[1]+dy)) and (t[0]+dx, t[1]+dy) not in (set(items)-{t})]
        mv = bfs(cur, adj, lambda c: in_b(c) and c not in obst)
        return _ACT[mv] if mv in _ACT else 4

    def _deliver(self, cur, items, helper, free):
        off = self.off
        obst = set(items) | helper
        goals = [(s[0]-off[0], s[1]-off[1]) for s in (free or [])]
        goals = [g for g in goals if in_b(g) and in_b((g[0]+off[0], g[1]+off[1]))
                 and (g[0]+off[0], g[1]+off[1]) not in obst]
        if cur in set(goals):
            self.carry = False; self.off = None; self.target = None; self.phase = "approach"
            self.drops += 1
            return 4

        def passable_c(c):
            ic = (c[0]+off[0], c[1]+off[1])
            return in_b(c) and in_b(ic) and c not in obst and ic not in obst
        mv = bfs(cur, goals, passable_c)
        if self.debug and self.s >= 45 and self.s <= 50:
            print(f"      DELIV s={self.s} cur={cur} off={off} free={sorted(free)} "
                  f"goals={sorted(goals)} obst_near={sorted(c for c in obst if abs(c[0]-cur[0])+abs(c[1]-cur[1])<=2)} "
                  f"mv={mv} pass(4,8)={passable_c((4,8))} pass(3,8)={passable_c((3,8))}")
        return _ACT[mv] if mv in _ACT else 4

    def _goto(self, cur, goals, obst, helper, allow_idle=False):
        goals = [g for g in goals if in_b(g)]
        if cur in set(goals):
            return 4
        mv = bfs(cur, goals, lambda c: in_b(c) and c not in (obst | helper))
        return _ACT[mv] if mv in _ACT else 4


def main():
    args = [a for a in sys.argv[1:] if a != "dbg"]
    park_after = int(args[0]) if len(args) > 0 else None
    park = (int(args[1]), int(args[2])) if len(args) > 2 else (1, 2)
    g = load()()
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    agent = SupervisedAgent(5, seed=0, dynamics=[Wa30Dynamic()])
    prev = 0
    for _ in range(400):
        if obs is None or str(obs.state) in END or not obs.frame:
            print("[died before L2]"); return
        a = agent.choose(np.asarray(obs.frame[-1])) % 5
        obs = g.perform_action(ActionInput(id=ACT[a]), raw=True)
        if obs and (obs.levels_completed or 0) > prev:
            prev = obs.levels_completed; break
    coop = Coop(park_after, park, debug=("dbg" in sys.argv))
    last = None
    for s in range(75):
        if obs is None or str(obs.state) in END or not obs.frame:
            print(f"[end] {str(obs.state) if obs else None} step={s}"); break
        a = coop.act(np.asarray(obs.frame[-1]))
        obs = g.perform_action(ActionInput(id=ACT[a]), raw=True)
        nd = len([it for it in g.current_level.get_sprites_by_tag("geezpjgiyd")
                  if (it.x, it.y) in getattr(g, "wyzquhjerd", set()) and it not in getattr(g, "zmqreragji", {})])
        lvl = (obs.levels_completed or 0) if obs else prev
        if lvl > prev:
            print(f"  [{s:2d}] delivered={nd}/5 timer={g.kuncbnslnm.current_steps} cursor_drops={coop.drops}  *** L2 WON ***")
            return
        if "dbg" in sys.argv and s == 45:
            occ = getattr(g, "pkbufziase", set())
            here = [(sp.name, sp.x, sp.y, list(sp.tags)) for sp in g.current_level.get_sprites()
                    if sp.x == 16 and sp.y == 32]
            allit = [(it.x, it.y, (it.x, it.y) in getattr(g, "wyzquhjerd", set()))
                     for it in g.current_level.get_sprites_by_tag("geezpjgiyd")]
            print(f"      WHO@(16,32): {here} | items(x,y,inDZ)={allit}")
        last = (s, a, nd, coop.carry, coop.drops, g.kuncbnslnm.current_steps)
    print(f"final: delivered={last[2]}/5 cursor_drops={last[4]} timer={last[5]} state={str(obs.state) if obs else None}")


if __name__ == "__main__":
    main()
