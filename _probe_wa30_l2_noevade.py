"""Run the EXISTING wa30 dynamic on L2 but with evasion DISABLED (empty hazard
occupancy) — turning its proven pickup/carry/drop logic into a pure cooperative
greedy. Tests whether removing the (unnecessary) patroller-evasion lets it win.
"""
import importlib.util, io, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction
import games.wa30.dynamic as WD
from core.solve_agent import SupervisedAgent

# Disable evasion: no cell is ever lethal -> spacetime_bfs == plain BFS, flee never fires.
_orig = WD.predict_occupancy
WD.predict_occupancy = lambda adv, horizon, radius=1, bounds=None: [set() for _ in range(horizon + 1)]

ENV = Path(__file__).parent / "environment_files"
ACT = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3, GameAction.ACTION4, GameAction.ACTION5]
END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")

def load():
    inst = next((ENV / "wa30").iterdir())
    spec = importlib.util.spec_from_file_location("nv_wa30", inst / "wa30.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values() if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)

g = load()()
obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
agent = SupervisedAgent(5, seed=0, dynamics=[WD.Wa30Dynamic()])
prev = 0
for _ in range(400):
    if obs is None or str(obs.state) in END or not obs.frame:
        print("[died before L2]"); sys.exit()
    a = agent.choose(np.asarray(obs.frame[-1])) % 5
    obs = g.perform_action(ActionInput(id=ACT[a]), raw=True)
    if obs and (obs.levels_completed or 0) > prev:
        prev = obs.levels_completed; break
agent.reset_level(level=2)
print(f"=== L2 START timer={g.kuncbnslnm.current_steps} ===")
for s in range(75):
    if obs is None or str(obs.state) in END or not obs.frame:
        print(f"[end] {str(obs.state) if obs else None} step={s}"); break
    a = agent.choose(np.asarray(obs.frame[-1])) % 5
    obs = g.perform_action(ActionInput(id=ACT[a]), raw=True)
    nd = len([it for it in g.current_level.get_sprites_by_tag("geezpjgiyd")
              if (it.x, it.y) in getattr(g, "wyzquhjerd", set()) and it not in getattr(g, "zmqreragji", {})])
    lvl = (obs.levels_completed or 0) if obs else prev
    if lvl > prev:
        print(f"  [{s:2d}] delivered={nd}/5 timer={g.kuncbnslnm.current_steps}  *** L2 WON ***"); sys.exit()
print(f"final delivered={nd}/5 timer={g.kuncbnslnm.current_steps} state={str(obs.state) if obs else None}")
