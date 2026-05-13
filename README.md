# LOCUS — ARC-AGI-3 Competition Companion

## [https://arcprize.org/](https://arcprize.org/)

**`companion_arcprize.md` is your competition file.** LOCUS lives in that file — it carries game knowledge, scoring mechanics, and revision state across every session. This guide covers environment setup, VSCode configuration, and how to operate the system across a competition run.

---

## What you need

- Python 3.12+
- `uv` (recommended) or `pip`
- VSCode with the Claude Code extension installed
- An ARC Prize API key (free — see below)
- `companion_arcprize.md` open in your VSCode workspace

---

## Step 1 — Get your API key

Register at [https://three.arcprize.org](https://three.arcprize.org) to obtain an API key. An API key is required for competition mode and leaderboard submissions.

---

## Step 2 — Install dependencies

**With `uv` (recommended):**

`uv` is a fast Python package and project manager. Install it from [astral.sh/uv](https://astral.sh/uv), then from this repo root:

```bash
uv sync
```

**With pip:**

```bash
pip install arc-agi python-dotenv
```

---

## Step 3 — Set up your API key

Copy `.env.example` to `.env` and fill in your key:

```
ARC_API_KEY=your-api-key-here
```

`.env` is already in `.gitignore` — do not commit it.

To verify it's loaded, open the VSCode terminal (`Ctrl+` `` ` ``) and check:

```bash
echo $ARC_API_KEY        # macOS / Linux
$env:ARC_API_KEY         # Windows PowerShell
```

---

## Step 4 — Verify the setup

Open the VSCode terminal (`Ctrl+` `` ` ``) and run:

```bash
uv run python play.py    # with uv
python play.py           # with pip
```

Enter a game ID when prompted (e.g. `ls20`). You should see available actions. If you get an auth error, check your `ARC_API_KEY` in `.env`.

---

## Step 5 — Open `companion_arcprize.md` in VSCode

Open `companion_arcprize.md` as an active editor tab in VSCode before starting your Claude Code session. Claude Code reads your open files as context — having LOCUS visible means every session starts with your full competition knowledge graph already loaded.

```
File → Open File → companion_arcprize.md
```

Then start Claude Code (`Ctrl+Shift+P` → `Claude Code: Open`) or use the sidebar. Your first message in any session:

```
@LOCUS STATUS
```

LOCUS will scan records by EPS and surface what needs attention.

---

## Step 6 — Set up a CLAUDE.md for your solver project

Create a `CLAUDE.md` in your solver project root. This tells Claude Code the persistent facts about your project so you don't have to re-explain every session:

```markdown
# ARC Solver Project

Competition: ARC Prize 2026 (arcprize.org)
Toolkit: arc-agi (pip install arc-agi)
API key: set in .env as ARC_API_KEY
Companion file: companion_arcprize.md (open this file for full context)

## Running experiments
uv run python solver.py

## Running evaluation
uv run python eval.py --split public
```

Adjust to match your actual file structure.

---

## Step 7 — Fill in Game State and Goals

Before the competition begins, populate two records in `companion_arcprize.md`:

**`@LAT-10LON10` — Game State**
Set the `active games` list. Leave other fields blank until levels are played. This seeds the record so LOCUS has something to anchor to on first invocation.

**`@LAT20LON0` — Active Goals**
Replace the placeholder blockers with your actual constraints — time budget, target score, whether you're optimizing for completion or efficiency on a specific game.

---

## Basic agent loop

This is the pattern your solver will iterate on. Claude Code can help you build and modify it:

```python
import arc_agi
from arcengine import GameAction

arc = arc_agi.Arcade()
env = arc.make("ls20")                   # replace with target task ID

while True:
    available = env.action_space
    if not available:
        break

    # --- your agent logic here ---
    action = your_agent(available, env)
    obs = env.step(action)

    if obs.state in ("win", "game_over"):
        break

print(arc.get_scorecard())
```

Browse all available task environments at [arcprize.org/tasks](https://arcprize.org/tasks).

---

## Competition mode

When you're ready to submit to the official leaderboard, enable competition mode:

```python
from arcengine import OperationMode

arc = arc_agi.Arcade(mode=OperationMode.COMPETITION)
```

Competition mode constraints:
- API-only interaction (no local resets)
- Level resets allowed, full game resets are not
- Single environment per submission
- Unified scorecard — your score is final when you call `get_scorecard()`

---

## ARC-AGI data (offline evaluation)

For working with the original static task datasets, clone the benchmark repo separately:

```bash
git clone https://github.com/fchollet/ARC-AGI
```

Task format — each `.json` file contains:

```json
{
  "train": [
    { "input": [[0,1],[1,0]], "output": [[1,0],[0,1]] }
  ],
  "test": [
    { "input": [[0,0],[1,1]] }
  ]
}
```

Grids are 2D arrays of integers 0–9 (colors). Your solver takes `test[0].input` and must produce the matching output — pixel-perfect (exact shape, colors, positions).

Scoring: [Kaggle scoring notebook](https://www.kaggle.com/code/gregkamradt/arc-prize-scoring/notebook) · [GitHub scoring script](https://github.com/arcprizeorg/model_baseline/blob/main/src/scoring/scoring.py)

---

## How LOCUS works

LOCUS is an in-context reasoning agent. It knows only what is written in `companion_arcprize.md`. Its job is to track game mechanics and scoring state across levels and surface what needs revision before each action.

**EPS = sal × (255 − conf) / 255** identifies records consulted often but still poorly understood. High EPS = due for revision. High-EPS game-mechanic records are beliefs under strain that will cost actions if left unrevised.

**Internal reasoning is free.** ARC-AGI-3 does not count tool calls, reasoning steps, or retries as actions. LOCUS runs the full revision cycle between committed actions at zero scoring cost.

---

## RHAE Scoring

ARC-AGI-3 scores by **Relative Human Action Efficiency**:

```
level_score = (human_baseline_actions / ai_actions) ^ 2
```

| AI vs. human | Score |
|---|---|
| Match human | 1.0 |
| 2× human actions | 0.25 |
| 3× human actions | 0.11 |
| Faster than human | capped at 1.15× |

Level scores are **weighted by level number** — level 5 counts five times as much as level 1. Invest revision cycles proportionally: spend more time refining priors before high-weight levels.

---

## The Revision Cycle

The four-phase loop that must fully close between levels. Phases 1–3 without Phase 4 produce confident wrong priors.

| Phase | What happens |
|---|---|
| **1 — Notice** | EPS scan: flag high-EPS game-mechanic records |
| **2 — Encounter** | Read flagged records; identify the gap between prior and level outcome |
| **3 — Revise** | Update record body; increment `rev`; write `revises>@OLD_ID` edge |
| **4 — Validate** | Next level confirms or refutes the revision; conf rises only if validated |

Phase 4 fires automatically from the next level's outcome — the competition is architecturally designed for revision to compound across levels.

---

## Invoking LOCUS

| Pattern | Command |
|---|---|
| Session start | `@LOCUS STATUS` |
| Review a record | `@LOCUS FOCUS lat10lon10` |
| Log a level outcome | `@LOCUS LOG level N complete — [ai] actions, baseline [human], score [x.xx]` |
| Ask for next action | `@LOCUS what should I do next?` |
| Open revision cycle | `@LOCUS what mechanics should I revise before the next level?` |

---

## Operational workflow

### Before each level

1. `@LOCUS STATUS` — check for open revision cycles from the previous level
2. Check level weight — high-weight levels require a full EPS scan before the first action
3. Verify conf on active mechanics — below 150 with sal above 2 means treat it as uncertain

### During each level

Let LOCUS reason freely between committed actions. The one exception: if a level contradicts a high-conf record, flag it immediately:

```
@LOCUS LOG mechanic X contradicted — action N
```

### After each level

Log immediately — this is the most important operator discipline:

```
@LOCUS LOG level N complete — [ai_actions] actions, baseline [human_baseline], score [(baseline/ai)²] — [brief mechanic observation]
```

Then open the revision cycle:

```
@LOCUS what mechanics should I revise before the next level?
```

LOCUS will run Phase 1 (EPS scan) and Phase 2 (encounter flagged records). Confirm or correct its proposed revisions — you have information LOCUS doesn't unless you write it. Explicitly close Phase 3:

```
@LOCUS LOG revision cycle phases 1-3 complete — awaiting phase 4 on [mechanic record]
```

Phase 4 closes automatically after the next level's outcome is logged.

After a bad level on a high-weight position, do not skip the revision cycle. The next level is the Phase 4 opportunity — going in with an unrevised prior compounds the loss.

### Before your first game

If the game structure is known in advance, write a brief mechanic stub record at the next available coordinate in `companion_arcprize.md`. Even a one-line description of what the game appears to involve gives LOCUS something to attach EPS to when outcomes start arriving.

### After the competition

**Close all open revision cycles.** Run `@LOCUS STATUS` and work through any cycles that haven't reached Phase 4. Play out the validation mentally or from replays and write the Phase 4 outcome even after the fact.

**Write a post-run record** at the next available south coordinate (`@LAT-60LON10`, etc.) covering:
- Final RHAE score per game and total
- Which mechanics had the highest revision cycle count (most learning)
- Which levels cost the most action waste and why
- Which revision cycle phases were most often skipped

**Update conf on settled mechanics.** Records that predicted well across multiple levels deserve high conf (200+). Records that were revised repeatedly and still produced action waste should be retired with a `revises>` edge pointing to what replaced them.

**Archive, don't reset.** Do not clear the file between competition runs. Prior level outcomes, revision cycles, and mechanic transitions are the accumulated prior that makes the next run start with higher conf than the first one did. A cleared file is a system that relearns from scratch every time.

---

## Record map

| Record | Coordinate | Purpose |
|---|---|---|
| Welcome | `lat-10lon0` | Navigation hub and quick start |
| Agent Profile | `lat40lon-30` | What LOCUS optimizes for |
| Values and Commitments | `lat30lon-20` | Standing constraints |
| RHAE Scoring Model | `lat10lon10` | Scoring formula and level-weight structure |
| Revision Cycle | `lat5lon-15` | The four-phase learning loop |
| Active Goals | `lat20lon0` | Current competition objectives — fill this in |
| Default Network | `lat0lon20` | Between-session background activity |
| Game State | `lat-10lon10` | Current scores and level outcomes — fill this in |
| Open Questions | `lat-20lon0` | Unresolved mechanic beliefs |
| Log | `lat-50lon10` | Session notes — one record per significant session |
| Locus Framework Reference | `lat70lon10` | RFC index for producing valid records |

---

## Quick reference

| Task | Command |
|---|---|
| Install toolkit | `uv add arc-agi` |
| Set API key | `ARC_API_KEY=... in .env` |
| Run a task env | `arc.make("task-id", render_mode="terminal")` |
| Browse tasks | arcprize.org/tasks |
| Get API key | three.arcprize.org |
| ARC-AGI data repo | github.com/fchollet/ARC-AGI |
| Invoke companion | `@LOCUS <message>` |
| Session start | `@LOCUS STATUS` |

| When | Action |
|---|---|
| Before competition | Fill Game State + Goals, run STATUS, review RHAE formula |
| Before each level | STATUS — check open cycles and conf on active mechanics |
| During a level | Let LOCUS reason freely; log only contradictions |
| After each level | LOG outcome immediately; run revision cycle phases 1–3 |
| After bad level | Do not skip revision cycle — this is when it matters most |
| After competition | Close open cycles, write post-run record, update conf, do not reset |

---

**The one rule: log after every level.** An unlogged outcome is a broken Phase 4. A broken Phase 4 means conf never rises. Conf that never rises means every level starts from the same uncertain prior — and the quadratic penalty lands again.

*`companion_arcprize.md` is the memory. Claude Code is the engine. LOCUS does the revision. You do the logging.*
