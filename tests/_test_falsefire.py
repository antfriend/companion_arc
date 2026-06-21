import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent))
"""
_test_falsefire.py — HIDDEN-GAME false-fire fuzzer for the dynamics recognizers.

The §6.1 confusion matrix in _test_dynamics.py only covers the 11 KNOWN games, so it
is structurally BLIND to a recognizer firing on a HIDDEN game it has never seen — the
exact failure once seen when ls20 fired on any frame with 1–50 px of colour-12. A false
fire is the only way the additive stack can do WORSE than its own floor: a mis-recognized
dynamic drives bogus directional moves into GAME_OVER on a game the floor would have
played cleanly, costing levels we could otherwise reach.

This harness approximates the hidden distribution with randomized 64×64 decoy frames
(random palette, random small blobs of every colour, random HUD bars) and asserts NO
recognizer fires above RECOG_HI. A missed fire on a real target only forfeits upside
(defers to the floor, no regression); a FALSE fire is the dangerous direction, so we
fuzz hard for it. Run: python _test_falsefire.py [N]
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np

from core.dynamics import library          # noqa: F401 — registers all dynamics
from core.dynamics.registry import DYNAMICS, RECOG_HI, dispatch

H = W = 64                                  # ARC frames are 64×64
_PALETTE = list(range(16))


def _decoy(rs):
    """A random hidden-game-like frame: a background colour + a handful of small
    blobs (1–60 px) of random colours at random positions + an occasional HUD bar."""
    bg = rs.randint(0, 16)
    f = np.full((H, W), bg, dtype=np.int64)
    for _ in range(rs.randint(1, 9)):
        col = rs.choice(_PALETTE)
        h, w = rs.randint(1, 9), rs.randint(1, 9)        # blob up to ~64 px
        r, c = rs.randint(0, H - h), rs.randint(0, W - w)
        f[r:r + h, c:c + w] = col
    if rs.rand() < 0.5:                                  # a thin HUD bar (timer/score)
        col = rs.choice(_PALETTE)
        row = rs.randint(0, H)
        f[row, : rs.randint(2, W)] = col
    return f


def run(n=4000, seed=0):
    rs = np.random.RandomState(seed)
    fires = {d.id: 0 for d in DYNAMICS}
    hijacks = 0                                          # dispatch actually selected one
    for _ in range(n):
        f = _decoy(rs)
        for d in DYNAMICS:
            try:
                if float(d.recognize(f)) >= RECOG_HI:
                    fires[d.id] += 1
            except Exception:
                pass                                     # an exception is a non-fire (safe)
        if dispatch(f, DYNAMICS) is not None:
            hijacks += 1

    print(f"false-fire fuzz — {n} random 64×64 decoy frames (seed {seed}):\n")
    print(f"    {'dynamic':8s} | recognize>=RECOG_HI  (rate)")
    worst = 0
    for did, k in sorted(fires.items(), key=lambda t: -t[1]):
        worst = max(worst, k)
        flag = "  <-- FALSE FIRE" if k else ""
        print(f"    {did:8s} | {k:5d}/{n}  ({k / n:6.3%}){flag}")
    print(f"\n    dispatch hijacked the floor on {hijacks}/{n} decoys "
          f"({hijacks / n:.3%}) — a non-zero rate means we corrupt games we shouldn't touch.")
    clean = (hijacks == 0)
    print("\nverdict:", "CLEAN — no recognizer fires on hidden-like decoys"
          if clean else "FALSE FIRES PRESENT — tighten the flagged recognizers")
    return clean


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    sys.exit(0 if run(n) else 1)
