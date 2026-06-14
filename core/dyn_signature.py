"""
core/dyn_signature.py — board signature with an adaptive volatile-cell mask.

Discovered 2026-06-14: board_signature() (general_agent v1) strips only the
outer UI border. But some games render HUD elements INSIDE the play area — cn04
has an action-budget bar at row 4 that depletes on every action (144 cells flip
per step); sk48 has an animated band at row 23. These make every frame look
novel, which silently defeats count-based exploration: no-op detection fails,
no state is ever "revisited", the click stall-gate never triggers. On those
games v1 degrades to pure random.

Fix: learn which cells are VOLATILE (change on nearly every step regardless of
the action) and exclude them from the signature, keeping the real game state.
The mask refines online; after a short warmup it is frozen for the level so the
visit/trans tables stay comparable.

Drop-in: DynamicSignature().sig(frame) returns bytes like board_signature, but
call .observe(frame) (or sig(), which observes) every step so it can learn.
"""

import numpy as np

_WARMUP = 6          # steps before the volatile mask is trusted/frozen
_VOL_THRESHOLD = 0.6  # cell counts as volatile if it changes on >60% of steps


def _core(frame: np.ndarray) -> np.ndarray:
    a = np.asarray(frame)
    if a.shape[0] >= 3 and a.shape[1] >= 2:
        return a[1:-1, :-1]
    return a


class DynamicSignature:
    def __init__(self, warmup: int = _WARMUP, vol_threshold: float = _VOL_THRESHOLD):
        self._warmup = warmup
        self._vol = vol_threshold
        self.reset()

    def reset(self) -> None:
        self._prev = None
        self._frames = 0
        self._change = None      # per-cell change counter
        self._mask = None        # frozen volatile mask (bool), once warmed up

    def observe(self, frame: np.ndarray) -> None:
        core = _core(frame)
        if self._change is None or self._change.shape != core.shape:
            self._change = np.zeros(core.shape, dtype=np.int32)
            self._prev = core.copy()
            self._frames = 0
            self._mask = None
            return
        self._change += (core != self._prev)
        self._prev = core.copy()
        self._frames += 1
        if self._mask is None and self._frames >= self._warmup:
            # Freeze the mask: cells that changed on > vol_threshold of steps.
            self._mask = (self._change / max(1, self._frames)) > self._vol

    def sig(self, frame: np.ndarray) -> bytes:
        """Observe this frame, then return its masked signature."""
        self.observe(frame)
        core = _core(frame)
        if self._mask is None:
            return core.tobytes()
        c = core.copy()
        c[self._mask] = 0
        return c.tobytes()

    def peek(self, frame: np.ndarray) -> bytes:
        """Signature without observing (for read-only comparisons)."""
        core = _core(frame)
        if self._mask is None:
            return core.tobytes()
        c = core.copy()
        c[self._mask] = 0
        return c.tobytes()
