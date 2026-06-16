"""
core/dynamics/library.py — register all validated dynamics (ARC-RFC-0001 §8).

Importing this module populates the global DYNAMICS registry used by
SupervisedAgent (LOCUS_MODE=solve). Add a dynamic here ONLY after it passes the
de-risk tests in _test_dynamics.py (recognizer precision, within-dynamic
win-rate, abort safety) — precision is the additive-safety margin.

Validated so far:
  sp80  — de-risk 2026-06-16: precision 12/12 own & 0/12 on all 10 others;
          supervised 12/12 vs goal 3/12; no off-target regression.
  cd82  — de-risk 2026-06-16: pixel-2-on-basket fingerprint; see _test_dynamics.py.
  tu93  — de-risk 2026-06-16: small 3×3 cursor/exit + color-2 corridor; adaptive BFS.
  wa30  — de-risk 2026-06-16: delivery; plan-once + abortable replay (multi-phase).
  re86  — de-risk 2026-06-16: piece-placement; single color-0 active center; cycle.
  ar25  — de-risk 2026-06-16: reflection; re-derive, solvable-placement gate.
  cn04  — de-risk 2026-06-16: connector match; plan-once rotation×assignment search.
  ls20  — de-risk 2026-06-16: corridor nav; probe + plan-once choreography.
  g50t  — de-risk 2026-06-16: record-replay; robust 3×3 button finder + plan-once.
"""

from core.dynamics.registry import register
from games.sp80.dynamic import Sp80Dynamic
from games.cd82.dynamic import Cd82Dynamic
from games.tu93.dynamic import Tu93Dynamic
from games.wa30.dynamic import Wa30Dynamic
from games.re86.dynamic import Re86Dynamic
from games.ar25.dynamic import Ar25Dynamic
from games.cn04.dynamic import Cn04Dynamic
from games.ls20.dynamic import Ls20Dynamic
from games.g50t.dynamic import G50tDynamic

register(Sp80Dynamic())
register(Cd82Dynamic())
register(Tu93Dynamic())
register(Wa30Dynamic())
register(Re86Dynamic())
register(Ar25Dynamic())
register(Cn04Dynamic())
register(Ls20Dynamic())
register(G50tDynamic())
