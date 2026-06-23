# One Mechanic, One Solver — A Plan for Universal Pattern A

*Date opened: 2026-06-23*

> A locksmith who keeps a labelled key for every door he has ever opened has not
> understood locks. He has a heavy ring and a good memory, and the first unfamiliar
> door defeats him. The locksmith who understands locks carries one set of picks and
> a model of how tumblers fall; every door — including the ones he has opened before —
> is the same problem at a different setting. We have been collecting keys. This is
> the order to start carrying picks.

---

## 0. The thesis

A game is **not solved** because we can win its levels. It is solved when **one
frame-parameterized mechanic model + one planner** wins its levels, with each level
(L1 included) falling out as a *configuration* of that model rather than a branch in
our code. Winning L2 with an `if`-gated, hand-tuned, or hardcoded second algorithm is
**reconnaissance that happens to score** — a good start, but it is owed an evolution.

We name the two states from the 2026-06-23 review:

- **Pattern A — Unified.** One model, one planner; L1 is the degenerate instance.
  Today: `ls20`, `tu93`, `re86`, `ar25`, `sk48`.
- **Pattern B — Branched.** A frame discriminator routes L1 frames to the original
  L1 logic and L2 frames to a *disjoint* routine that does not reuse it. Today:
  `wa30`, `sp80`, `g50t`. (`g50t` is the extreme case: its L2 "plan" is a literal
  action sequence.)

**New definition of done:** *a game is "solved through level L" only if its dynamic is
Pattern A through level L.* Pattern B counts as **"reached L, not solved L"** on the
crow's nest and must be tracked as debt until it evolves.

---

## 1. The acceptance criteria (what "Pattern A" means, testably)

A dynamic is Pattern A through level L iff:

- **A1 — One reader.** `read_state(frame) -> params | None` extracts the mechanic's
  parameters (entities, counts, geometry, goal) from the frame with **no level
  argument that selects different code**. A level *hint* may parameterize search
  bounds; it may not pick the algorithm.
- **A2 — One planner.** `plan(params)` (or per-frame re-derivation) computes the
  solution by **search / BFS / constraint-solve over a forward model** — **no fixed
  action literals**, **no `if level == k`**, **no count-based dispatch to a second
  algorithm**.
- **A3 — L1 is a strict instance.** Running the planner on an L1 frame reproduces the
  L1 win (verify **byte-identical** action stream against the pre-refactor solver
  where possible — the `ar25`/`re86` standard).
- **A4 — Variant-general.** The solver wins **structurally perturbed** instances of
  the same mechanic, not only the canonical local ones (see §3 tests).
- **A5 — Laws intact.** Additive (abort-to-floor) holds, `_test_falsefire` clean for
  the recognizer, `_test_pollution` clean.

**The litmus test (the single question that separates A from B):** *delete the level/
count gate and run the L2 path on the L1 frame — does it still win?* If yes, A. If the
L2 path cannot handle L1 (or vice-versa), it is B.

---

## 2. The frame-sufficiency gate (a game that cannot be A)

Some mechanics hide the information the planner needs **in the frame itself**. These
cannot be Pattern A and must not be reported as "solved":

- **`cn04` L2** — connector *type* (8 vs 13) is erased by the display remap and a
  matched cell renders green for any coincidence, so 28 of 32 geometric assemblies are
  frame-indistinguishable decoys (verified 2026-06-23). No planner can choose the
  winner from frames. **Status: frame-insufficient → DEFERRED, not solved.**

So the taxonomy is three-way: **Pattern A (solved)** · **Pattern B (reached, debt)** ·
**frame-insufficient (deferred, unsolvable from frames as drawn)**. The strategy below
applies to Pattern B. A frame-insufficient game is closed with a documented wall, not a
solver.

---

## 3. The guardrails (tests that define and defend Pattern A)

Two new gates, added before any refactor so the evolution is measured, not asserted:

1. **`tests/_test_unification.py` (structural lint).** Grep each
   `games/*/dynamic.py` for the Pattern-B smells and fail on them for any game listed
   as "solved":
   - a list of >3 integer action literals assigned as a route (`= [2, 2, 4, ...]`),
   - `self._level ==` / `level ==` / `== 2` algorithm switches,
   - a count-or-presence gate (`len(...) > 1`, `_door_components(...) == 2`,
     `color-12 present`) that selects between two `next_action` code paths.
   This is intentionally blunt: it flags exactly the three current B games and any
   regression toward them. A game graduates only when its entry disappears from the
   lint **and** it stays green on the behavioral gates.

