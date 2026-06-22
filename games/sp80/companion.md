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
**Status**: L1+L2 SOLVED (L2 2026-06-22). L1 = single-deflector re-derivation Dynamic.
L2 = multi-piece CLOSED-LOOP deflector arranger. De-risk CLEAN, _test_multilevel max
level 2. Source: sp80-589a99af.

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

@LAT30LON10 sp80 L2 — SOLVED (multi-piece closed-loop arranger)
[ew]
conf:225
rev:2
sal:4
touched:2
[/ew]
SOLVED 2026-06-22. MECHANIC (read from source + engine probing): a FIXED spout drips a
single liquid stream that RISES (the level runs at `dojfslwbg=180`, so display is rotated
180° — moves are still display-nominal when sent as raw GameActions). Each ACTION5 is ONE
complete spill, resolved inside a single `perform_action`; WIN = that one spill covers
EVERY color-11 target (`repwkzbkhxl`) — flanked on both sides → recolor 13 / `cevwbinfgl`
— WITHOUT touching the hazard (`waoewejnqzc`, sets `kfdcqkodyy`). Coverage RESETS between
failed spills (`lpqbikobah` repaints targets to 11) and ~4 spills then GAME_OVER, so a
SINGLE arrangement must cover all targets at once. Pieces (`plzwjbfyfli`, color-8 idle /
color-9 selected) are DEFLECTORS: a rising drop hitting a piece splits L+R and continues
up. L2 = three pieces (one 5-wide, two interchangeable 3-wide) + three targets centred at
the top.
SOLVER (`Sp80Dynamic._arrange`): engaged when >1 movable piece is seen near the color-11
cluster. CLOSED-LOOP — re-detects pieces each frame (color-9 and color-8 detected
SEPARATELY so a moving piece is never merged with an adjacent idle one), assigns each to a
slot (TOP-LEFT offset from the target-cluster anchor: 5-wide→(+10,+3); 3-wide→(+5,+2),
(+7,+6)), then click-selects an unplaced piece and walks it in. Two rules avoid pieces
overlapping mid-move (which would hide one and trigger a premature spill): fill slots
BOTTOM-UP (largest row first) and move each piece VERTICALLY before horizontally. Once all
seated, ACTION5. Winning final board verified via the real engine; `_test_multilevel`
sp80 max level 2.
NOTE: slots/spill are anchored to the detected target cluster (translation-robust for this
layout) but the exact 3-slot recipe is tuned to the L2 geometry — L3+ (more pieces/targets,
multiple spouts) would need a search-derived recipe or a flow planner. The old "rotation
gotcha" (stale per-level actions list, FIXED 2026-06-10 f50f75b) is moot for the Dynamic,
which sends raw GameActions.

---

## Session log area

<!-- New session records are appended below. -->
