"""Play each game through ALL its levels with the current detector.

Levels 2-6 are real structurally-different instances of the same mechanic —
the best available proxy for the competition's hidden variants. A detector
that solves only level 1 is fit to one instance; one that solves all its
levels is variant-general.

For each level: re-scan the first frame, compute_route, execute, report
WIN/FAIL and the step count. Uses the local arcengine directly (no API).

Usage: python _test_levels.py [game ...] [--max-steps N] [--verbose]
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

VERBOSE = "--verbose" in sys.argv
sys.argv = [a for a in sys.argv if a != "--verbose"]
MAX_STEPS = 300
if "--max-steps" in sys.argv:
    i = sys.argv.index("--max-steps")
    MAX_STEPS = int(sys.argv[i + 1])
    del sys.argv[i:i + 2]

ACTIONS = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3,
           GameAction.ACTION4, GameAction.ACTION5, GameAction.ACTION6]

_END_WIN = ("GameState.WIN", "win")
_END_LOSE = ("GameState.GAME_OVER", "game_over")


def load_game(game: str):
    inst_dir = next((ENV_DIR / game).iterdir())
    py = inst_dir / f"{game}.py"
    spec = importlib.util.spec_from_file_location(f"lvl_{game}_{id(py)}", py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for v in vars(mod).values():
        if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame:
            return v, mod
    raise RuntimeError(f"no game class in {game}")


def num_levels(mod) -> int:
    return len(mod.levels)


def play_all_levels(game: str, max_steps: int = MAX_STEPS):
    """Test each level in ISOLATION: jump to level n, render its clean initial
    frame, detect+route+execute. Decouples detector generality from
    level-transition framework quirks (which affect all games equally)."""
    cls, mod = load_game(game)
    detector = get_detector(game)
    n_levels = num_levels(mod)
    results = []

    for idx in range(n_levels):
        level_num = idx + 1
        g = cls()
        g.set_level(idx)
        avail = list(getattr(g, "_available_actions", [1, 2, 3, 4, 5]))
        score0 = g._score

        frame = np.asarray(g.camera.render(g.current_level.get_sprites()))
        route = []
        if detector is not None:
            try:
                state = detector.detect_state(frame)
                route = list(detector.compute_route(state, level_num) or [])
            except Exception as exc:
                results.append((level_num, f"detector-error:{type(exc).__name__}:{exc}", 0))
                continue
        if not route:
            results.append((level_num, "no-route", 0))
            continue

        lvl_steps = 0
        won = False
        for a in route:
            obs = g.perform_action(ActionInput(id=ACTIONS[a % len(avail)]), raw=True)
            lvl_steps += 1
            if obs.levels_completed > score0 or str(obs.state) in _END_WIN:
                won = True
                break
            if str(obs.state) in _END_LOSE:
                break
            if lvl_steps >= max_steps:
                break
        results.append((level_num, "WIN" if won else "FAIL", lvl_steps))

    return n_levels, results


def main():
    games = sys.argv[1:] or [
        "ls20", "cd82", "sp80", "re86", "tu93", "wa30",
        "ar25", "g50t", "sk48", "cn04", "ka59",
    ]
    print(f"{'game':6s} {'levels':>6s}  per-level result")
    for game in games:
        try:
            n, results = play_all_levels(game)
        except Exception as exc:
            print(f"{game:6s} ERROR: {exc}")
            continue
        cells = []
        wins = 0
        for lvl, status, steps in results:
            if status == "WIN":
                cells.append(f"L{lvl}:WIN({steps})")
                wins += 1
            else:
                cells.append(f"L{lvl}:{status}")
        print(f"{game:6s} {wins}/{n:>4d}  " + "  ".join(cells))


if __name__ == "__main__":
    main()