2. **`tests/_test_variants.py` (behavioral generality).** For each solved game, win
   **perturbed** copies of every currently-won level:
   - **translation** (shift all sprite positions; cheap, catches hardcoded pixel
     coords),
   - **recolor** (permute the non-structural palette; catches hardcoded colors),
   - **structure** where a generator exists (e.g. `g50t`: random corridor/door/button
     mazes of the same mechanic — the only perturbation that catches a translation-
     invariant *fixed route*).
   Pattern A must pass all three; translation+recolor are universal, structure is
   required wherever the mechanic admits a generator.

   Note for honesty: translation+recolor alone do **not** catch `g50t`'s fixed route
   (it is relative-move, palette-blind). `g50t` is therefore the one game whose
   Pattern-A claim **requires** the structural generator — which is also exactly the
   work that makes it Pattern A. The test and the fix are the same lever.

The existing crow's nest (`_test_multilevel.py`) keeps its meaning but its column is
re-read: **"max level"** is split into **"max level reached"** and **"max level
*solved* (Pattern A)."** Today the second column would read: ls20 3, tu93/re86/ar25/
sk48 2, and wa30/sp80/g50t **1** (reached 2).

---

## 4. The general refactor recipe (Pattern B → A)

The same six moves for every game; the difficulty is entirely in steps 3–4.

1. **Name the parameters.** Write down the mechanic as `(entities, geometry, goal,
   dynamics-constants)` — the thing the engine source actually checks for a win.
2. **Write the level-free reader.** `read_state(frame)` returns those params or `None`.
   Detect entities by *structure* (counts, bbox relations, connectivity), never by
   canonical coordinate. This subsumes both levels' detection.
3. **Write the forward model.** A pure function `apply(state, action) -> state` (or the
   win predicate over a final configuration) faithful to the engine. This is where the
   reverse-engineering already done per game gets cashed in.
4. **Write the planner.** Search/BFS/constraint-solve over the forward model to a win.
   No literals. For plan-once games this returns a route; for re-derivation games it
   returns the next step. The planner must be *correct at N=1*, which is L1.
5. **Collapse L1 into it.** Delete the L1 branch and the gate. Run the planner on L1;
   assert byte-identical (A3). If not byte-identical, prove the new stream also wins
   and update the companion's "canonical route."
6. **Lock it in.** Add the structural generator to `_test_variants.py`; confirm
   `_test_unification`, `_test_falsefire`, `_test_pollution`, `_test_multilevel` green;
   update `games/<g>/companion.md` and memory; flip the game's status to "solved L2."

---

## 5. Per-game plans (ordered by lift, ascending)

### 5.1 `wa30` — *easiest; the L2 solver likely already contains L1*

The L2 cooperative-delivery solver (`_l2_step`) is already a closed-loop, frame-derived,
multi-agent delivery planner. The only thing making it Pattern B is the gate
`if len(_adv_cells(f)) > 0` that hands the no-helper case to a separate plan-once route.

- **Hypothesis:** with **zero** helpers, the cooperative solver degenerates correctly —
  the cursor is assigned *all* items (the farthest-from-helper heuristic with `hc = cur`
  becomes farthest-from-cursor ordering) and delivers them. L1 = "cooperative delivery,
  cooperators = {cursor}."
- **Work:** remove the gate; let `_l2_step` run on L1; fix the item-ordering fallback so
  no-helper order is sane; delete the `compute_route` L1 branch and `self._route`.
- **Acceptance:** byte-identical not required (different but valid route is fine if it
  wins); must win L1+L2 and translation/recolor variants of both.
- **Risk:** low. Worst case the no-helper ordering is suboptimal and trips the timer on
  L1 — mitigated by nearest-first ordering when `helper == ∅`.

### 5.2 `sp80` — *medium; replace hardcoded slots with a computed arrangement*

`_arrange` is closed-loop but carries **hardcoded slot offsets** (`_L2_SLOTS_LARGE`,
`_L2_SLOTS_SMALL`) found by offline search — that is a key-ring, not picks. And L1 runs
a separate `nav + _SPILL_ROUTE` choreography.

