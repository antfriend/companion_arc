"""
core/dynamics/base.py — the Dynamic protocol (ARC-RFC-0001 §3).

A Dynamic is the unit of recognized game knowledge: a structural RECOGNIZER, a
per-frame RE-DERIVATION solver, and a forward CONSISTENCY predicate. This is the
disciplined replacement for games/<id>/detector.py's fixed-route style: the
solver emits ONE action at a time, re-derived from the CURRENT frame, plus an
expectation of what the next frame must look like — so the supervisor
(core/solve_agent.py) can abort the moment reality diverges from the plan.

Everything is frame-structural (entity colors / counts / bbox relations); NO
canonical coordinates, so a translated/recolored hidden variant still matches.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np


@dataclass
class SolverStep:
    """One re-derived move plus the predicate the resulting frame must satisfy."""
    action: int
    expect: Callable[[np.ndarray], bool] = field(default=lambda f: True)
    note: str = ""


class Dynamic:
    """Base class. Subclasses live in games/<id>/dynamic.py and override all three."""

    id: str = "base"

    def recognize(self, frame: np.ndarray) -> float:
        """Confidence in [0,1] that this frame is an instance of my dynamic.
        PRECISION-first: return high only on an unambiguous structural match."""
        return 0.0

    def reset(self) -> None:
        """Clear per-level solver memory (called on every level start)."""
        pass

    def next_action(self, frame: np.ndarray, n_actions: int) -> Optional[SolverStep]:
        """Re-derive the next move from THIS frame. Return a SolverStep, or None
        if the dynamic cannot produce a confident next step right now (the
        supervisor then defers to the explorer for this step)."""
        return None
