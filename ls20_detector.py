"""
ls20_detector.py — Thin re-export shim.

All logic has moved to games/ls20/detector.py.
This file exists so existing imports keep working unchanged.
"""

from games.ls20.detector import (
    # Constants
    BLOCK,
    WALL,
    FLOOR,
    ENT1,
    TIMER,
    VOID,

    # Data structures
    GameState,
    StepResult,

    # Detection functions
    detect_block,
    detect_entity2_ring,
    detect_cluster,
    detect_entity1_state,

    # Standard interface
    detect_state,
    compute_route,
    verify_step,
    format_companion_block,

    # Legacy entry points
    compute_l1_route,
    format_strategy_block,

    # I/O
    update_strategy_in_file,
    parse_strategy,
)

__all__ = [
    "BLOCK", "WALL", "FLOOR", "ENT1", "TIMER", "VOID",
    "GameState", "StepResult",
    "detect_block", "detect_entity2_ring", "detect_cluster", "detect_entity1_state",
    "detect_state", "compute_route", "verify_step", "format_companion_block",
    "compute_l1_route", "format_strategy_block",
    "update_strategy_in_file", "parse_strategy",
]