- **Target model:** a **spill forward-model** — given deflector placements, simulate the
  rising liquid and test whether every color-11 target is wetted. Then **search** piece
  placements (positions × the interchangeable assignment) for a wetting arrangement.
  L1 = the N=1 arrangement (one deflector); L2 = N≥3.
- **Work:** (a) write the spill simulation from the engine source; (b) replace the slot
  constants with a search that *computes* slots from the target geometry; (c) confirm a
  single `SPILL` after correct N=1 placement wins L1 (collapsing the `_SPILL_ROUTE`
  choreography), else fold the choreography into the model; (d) delete the
  `len(_pieces) > 1` gate.
- **Acceptance:** wins L1+L2; the computed L2 slots match the previously-hardcoded ones
  on the local instance (regression check); translation/recolor variants pass.
- **Risk:** medium. The spill simulation must match the engine exactly; the search space
  (placements × assignment) needs pruning by the wetting model. Note the L2 board is
  history-dependent on how L1 was won — the closed-loop re-detect already handles that.

### 5.3 `g50t` — *hardest; build the planner the fixed route stands in for*

Today: a literal `_L2_ROUTE`. This is the largest lift and the one whose Pattern-A
claim the variant test actually depends on.

- **Target model:**
  - **Reader:** goal, tracker (→ win cell = tracker+(1,1)), buttons (3×3 color-8,
    possibly welded to a door), doors (larger color-8 blocks), and a **walkable maze
    graph** (6px-lattice cells where the 7×7 goal footprint lies on floor, doors as
    toggleable blockers). Door/button separation needs care (both are color-8) — use
    component size + the welded-bar heuristic already in `_find_button`.
  - **Forward model (reverse-engineered 2026-06-23, in the companion):** ghosts replay
    one recorded step **per player move**, indexed by move count; a step into a shut
    door is **lost** (permanent desync); a no-op/wall-bump move does **not** advance
    ghosts; a door is open only while its button is held (non-latching here; L3 adds
    latching via center pixel == 11); win registers on the step **after** goal == win
    cell. Stage count = (#buttons that must be co-held) + 1.
  - **Planner:** infer stage count from #doors/#buttons; per record stage, BFS the
    goal→button path respecting which doors are open *in that stage*; in the final stage
    run a **time-aware** search (state = `(goal_cell, t)`) so the player spends enough
    real moves to seat the late ghost before crossing its door.
- **Work:** the maze reader, a faithful internal simulator of the above, and the staged
  time-aware planner. Validate the planner reproduces the verified 31-action route on
  the local instance (A3), then delete `_L2_ROUTE` and the `_door_components == 2` gate
  (which also mis-targets L3 today).
- **Acceptance:** wins L1+L2; wins **synthetic** mazes from the `_test_variants.py`
  generator (the real Pattern-A proof); ideally also makes progress on L3 (latching
  doors) for free, validating generality.
- **Risk:** high — an internal simulator that must match the engine's ghost/door/timing
  exactly. De-risk by reusing the engine offline as an oracle during development (as in
  the 2026-06-23 session) and diffing planner output against engine outcomes.

---

## 6. Sequencing & milestones

1. **M0 — Instrument.** Land `_test_unification.py` + `_test_variants.py` (translation
   + recolor first; generators per game as they come). Re-label the crow's nest with the
   "solved (Pattern A)" column. *Now the debt is visible and regressions are caught.*
2. **M1 — `wa30` → A.** Smallest lift; proves the recipe end-to-end and the "L1 is the
   degenerate case" collapse.
3. **M2 — `sp80` → A.** Spill forward-model + computed slots; removes the first set of
   magic numbers.
4. **M3 — `g50t` → A.** Maze reader + recording simulator + staged time-aware planner;
   add the structural maze generator that the test needs.
5. **Mn — Doctrine forward.** Every *future* level is built Pattern A from the start
   (read_state level-free, planner, no route literals). New games enter the multilevel
   table only in the "solved (Pattern A)" sense.

Each milestone is independently shippable and additive: until a game graduates, its
existing Pattern-B branch keeps winning its levels, so no crow's-nest height is lost en
route — we are upgrading *how* we hold a level, not whether.

---

## 7. What success looks like

The `_test_multilevel.py` "solved (Pattern A)" column reads the same as "reached" for
every game except the frame-insufficient ones, which are honestly marked DEFERRED with a
documented wall. `_test_unification.py` is empty of findings. Every solver in the library
is a model + a planner; there is not one labelled key left on the ring.
