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
**Status**: L1 + L2 **SOLVED & PORTED to games/ls20/dynamic.py 2026-06-17**. ls20 is a single
"transform-and-deliver" mechanic at every level (block carries shape/color/rotation; changer
tiles cycle them; rings reset a move-timer; deliver to every target with matching attrs =
win). ONE frame-driven solver (`games/ls20/solver.py`) clears L1 (13 moves) and L2 (47 moves):
L1 is a trivial config (1 cross visit), L2 richer (3 visits + 2 ring resets), L3 adds a COLOR
change. **read_spec reads COLOUR + ROTATION from the frame** (validated == ground-truth for
L1/L2/L3) and the planner is multi-attribute. **L3 also carries a PUSHER mechanic** (a colour-1
`gbvqrjtaqo` bar that shoves the block several cells — and on L3 the pusher cell is the ONLY way
out of the start pocket, so it must be used). Pure-BFS can't model the shove, so the dynamic is
CLOSED-LOOP: it verifies the block reaches each predicted cell and, on divergence, RE-PLANS from
the actual position (@LAT20LON30). **L1+L2+L3 all SOLVED in-game** — `_test_multilevel` reaches
**max level 3** (L3 = 1 push + 1 replan) — and **de-risk CLEAN** (diagonal confusion matrix, ls20
10/10, no regression). read_spec also reads SHAPE now (all 3 attrs from the frame, validated == GT
for **L4**), but **L4 is blocked by a PUSHER-TRAP** (8 pusher bars; one reverses the only route) —
the next organ is modelling pushers IN navigation, not more attribute reading. Source:
ls20-9607627b. See @LAT60LON0 (model), @LAT55LON-10 (L1⊂L2), @LAT20LON20 (solver+port), @LAT20LON30
(colour + timer + pusher replan), @LAT20LON40 (shape reading + the L4 pusher-trap).

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
PORTED 2026-06-17 to games/ls20/{solver.py,dynamic.py} (DONE for L1+L2): `solver.read_spec`
reads the spec FROM THE FRAME (block cell = color-12; rings = small color-11 squares, NOT the
wide color-11 timer bar; cross = color-0/1 cluster; targets = color-9 shapes in the play area,
fragments merged, trail excluded; block ROTATION read from the bottom-left color-9 preview
panel downscaled to 3×3 and rotation-matched to each target's drawn 3×3). `solver.plan` is the
proven planner. The dynamic plans once per level, emits 1 action/frame (1-indexed solver →
0-indexed supervisor via a−1; this off-by-one was the porting bug), abort-safe (expect frame
change), defers to the floor when read_spec/plan returns None (e.g. a target needs a
shape/COLOR change — L3+). VALIDATED: `_test_ls20_port.py` (read_spec == ground truth for
L1/L2; plan clears both in-game), `_test_multilevel.py ls20` → max level 2, `_test_dynamics.py`
CLEAN. NEXT (L3+): read shape/color deltas from the frame (identify the shape/color changer
tiles + cycle by observation); the planner already supports multi-attr/multi-target.

@LAT20LON30 ls20 — COLOUR reading + frame-timer + the L3 PUSHER (2026-06-17)
[ew]
conf:235
rev:1
sal:7
touched:1
[/ew]
Extended the port to read COLOUR (and keep ROTATION) from the frame — read_spec == ground
truth for L1, L2 AND L3 (`_test_ls20_port.py 3`). The decode (source `tnkekoeuk` etc.):
- PALETTE = [12,9,14,8] is a FIXED module constant = the colour CYCLE order; a colour-changer
  visit advances the index by 1. These four are the ONLY palette colours that appear INSIDE
  the 10×10 play grid (rows[5,55)×cols[9,59)), and only on three things: the mover (a FIXED
  colour-12 head + colour-9 body — independent of its colour attr, so colour-12 always marks
  the block), the COLOUR-CHANGER (its 5×5 interior shows ≥3 distinct palette colours at once —
  a unique signature), and the TARGETS (each drawn in its required colour). ⇒ cell-based
  detection: scan grid cells; block cell excluded; ≥3 palette colours ⇒ colour-changer;
  otherwise a target whose dominant palette colour = its required colour. ROT-changer (cross)
  = the colour-0/1 cell.
- BLOCK colour = which palette colour the LEFT-MARGIN preview (rows≥50, cols<9, the
  `htkmubhry_2` panel) is painted in (9 at L1/L2 where block colour idx=1; 12 at L3 where idx=0
  — this is why the old colour-9-only reader returned None at L3). colour_delta =
  (target_idx − block_idx) % 4. ROTATION still via the preview silhouette rotation-matched to
  each target's drawn 3×3. SHAPE: deferred (no shape-changer present to calibrate; silhouette
  mismatch under all rotations ⇒ read_spec returns None).
