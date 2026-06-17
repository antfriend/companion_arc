# LOCUS — tu93 Game Companion

Per-game companion for tu93 (ARC-AGI-3). Canonical record of tu93's elements,
goals, and dynamics — the source of truth the functional code (`games/tu93/
detector.py`, `games/tu93/dynamic.py`) evolves around. Keep this file in sync when
refactoring game code.

Cross-game overview lives in companion_arcprize.md (Dynamics Catalog).

**To invoke**: start any message with `@LOCUS`.

```mmpdb
db_id: ttdb:companion:locus:tu93:v1
db_name: "LOCUS — tu93 Game Companion"
coord_increment:
  lat: 10
  lon: 10
collision_policy: southeast_step
timestamp_kind: unix_utc
umwelt:
  umwelt_id: umwelt:companion:locus:tu93:v1
  role: game_companion_tu93
  perspective: "LOCUS grounded in tu93 game knowledge. Tracks elements, win condition, per-level dynamics, the solver shape, and what remains unknown."
  scope: "tu93 only. Elements, goals, dynamics, solver state, and session records for all tu93 instances and levels."
  constraints:
    - "Only claim to know what is written in this file."
    - "Records are confidence-tagged: high conf = confirmed from game source or repeated wins; low conf = hypothesis / open problem (the first targets each session)."
    - "Elements/dynamics are frame-structural (colors, counts, bbox relations) — translation/recolor independent. Re-detect from the first frame; never hardcode canonical coordinates."
    - "When game code is refactored, update the matching record and increment rev."
  globe:
    frame: "tu93_globe"
    origin: "The agent — at the intersection of element knowledge and verified solving."
    mapping: "Latitude = certainty (N = confirmed / understood; S = uncertain / open). Longitude = scope (W = elements & mechanics; E = goal & solver route)."
```

---

## Summary (glance)

**Type**: maze navigation (L1) → maze navigation under turret fire (L2+).
**Status**: L1 SOLVED (adaptive BFS, re-derivation Dynamic, de-risk CLEAN, registered).
L2 mechanic DECODED 2026-06-17 (turrets) but UNSOLVED — genuine timing puzzle, no
quick win. Source instance: tu93-0768757b.

---

@LAT20LON-10 tu93 elements
[ew]
conf:245
rev:1
sal:3
touched:1
[/ew]
Frame colors (from game source tu93-0768757b):
- CURSOR: 3×3 sprite "0016ihgrljrgpq" = body color-9 + a single color-4 marker pixel.
  The marker's position within the 3×3 rotates with the cursor's facing → use the
  full color-4∪color-9 sprite extent for the top-left anchor, NOT the marker alone.
  Tag "0017unajnymcki" (the player "mover").
- EXIT: 3×3 solid color-14 block "0014mzhhvzrazi". Tag "0015msvpvzxhqf".
- MAZE: tag "0005uvnhiglpvh". pixels are 0 (room), color-2 (passage/corridor), -1 (void).
- CORRIDOR_COLOR = 2 — movement is allowed iff the passage pixel ahead == 2.
- TURRETS (L2+ only): 3×3 sprites, body color + a color-15 marker on the FACING edge.
  Families: color-8 (tag 0001haidilggfh), color-12 (tag 0020npxxteirsg), color-13
  (tag 0023otenflmryc). Color-11 appears as the "armed/projectile" marker.
- STEP COUNTER: a one-row progress bar at frame row 63 (color-6 = steps remaining).

Geometry constants: CELL_SIZE=3 (`hwthhtvyki`, passage-pixel offset); LOGICAL_CELL_SIZE=6
(`hcgctulqhn`, room-to-room pitch). Cursor moves one logical cell (6px) per action.
Origin is DERIVED from the frame (corridor bbox snapped to the cursor's 6px lattice
phase) — translation-independent across hidden variants. Code: `games/tu93/detector.py`.

---

@LAT20LON0 tu93 goal / win condition
[ew]
conf:240
rev:1
sal:3
touched:1
[/ew]
WIN = every mover (tag 0017unajnymcki) is positioned on an exit (tag 0015msvpvzxhqf):
`mover.x == exit.x and mover.y == exit.y`. L1 has one mover + one exit → cursor reaches
the exit cell. LOSE = no movers remain (cursor destroyed) OR the step counter hits 0.
Actions: ACTION1=UP, ACTION2=DOWN, ACTION3=LEFT, ACTION4=RIGHT (indices 0–3). No ACTION5.

