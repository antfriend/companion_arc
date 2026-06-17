# LOCUS — cd82 Game Companion

Per-game companion for cd82 (ARC-AGI-3). Canonical record of cd82's elements,
goals, and dynamics — the source of truth the functional code (`games/cd82/
detector.py`, `games/cd82/dynamic.py`) evolves around. Keep this file in sync when
refactoring game code.

Cross-game overview lives in companion_arcprize.md (Dynamics Catalog).

**To invoke**: start any message with `@LOCUS`.

```mmpdb
db_id: ttdb:companion:locus:cd82:v1
db_name: "LOCUS — cd82 Game Companion"
coord_increment:
  lat: 10
  lon: 10
collision_policy: southeast_step
timestamp_kind: unix_utc
umwelt:
  umwelt_id: umwelt:companion:locus:cd82:v1
  role: game_companion_cd82
  perspective: "LOCUS grounded in cd82 game knowledge. Tracks elements, win condition, per-level dynamics, the solver shape, and what remains unknown."
  scope: "cd82 only. Elements, goals, dynamics, solver state, and session records for all cd82 instances and levels."
  constraints:
    - "Only claim to know what is written in this file."
    - "Records are confidence-tagged: high conf = confirmed from game source or repeated wins; low conf = hypothesis / open problem (the first targets each session)."
    - "Elements/dynamics are frame-structural (colors, counts, bbox relations) — translation/recolor independent. Re-detect from the first frame; never hardcode canonical coordinates."
    - "When game code is refactored, update the matching record and increment rev."
  globe:
    frame: "cd82_globe"
    origin: "The agent — at the intersection of element knowledge and verified solving."
    mapping: "Latitude = certainty (N = confirmed / understood; S = uncertain / open). Longitude = scope (W = elements & mechanics; E = goal & solver route)."
```

---

## Summary (glance)

**Type**: basket-ring navigation + fire. Move an active-basket selector around a 3×3 ring
and FIRE to paint the canvas to a target.
**Status**: L1 SOLVED (re-derivation Dynamic, de-risk CLEAN, registered). L2+ infeasible
with simple actions (needs color selection / click). Source: cd82-fb555c5d.

---

@LAT20LON-10 cd82 elements
[ew]
conf:240
rev:1
sal:3
touched:1
[/ew]
- BASKET RING: 8 baskets on a 3×3 grid; center (1,1) is FORBIDDEN. Layout (index(grid)):
  `7(0,0) 0(0,1) 1(0,2) / 6(1,0) [ctr] 2(1,2) / 5(2,0) 4(2,1) 3(2,2)`.
- ACTIVE-BASKET sprite: color-2 = border, color-15 = fill. The detector finds the color-2
  entity bbox → (r_min, c_min) → basket lookup → grid position.
- CANVAS: the target region painted by FIRE (rows of color-15 vs color-0).
- RECOGNIZER caps: small color-2 selector with `_MAX_SELECTOR=60` (added 2026-06-16 to
  stop cd82 cross-firing on tu93 L2's 117px color-2 corridor — a real precision gain;
  do NOT regress).

---

@LAT20LON0 cd82 goal / win condition
[ew]
conf:235
rev:1
sal:3
touched:1
[/ew]
L1 target: canvas rows 5–9 = color-15, rows 0–4 = 0. Reached by firing from basket 4.
Actions: ACTION1=row−1, ACTION2=row+1, ACTION3=col−1, ACTION4=col+1, ACTION5=FIRE
(indices 0–4). Default start: basket 0 at grid (0,1); a random step-0 may move the basket,
so always re-detect.

---

@LAT20LON10 cd82 L1 dynamics + solver
[ew]
conf:240
rev:1
sal:4
touched:1
[/ew]
SOLVER (re-derivation): detect the current basket/grid pos each frame; navigate to basket
4 at grid (2,1) AVOIDING the forbidden center (1,1); then FIRE. Per-start routes (to
basket 4): (0,0)→[1,1,3,4]; (0,1)→[3,1,1,2,4]; (0,2)→[1,1,2,4]; (1,0)→[1,3,4];
(1,2)→[1,2,4]; (2,0)→[3,4]; (2,1)→[4]; (2,2)→[2,4]. Canonical full route (search trial 366,
seed 42): `3,0,1,0,0,0,1,1,1,3,2,0,4,4,2,0,0,0,1` (19 steps). `Cd82Dynamic` /
`games/cd82/detector.py`. De-risk CLEAN.

---

@LAT-30LON-10 cd82 L1 failure mode + L2+ (open)
[ew]
conf:120
rev:1
sal:3
touched:1
[/ew]
L1 FAILURE MODE: if a random step-0 = FIRE on basket 0, canvas rows 0–4 become color-15
(L1 needs 0 there) → canvas_dirty → win check fails. Probability ~1/5; no recovery with
simple actions. L2–6: require COLOR SELECTION (ACTION5/click to pick colors other than
15) → not achievable with simple actions; the solver returns empty for level ≥ 2 and
defers to the explorer floor. Open.

---

## Session log area

<!-- New session records are appended below. -->
