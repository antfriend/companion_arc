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

## Summary (glance)

**Type**: push-block maze with collectibles, rotating inner ring, and a countdown timer.
**Status**: L1 SOLVED (adaptive route, 41+ wins, registered Dynamic). L2 SOLVED IN TRAINING
(123-action route) but FAILS IN COMPETITION (Phase-3 desync after the oscillation reset) —
the standing open problem. Source: ls20-9607627b. Extensive L2 session logs live in
companion_arcprize.md.

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

## L2 dynamics + open problem

@LAT-30LON-10 ls20 L2 — empirical action model + block corridor (explore.py 2026-06-17)
[ew]
conf:205
rev:1
sal:4
touched:1
[/ew]
Confirmed live via `explore.py` (session ls20L2, instance 9607627b, `goto --level 2` then
single-action probes + `watch 12 9 11`):
- ACTION MODEL: a1=UP, a4=RIGHT move the BLOCK (color-12, 5-wide×2-tall) by ONE cell = 5px.
  a2=DOWN and a3=LEFT are BLOCKED at the L2 start (void on those sides) — they tick the
  timer but do not move the block. (So the start is a UP/RIGHT-only pocket.)
- TIMER (color-11 bottom bar) ≈ 100 cells, drains ~4/step ⇒ ~25 moves per timer window
  before expiry/reset. Collecting a ring resets it (see @LAT-40LON10).
- ENTITY1 (color-9, in the goal room) shifts its centroid in the block's movement
  direction each step — the "trail attraction" tracking; it is NOT independently steerable.
- OPENING CORRIDOR (confirmed): from start (block rows 40-41 cols 29-33) UP alone climbs
  only ONE cell (to row 35) then blocks (void above cols 29-33). The vertical corridor is
  at cols 34-38: `RIGHT` (→cols 34-38) then `UP×7` climbs to row 5 (top), then blocks.
  This is the concrete "route via c34" the open-loop route assumes.
- L2 START LAYOUT (this instance): block rows 40-41 c29-33; goal room (color-5 floor in
  color-3 walls) rows 38-46 c12-20 with the inner color-9 pattern at rows 41-43 c15-17;
  rings (color-11, 3×3 notched) at (16-18,14-16) and (51-53,38-40); state-changer/cross
  (color-0/1 box) at rows 46-48 c49-52; walls color-3, void color-4, floor color-5.
PLAYTHROUGH PROBE (explore.py `goto --level 3`, full-library solver, 81 actions → GAME_OVER):
the state-box (cross) at c0/c1 ≈ (row46-47,col50-51) NEVER changed across the entire run —
the block NEVER reached/collected the cross, so entity1 (c9, n=45) state never advanced and
WIN was impossible. A TIMER-EXPIRY FULL RESET was captured (c11 jumps n16→n100; block +
entity1 snap back to start) — the documented oscillation that desyncs the open-loop route.
⇒ THE BOTTLENECK is concretely: navigate the 5-wide block to the cross (lower-right, behind
the void gap) WITHIN the ~21–25-step timer window. The cross is far from the UP/RIGHT start
pocket; reaching it needs the wide top connector (rows 5–14) then a descent on the right —
more than one timer window, so ring collection (timer reset) must be interleaved. This is
the closed-loop adaptive-BFS-for-a-5-wide-block build the open-loop route cannot do.
NEXT PROBE (unverified): once at the cross, `watch 9 11` to confirm the cross→inner-ring 90°
rotation + entity1 state change — the crux of the win condition.

@LAT-40LON10 ls20 L2 — rings/cross/timer (training-solved, competition-open)
[ew]
conf:120
rev:1
sal:5
touched:1
[/ew]
L2 ELEMENTS: a 5-wide push BLOCK (color-12); WALLS color-3; FLOOR color-5; VOID color-4;
a state-changing CROSS ("+"); an inner RING (entity2) whose notch ROTATES 90° each time
the cross is landed on; entity1 STATE (0/1/2); a TIMER (color-11) that counts down and, at
0, RESETS (rings+cross respawn, block resets toward its L2 start). Collecting ring-B / ring-A
RESETS the timer (does NOT game-over). The "+" rotation must align the inner ring with the
block's shape before the block can enter the inner ring.

WIN (training, 123 actions): a choreographed sequence of 5 cross visits + 2 ring-B + 2
ring-A collections that rotates the inner ring so DOWN from r35,c14 → r40,c14 enters it.
Full route in companion_arcprize.md.

OPEN PROBLEM: the `_L2_ROUTE` is a BLIND open-loop plan. In competition it desyncs —
(a) after the timer-expiry OSCILLATION the block resets to a position different from the
training r40,c29 (e.g. r10,c34), so the hardcoded Phase-3 preamble navigates the wrong path
into VOID → GAME_OVER; (b) the probe never actually collects the cross in some instances
(entity1_state stays 0, notch stays 270). FIX (substantial, deferred): a closed-loop
adaptive maze-BFS that navigates the 5-wide block through OPEN cells + state-driven cross
collection (collect until entity1_state/notch == target) + timer management. The Dynamic is
LEVEL-AWARE (`self._level`, `set_level`) and emits a canonical probe before planning, but
the L2 plan itself is not yet closed-loop.

---

## Session log area

<!-- New session records are appended below by locus_apply_updates -->
