"""Manually drive tu93 L2 with a fixed action list (after auto-clearing L1 via the
BFS dynamic) to learn the turret's temporal behaviour: does triggering it and
dodging perpendicular leave the corridor permanently clear?"""
import importlib.util, io, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction
from core.solve_agent import SupervisedAgent
from games.tu93.dynamic import Tu93Dynamic
from games.tu93 import detector as D

ACT = {0: GameAction.ACTION1, 1: GameAction.ACTION2, 2: GameAction.ACTION3, 3: GameAction.ACTION4}
NAME = {0: "UP", 1: "DOWN", 2: "LEFT", 3: "RIGHT"}
END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")
ENV = Path(__file__).parent / "environment_files"

def load(game="tu93"):
    inst = next((ENV / game).iterdir())
    spec = importlib.util.spec_from_file_location("s_" + game, inst / f"{game}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values() if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)

def snap(f):
    f = np.asarray(f)
    st = D.detect_state(f)
    t8 = np.argwhere(f == 8); t15 = np.argwhere(f == 15); t11 = np.argwhere(f == 11)
    tinfo = ""
    if len(t8):
        tinfo += f" T8@r{t8[:,0].min()}-{t8[:,0].max()},c{t8[:,1].min()}-{t8[:,1].max()}"
    if len(t15): tinfo += f" mark15@{tuple(t15[0])}"
    if len(t11): tinfo += f" ARMED11@{tuple(t11[0])}"
    return f"cur={st.cursor_pixel} cell={st.cursor_cell} route={st.route[:8]}{tinfo}"

# manual L2 plan passed on argv as e.g. "0 3 3 3 1 1 1 1 0 3 3 3 1 0"
plan = [int(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else [0,3,3,3]

g = load()()
obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
agent = SupervisedAgent(4, seed=0, dynamics=[Tu93Dynamic()])
prev = 0
# auto-clear L1
for _ in range(60):
    if obs is None or str(obs.state) in END or not obs.frame: break
    f = np.asarray(obs.frame[-1])
    a = agent.choose(f) % 4
    obs = g.perform_action(ACT[a] and ActionInput(id=ACT[a]), raw=True)
    if obs and (obs.levels_completed or 0) > prev:
        prev = obs.levels_completed
        print(f"L1 done. L2 start: {snap(obs.frame[-1])}")
        break

# now run the manual plan on L2
for i, a in enumerate(plan):
    if obs is None or str(obs.state) in END or not obs.frame:
        print(f"[end at plan idx {i}] state={str(obs.state) if obs else None}")
        break
    obs = g.perform_action(ActionInput(id=ACT[a]), raw=True)
    s = snap(obs.frame[-1]) if (obs and obs.frame) else "no-frame"
    st = str(obs.state) if obs else None
    print(f"  [{i:2d}] {NAME[a]:5s} lvl={obs.levels_completed if obs else '?'} {st:20s} | {s}")
print(f"FINAL state={str(obs.state) if obs else None} levels={obs.levels_completed if obs else '?'}")
