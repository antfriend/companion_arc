# LOCUS — wa30 Game Companion

Per-game companion for wa30 (ARC-AGI-3). Canonical record of wa30's elements,
goals, and dynamics — the source of truth the functional code (`games/wa30/
detector.py`, `games/wa30/dynamic.py`) evolves around. Keep this file in sync when
refactoring game code.

Cross-game overview lives in companion_arcprize.md (Dynamics Catalog).

**To invoke**: start any message with `@LOCUS`.

```mmpdb
db_id: ttdb:companion:locus:wa30:v1
db_name: "LOCUS — wa30 Game Companion"
coord_increment:
  lat: 10
  lon: 10
collision_policy: southeast_step
timestamp_kind: unix_utc
umwelt:
  umwelt_id: umwelt:companion:locus:wa30:v1
  role: game_companion_wa30
  perspective: "LOCUS grounded in wa30 game knowledge. Tracks elements, win condition, per-level dynamics, the solver shape, and what remains unknown."
  scope: "wa30 only. Elements, goals, dynamics, solver state, and session records for all wa30 instances and levels."
  constraints:
    - "Only claim to know what is written in this file."
    - "Records are confidence-tagged: high conf = confirmed from game source or repeated wins; low conf = hypothesis / open problem (the first targets each session)."
    - "Elements/dynamics are frame-structural (colors, counts, bbox relations) — translation/recolor independent. Re-detect from the first frame; never hardcode canonical coordinates."
    - "When game code is refactored, update the matching record and increment rev."
  globe:
    frame: "wa30_globe"
    origin: "The agent — at the intersection of element knowledge and verified solving."
    mapping: "Latitude = certainty (N = confirmed / understood; S = uncertain / open). Longitude = scope (W = elements & mechanics; E = goal & solver route)."
```

---

## Summary (glance)

**Type**: pickup-and-deliver puzzle (a cursor carries items to a drop zone).
**Status**: L1 SOLVED (adaptive greedy BFS, PLAN-ONCE+abort Dynamic, de-risk CLEAN,
registered). L2+ UNSOLVED — adversaries move items autonomously. Source: wa30-ee6fef47.

---

@LAT20LON-10 wa30 elements
[ew]
conf:240
rev:1
sal:3
touched:1
[/ew]
Step size `celomdfhbh = 4` — all game positions are multiples of 4; game (x,y) maps
directly to frame[y][x] (NO camera offset). BACKGROUND_COLOR=1, PADDING_COLOR=0.
- CURSOR ("wppuejnwhl", 4×4): color-14 body + a color-0 directional EDGE (the 4-pixel
  edge row/col gives facing: top edge=rot0, bottom=rot180, right=rot90, left=rot270).
- ITEM ("pktgsotzmw", 4×4, tag "geezpjgiyd"): color-4 outer border + color-9 interior;
  collidable (blocks the cursor).
- DROP ZONE ("jigtxgzhwt", tag "fsjjayjoeg"): color-9 border + color-2 interior;
  NON-collidable (cursor moves freely over it).
- PROGRESS BAR: frame row 63 (color-7 = steps remaining, color-4 = expired). NOTE: row 63
  color-4 is NOT an item — restrict item detection to rows 0–62.

---

@LAT20LON0 wa30 goal / win condition
[ew]
conf:240
rev:1
sal:3
touched:1
[/ew]
WIN = ALL items (tag geezpjgiyd) sit at grid-aligned positions within the drop-zone
sprite bounds AND are detached (dropped). Fires immediately when the last item is dropped
in zone. Actions: 0=UP(dy-4), 1=DOWN(dy+4), 2=LEFT(dx-4), 3=RIGHT(dx+4), 4=PICKUP/DROP.
PICKUP: ACTION5 with the cursor facing an adjacent item attaches it (moves with cursor);
ACTION5 while carrying drops it. Cursor rotation updates only when NOT carrying.

---

@LAT20LON10 wa30 L1 dynamics + solver
[ew]
conf:235
rev:1
sal:4
touched:1
[/ew]
L1 = no adversaries; just route each item to the zone. SOLVER (PLAN-ONCE + abortable
replay — a carried item still reads as a loose color-4 so per-frame re-derivation is
ambiguous; the plan-once route + abort caps downside): greedy nearest-item BFS
pickup-and-deliver. Detect cursor pos + items + valid drop slots from color signatures,
then for each item: face it, ACTION5 (pickup), BFS to a free drop slot, ACTION5 (drop).
`Wa30Dynamic` / `games/wa30/detector.py compute_route(state, 1)`. L1 confirmed WIN,
30-step route on ee6fef47, score 2.22. De-risk CLEAN. Recall is translation-biased
toward canonical positions but precision is clean (defers to explorer otherwise).

---

@LAT-30LON-10 wa30 L2+ — ADVERSARIES (open)
[ew]
conf:70
rev:1
sal:4
touched:1
[/ew]
NO solver. L2+ introduce adversary sprites (tags "kdweefinfi", "ysysltqlke") that
autonomously MOVE items — so a plan-once delivery route desyncs (items relocate between
plan and execution). L2 baseline = 119 steps. Needs closed-loop, adversary-aware
re-planning (re-derive item positions every step and re-route), an UNSOLVED shape here
because a carried vs loose item are not yet disambiguated frame-structurally.

---

## Session log area

<!-- New session records are appended below. -->
