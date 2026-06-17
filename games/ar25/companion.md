# LOCUS — ar25 Game Companion

Per-game companion for ar25 (ARC-AGI-3). Canonical record of ar25's elements,
goals, and dynamics — the source of truth the functional code (`games/ar25/
detector.py`, `games/ar25/dynamic.py`) evolves around. Keep this file in sync when
refactoring game code.

Cross-game overview lives in companion_arcprize.md (Dynamics Catalog).

**To invoke**: start any message with `@LOCUS`.

```mmpdb
db_id: ttdb:companion:locus:ar25:v1
db_name: "LOCUS — ar25 Game Companion"
coord_increment:
  lat: 10
  lon: 10
collision_policy: southeast_step
timestamp_kind: unix_utc
umwelt:
  umwelt_id: umwelt:companion:locus:ar25:v1
  role: game_companion_ar25
  perspective: "LOCUS grounded in ar25 game knowledge. Tracks elements, win condition, per-level dynamics, the solver shape, and what remains unknown."
  scope: "ar25 only. Elements, goals, dynamics, solver state, and session records for all ar25 instances and levels."
  constraints:
    - "Only claim to know what is written in this file."
    - "Records are confidence-tagged: high conf = confirmed from game source or repeated wins; low conf = hypothesis / open problem (the first targets each session)."
    - "Elements/dynamics are frame-structural (colors, counts, bbox relations) — translation/recolor independent. Re-detect from the first frame; never hardcode canonical coordinates."
    - "When game code is refactored, update the matching record and increment rev."
  globe:
    frame: "ar25_globe"
    origin: "The agent — at the intersection of element knowledge and verified solving."
    mapping: "Latitude = certainty (N = confirmed / understood; S = uncertain / open). Longitude = scope (W = elements & mechanics; E = goal & solver route)."
```

---

## Summary (glance)

**Type**: REFLECTION puzzle. Move a piece so it AND its mirror image (reflected through a
mirror bar) together cover all target markers.
**Status**: L1 SOLVED (re-derivation Dynamic, de-risk CLEAN, registered). L2+ UNSOLVED.
Source: ar25 (21×21 logical grid, scale 3).

---

@LAT20LON-10 ar25 elements
[ew]
conf:235
rev:1
sal:3
touched:1
[/ew]
Grid 21×21, scale=3 → 63×63 game area in a 64×64 frame; letterbox at row/col 63 = color-5.
BACKGROUND_COLOR=9, PADDING_COLOR=5.
- PIECE ("0007arvfmhagbj", tags ["0006lxjtqggkmi","sys_click"]): Γ-shape color-5,
  pixels `[[5,5,5],[-1,-1,5],[-1,-1,5]]` (5 pixels). Does NOT auto-rotate. Detector reads
  its game pos = color-5 cluster min_col//3, min_row//3.
- MIRROR ("0055nwhypaamix", tag "0054kgxrvfihgm"): 41×1 vertical bar, color-10, at x=10.
  Vertical mirror → reflected_x = 2*10 − pixel_x = 20 − pixel_x. (Tag "0056icpryeujyf" =
  not selectable.) The piece's REFLECTION renders as color-4 (pbtdgroplk=4).
- MARKERS ("0001sruqbuvukh"): 1×1 color-11 cells (the targets), layer -4.

---

@LAT20LON0 ar25 goal / win condition
[ew]
conf:235
rev:1
sal:3
touched:1
[/ew]
WIN (`vplrhaovhr`) = every color-11 marker is covered by a piece pixel OR a reflected
pixel in the combined (direct ∪ reflection) map. Actions: ACTION1=UP(dy-1), ACTION2=DOWN
(dy+1), ACTION3=LEFT(dx-1), ACTION4=RIGHT(dx+1), ACTION5=cycle selection, ACTION7=undo.

---

@LAT20LON10 ar25 L1 dynamics + solver
[ew]
conf:230
rev:1
sal:4
touched:1
[/ew]
L1 = one piece, one vertical mirror at x=10, 5 markers. Solution (confirmed): drive the
piece to (1,15) → direct pixels (1,15),(2,15),(3,15),(3,16),(3,17) reflect through x=10
to (19,15),(18,15),(17,15),(17,16),(17,17) = all 5 markers. SOLVER (re-derivation):
route = `[LEFT]*(piece_x−1) + [DOWN]*(15−piece_y)`. NOTE: the framework plays a step-0 UP
to get the first frame (piece shifts (6,5)→(6,4)) → detected route LEFT×5 + DOWN×11 =
16 steps; 17 total game actions; StepCounter=64. Score 2.7778 (human≈25). `Ar25Dynamic` /
`games/ar25/detector.py`. De-risk CLEAN.

---

@LAT-30LON-10 ar25 L2+ — open
[ew]
conf:70
rev:1
sal:4
touched:1
[/ew]
NO solver. L2 has a different piece ("0026ptolirjxrb") at (15,6) and a different marker
pattern; levels 3+ add multiple pieces and HORIZONTAL mirrors → multi-piece reflection
placement not yet built. Open.

---

## Session log area

<!-- New session records are appended below. -->
