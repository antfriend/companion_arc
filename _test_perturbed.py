"""Hidden-set simulation: replay each solved game under whole-scene translation.

The 2026-06-02 competition observation showed instance layouts shifted by
whole cells (ls20 block start (45,34)/(45,39)/(45,29)). This harness applies
the same class of perturbation locally: translate every sprite in every level
by (dx, dy) grid cells, then run the competition play pattern (burn ACTION1,
detect from frame, execute route) and report WIN/FAIL per game per delta.

Games that pass only at (0,0) are canonical-coordinate-dependent and will
score zero on the competition's hidden game set.

Usage: python _test_perturbed.py [game ...]
"""
import importlib.util
import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path

import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction

from core.game_registry import get_detector

ROOT = Path(__file__).parent
ENV_DIR = ROOT / "environment_files"

# Hardcoded routes mirror launch_competition._HARDCODED_ROUTES for games whose
# detectors return empty routes (sp80 env files are not present locally).
from launch_competition import _HARDCODED_ROUTES

ACTIONS = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3,
           GameAction.ACTION4, GameAction.ACTION5]

DELTAS = [(0, 0), (2, 1), (-1, 2), (3, -1), (-2, -2)]

# Entity mode: translate only "small" sprites (entities), leave walls/scene.
# Mirrors the observed hidden-set variation (ls20 block start moved; maze didn't).
ENTITY_MODE = "--entities" in sys.argv


def load_game_module(game: str):
    inst_dir = next((ENV_DIR / game).iterdir())
    py = inst_dir / f"{game}.py"
    spec = importlib.util.spec_from_file_location(f"perturb_{game}_{id(py)}", py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def translate_levels(mod, dx: int, dy: int) -> bool:
    """Shift every sprite in every level by (dx, dy).

    Some level definitions intentionally place sprites overhanging the grid;
    only sprites that start fully in bounds must remain in bounds.
    """
    if (dx, dy) == (0, 0):
        return True
    level = mod.levels[0]   # we play level 1 only
    gw, gh = level.grid_size if level.grid_size else (64, 64)

    def movable(s) -> bool:
        if not ENTITY_MODE:
            return True
        return s.width <= gw // 3 and s.height <= gh // 3

    targets = [s for s in level.get_sprites() if movable(s)]
    if ENTITY_MODE and not targets:
        return False
    for s in targets:
        in_bounds = s.x >= 0 and s.y >= 0 and s.x + s.width <= gw and s.y + s.height <= gh
        if not in_bounds:
            continue
        nx, ny = s.x + dx, s.y + dy
        if nx < 0 or ny < 0 or nx + s.width > gw or ny + s.height > gh:
            return False
    for s in targets:
        s.set_position(s.x + dx, s.y + dy)
    return True


def game_class(mod):
    for v in vars(mod).values():
        if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame:
            return v
    raise RuntimeError("no game class")


def play(game: str, mod, max_steps: int = 250) -> tuple:
    g = game_class(mod)()
    fd = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    detector = get_detector(game)

    obs = g.perform_action(ActionInput(id=GameAction.ACTION1), raw=True)  # burn
    steps = 1
    frame = np.asarray(obs.frame[0]) if obs.frame else None

    route = []
    if detector is not None and frame is not None:
        try:
            state = detector.detect_state(frame)
            route = list(detector.compute_route(state, 1) or [])
        except Exception as exc:
            return False, steps, f"detector error: {exc}"
    if not route:
        route = list(_HARDCODED_ROUTES.get(game, []))
    if not route:
        return False, steps, "no route"

    for a in route:
        obs = g.perform_action(ActionInput(id=ACTIONS[a % len(ACTIONS)]), raw=True)
        steps += 1
        if obs.levels_completed >= 1 or str(obs.state) in ("GameState.WIN", "win"):
            return True, steps, "WIN"
        if str(obs.state) in ("GameState.GAME_OVER", "game_over"):
            return False, steps, "GAME_OVER mid-route"
        if steps >= max_steps:
            break
    return False, steps, f"route exhausted (L{obs.levels_completed})"


def main():
    games = sys.argv[1:] or ["cn04", "g50t", "sk48", "tu93", "wa30", "ar25", "re86", "ls20", "cd82"]
    print(f"{'game':6s} " + " ".join(f"{str(d):>9s}" for d in DELTAS))
    summary = {}
    for game in games:
        cells = []
        for dx, dy in DELTAS:
            try:
                mod = load_game_module(game)
                if not translate_levels(mod, dx, dy):
                    cells.append("   oob   ")
                    continue
                ok, steps, why = play(game, mod)
                cells.append(f" WIN:{steps:3d} " if ok else f" fail:{steps:3d}")
                if not ok and (dx, dy) == (0, 0):
                    cells[-1] = f" FAIL0:{steps:2d}"
                summary.setdefault(game, []).append(((dx, dy), ok, why))
            except Exception as exc:
                cells.append(" ERR     ")
                summary.setdefault(game, []).append(((dx, dy), False, str(exc)[:60]))
        print(f"{game:6s} " + " ".join(f"{c:>9s}" for c in cells))
    print()
    for game, rows in summary.items():
        fails = [(d, why) for d, ok, why in rows if not ok]
        if fails:
            for d, why in fails:
                print(f"  {game} {d}: {why}")


if __name__ == "__main__":
    main()