- TIMER is frame-read: `steps` = count of colour-11 columns in row 61 of the bottom bar
  (max 42; StepsDecrement=2 on L2/L3 ⇒ window = 21 moves; seed since_reset = 21 − steps//2 so
  it's correct whether or not a level refills the budget). The planner's ring-interleaving was
  rebuilt: waypoints = cells to LAND on (a repeated changer cell = a re-trigger), delivered by
  a tiny DFS that realises each re-trigger by a plain-neighbour bounce OR a ring detour
  (productive bounce that ALSO resets the timer), backtracking to place single-use ring resets
  where needed. This solves L1 (13) and L2 (45) cleanly in-game.
- L3 is NOT just "+colour": it also has a PUSHER (tag `gbvqrjtaqo`, the colour-1 bar
  `yjgargdic_r`, class `twkzhcfelv`). When the block collides with it, `prpxgfxlcm`/`ullzqnksoj`
  SHOVE the block several cells toward the next wall (a sokoban-slide; here cell(0,0)→(0,5),
  +5). The maze makes this UNAVOIDABLE — col0 is the only highway out of the start pocket and
  (0,0) is its sole exit, so the pusher MUST be used. Pure-cell BFS can't model the shove, so
  the DYNAMIC is CLOSED-LOOP: it precomputes the predicted block-cell path and, on divergence
  (the shove), RE-PLANS from the block's actual position (`_plan_from`); a MAX_REPLANS cap
  latches to the floor if it can't progress. **L3 WON** this way — block→(0,0) [pushed to (0,5)]
  → 1 replan → deliver (49 moves, 1 push, 1 replan). Validated: `_test_multilevel.py ls20` →
  **max level 3**; `_test_dynamics.py --games` CLEAN (diagonal confusion, ls20 10/10, no
  off-target regression); `_test_ls20_port.py 3` (read_spec==GT L1/L2/L3; single-shot plan
  clears L1+L2 — it doesn't replan, so L3 wins only through the dynamic). The closed-loop replan
  is GENERAL: any unmodeled teleport/shove → re-read & re-plan, no per-mechanic code.
  New tool: `_probe_ls20_l3.py` (advances via the solver to dump L3 ground-truth + tiles).

@LAT20LON40 ls20 — SHAPE reading done; L4 blocked by a PUSHER-TRAP (2026-06-17)
[ew]
conf:230
rev:1
sal:6
touched:1
[/ew]
Completed the attribute-reading anatomy: read_spec now reads SHAPE too — all of
shape+colour+rotation come from the frame. SHAPE_CATALOG = the 6 source shape silhouettes
(`ijessuuig`); all 24 (shape,rotation) 3×3 silhouettes are DISTINCT, so `identify(sig)` recovers
BOTH indices from one silhouette. read_spec now classifies every grid cell in ONE scan by its
interior signature: ≥3 palette colours = COLOUR-changer; colour-0 AND colour-1 = ROT-changer
(cross); colour-1 only = PUSHER bar (skip — not a changer); colour-0 only = SHAPE-changer
(`mkjdaccuuf`); a single palette colour = a target (identify→its shape+rot, colour from palette).
deltas = [(ts−bs)%6, (tc−bc)%4, (tr−br)%4]. VALIDATED == ground truth for **L4** (block
shape4/col2/rot0 → target shape5/col1/rot0 ⇒ deltas [1,3,0]; SHAPE-changer@(5,3),
COLOUR-changer@(5,5)) and still == GT for L1/L2/L3; de-risk CLEAN, no regression.
**But L4 is NOT solved**: it has 8 PUSHER bars and one is a REVERSING TRAP — at cell (7,9) the
only short route goes LEFT into the pusher at (7,7), which shoves the block right back to (7,9).
Closed-loop replan can't escape (re-plans the same reversed move forever, draining the timer), so
the dynamic now FAILS FAST: if a divergence re-plans FROM a cell already re-planned from
(`_replan_cells`), it latches to the floor instead of thrashing. ⇒ the TRUE next organ is
**modelling the pushers IN navigation** (read each bar's position+direction from the frame; make
BFS transitions reflect the shove, so it routes around reversing traps and exploits helpful
ones), not more attribute reading. New tool: `_probe_ls20_level.py` (advance via solver+replan to
any level N; dump GT, tiles, and un-modelled sprites).

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
