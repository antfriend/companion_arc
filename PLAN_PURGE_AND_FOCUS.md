# The Long Tack Home — A Plan for Universal Purge and Renewed Focus

*Date opened: 2026-06-21*

> A ship had been at sea so long that no one remembered the harbor. The hold
> was full of salvage from a hundred ports, the hull wore a beard of barnacles,
> and the crew steered by a dozen superstitions about the tides — chiefly the
> one that said the ship was *winning* whenever a certain gull (call it 0.18)
> flew past, and *losing* when a lesser gull (0.16) flew instead. They had
> stopped counting leagues to the harbor and started counting gulls.
>
> One morning the captain climbed the mast, found the one true star again, and
> came down with a single order: **everything that does not help us reach the
> harbor goes over the side.** Not because salvage is shameful — it kept us
> alive — but because a ship that steers by gulls never makes landfall.
>
> This is that order, written down.

---

## The One Star (the focus, and the only thing we steer by)

**Solve games. Reach the highest solvable level of every game. Use the same
method to do it in every environment.**

Everything in this repository earns its place by answering *one* question:

> Does this help us solve a game to a higher level?

If yes, it is the hull, the rigging, or the crew. If no, it is barnacle or
superstition, and it goes over the side.

Two kinds of code serve the star, and only two:

1. **The hull — the solving code.** It carries us to harbor. It must be
   **bulletproof**: identical behavior offline, in the competition rerun, and
   during training; no crashes on a malformed frame; never scores *worse* than
   doing nothing (the additive law); one method, everywhere.
2. **The crew — the training code.** It is how we learn new waters — new games
   and new levels. It does not carry cargo to harbor itself; it exists *solely*
   so the hull can reach harbors it could not reach before. It is optimized for
   one thing: turning an unsolved level into a solved one and handing that
   solution to the hull.

The cargo manifest — **the Kaggle dataset — carries only what the hull needs to
sail.** Training tools, session logs, probes, and lore do not board.

### Superstitions we are throwing overboard by name

- **Counting gulls (public score).** 0.08 vs 0.16 vs 0.18 are gulls, not
  leagues. We will not tune, decide, ship, or *feel* anything based on a
  leaderboard delta. The only measure is: *which games reach which level.*
- **Counting strokes (step counting / RHAE).** The `(human_baseline /
  ai_actions)^2` framing in the code and the urge to minimize action count are
  superstition. We solve to the highest level; we do not optimize the number of
  oar-strokes it took. (Reaching a level *at all* is the win; efficiency is not
  the star.)

---

## Phase 0 — Climb the mast (before touching anything)

**Goal:** one page of ground truth so the purge cuts barnacle, not hull.

- [ ] Identify the **live solve path** end to end: which single agent + launcher
      actually plays a game today. (Current best read: `core/general_agent.py`
      as the floor + `core/solve_agent.py` as the recognition-gated solver
      layer, driven for offline batch by `launch_competition.py`, and *inline in
      the notebook* for the competition rerun — see the divergence in Phase 3.)
- [ ] Identify the **live train path** end to end (`launch_training.py` →
      `kaggle_agent.py` → LOCUS).
- [ ] List every **per-game solver** that is real (has a working
      `detector.py`/`dynamic.py`/`solver.py`) vs. stub. Source of truth:
      `core/game_registry.py` and `_test_multilevel.py`.
- [ ] Mark every other file at root and in `core/` as one of: **hull**,
      **crew**, **scratch**, or **lore**.

> Nothing is deleted in Phase 0. We are only drawing the map of what to keep.

---

## Phase 1 — Scrape the barnacles (purge scratch)

**Goal:** the root directory contains only files a newcomer would expect.

Targets (scratch — single-use exploration that has already paid out into a
solver or a memory):

