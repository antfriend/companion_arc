# LOCUS — g50t Game Companion

Per-game companion for g50t (ARC-AGI-3). Canonical record of g50t's elements,
goals, and dynamics — the source of truth the functional code (`games/g50t/
detector.py`, `games/g50t/dynamic.py`) evolves around. Keep this file in sync when
refactoring game code.

Cross-game overview lives in companion_arcprize.md (Dynamics Catalog).

**To invoke**: start any message with `@LOCUS`.

```mmpdb
db_id: ttdb:companion:locus:g50t:v1
db_name: "LOCUS — g50t Game Companion"
coord_increment:
  lat: 10
  lon: 10
collision_policy: southeast_step
timestamp_kind: unix_utc
umwelt:
  umwelt_id: umwelt:companion:locus:g50t:v1
  role: game_companion_g50t
  perspective: "LOCUS grounded in g50t game knowledge. Tracks elements, win condition, per-level dynamics, the solver shape, and what remains unknown."
  scope: "g50t only. Elements, goals, dynamics, solver state, and session records for all g50t instances and levels."
  constraints:
    - "Only claim to know what is written in this file."
    - "Records are confidence-tagged: high conf = confirmed from game source or repeated wins; low conf = hypothesis / open problem (the first targets each session)."
    - "Elements/dynamics are frame-structural (colors, counts, bbox relations) — translation/recolor independent. Re-detect from the first frame; never hardcode canonical coordinates."
    - "When game code is refactored, update the matching record and increment rev."
  globe:
    frame: "g50t_globe"
    origin: "The agent — at the intersection of element knowledge and verified solving."
    mapping: "Latitude = certainty (N = confirmed / understood; S = uncertain / open). Longitude = scope (W = elements & mechanics; E = goal & solver route)."
```

---

## Summary (glance)

**Type**: RECORDING / REPLAY maze. Record a path, submit it (ACTION5) to spawn a GHOST
that replays it (e.g. to hold a door/button open), then navigate the goal to the target.
**Status**: L1 + L2 SOLVED (PLAN-ONCE choreographed Dynamic + frame-gated relative-move
routes, de-risk CLEAN, _test_multilevel max level 2). L3+ UNSOLVED.

---

@LAT-10LON10 g50t L2 — SOLVED 2026-06-23 (two-ghost / two-door / three-stage)
[ew]
conf:210
rev:1
sal:5
touched:1
[/ew]
L2 is a 2-GHOST 2-DOOR variant with THREE recording stages (verified from source —
`drofvwhbxb` has 3 stage sprites; the controller `qxlodtievc` clones a ghost on each
non-final submit and freezes them on the final). Elements (this instance, x,y):
goal start (49,25); tracker (24,18) → win cell (25,19); buttons (37,25) & (13,37);
doors (13,19) & (37,49). Both doors are NON-latching (door sprite `kjrcloicja` centre
pixel = 8 ≠ 11; latching needs centre==11, as seen in L3's `color_remap(None,11)`).
Geometry: button (37,25) opens door (37,49) → exposes the bottom corridor with button
(13,37); button (13,37) opens door (13,19) → the tracker room (otherwise sealed).
MECHANIC: ghosts replay one recorded step PER PLAYER MOVE, indexed by the player's
move count this stage; a path step into a shut door is LOST (index still advances →
permanent desync), and a NO-OP/wall-bump player move returns early WITHOUT advancing
ghosts. So both ghosts must be recorded (stage0→buttonA, stage1→buttonB), and in
stage2 the player must make ≥12 REAL moves (so ghost2 seats buttonB) before crossing
door-B. WIN fires when goal == tracker+(1,1); the engine registers the level on the
NEXT step (sets a flag, advances on the following action).
ROUTE (relative moves, simple-action indices 0=U 1=D 2=L 3=R 4=SUBMIT), verified
end-to-end (level_index 1→2): `[2,2,4, 1,1,1,1,2,2,2,2,0,0,2,2,4, 0,0,0,2,2,2,2,2,2,2,1,1, 3,3,3]`.
Relative moves → translation-invariant (like the L1 route); instance-structure-specific
otherwise. L1-vs-L2 read from frame: L1 has ONE merged color-8 region (button welded to
door), L2 has TWO color-8 door regions (`_door_components`). In `games/g50t/dynamic.py`.

---

@LAT20LON-10 g50t elements
[ew]
conf:230
rev:1
sal:3
touched:1
[/ew]
Move step `jarvstobjt = 6` px per action.
- GOAL CURSOR ("qftsebtxuc", 7×7) — the player-moved token; starts inside the player body.
- PLAYER BODY ("vsrojdvivb", 38×50, color-5) — the traversable region; its non-transparent
  pixels define valid goal positions (a wide-top / narrow-middle / wide-bottom corridor).
- TRACKER ("gilbljmfbc", 9×9, color reference) — the win anchor.
- DOOR ("kjrcloicja", 7×7) — obstacle; rotation 270 → opens RIGHT when its button is held.
- BUTTON ("medyellngi", 7×7) — opens the door while the goal/ghost center is inside it.
- STAGE BUTTONS ("gpkhwmwioo") — recording-stage indicators.
- GHOST (color-8 interior) — replay of the submitted path; ghost step N fires on the
  player's move N; holds last position when its path is exhausted.

---

@LAT20LON0 g50t goal / win condition
[ew]
conf:230
rev:1
sal:3
touched:1
[/ew]
WIN = the goal reaches tracker_pos + (1,1) (e.g. tracker at (42,48) → win cell (43,49)).
Door behaviour: `dpdubazedr=False` ⇒ the door stays open ONLY while the button is occupied
→ a ghost must HOLD the button while the player walks through. Actions (indices 0–4):
0=UP, 1=DOWN, 2=LEFT, 3=RIGHT, 4=SUBMIT(ACTION5).

---

@LAT20LON10 g50t L1 dynamics + solver
[ew]
conf:225
rev:1
sal:4
touched:1
[/ew]
Two-phase choreography. Phase 1 (record): RIGHT×4 walks the goal onto the button, then
ACTION5 submits → spawns a ghost replaying [RIGHT×4]. Phase 2 (replay): as the player
moves, the ghost re-walks onto the button and holds the door open; DOWN×7 + RIGHT×5 walks
the goal to the win cell. CONFIRMED route (a049952): `[3,3,3,3,4,1,1,1,1,1,1,1,3,3,3,3,3]`
= RIGHT×4, ACTION5, DOWN×7, RIGHT×5 (17 actions), local score 100.0 (uncapped ratio).
SOLVER (PLAN-ONCE + abort — self-occluding choreography, can't re-derive cleanly). The
de-risk gate REJECTED a naive recognizer (the 3×3 button merged with the door's color-8)
and was FIXED with a most-isolated-3×3-window finder. `G50tDynamic` / `games/g50t/`.
De-risk CLEAN.

---

@LAT-30LON-10 g50t L2+ — open
[ew]
conf:70
rev:1
sal:4
touched:1
[/ew]
NO solver. L2 has the tracker at (24,18), TWO doors, and a different layout → needs a
general record-and-replay planner (find a path, identify which button(s) need holding,
record the holding path, then route) rather than a hardcoded sequence. Open.

---

## Session log area

<!-- New session records are appended below. -->
