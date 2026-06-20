"""
core/click_agent.py — count-based explorer WITH ACTION6 (click) support.

Why this exists (2026-06-14): both the 0.15 random baseline and the general v1
explorer are structurally blind to click games. ACTION6 needs (x,y) coords so
is_simple() is False, so `actions = [a for a in action_space if a.is_simple()]`
excludes it everywhere. Yet 6 of 11 canonical games expose ACTION6
(cd82, sp80, ar25, sk48, cn04, ka59) — and the hidden set surely mirrors that.
An agent that cannot click can never solve those games.

For the standard 64x64 camera the display->grid mapping is identity
(scale=1, padding=0), so a click on frame cell (x,y) is just
ActionInput(ACTION6, data={"x": x, "y": y}).

Design — same count-based novelty model as general_agent v1, generalized to a
per-state DYNAMIC action set:

  Each step the candidate actions are
     moves:  ("m", i)  for each simple action i
     clicks: ("c", gx, gy)  one per foreground object (connected component
             centroid), capped at _MAX_CLICKS by component size.
  Click candidates are derived deterministically from the board, so for a given
  board signature the candidate set (and its action keys) is always identical —
  which keeps the tabular model (visit / trans / noop keyed on (sig, action_key))
  consistent, exactly as in v1.

Policy (per current signature s, over that state's candidate keys):
  1. untried candidate keys -> take one (max novelty), skipping known no-ops
  2. else -> the key whose known successor is least-visited, skipping no-ops.

choose(frame) returns an action SPEC: ("m", i) or ("c", gx, gy). The caller
translates it into a simple action or an ACTION6 ActionInput. Movement games
(no ACTION6 available) get no click candidates, so this reduces to v1.
"""

import random
from collections import deque
from typing import Optional

import numpy as np

from core.general_agent import board_signature

_MAX_CLICKS = 12          # cap click candidates per frame (largest components first)
_MIN_COMPONENT = 1        # ignore components smaller than this many cells


def spec_to_action_input(spec, move_objs):
    """Translate an action SPEC into an ARC ActionInput. The shared convention used
    by ClickExplorer and SupervisedAgent.spec:
        ("m", i)      → move_objs[i]                       (a simple movement action)
        ("c", x, y)   → ACTION6 with data {"x": x, "y": y} (click-select cell (x, y))
    move_objs is the per-game list of simple-action GameActions (ACTION6 excluded)."""
    from arcengine import ActionInput, GameAction
    if spec[0] == "m":
        return ActionInput(id=move_objs[spec[1] % len(move_objs)], data={})
    return ActionInput(id=GameAction.ACTION6, data={"x": int(spec[1]), "y": int(spec[2])})


def _foreground_components(frame: np.ndarray, max_clicks: int = _MAX_CLICKS):
    """Return up to max_clicks click targets (gx, gy): centroids of the largest
    non-background connected components (4-connectivity)."""
    a = np.asarray(frame)
    if a.ndim != 2:
        return []
    vals, counts = np.unique(a, return_counts=True)
    bg = int(vals[int(np.argmax(counts))])      # background = most common color
    h, w = a.shape
    seen = np.zeros((h, w), dtype=bool)
    comps = []  # (size, gx, gy)
    for y in range(h):
        for x in range(w):
            if seen[y, x] or a[y, x] == bg:
                continue
            # BFS over the same-foreground (non-bg) region of this color.
            color = a[y, x]
            q = deque([(y, x)])
            seen[y, x] = True
            cells = []
            while q:
                cy, cx = q.popleft()
                cells.append((cy, cx))
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < h and 0 <= nx < w and not seen[ny, nx] and a[ny, nx] == color:
                        seen[ny, nx] = True
                        q.append((ny, nx))
            if len(cells) < _MIN_COMPONENT:
                continue
            cy = sum(c[0] for c in cells) / len(cells)
            cx = sum(c[1] for c in cells) / len(cells)
            # snap centroid to an actual cell of the component (nearest)
            by, bx = min(cells, key=lambda c: (c[0] - cy) ** 2 + (c[1] - cx) ** 2)
            comps.append((len(cells), int(bx), int(by)))
    comps.sort(key=lambda t: -t[0])
    return [(gx, gy) for _, gx, gy in comps[:max_clicks]]


