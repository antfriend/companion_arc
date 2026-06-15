"""
core/general_agent_dyn.py — general-v1 explorer with HUD-noise-immune signature.

Identical to general_agent v1 in every respect EXCEPT the board signature: it
uses DynamicSignature (core/dyn_signature.py) instead of the static
board_signature. v1 strips only the outer UI border, so games that render a HUD
element INSIDE the play area (cn04's depleting action-budget bar, sk48's band)
make every frame look novel — defeating no-op/revisit detection and degrading
v1 to random on those games. DynamicSignature learns a per-cell volatility mask
(cells that change on >60% of steps, frozen after a 6-step warmup) and excludes
them, so the signature tracks real game state.

Verified harmless: stable games (cd82/sp80) collapse to one signature exactly as
under v1; moving gameplay (sk48's snake, which occupies *different* cells over
time) is NOT masked. So this is a strict, no-regression upgrade — the next rung
after general-v1's 0.18, and a prerequisite for ClickExplorer's stall-gate.

Leaderboard ladder: detectors 0.08 -> random 0.15 -> general-v1 0.18 -> (this).
"""

import numpy as np

from core.general_agent import GeneralAgent
from core.dyn_signature import DynamicSignature


class GeneralAgentDyn(GeneralAgent):
    def reset_level(self) -> None:
        # Create the per-level dynamic signature BEFORE the parent reset (which
        # is also invoked from __init__) so _sig is always usable.
        self._dynsig = DynamicSignature()
        super().reset_level()

    def _sig(self, frame: np.ndarray) -> bytes:
        return self._dynsig.sig(frame)
