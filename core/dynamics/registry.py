"""
core/dynamics/registry.py — recognition dispatcher (ARC-RFC-0001 §4).

Precision is enforced HERE, not inside the solvers: a dynamic only takes control
when its recognition is both confident (>= RECOG_HI) AND uniquely the best
(margin >= RECOG_MARGIN over the runner-up). Unknown OR ambiguous → None → the
explorer floor keeps control. This is the gate that bounds the one deliberate
relaxation of the additive-only law (ARC-RFC-0001 §7).
"""

from typing import List, Optional

import numpy as np

from core.dynamics.base import Dynamic

# Tunable gates — calibrated against the recognizer confusion matrix
# (_test_dynamics.py §1). Conservative defaults: high bar, clear margin.
RECOG_HI = 0.75
RECOG_MARGIN = 0.25

# Populated by games/<id>/dynamic.py at import (via register), or injected
# explicitly into SupervisedAgent for tests.
DYNAMICS: List[Dynamic] = []


def register(d: Dynamic) -> None:
    DYNAMICS.append(d)


def dispatch(frame: np.ndarray, dynamics: Optional[List[Dynamic]] = None) -> Optional[Dynamic]:
    """Return the uniquely-confident dynamic for this frame, or None."""
    pool = DYNAMICS if dynamics is None else dynamics
    if not pool:
        return None
    scored = sorted(((d, float(d.recognize(frame))) for d in pool),
                    key=lambda t: -t[1])
    top, c0 = scored[0]
    c1 = scored[1][1] if len(scored) > 1 else 0.0
    if c0 >= RECOG_HI and (c0 - c1) >= RECOG_MARGIN:
        return top
    return None
