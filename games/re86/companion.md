# LOCUS — re86 Game Companion

Per-game companion for re86 (ARC-AGI-3). Canonical record of re86's elements,
goals, and dynamics — the source of truth the functional code (`games/re86/
detector.py`, `games/re86/dynamic.py`) evolves around. Keep this file in sync when
refactoring game code.

Cross-game overview lives in companion_arcprize.md (Dynamics Catalog).

**To invoke**: start any message with `@LOCUS`.

```mmpdb
db_id: ttdb:companion:locus:re86:v1
db_name: "LOCUS — re86 Game Companion"
coord_increment:
  lat: 10
  lon: 10
collision_policy: southeast_step
timestamp_kind: unix_utc
umwelt:
  umwelt_id: umwelt:companion:locus:re86:v1
  role: game_companion_re86
  perspective: "LOCUS grounded in re86 game knowledge. Tracks elements, win condition, per-level dynamics, the solver shape, and what remains unknown."
  scope: "re86 only. Elements, goals, dynamics, solver state, and session records for all re86 instances and levels."
  constraints:
    - "Only claim to know what is written in this file."
    - "Records are confidence-tagged: high conf = confirmed from game source or repeated wins; low conf = hypothesis / open problem (the first targets each session)."
    - "Elements/dynamics are frame-structural (colors, counts, bbox relations) — translation/recolor independent. Re-detect from the first frame; never hardcode canonical coordinates."
    - "When game code is refactored, update the matching record and increment rev."
  globe:
    frame: "re86_globe"
    origin: "The agent — at the intersection of element knowledge and verified solving."
    mapping: "Latitude = certainty (N = confirmed / understood; S = uncertain / open). Longitude = scope (W = elements & mechanics; E = goal & solver route)."
```

---

## Summary (glance)

**Type**: piece-PLACEMENT puzzle (NOT cursor navigation — the early detector got this
wrong). Move/cycle cross-shaped pieces so their composite matches a target sprite.
**Status**: L1 SOLVED (plan-once + abort Dynamic, de-risk CLEAN, registered). L2+ UNSOLVED.
Source: re86-8af5384d.

---

@LAT20LON-10 re86 elements
[ew]
conf:235
rev:1
sal:3
touched:1
[/ew]
Step size = 3px. Background/target-fill = color-4 (excluded from win comparison).
- MOVEABLE PIECES (tag "0031cppcuvqlbi"), cross sprites with a CENTER pixel that flags
  active (center=0 ⇒ ACTIVE; center=its-own-color ⇒ inactive):
  - Sprite "0042" — color-9, 27×27 cross.
  - Sprite "0030" — color-11, 23×23 cross.
- TARGET (tag "0054xnsuqceejm", sprite "0053", 64×64): a full-frame map whose non-color-4
  pixels mark the required positions (3×3 boxes) for each piece color.
- The single color-0 pixel = the center of the currently ACTIVE piece (the position anchor
  the detector reads each frame).

---

@LAT20LON0 re86 goal / win condition
[ew]
conf:235
rev:1
sal:3
touched:1
[/ew]
WIN = the composite of all placed pieces matches the target sprite (color-4 border
pixels EXCLUDED from comparison). Bounds check `xvvulayfrq` only requires the active
piece's CENTER point to be within [0,64) — so a piece may extend slightly off-grid
(e.g. y=-2 is legal if center y+11 ≥ 0). Actions: ACTION1–4 move the ACTIVE piece by 3px;
ACTION5 = `gxncswszaq` deactivates all then activates the NEXT piece in the list.

---

@LAT20LON10 re86 L1 dynamics + solver
[ew]
conf:230
rev:1
sal:4
touched:1
[/ew]
L1 = two cross pieces to place to cover all target markers. Confirmed satisfying solution
(8af5384d): place color-9 piece "0042" so its arms cover the four color-9 targets, cycle,
place color-11 piece "0030" so its arms cover the four color-11 targets.
SOLVER (PLAN-ONCE + abort — a placed piece self-occludes / overlaps so per-frame
re-derivation is ambiguous → plan once, abort caps downside): route =
`[UP]*up_042 + [RIGHT]*4 + [CYCLE] + [UP]*6 + [LEFT]*2`, where `up_042 = (v0_row-24)//3`
adapts to batch-vs-competition step-0 timing (comp 20 steps / batch 19). `Re86Dynamic` /
`games/re86/detector.py`. L1 confirmed WIN. De-risk CLEAN.

---

@LAT-30LON-10 re86 L2+ — open
[ew]
conf:70
rev:1
sal:4
touched:1
[/ew]
NO solver. L2+ have different target patterns and (levels 3+) multiple pieces / more
cross shapes → multi-piece placement search not yet built. Open.

---

## Session log area

<!-- New session records are appended below. -->
