"""Test the wa30 L2 feasibility hypothesis: the kdweefinfi adversary (byigobxzpg,
color-12) is a DELIVERY HELPER (carries items into the drop zone and drops them),
not a lethal hazard, and the only failure is the 70-step TIMER.

We clear L1 with the existing dynamic, then at L2 hold the cursor IDLE and watch,
per step, how many items the HELPER delivers on its own. Reading sprite positions
straight from the game object (not the frame) for ground truth.
"""
import importlib.util, io, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction

from core.solve_agent import SupervisedAgent
from games.wa30.dynamic import Wa30Dynamic
from games.wa30 import detector as D

ENV = Path(__file__).parent / "environment_files"
ACT = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3, GameAction.ACTION4, GameAction.ACTION5]
END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")
ITEM_TAG, HELPER_TAG, DZ_TAG, CURSOR_TAG = "geezpjgiyd", "kdweefinfi", "fsjjayjoeg", "wbmdvjhthc"


def load(game="wa30"):
    inst = next((ENV / game).iterdir())
    spec = importlib.util.spec_from_file_location("h_" + game, inst / f"{game}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values()
               if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def snapshot(g):
    """Return (n_items, n_delivered, helper_pos, helper_carrying, timer, drops)."""
    lvl = g.current_level
    items = lvl.get_sprites_by_tag(ITEM_TAG)
    helpers = lvl.get_sprites_by_tag(HELPER_TAG)
    # drop positions = the game's wyzquhjerd set; carried = zmqreragji keys
    drops = getattr(g, "wyzquhjerd", set())
    carried = set(getattr(g, "zmqreragji", {}).keys())
    delivered = [it for it in items if (it.x, it.y) in drops and it not in carried]
    h = helpers[0] if helpers else None
    h_carry = (h in getattr(g, "nsevyuople", {})) if h else False
    timer = g.kuncbnslnm.current_steps
    return len(items), len(delivered), (h.x, h.y) if h else None, h_carry, timer, len(drops)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "idle"   # idle | dynamic
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
    if prev < 1:
        print("[never cleared L1]"); return

    ni, nd, hp, hc, t0, ndrop = snapshot(g)
    items = g.current_level.get_sprites_by_tag(ITEM_TAG)
    print(f"=== L2 START === items={ni} delivered={nd} drop_slots={ndrop} timer={t0}")
    print(f"item positions: {[(it.x, it.y) for it in items]}")
    print(f"helper@{hp} carrying={hc}")
    print(f"--- stepping ({mode}); cursor IDLE means repeated ACTION5 (no-op unless on item) ---")
    agent.reset_level(level=2)
    for s in range(75):
        if obs is None or str(obs.state) in END or not obs.frame:
            print(f"[end] state={str(obs.state) if obs else None} step={s}"); break
        if mode == "dynamic":
            a = agent.choose(np.asarray(obs.frame[-1])) % 5
        else:
            a = 4   # ACTION5 — idle-ish; ticks timer, lets the helper act
        obs = g.perform_action(ActionInput(id=ACT[a]), raw=True)
        ni, nd, hp, hc, t, _ = snapshot(g)
        lvl = (obs.levels_completed or 0) if obs else prev
        flag = ""
        if lvl > prev:
            flag = " *** L2 CLEARED ***"
        if s < 75:
            print(f"  [{s:2d}] a={a} delivered={nd}/{ni} helper@{hp} carry={int(hc)} timer={t} state={str(obs.state) if obs else None}{flag}")
        if lvl > prev:
            print(f"\nWON at step {s}"); return
    print(f"\nfinal: delivered={nd}/{ni} timer={g.kuncbnslnm.current_steps}")


if __name__ == "__main__":
    main()
