"""Generalized re86 N-piece solver — validate end-to-end on the real engine.

Detection (shape/color-agnostic):
  - pieces = color blobs (clusters of a non-bg,non-4,non-15 color merged across
    small gaps, e.g. the color-0 active-center hole); a piece is a blob with
    >= _PIECE_MIN pixels.
  - targets = small marker dots (<= _MARK_MAX px) of a piece color, away from
    that color's piece blob.
  - target placement T (new piece center) = the 3px-reachable translation whose
    piece footprint covers ALL of that color's target markers (shape-agnostic).

Control: closed-loop. Each step re-detect the ACTIVE piece (unique color-0
center) + its color, route toward its captured target T (UP/DOWN/LEFT/RIGHT, 3px);
on arrival emit CYCLE (ACTION5); after N pieces placed, stop.
"""
import io
import sys
from collections import deque
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np
import importlib.util
from arcengine import ARCBaseGame, ActionInput, GameAction

ENV = Path(__file__).parent / "environment_files"
UP, DOWN, LEFT, RIGHT, CYCLE = 0, 1, 2, 3, 4
GA = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3,
      GameAction.ACTION4, GameAction.ACTION5]
_STEP = 3
_PIECE_MIN = 18          # a piece blob has at least this many px (markers are tiny)
_MARK_MAX = 4            # a marker cluster is at most this many px
_IGNORE = {4, 15}        # color-4 = excluded border markers; 15 = bottom UI bar


