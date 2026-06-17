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
**Status**: L1 + L2 **SOLVED 2026-06-17 by ONE unified level-agnostic solver**
(`_solve_ls20.py`): ls20 is a single "transform-and-deliver" mechanic at every level (block
carries shape/color/rotation; changer tiles cycle them; rings reset a move-timer; deliver to
every target with matching attrs = win). L1 is a TRIVIAL config of it (1 cross visit), L2 a
richer one (3 visits + 2 ring resets), L3 adds color changes — same core, growing config.
Decoded from source + validated in-game (L1 13 moves, L2 47 moves). Not yet ported to
dynamic.py (the remaining ship step). Source: ls20-9607627b. See @LAT60LON0 (model),
@LAT55LON-10 (L1⊂L2), @LAT20LON20 (unified solver + port plan).

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

NOTE 2026-06-17: this "entity2 entry at STATE 0" framing is the OLD per-level model.
The TRUE model (below) shows L1 is just a trivial config of the L2 transform-and-deliver
mechanic — the unified solver supersedes this detector. Kept for history.

---

@LAT55LON-10 ls20 L1 = trivial subset of the L2 mechanic (2026-06-17)
[ew]
conf:240
rev:1
sal:6
touched:1
[/ew]
L1 IS THE SAME "transform-and-deliver" mechanic as L2 (@LAT60LON0) — `step()`/`pbznecvnfr`
are level-agnostic; levels differ only in CONFIGURATION. L1 spec (instance 9607627b, from
`_probe_ls20_state.py 1`): block shape5/color1/**rot3** @game(34,45); ONE target
shape5/color1/**rot0** @(34,10); a rotation-changer (cross) @(19,30); NO rings. Shape+color
already match ⇒ need exactly **+1 cross visit** (rot 3→0), then deliver. So L1 = (1 changer
visit + delivery), L2 = (3 changer visits + 2 ring resets + delivery), L3 = (color + rotation
changes + 2 rings) — ONE solver, growing configs. The unified planner (@LAT20LON20) clears
L1 in 13 moves WITHOUT any L1-specific code. ⇒ build ls20's dynamic as ONE core
transform-and-deliver solver; each new level adds/refines config-handling (more targets,
shape/color changers, timer routing), never a new per-level route.

---

## L2 dynamics + open problem

@LAT30LON10 ls20 L2 — closed-loop navigation + collection mechanics (VALIDATED 2026-06-17)
[ew]
conf:235
rev:1
sal:6
touched:1
[/ew]
BREAKTHROUGH (explore.py + `_research_ls20_l2.py`, instance 9607627b): the L2 bottleneck
was NAVIGATION, and it is now SOLVED with a map-based BFS — all primitives validated in-game.
- GRID: 5px logical cells. Row-cells at rows {5,10,…,50}; col-cells at cols {9,14,…,54}.
  The block (color-12, 5px wide × 2 tall "head" + a color-9 trail filling its cell) moves
  exactly ONE cell (5px) per action: a1=UP a2=DOWN a3=LEFT a4=RIGHT.
- PASSABILITY: color-3 (track) AND color-5 (floor) are PASSABLE for the block; color-4 =
  void = blocked. (So the goal-room color-3 "walls" are themselves passable — see win note.)
  Build the map by majority-non-void colour per 5×5 cell; BFS over cells. Validated: the
  BFS route was followed move-for-move in the live game.
- CROSS COLLECTION: the block COLLECTS the cross (color-0/1 box) by LANDING ON its cell;
  the box vanishes, and it RESPAWNS the instant the block steps off → re-collectable by
  oscillating on/off (this is the recipe's "cross ×N visits"). Validated.
- RING COLLECTION (ring A upper @cell r15c14; ring B lower @cell r50c39): landing on a ring
  RESETS the timer (c11 jumped 56→92). Validated for both. This is how the multi-window
  route refreshes the budget.
- TIMER: color-11 bottom bar ≈100 units, −4/move ⇒ ~25 moves/window. A clean BFS reaches
  the cross in 17 moves (1 window). Timer expiry → full reset (block snaps to start).
- VALIDATED ROUTES (from L2 start, explore tokens): to the CROSS = `1 4 1 1 1 1 1 4 4 2 4 2
  2 2 2 2 2` (17 moves, collects it); to RING A = `1 4 1 1 1 1 1 3 3 3 3` then `3` onto it.

@LAT60LON0 ls20 L2 — SOLVED: transform-and-deliver model (decoded from source + WON 2026-06-17)
[ew]
conf:245
rev:1
sal:7
touched:1
[/ew]
**L2 WON by a closed-loop planner (first non-open-loop win).** The mechanic, decoded from
the game source (`pbznecvnfr`/`bejndxqqzf`/`txnfzvzetn`) and confirmed by reading the live
game object (`_probe_ls20_state.py`):
- The BLOCK carries a transformable state: SHAPE (`fwckfzsyc`), COLOR (`hiaauhahz`),
  ROTATION (`cklxociuu`). Each is CYCLED by stepping the block onto a changer tile:
  SHAPE-changer (tag ttfwljgohq), COLOR-changer (soyhouuebz), ROTATION-changer = THE CROSS
  (rhsxkxzdjz, color-0/1 box; `cklxociuu=(cklxociuu+1)%4`). RINGS (npxgalaybz, color-11)
  RESET the timer and are SINGLE-USE (removed on collection). WALL = tag ihdgageizm.
- Each TARGET (tag rjlbuycveu) requires a specific (shape,color,rotation) and is RENDERED
  with that required appearance (so a solver can read each target's requirement from how it
  is drawn). A target REJECTS (blocks) a non-matching block — that was the earlier "entry
  NO-OP". WIN = deliver the block onto EVERY target position with all three attrs matching
  (`bejndxqqzf`). The "goal-room inner pattern" is just the target's required appearance.
- TIMER EXPIRY resets the block position AND its shape/color/rotation (`qetwzqzzik`) — so a
  win must be completed within the available ring resets; expiry is pure loss of progress.
- THIS INSTANCE (9607627b) L2 SPEC (from _probe_ls20_state.py): block at game(29,40)
  shape5/color1/rot0; ONE target at game(14,40) requiring shape5/color1/**rot3**; only the
  CROSS exists (no shape/color changers) ⇒ need exactly **+3 cross visits**; rings at
  game(15,16)=ringA & (40,51)=ringB; cross at (49,45). #shapes=6 #colors=4 rot∈{0,90,180,270}.

@LAT20LON20 ls20 — UNIFIED level-agnostic CORE-DYNAMICS solver (L1+L2 solved 2026-06-17)
[ew]
conf:240
rev:3
sal:7
touched:1
[/ew]
**ONE solver clears L1 AND L2** (`_solve_ls20.py`): L1 is a TRIVIAL CONFIG of the L2 model
(see @LAT55LON-10), so a single level-agnostic planner handles both — the design goal. It
reads the per-level spec (block attrs; per-target required attrs; changer/ring/target/wall
cells), builds the 5px-cell passability map, and plans transform-and-deliver with timer-aware
ring interleaving. Results: L1 SOLVED 13 moves, L2 SOLVED 47 moves (both validated by playing
the real game to `levels_completed`++). L3 uses the SAME dynamics (now also a COLOR changer:
block shape5/color0/rot0 → target shape5/color1/rot2) and is planned correctly but expires —
only the timer-routing needs polish, NO new mechanic. This is the "core dynamics, extended
per level" architecture working.
PLANNER (the core algorithm):
  1. order targets (nearest first); for each, for each attr (shape,color,rotation): compute
     need=(req-cur)%N; append `need` visits to the nearest changer of that type (repeated
     visits bounce off a neighbour to re-trigger); then append the target as a delivery wp.
  2. WALK the waypoints over BFS legs that AVOID changers+targets in transit (crossing a
     changer mutates attrs; a non-matching target bounces) but MAY cross rings (a crossed
     ring is a free timer RESET, accounted for).
  3. TIMER: ~100 units, −4/move, window≈23 moves. Invariant — keep a ring reachable: if
     finishing a leg would leave the nearest remaining ring unreachable while work remains,
     detour to a ring NOW (single-use). Plus a safety detour if a leg's ring-free prefix
     would itself exceed the window.
PORT TO games/ls20/dynamic.py (the only remaining step to ship): replace the hardcoded
_L2_ROUTE/_L1 detector with this planner, reading the spec FROM THE FRAME (block attrs from
the block/preview appearance; each target's required attrs from how it is drawn — both are
rendered, so frame-readable). Re-derive each frame, abort to the explorer floor on
divergence; recognition-gated + additive-safe; gate on `_test_dynamics.py`. The prototype
reads the spec from the game object for validation; the frame-reading layer is the port work.
Generalizes by construction to multi-target and shape/color changers (L3+).

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

@LAT-40LON10 ls20 L2 — rings/cross/timer (SUPERSEDED by @LAT60LON0/@LAT20LON20, 2026-06-17)
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
