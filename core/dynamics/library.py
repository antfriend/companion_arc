"""
core/dynamics/library.py — register all validated dynamics (ARC-RFC-0001 §8).

Importing this module populates the global DYNAMICS registry used by
SupervisedAgent (LOCUS_MODE=solve). Add a dynamic here ONLY after it passes the
de-risk tests in _test_dynamics.py (recognizer precision, within-dynamic
win-rate, abort safety) — precision is the additive-safety margin.

Validated so far:
  sp80  — de-risk 2026-06-16: precision 12/12 own & 0/12 on all 10 others;
          supervised 12/12 vs goal 3/12; no off-target regression.
"""

from core.dynamics.registry import register
from games.sp80.dynamic import Sp80Dynamic

register(Sp80Dynamic())
