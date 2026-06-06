"""
core/game_registry.py — Maps game_id prefix → detector module + companion path.

Adding a new game:
  1. Create games/<id>/detector.py implementing the standard interface
  2. Create games/<id>/companion.md
  3. Add a register() call at the bottom of this file

Standard detector interface (each games/<id>/detector.py must export):
  detect_state(grid)                   → GameState
  compute_route(state)                 → list[int]
  verify_step(before, after, action)   → StepResult
  format_companion_block(state, route) → str
"""

from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).parent.parent
_REGISTRY: dict = {}


def register(game_prefix: str, detector_module, companion_path: Path) -> None:
    _REGISTRY[game_prefix] = {
        "detector": detector_module,
        "companion_path": companion_path,
    }


def _prefix(game_id: str) -> str:
    return game_id.split("-")[0] if "-" in game_id else game_id


def get_detector(game_id: str):
    """Return the detector module for game_id, or None if not registered."""
    return _REGISTRY.get(_prefix(game_id), {}).get("detector")


def get_companion_path(game_id: str) -> Path:
    """Return per-game companion path, falling back to the global file."""
    entry = _REGISTRY.get(_prefix(game_id))
    if entry:
        return entry["companion_path"]
    return _ROOT / "companion_arcprize.md"


# ---------------------------------------------------------------------------
# Auto-register known games
# ---------------------------------------------------------------------------

try:
    from games.ls20 import detector as _ls20
    register("ls20", _ls20, _ROOT / "games" / "ls20" / "companion.md")
except ImportError:
    pass

try:
    from games.sp80 import detector as _sp80
    register("sp80", _sp80, _ROOT / "games" / "sp80" / "companion.md")
except ImportError:
    pass
