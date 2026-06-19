"""Prove wa30 L2 is winnable by COOPERATION (no evasion): the cursor greedily
delivers items in parallel with the kdweefinfi HELPER (which delivers ~4/5 on its
own). Plain BFS pickup-and-deliver, treating the helper as a non-lethal mover.
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
_ACT = {(0, -1): 0, (0, 1): 1, (-1, 0): 2, (1, 0): 3}   # (dx,dy) cell -> action
_DIRS = [(0, -1), (0, 1), (-1, 0), (1, 0)]


def load(game="wa30"):
    inst = next((ENV / game).iterdir())
    spec = importlib.util.spec_from_file_location("c_" + game, inst / f"{game}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values()
               if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def bfs(start, goals, passable):
    """First move (dx,dy) on a shortest path from start to any goal cell."""
    goals = set(goals)
    if start in goals:
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


def helper_cells(frame):
    """Color-12 helper sprite centroid(s) → cell (x,y)."""
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


def main():
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
            prev = obs.levels_completed
            break

    carrying = False; item_off = None; phase = "approach"; target = None
    cursor_drops = 0; MAX_CURSOR_DROPS = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    drops = getattr(g, "wyzquhjerd", set())
    print(f"=== L2 START === drop_slots={len(drops)} timer={g.kuncbnslnm.current_steps}")
    for s in range(75):
        if obs is None or str(obs.state) in END or not obs.frame:
            print(f"[end] state={str(obs.state) if obs else None} step={s}"); break
        f = np.asarray(obs.frame[-1])
        st = W.detect_state(f)
        if not st:
            obs = g.perform_action(ActionInput(id=ACT[4]), raw=True); continue
        cursor = (st["cursor_x"] // STEP, st["cursor_y"] // STEP)
        dz = {(x // STEP, y // STEP) for (x, y) in st["dz_valid"]}
        items = [(x // STEP, y // STEP) for (x, y) in st["items"]]
        helpers = helper_cells(f)
        carried = (cursor[0] + item_off[0], cursor[1] + item_off[1]) if (carrying and item_off) else None
        if carried:
            items = [it for it in items if it != carried]
        undelivered = [it for it in items if it not in dz]

        def in_b(c):
            return LO <= c[0] <= HI and LO <= c[1] <= HI

        a = 4  # default no-op
        if cursor_drops >= MAX_CURSOR_DROPS and not carrying:
            a = 4  # done our share — idle, let the helper finish into the open dz
        elif not carrying:
            if undelivered:
                if phase == "approach" and target not in undelivered:
                    target = min(undelivered, key=lambda it: abs(it[0]-cursor[0])+abs(it[1]-cursor[1]))
                if target is None or target not in undelivered:
                    target = min(undelivered, key=lambda it: abs(it[0]-cursor[0])+abs(it[1]-cursor[1]))
                # obstacles: every OTHER item + the moving helper (helper isn't lethal,
                # but the cursor can't move into an occupied cell → it would no-op/stall)
                obst = (set(items) - {target}) | helpers

                def passable(c):
                    return in_b(c) and c not in obst
                adj = [a2 for a2 in [(target[0]+dx, target[1]+dy) for dx, dy in _DIRS]
                       if in_b(a2) and a2 not in (set(items) - {target})]
                if cursor in adj or phase in ("face", "pickup"):
                    if phase != "pickup":
                        phase = "pickup"
                        fdx = max(-1, min(1, target[0]-cursor[0])); fdy = max(-1, min(1, target[1]-cursor[1]))
                        a = _ACT[(fdx, fdy)]
                    else:
                        carrying = True; item_off = (target[0]-cursor[0], target[1]-cursor[1]); phase = "carry"
                        a = 4
                elif adj:
                    mv = bfs(cursor, adj, passable)
                    a = _ACT[mv] if mv else 4
        else:
            off = item_off
            free = [d for d in dz if d not in items] or list(dz)
            goals = [(d[0]-off[0], d[1]-off[1]) for d in free]
            goals = [gg for gg in goals if in_b(gg) and in_b((gg[0]+off[0], gg[1]+off[1]))]
            # rigid cursor+item body: both cells must avoid every other item + helper
            obst = set(items) | helpers

            def passable_c(c):
                ic = (c[0]+off[0], c[1]+off[1])
                return in_b(c) and in_b(ic) and c not in obst and ic not in obst
            if cursor in set(goals):
                carrying = False; item_off = None; target = None; phase = "approach"; a = 4
                cursor_drops += 1
            else:
                mv = bfs(cursor, goals, passable_c)
                a = _ACT[mv] if mv else 4
                if s >= 54 and s <= 57:
                    print(f"    DBG s={s} cursor={cursor} off={off} carried={carried} "
                          f"dz={sorted(dz)} items={sorted(items)} free={sorted(free)} "
                          f"goals={sorted(goals)} helper={helpers} mv={mv} "
                          f"reach_goal={[gg for gg in goals if passable_c(gg)]}")

        obs = g.perform_action(ActionInput(id=ACT[a]), raw=True)
        nd = len([it for it in g.current_level.get_sprites_by_tag("geezpjgiyd")
                  if (it.x, it.y) in getattr(g, "wyzquhjerd", set()) and it not in getattr(g, "zmqreragji", {})])
        lvl = (obs.levels_completed or 0) if obs else prev
        print(f"  [{s:2d}] a={a} carry={int(carrying)} delivered={nd}/5 cursor={cursor} timer={g.kuncbnslnm.current_steps} state={str(obs.state) if obs else None}")
        if lvl > prev:
            print(f"\n*** L2 WON at step {s} (timer {g.kuncbnslnm.current_steps}) ***"); return
    print(f"\nfinal: state={str(obs.state) if obs else None}")


if __name__ == "__main__":
    main()
