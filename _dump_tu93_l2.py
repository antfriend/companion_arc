"""Dump the tu93 L2 maze as a logical grid with cursor/exit/turret marked, so we
can see whether a turret-safe BFS path to the exit exists."""
import importlib.util, io, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction
from core.solve_agent import SupervisedAgent
from games.tu93.dynamic import Tu93Dynamic
from games.tu93 import detector as D

ACT = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3, GameAction.ACTION4]
END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")
ENV = Path(__file__).parent / "environment_files"

def load(game="tu93"):
    inst = next((ENV / game).iterdir())
    spec = importlib.util.spec_from_file_location("d_" + game, inst / f"{game}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values() if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)

g = load()()
obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
n = 4
agent = SupervisedAgent(n, seed=0, dynamics=[Tu93Dynamic()])
prev = 0
for step in range(300):
    if obs is None or str(obs.state) in END or not obs.frame:
        break
    full = np.asarray(obs.frame[-1])
    a = agent.choose(full) % n
    obs = g.perform_action(ActionInput(id=ACT[a]), raw=True)
    if obs and (obs.levels_completed or 0) > prev:
        prev = obs.levels_completed
        agent.reset_level(level=prev + 1)
        f = np.asarray(obs.frame[-1])
        print("=== L2 START FRAME (raw colors, 64x64) ===")
        # crop to the active region
        nz = np.argwhere(f != f[0, 0])
        r0, c0 = nz[:, 0].min(), nz[:, 1].min()
        r1, c1 = nz[:, 0].max(), nz[:, 1].max()
        st = D.detect_state(f)
        print(f"cursor_pixel={st.cursor_pixel} cursor_cell={st.cursor_cell} target_pixel={st.target_pixel} target_cell={st.target_cell}")
        print(f"route={st.route}")
        print(f"crop rows {r0}-{r1} cols {c0}-{c1}")
        # print the grid using single chars
        charmap = {2: '.', 4: 'C', 9: 'c', 14: 'E', 8: 'T', 15: '*', 11: '!', 12: 'U', 13: 'V', 6: '_'}
        for r in range(r0, r1 + 1):
            row = ""
            for c in range(c0, c1 + 1):
                v = int(f[r, c])
                row += charmap.get(v, ' ' if v == int(f[0,0]) else str(v % 10))
            print(f"{r:2d} {row}")
        break