- [ ] All `_probe_*.py` (ar25, cd82, ls20, re86, sp80, tu93, wa30, …) — ~40 files.
- [ ] One-off investigators: `_research_ls20_l2.py`, `_solve_ls20.py`,
      `_sim_tu93_l2.py`, `_dump_tu93_l2.py`, `_dbg_level.py`, `_survey_levels.py`,
      `_analyze_games.py`, `_dl_envs.py`, `_patch_notebook.py`.
- [ ] Score/step-experiment harnesses (the gull-counting rigs):
      `_test_agent_ab.py`, `_test_agent_ab2.py`, `_test_proxy_curve.py`,
      `_test_solve_proxy.py`, `_test_scalar_detect.py`, `_test_winpool.py`,
      `_test_meta_transfer.py`, `_test_perturbed.py`,
      `_test_online_randomization.py`, `_test_instance_variation.py`.

**Keep, but move into a real `tests/` folder** (these are hull-integrity guards,
not barnacle):

- [ ] `_test_multilevel.py` (which game reaches which level — *this is the star
      made measurable*).
- [ ] `_test_pollution.py` (proves the additive law: floor+solver ≥ floor).
- [ ] `_test_falsefire.py` (recognizers don't hijack the wrong game).
- [ ] `_test_hazard_nav.py`, `_test_click_plumbing.py`, `_test_dynamics.py`,
      `_test_levels.py`, `_test_ls20_port.py` — keep the ones that still guard
      live code; drop any whose subject was itself purged.

**Acceptance:** `ls *.py` at root shows only launchers, the live agent entry
points, and genuine utilities. No `_probe_*`. Tests live under `tests/`.

---

## Phase 2 — Strip the dead rigging (purge duplicate/abandoned agents)

**Goal:** exactly one solving brain and one training brain. No "v2", no variants
kept around because they once scored a different gull.

Candidates in `core/` (confirm against Phase 0's live-path map first):

- [ ] `general_agent_v2.py`, `general_agent_dyn.py` — variant explorers.
- [ ] `goal_agent.py` (the 0.10 experiment), `meta_agent.py` (transfer
      experiment) — kept only for score comparisons we are abandoning.
- [ ] Reconcile `click_agent.py` / `solve_agent.py` / `general_agent.py` into the
      single live solve path; fold the click capability in rather than leaving it
      as a parallel agent.

**Acceptance:** `core/` contains one explorer floor, one solver layer, the
per-game `dynamics/`, the registry, and nothing whose only reason to exist was a
leaderboard A/B.

---

## Phase 3 — Reinforce the hull (one bulletproof solving method, everywhere)

**Goal:** the *same* solving code runs offline, in the competition rerun, and
inside training. This is the heart of the plan.

The divergence to fix: today the competition rerun is "handled entirely by the
notebook's inline agent" (per `launch_competition.py`'s own docstring), while
offline batch runs `launch_competition.py`. **Two code paths is two
methodologies.** Collapse them.

- [ ] Make the notebook a thin shell: install wheels, then call the *same*
      solve entry point that offline batch uses. No game logic inline in the
      `.ipynb`.
- [ ] Define a single `solve(env)` contract used by all three environments
      (offline / rerun / training-evaluation).
- [ ] **Bulletproofing pass:** every solver must (a) never raise on a malformed
      or unexpected frame — fall back to the explorer floor; (b) honor the
      additive law (guarded by `_test_pollution.py`); (c) be deterministic under
      a fixed `LOCUS_SEED`.
- [ ] **Purge step-count framing from the code:** rewrite the RHAE/scoring
      docstring in `launch_competition.py` and any `ai_actions`-minimizing logic.
      Diagnostics may *report* level reached; they must not *optimize* strokes.
- [ ] **Purge gull-counting from the code:** strip the leaderboard-score
      changelog from the notebook header. The header should describe the method,
      not the gulls it once attracted.

**Acceptance:** a single grep proves it — no `human_baseline`, no `ai_actions`,
no `0.18`/`0.16` score-chasing comments in shipped code. `_test_multilevel.py`
reports the same level-per-game in all three environments.

---

## Phase 4 — Re-rate the crew (training optimized to learn new waters)

**Goal:** training is lean, repeatable, and exists only to convert an unsolved
level into a solved solver the hull can carry.

- [ ] Confirm `launch_training.py` → `kaggle_agent.py` (LOCUS) is the single
      train path; remove training-side score/step instrumentation.
- [ ] The output contract of training is explicit: a new/updated
      `games/<id>/{detector,dynamic,solver}.py` that the registry picks up and
      `_test_multilevel.py` confirms reaches a higher level than before.
- [ ] Keep the genuinely useful field instruments (`explore.py`,
      `practice_offline.py`, `level_scanner.py`) — these are how the crew reads
      new water. Verify each still serves; retire any that only fed a purged
      experiment.

**Acceptance:** running training on an unsolved game produces a registered
solver and a measurable level gain — nothing else.

---

## Phase 5 — Trim the manifest (the Kaggle dataset carries only the hull)

**Goal:** the uploaded dataset contains *only* the files the solving path needs
to run in the competition rerun. Training tools, logs, probes, and lore stay on
shore.

- [ ] Rewrite `.kaggleignore` from the One Star: exclude all of Phase 1/2/4's
      shore-side files (probes, tests, training launcher, session logs, PDFs,
      RFCs, this plan) — keep only `core/` (live solve path), `games/` (real
      solvers), `launch_competition.py`'s solve entry, and the wheels/registry.
- [ ] Rewrite the `upload_dataset.py` version string to describe the *method and
      the levels reached*, not the score delta. (It currently narrates gulls.)
- [ ] Verify the dataset mirror (`kaggle_upload/`) matches the committed repo —
      a stale mirror has shipped broken imports before.

**Acceptance:** the dataset file list, eyeballed, contains nothing a solver
wouldn't import at runtime.

---

## Phase 6 — Rewrite the ship's log (purge beliefs; keep one scar)

**Goal — done LAST, only once Phases 1–5 land.** The old memories about gull-
counting and stroke-counting become *history*, not *doctrine*.

- [ ] In `memory/`: retire or rewrite every memory whose core claim is a
      leaderboard number or a step-count strategy. Chiefly
      `project_general_agent.md` (the "0.08→0.18→0.16" ladder) — collapse its LB
      ladder into a single archival line.
- [ ] Write **one** new memory — *"What we used to do"* — recording, as history:
      we once steered by public score and step efficiency; we stopped on
      2026-06-21 because it never made landfall; the star is now level reached,
      same method everywhere. Link the purged projects to it.
- [ ] Keep all the *solving knowledge* memories intact (per-game mechanics:
      ls20, tu93, re86, wa30, sk48, ar25, …). Those are charts of real water and
      they stay.
- [ ] Update `MEMORY.md` index to match.

**Acceptance:** a fresh session, reading only `MEMORY.md`, learns *how to solve
games* and *that score-chasing is behind us* — and learns nothing that would
tempt it to count gulls again.

---

## Landfall (definition of done)

- One solving method, byte-identical across offline / rerun / training.
- The hull is bulletproof: no crash on bad frames; additive law enforced; tests
  green.
- The Kaggle dataset carries only solving files.
- Training is lean and its only product is a registered, level-raising solver.
- No public-score or step-count logic in any shipped code path.
- Memory remembers the old way as a scar, not a star.

> The crew still tells the story of the gulls — how they once counted them, and
> how the counting nearly kept them at sea forever. But they tell it at harbor.

---

## Order of operations (so we never cut the hull)

`Phase 0 (map)` → `1 (scratch)` → `2 (dead agents)` → `3 (unify + bulletproof
hull)` → `4 (training)` → `5 (dataset)` → `6 (memory, last)`.

Each phase ends with `_test_multilevel.py` confirming **no game lost a level.**
That test is the lookout in the crow's nest: if any harbor we already reach goes
dark, we stop and fix before sailing on.
