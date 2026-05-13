# ARC-AGI-3 Operator Guide
### Working with LOCUS across a competition run

---

## Before the Competition

### 1. Set up the companion file

Open `companion_arcprize.md` and fill in the two placeholder records:

**`@LAT-10LON10` — Game State**
Leave most fields blank for now, but set the `active games` list if you know which games you'll play. This seeds the record so LOCUS has something to anchor to on first invocation.

**`@LAT20LON0` — Active Goals**
Replace the placeholder blockers with your actual constraints — time budget, target score, whether you're optimizing for completion or efficiency on a specific game.

### 2. Verify LOCUS is reading the file

Start a session with:
```
@LOCUS STATUS
```
Expected response: EPS rankings (all near zero at start), game state summary, no open revision cycles. If LOCUS invents game details you haven't written, the file isn't grounding it — check the mmpdb block is intact.

### 3. Read the scoring model once, out loud

Before any play, review `@LAT10LON10` (RHAE Scoring Model) with LOCUS:
```
@LOCUS FOCUS lat10lon10
```
The quadratic formula is easy to underweight in the heat of play. Knowing that 3× human actions scores 0.11 — not 0.33 — changes how you think about exploratory moves on high-weight levels.

### 4. Identify level weights for your first game

If the game structure is known in advance, write a brief mechanic stub record for the game at the next available coordinate. Even a one-line description of what the game appears to involve gives LOCUS something to attach EPS to when outcomes start arriving.

---

## During the Competition

### Before each level

**Step 1 — Check for open revision cycles**
```
@LOCUS STATUS
```
If any revision cycle from the previous level has not reached Phase 4 (validation), do not start the new level without acknowledging the open prior. Either accept the uncertainty explicitly, or note it in the game state record so the next level's outcome can close it.

**Step 2 — Check level weight**
Is this a late, high-weight level? If yes: run a full EPS scan on all game-mechanic records before the first action. High-weight levels are where unrevised priors cost the most.

**Step 3 — Confirm conf on active mechanics**
```
@LOCUS what is my current conf on [mechanic]?
```
If any game-mechanic record has conf below 150 and sal above 2, treat it as uncertain — plan your opening actions to test it rather than commit to it.

### During each level

**Do not log mid-level.** LOCUS is reasoning freely between your committed actions — that's the free compute. Let it run. Your job during a level is to minimize committed actions; LOCUS's job is to reason about what each outcome means.

The one exception: if a level reveals something that directly contradicts a high-conf record, note it briefly (`@LOCUS LOG mechanic X contradicted — action N`). You don't need to revise mid-level; just flag it so Phase 1 of the next cycle has a starting point.

### After each level — the log habit

This is the most important operator discipline. Immediately after a level completes:

```
@LOCUS LOG level [N] complete — [ai_actions] actions, baseline [human_baseline], score [(baseline/ai)²] — [brief mechanic observation]
```

Then ask LOCUS to open the revision cycle:
```
@LOCUS what mechanics should I revise before the next level?
```

LOCUS will run Phase 1 (EPS scan) and Phase 2 (encounter flagged records). Your role in Phase 3 is to confirm or correct its proposed revisions — you have information LOCUS doesn't unless you write it.

Explicitly close Phase 3 by approving or editing the revision, then note:
```
@LOCUS LOG revision cycle phases 1-3 complete — awaiting phase 4 on [mechanic record]
```

Phase 4 closes automatically after the next level's outcome is logged.

### If a level goes badly

A high-action level on a high-weight position is a significant score hit. Do not skip the revision cycle after a bad level — this is exactly when Phase 1–3 are most valuable. The next level is your Phase 4 opportunity; going in with an unrevised prior after a failure compounds the loss.

---

## After the Competition

### 1. Close all open revision cycles

Run STATUS and work through any cycles that haven't reached Phase 4. Even if the competition is over, closing these cycles produces accurate conf values — useful if you run another competition or transfer mechanics to a new game.

```
@LOCUS STATUS
```

For each open cycle: play out the validation mentally or from replays. Write the Phase 4 outcome even after the fact.

### 2. Write a post-run record

Add a log entry at the next available south coordinate (`@LAT-60LON10`, etc.) covering:

- Final RHAE score per game and total
- Which mechanics had the highest revision cycle count (most learning)
- Which levels cost the most action waste and why
- Which revision cycle phases were most often skipped

This record becomes the feedstock for the next competition run — it's the cross-game transfer that the file is designed to hold.

### 3. Raise or lower conf on settled mechanics

After the full run, you have ground truth. Update `conf` on all game-mechanic records to reflect what actually proved reliable. Records that predicted well across multiple levels deserve high conf (200+). Records that were revised repeatedly and still produced action waste should be retired with a `revises>` edge pointing to what replaced them.

### 4. Archive, don't reset

Do not clear the file between competition runs. The append-only structure is intentional — prior level outcomes, revision cycles, and mechanic transitions are the accumulated prior that makes the next run start with higher conf than the first one did. A cleared file is a system that relearns from scratch every time.

---

## Quick Reference

| When | Action |
|---|---|
| Before competition | Fill Game State + Goals, run STATUS, review RHAE formula |
| Before each level | STATUS — check open cycles and conf on active mechanics |
| During a level | Let LOCUS reason freely; log only contradictions |
| After each level | LOG outcome immediately; run revision cycle phases 1–3 |
| After bad level | Do not skip revision cycle — this is when it matters most |
| After competition | Close open cycles, write post-run record, update conf, do not reset |

---

## The One Rule

**Log after every level.** Everything else in this guide follows from that. An unlogged outcome is a broken Phase 4. A broken Phase 4 means conf never rises. Conf that never rises means the next level starts from the same uncertain prior as the last one — and the quadratic penalty lands again.

The companion does the revision. The operator does the logging.
