# LOCUS — sp80 Game Companion

Per-game companion for sp80 (ARC-AGI-3). Canonical record of sp80's elements,
goals, and dynamics — the source of truth the functional code (`games/sp80/
detector.py`, `games/sp80/dynamic.py`) evolves around. Keep this file in sync when
refactoring game code.

Cross-game overview lives in companion_arcprize.md (Dynamics Catalog).

**To invoke**: start any message with `@LOCUS`.

```mmpdb
db_id: ttdb:companion:locus:sp80:v1
db_name: "LOCUS — sp80 Game Companion"
coord_increment:
  lat: 10
  lon: 10
collision_policy: southeast_step
timestamp_kind: unix_utc
umwelt:
  umwelt_id: umwelt:companion:locus:sp80:v1
  role: game_companion_sp80
  perspective: "LOCUS grounded in sp80 game knowledge. Tracks elements, win condition, per-level dynamics, the solver shape, and what remains unknown."
  scope: "sp80 only. Elements, goals, dynamics, solver state, and session records for all sp80 instances and levels."
  constraints:
    - "Only claim to know what is written in this file."
    - "Records are confidence-tagged: high conf = confirmed from game source or repeated wins; low conf = hypothesis / open problem (the first targets each session)."
    - "Elements/dynamics are frame-structural (colors, counts, bbox relations) — translation/recolor independent. Re-detect from the first frame; never hardcode canonical coordinates."
    - "When game code is refactored, update the matching record and increment rev."
  globe:
    frame: "sp80_globe"
    origin: "The agent — at the intersection of element knowledge and verified solving."
    mapping: "Latitude = certainty (N = confirmed / understood; S = uncertain / open). Longitude = scope (W = elements & mechanics; E = goal & solver route)."
```

---

## Summary (glance)

**Type**: two-phase SPILL/liquid puzzle — position a piece, then spill liquid to cover a
target. The only canonical game the explorer floor can sometimes win by chance.
**Status**: L1 SOLVED (re-derivation Dynamic, de-risk CLEAN, registered). L2 has an
action-space ROTATION gotcha (fixed) but the spill heuristic is L1-tuned → L2 still open.
Source: sp80-589a99af.

---

@LAT20LON-10 sp80 elements
[ew]
conf:235
rev:1
sal:3
touched:1
[/ew]
- PIECE: selected = color-9, unselected = color-8 (fallback: widest ≥20px color-8 entity).
- Frame mapping: frame_col = game_x × 4, frame_row = game_y × 4.
- OBSTACLES: color-11 cells (L1 ~160px; L2 ~240px — more obstacles at L2).
- Canonical L1 winning piece position: game (3, 4).
- ACTION-SPACE ROTATION (per level, `dojfslwbg`): L1 = k=0 (no remap), L2 = k=2 (180°).
  `othselxnik[k]` remaps the action SLOTS returned by `_get_valid_actions()`; `krehtwyvlu`
  remaps incoming actions — the two cancel ONLY if the actions list used for that level is
  the one freshly read on that level's first frame (see L2 record).

---

@LAT20LON0 sp80 goal / win condition
[ew]
conf:235
rev:1
sal:3
touched:1
[/ew]
WIN = spilled liquid covers the target region. Actions: ACTION1=UP, ACTION2=DOWN,
ACTION3=LEFT, ACTION4=RIGHT, ACTION5=SPILL (indices 0–4). The first SPILL wins in 6+1
propagation ticks; the remaining moves are dummies sent during the spill animation.

---

@LAT20LON10 sp80 L1 dynamics + solver
[ew]
conf:240
rev:1
sal:4
touched:1
[/ew]
SOLVER (re-derivation): detect the color-9 (selected) piece → game_x, game_y; prefix
LEFT/RIGHT/UP/DOWN to reach canonical (3,4); then append the spill sequence. Confirmed L1
spill route (search seed 42, trial 159): `[4,3,3,3,4,2,2,1]` = SPILL, RIGHT×3, SPILL,
LEFT×2, DOWN (8 steps — shortest of the solved games, near-optimal). `Sp80Dynamic` /
`games/sp80/detector.py`. De-risk CLEAN. NOTE: sp80 is also the one canonical game the
undirected explorer (random/v1/goal) occasionally wins by chance — its offline score
flickers; ignore that flicker as noise.

---

@LAT-30LON-10 sp80 L2 — rotation gotcha (fixed) + spill open
[ew]
conf:110
rev:1
sal:4
touched:1
[/ew]
L2 BUG (FIXED 2026-06-10, commit f50f75b): `_play_game` built the actions list ONCE on
L1 (k=0); for L2 (k=2) `_get_valid_actions()` returns remapped slots, so a stale L1 list
sent index-2 "LEFT" as ACTION3 → mapped to RIGHT → piece placed at x=9 not x=3 → spill
missed → GAME_OVER. FIX: refresh the actions list from `env.action_space` on each level's
first frame. L2 STILL OPEN: the spill heuristic (`_ANCHOR_TO_PIECE` / `_SPILL_ROUTE`) is
L1-tuned to canonical positions and L2 has more color-11 obstacles (~240 vs ~160) → the
fixed route does not transfer; L2 needs non-L1 spill logic. Open.

---

## Session log area

<!-- New session records are appended below. -->
