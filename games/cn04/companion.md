# LOCUS — cn04 Game Companion

Per-game companion for cn04 (ARC-AGI-3). Canonical record of cn04's elements,
goals, and dynamics — the source of truth the functional code (`games/cn04/
detector.py`, `games/cn04/dynamic.py`) evolves around. Keep this file in sync when
refactoring game code.

Cross-game overview lives in companion_arcprize.md (Dynamics Catalog).

**To invoke**: start any message with `@LOCUS`.

```mmpdb
db_id: ttdb:companion:locus:cn04:v1
db_name: "LOCUS — cn04 Game Companion"
coord_increment:
  lat: 10
  lon: 10
collision_policy: southeast_step
timestamp_kind: unix_utc
umwelt:
  umwelt_id: umwelt:companion:locus:cn04:v1
  role: game_companion_cn04
  perspective: "LOCUS grounded in cn04 game knowledge. Tracks elements, win condition, per-level dynamics, the solver shape, and what remains unknown."
  scope: "cn04 only. Elements, goals, dynamics, solver state, and session records for all cn04 instances and levels."
  constraints:
    - "Only claim to know what is written in this file."
    - "Records are confidence-tagged: high conf = confirmed from game source or repeated wins; low conf = hypothesis / open problem (the first targets each session)."
    - "Elements/dynamics are frame-structural (colors, counts, bbox relations) — translation/recolor independent. Re-detect from the first frame; never hardcode canonical coordinates."
    - "When game code is refactored, update the matching record and increment rev."
  globe:
    frame: "cn04_globe"
    origin: "The agent — at the intersection of element knowledge and verified solving."
    mapping: "Latitude = certainty (N = confirmed / understood; S = uncertain / open). Longitude = scope (W = elements & mechanics; E = goal & solver route)."
```

---

## Summary (glance)

**Type**: CONNECTOR-MATCHING puzzle. Rotate + translate a piece so its connector pixels
mate with a same-type connector of another sprite.
**Status**: L1 SOLVED (re-derivation Dynamic, de-risk CLEAN, registered). L2+ UNSOLVED.

---

@LAT20LON-10 cn04 elements
[ew]
conf:230
rev:1
sal:3
touched:1
[/ew]
- SPRITES carry CONNECTOR pixels: color-8 and color-13. The engine auto-SELECTS the
  sprite nearest the origin; the selected sprite renders its body as color-0 with its
  connector markers as color-8.
- KEY detection insight: the body (color-0) bbox is 5×5 at EVERY rotation — the marker
  column/row falls OUTSIDE it. So position AND rotation must come from the body∪marker
  cell extent: 6 wide ⇒ rot 0/180 (read marker edge); 6 tall ⇒ rot 90/270. (The first
  detector misread rot 180/270; fixed before commit — do not regress this.)

---

@LAT20LON0 cn04 goal / win condition
[ew]
conf:230
rev:1
sal:3
touched:1
[/ew]
WIN = every sprite's connectors overlap a SAME-TYPE connector of another sprite:
8-to-8 and 13-to-13 only. (8-to-13 contacts DISPLAY matched-green but do NOT count —
a deliberate decoy.) Actions: ACTION1–4 move the selected sprite 1 cell (no collision,
bounds-only), ACTION5 rotates +90°. ACTION6 (click) is NOT needed for L1.

---

@LAT20LON10 cn04 L1 dynamics + solver
[ew]
conf:230
rev:1
sal:4
touched:1
[/ew]
SOLVER (re-derivation): rotate the selected sprite to rot 0 (ACTION5 × ((360−rot)/90)),
then translate to the grid target. Canonical: 3 rot + RIGHT×4 + DOWN×7 = 14 actions,
baseline 29, score 4.7619 (capped 115). `Cn04Dynamic` / `games/cn04/detector.py`.
Validated 7/7 incl. an ACTION5-burn scenario. De-risk CLEAN (registered).

---

@LAT-30LON-10 cn04 L2+ — open
[ew]
conf:70
rev:1
sal:4
touched:1
[/ew]
NO solver. Levels 2–6 have 3–4 pieces, GreyMasking, and stacked variants → need
click-select (ACTION6) to choose which piece to move, plus multi-piece search. Open.

---

## Session log area

<!-- New session records are appended below. -->
