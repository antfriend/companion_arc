"""Find HOW the block's current appearance (shape/color/rotation) and each target's
required appearance are encoded in the FRAME, by cross-referencing the game object's
sprites (htkmubhry = block appearance preview; srgbthxut[i] = target appearance) with
the rendered pixels. Drives the frame-reader for the dynamic.py port."""
import importlib.util, io, random, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction
from core.solve_agent import SupervisedAgent
from core.dynamics import library  # noqa

ENV = Path(__file__).parent / "environment_files"
ACT = {1: GameAction.ACTION1, 2: GameAction.ACTION2, 3: GameAction.ACTION3, 4: GameAction.ACTION4}
END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")


def load():
    inst = next(d for d in (ENV / "ls20").iterdir() if d.is_dir() and not d.name.startswith("__"))
    spec = importlib.util.spec_from_file_location("ap_ls20", inst / "ls20.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return next(v for v in vars(m).values() if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def to_level(n):
    random.seed(0); np.random.seed(0)
    g = load()(); obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    if n <= 1:
        return g, obs
    ag = SupervisedAgent(4, seed=0); prev = 0
    for _ in range(200):
        if obs is None or str(obs.state) in END or not obs.frame:
            break
        a = ag.choose(np.asarray(obs.frame[-1])) % 4
        obs = g.perform_action(ACT[a + 1], raw=True) if False else g.perform_action(ActionInput(id=ACT[a + 1]), raw=True)
        if obs and (obs.levels_completed or 0) >= n - 1:
            return g, obs
    return g, obs


def sprite_region(f, sp):
    """Crop the frame to a sprite's bbox and show it."""
    x, y = sp.x, sp.y
    h, w = sp.pixels.shape
    sub = f[y:y + h, x:x + w]
    return x, y, h, w, sub


def main():
    level = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    g, obs = to_level(level)
    f = np.asarray(obs.frame[-1])
    print(f"=== L{level} appearance encoding (levels_completed={obs.levels_completed}) ===")
    print(f"block attrs: shape={g.fwckfzsyc} color={g.hiaauhahz} rotation_idx={g.cklxociuu}  "
          f"(rotations={g.dhksvilbb} colors={g.tnkekoeuk})")
    print(f"gudziatsk(mover) pos=({g.gudziatsk.x},{g.gudziatsk.y}) pixels.shape={g.gudziatsk.pixels.shape}")
    for nm, sp in [("htkmubhry(appearance)", g.htkmubhry), ("htkmubhry_2", g.htkmubhry_2)]:
        x, y, h, w, sub = sprite_region(f, sp)
        print(f"\n{nm}: sprite pos=({x},{y}) shape={sp.pixels.shape} rotation={getattr(sp,'rotation',None)}")
        print(f"  sprite.pixels (own):\n{np.array2string(np.asarray(sp.pixels))}")
        print(f"  frame@region:\n{np.array2string(sub)}")
    for i, t in enumerate(g.srgbthxut):
        x, y, h, w, sub = sprite_region(f, t)
        print(f"\ntarget-appearance[{i}] (srgbthxut): pos=({x},{y}) shape={t.pixels.shape} "
              f"rotation={getattr(t,'rotation',None)} REQ shape={g.ldxlnycps[i]} color={g.yjdexjsoa[i]} rot={g.ehwheiwsk[i]}")
        print(f"  frame@region:\n{np.array2string(sub)}")


if __name__ == "__main__":
    main()


def dump_tiles(level):
    g, obs = to_level(level)
    f = np.asarray(obs.frame[-1])
    print(f"\n######## L{level} TILES ########")
    p = g.gudziatsk
    print(f"gudziatsk(mover) pos=({p.x},{p.y}) shape={p.pixels.shape} frame:\n{np.array2string(f[p.y:p.y+p.pixels.shape[0], p.x:p.x+p.pixels.shape[1]])}")
    for tag, nm in [("ttfwljgohq","SHAPE"),("soyhouuebz","COLOR"),("rhsxkxzdjz","ROT/cross"),("npxgalaybz","RING")]:
        for s in g.current_level.get_sprites_by_tag(tag):
            h,w = s.pixels.shape
            print(f"{nm} @({s.x},{s.y}) {s.pixels.shape} frame:\n{np.array2string(f[s.y:s.y+h, s.x:s.x+w])}")