class ClickExplorer:
    def __init__(self, n_moves: int, allow_click: bool = False,
                 seed: Optional[int] = None) -> None:
        self.n_moves = max(0, n_moves)
        self.allow_click = allow_click
        self._rng = random.Random(seed)
        # Movement-stall threshold: clicks latch on after this many steps with
        # no never-seen signature. Scaled to the move count so a game gets a
        # fair chance to exhaust movement before clicks are introduced.
        self._stall = max(8, 2 * self.n_moves)
        self.reset_level()

    def reset_level(self) -> None:
        self.visit: dict = {}
        self.trans: dict = {}      # (sig, key) -> next_sig
        self.noop: set = set()     # (sig, key) with no board change
        self._prev_sig = None
        self._prev_key = None
        self._since_new = 0        # steps since a never-seen signature appeared
        self._clicks_on = False    # latched once movement stalls (this level)

    def set_actions(self, n_moves: int, allow_click: bool) -> None:
        self.n_moves = max(0, n_moves)
        self.allow_click = allow_click
        self._stall = max(8, 2 * self.n_moves)

    # back-compat with the v1 interface so callers can swap import cleanly
    def set_n_actions(self, n: int) -> None:
        self.n_moves = max(0, n)

    def _candidates(self, sig: bytes, frame: np.ndarray):
        """Movement-first, clicks-on-global-stall.

        Clicks dilute movement-solvable games (12 extra candidates per state
        balloon the search). A per-state gate ("offer clicks only where this
        state has no untried move") fails on games whose moves keep generating
        fresh states — there is always an untried move somewhere, so clicks
        never unlock (cn04 issued 0 clicks). The correct trigger is GLOBAL
        movement-stall: once movement has gone _stall steps without revealing a
        never-seen signature, movement has dead-ended for this level and clicks
        latch on for the rest of it. A movement-solvable game (sp80) keeps
        finding new states, never stalls, never clicks — preserved exactly.
        """
        move_keys = [("m", i) for i in range(self.n_moves)]
        if not (self.allow_click and self._clicks_on):
            return move_keys or [("m", 0)]
        click_keys = [("c", gx, gy) for gx, gy in _foreground_components(frame)]
        return (move_keys + click_keys) or [("m", 0)]

    def choose(self, frame: np.ndarray):
        sig = board_signature(frame)
        is_new = sig not in self.visit
        self.visit[sig] = self.visit.get(sig, 0) + 1
        # Track movement-stall: clicks latch on once novelty dries up.
        if is_new:
            self._since_new = 0
        else:
            self._since_new += 1
            if self.allow_click and not self._clicks_on and self._since_new >= self._stall:
                self._clicks_on = True

        if self._prev_sig is not None and self._prev_key is not None:
            k = (self._prev_sig, self._prev_key)
            self.trans[k] = sig
            if sig == self._prev_sig:
                self.noop.add(k)

        cands = self._candidates(sig, frame)
        key = self._policy(sig, cands)
        self._prev_sig, self._prev_key = sig, key
        return key

    def _policy(self, sig, cands):
        tried = [k for k in cands if (sig, k) in self.trans]
        untried = [k for k in cands if k not in tried]

        live_untried = [k for k in untried if (sig, k) not in self.noop]
        if live_untried:
            return self._rng.choice(live_untried)
        if untried:
            return self._rng.choice(untried)

        live = [k for k in cands if (sig, k) not in self.noop] or cands
        best, best_v = [], None
        for k in live:
            nsig = self.trans.get((sig, k))
            v = self.visit.get(nsig, 0) if nsig is not None else 0
            if best_v is None or v < best_v:
                best_v, best = v, [k]
            elif v == best_v:
                best.append(k)
        return self._rng.choice(best)
