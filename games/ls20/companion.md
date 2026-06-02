# LOCUS — ls20 Game Companion

Per-game companion for ls20 (ARC-AGI-3). This file holds all ls20-specific
knowledge: level maps, strategies, session logs, and revision state. LOCUS
loads only this file when playing ls20, keeping the context tight.

Cross-game overview lives in companion_arcprize.md.

**To invoke**: start any message with `@LOCUS`.

```mmpdb
db_id: ttdb:companion:locus:ls20:v1
db_name: "LOCUS — ls20 Game Companion"
coord_increment:
  lat: 10
  lon: 10
collision_policy: southeast_step
timestamp_kind: unix_utc
umwelt:
  umwelt_id: umwelt:companion:locus:ls20:v1
  role: game_companion_ls20
  perspective: "LOCUS grounded in ls20 game knowledge. Tracks level mechanics, verified step outcomes, and winning routes across sessions."
  scope: "ls20 only. Level maps, strategies, step-verification logs, and session records for all ls20 instances."
  constraints:
    - "Only claim to know what is written in this file."
    - "Each route step has a verify_step outcome (success/fail + reason). Failed steps inform recovery strategy."
    - "A StepResult.success=False means the block did not move as expected — record the action and reason."
    - "Routes are instance-specific: always re-detect state from first frame and recompute before executing."
    - "Write StepResult logs to the active session record after each level attempt."
  globe:
    frame: "ls20_globe"
    origin: "The agent — positioned at the intersection of level knowledge and verified execution."
    mapping: "Latitude = certainty (N = confirmed; S = uncertain). Longitude = scope (W = level mechanics; E = routes / strategies)."
```

---

## Known mechanics

@LAT-10LON-10 ls20 grid constants
[ew]
conf:240
rev:1
sal:3
touched:1
[/ew]
BLOCK=12 (2 rows × 5 cols player block)
WALL=3 (ring boundaries, corridor walls)
FLOOR=5 (passable interior)
ENT1=9 (entity1 carrier, rows 55-60 cols 1-10)
TIMER=11 (countdown cells, row 61-62)
VOID=4 (impassable background)

Action space (simple): 0=UP  1=DOWN  2=LEFT  3=RIGHT

---

## L1 strategy

@LAT-10LON10 L1 winning strategy
[ew]
conf:250
rev:3
sal:5
touched:1
[/ew]
Straight UP from start into entity2 interior. Block stays in cols ~34-38;
cluster is at cols ~20-22 — they never overlap. Entity1 stays STATE 0.
Entity2 entry at STATE 0 = L1 WIN.

Route is adaptive: computed from first frame by detector.compute_route(state).
Typical: UP×7 from start row ~40-41. Varies by instance.

verify_step check: after each UP, block.row must decrease. If blocked
(row unchanged), the ring wall has been reached — stop or recover.

---

## Session log area

<!-- New session records are appended below by locus_apply_updates -->