def load(game):
    inst = next((ENV / game).iterdir())
    spec = importlib.util.spec_from_file_location("rs_" + game, inst / f"{game}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values()
               if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def _clusters(mask):
    """8-connected clusters of True cells in a bool mask → list of (r,c) lists."""
    remaining = {(int(r), int(c)) for r, c in np.argwhere(mask)}
    out = []
    while remaining:
        stack = [next(iter(remaining))]
        cl = []
        while stack:
            cur = stack.pop()
            if cur not in remaining:
                continue
            remaining.discard(cur)
            cl.append(cur)
            r, c = cur
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if (r + dr, c + dc) in remaining:
                        stack.append((r + dr, c + dc))
        out.append(cl)
    return out


def detect(frame):
    """Return (pieces, grid). A PIECE is a large connected blob of one color; the
    active piece's color-0 center hole is bridged by including color-0 in the
    connectivity (so a saltire/X whose arms meet only at the 0-center stays ONE
    blob). MARKERS are the small isolated clusters of a piece color (the target
    footprint dots) — kept separate (NOT merged into the piece)."""
    g = np.asarray(frame)
    vals, counts = np.unique(g, return_counts=True)
    bg = int(vals[int(np.argmax(counts))])
    pieces = []
    for v in vals:
        c = int(v)
        if c == bg or c in _IGNORE or c == 0:
            continue
        # connected components over (this color OR the 0-center bridge)
        comps = _clusters((g == c) | (g == 0))
        marks = []
        for comp in comps:
            cpix = [p for p in comp if g[p[0], p[1]] == c]
            if len(cpix) >= _PIECE_MIN:
                rs = [p[0] for p in cpix]; cs = [p[1] for p in cpix]
                pieces.append({"color": c, "bbox": (min(rs), max(rs), min(cs), max(cs)),
                               "pixels": set(cpix), "marks": None})
            elif 1 <= len(cpix) <= _MARK_MAX:
                marks.extend(cpix)
        # attach this color's markers to each piece of that color
        for p in pieces:
            if p["color"] == c and p["marks"] is None:
                p["marks"] = list(marks)
    return pieces, g


def required_disp(pixels, marks):
    """The 3px-divisible displacement D=(dr,dc) s.t. (pixels + D) covers every
    marker. Anchor-free: candidates = marker - piece-pixel, filtered to the move
    grid. Returns the max-coverage, smallest-|D| candidate (None if no markers)."""
    if not marks:
        return None
    Pset = pixels
    m0 = marks[0]
    cands = set()
    for p in Pset:
        dr, dc = m0[0] - p[0], m0[1] - p[1]
        if dr % 3 == 0 and dc % 3 == 0:
            cands.add((dr, dc))
    best, best_cov, best_d = None, -1, None
    for D in cands:
        cov = sum(1 for m in marks if (m[0] - D[0], m[1] - D[1]) in Pset)
        d = abs(D[0]) + abs(D[1])
        if cov > best_cov or (cov == best_cov and d < best_d):
            best, best_cov, best_d = D, cov, d
    return best


def active_piece(frame):
    """Return (color, pixel-set) of the active piece — the blob whose bbox
    contains the unique color-0 pixel (robust to HOLLOW shapes)."""
    g = np.asarray(frame)
    p0 = np.argwhere(g == 0)
    if len(p0) != 1:
        return None, None
    r, c = int(p0[0][0]), int(p0[0][1])
    pieces, _ = detect(g)
    cands = [p for p in pieces
             if p["bbox"][0] <= r <= p["bbox"][1] and p["bbox"][2] <= c <= p["bbox"][3]]
    if not cands:
        return None, None
    best = min(cands, key=lambda p: (p["bbox"][1] - p["bbox"][0]) * (p["bbox"][3] - p["bbox"][2]))
    return best["color"], best["pixels"]


def solve_level(cls, lvl, verbose=False):
    g = cls()
    g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    g.set_level(lvl)
    obs = g.perform_action(ActionInput(id=GameAction.ACTION7), raw=True)  # render the level
    # capture each piece's target markers at start (nothing placed yet → all visible)
    f0 = np.asarray(obs.frame[-1])
    pieces, _ = detect(f0)
    markers = {p["color"]: p["marks"] for p in pieces}
    N = len(pieces)
    if verbose:
        print(f"  L{lvl+1}: {N} pieces; markers={ {c: len(m) for c, m in markers.items()} }")
    placed = 0
    steps = 0
    BUDGET = 250
    cur_lvl = lvl
    while steps < BUDGET:
        f = np.asarray(obs.frame[-1])
        # level advanced? re-capture markers for the new level (the real pipeline
        # does this via reset_level on a level transition).
        lc = obs.levels_completed or 0
        if lc > cur_lvl:
            cur_lvl = lc
            pieces, _ = detect(f)
            markers = {p["color"]: p["marks"] for p in pieces}
            N = len(pieces)
            placed = 0
            if verbose:
                print(f"    -> advanced to L{cur_lvl+1}: {N} pieces markers={ {c: len(m) for c,m in markers.items()} }")
        color, pix = active_piece(f)
        if color is None or color not in markers:
            return False, cur_lvl, g, f"no-active (color={color}) at L{cur_lvl+1} step {steps}"
        D = required_disp(pix, markers[color])
        if D is None:
            return False, cur_lvl, g, "no-markers"
        if D == (0, 0):
            placed += 1
            a = CYCLE
        elif abs(D[0]) >= abs(D[1]) and D[0] != 0:
            a = DOWN if D[0] > 0 else UP
        elif D[1] != 0:
            a = RIGHT if D[1] > 0 else LEFT
        else:
            a = CYCLE
        obs = g.perform_action(ActionInput(id=GA[a]), raw=True)
        steps += 1
        st = str(obs.state)
        if st in ("GameState.GAME_OVER",) or not obs.frame:
            return (cur_lvl > lvl), cur_lvl, g, f"reached L{cur_lvl+1}, {st} after {steps}"
        if st in ("GameState.WIN",):
            return True, cur_lvl + 1, g, f"GAME WIN in {steps}"
    return cur_lvl > lvl, cur_lvl, g, f"reached L{cur_lvl+1} after {steps} steps"


def main():
    cls = load("re86")
    for lvl in (0, 1, 2):
        ok, lc, g, msg = solve_level(cls, lvl, verbose=True)
        print(f"  -> {'WIN' if ok else 'no'}  ({msg})")


if __name__ == "__main__":
    main()