---

@LAT20LON10 tu93 L1 dynamics + solver
[ew]
conf:245
rev:1
sal:4
touched:1
[/ew]
L1 = pure maze navigation. The cursor walks color-2 corridors to the color-14 exit.
Passability is checked from the frame: the passage pixel between cell (r,c) and an
adjacent cell is at (origin_r + r*6 + dr*3, origin_c + c*6 + dc*3); open iff == 2.

SOLVER (re-derivation, the preferred shape): each frame, detect cursor cell + exit
cell, BFS through open passages, emit ONE move. Self-correcting — re-BFS every step,
so a blocked/missed move just re-plans. Consistency predicate `_expect_moved`: the
cursor marker must shift in the commanded direction; else abort to the explorer floor.
Level-agnostic by construction (no level guard). `Tu93Dynamic` in `games/tu93/dynamic.py`.
Recognizer fingerprint: small 3×3 color-4 cursor (≤16px) + color-9 body (≤16px) + small
3×3 color-14 exit (≤16px) + substantial color-2 corridor (>50px). Size caps exclude
sk48 (huge color-4); corridor floor excludes cd82 (tiny selector, no maze). De-risk
CLEAN (diagonal confusion matrix). L1 confirmed WIN, 18-step adaptive route on 0768757b.

---

@LAT-30LON-10 tu93 L2 dynamic — TURRETS (decoded, unsolved)
[ew]
conf:200
rev:1
sal:5
touched:1
[/ew]
L2 adds TURRET sprites (e.g. "0018rquzkxccdu", color-8 body + color-15 marker). The
color-15 marker sits on the turret's FACING edge (left edge → faces rotation 270 = -col
= LEFT). Mechanic (decoded 2026-06-17 via `_probe_tu93_l2.py` / `_sim_tu93_l2.py` /
`_dump_tu93_l2.py`, confirmed against game source `step()`/`ixnhjkzwic`/`wlhbetxehh`/
`bwlnieccpx`/`uneirnujpq`):
- A turret ARMS the instant a mover is on its facing axis (same perpendicular coord) at
  EXACTLY the trigger distance: 6px for color-8 (`hcgctulqhn`), 12px for color-13
  (`anklfvjqkx`). It then BECOMES a projectile traveling along its facing axis and KILLS
  the mover on center-overlap (`bwrgmsbsrg`).
- **The kill is INTRA-STEP / instant.** Confirmed: mover safe at distance-12 → one move
  to distance-6 → armed + travels 6px + kills, all within that single action. There is
  NO trigger-then-dodge window.
WHY the L1 BFS dies (~4–5 L2 steps): `Tu93Dynamic` is turret-blind and walks straight
into the firing line. Probed 0768757b L2 geometry: cursor boxed bottom-left, only exit
is UP to the row-27 corridor; the turret sits on row 27 facing LEFT and blocks the ONLY
corridor to the exit half (top-right); closest safe cell is distance-12, the next cell
is instant death; NO turret-free path exists.

---

@LAT-40LON10 tu93 L2 solver — OPEN PROBLEM
[ew]
conf:65
rev:1
sal:5
touched:1
[/ew]
NO solver. tu93 L2 is a genuine hard TIMING puzzle, not a route-around fix and not a
bounded quick win (matches the cross-game "no quick L2 win" conclusion). A level-agnostic
BFS is necessary but NOT sufficient. Future shape (deferred): turret-aware BFS that
treats each turret's facing-ray as lethal; when a turret blocks the only corridor it
needs a neutralize/pass mechanic — OPEN, because the instant-kill removes the obvious
perpendicular dodge. L2 baseline geometry: maze "0006fwxohroqxn", grid 45×45,
StepCounter=50. Levels 3+ stack more turret families (color-12/13) and larger mazes.

---

## Session log area

<!-- New session records are appended below. -->
- 2026-06-17: L1 re-confirmed (multi-level scoreboard). L2 turret mechanic fully decoded
  (above). No L2 solve. Probes added: `_probe_tu93_l2.py`, `_sim_tu93_l2.py`, `_dump_tu93_l2.py`.
