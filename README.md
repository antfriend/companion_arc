# ARC-AGI-3 LOCUS Companion

This repo contains the **LOCUS** competition agent and tools for training against [ARC-AGI-3](https://arcprize.org) games.

**Resources**
- [Locus: A Toot Toot Framework](https://antfriend.github.io/locus_arxiv.pdf) — theory paper
- [Locus Seed](https://antfriend.github.io/share/companion.html) — the seed this project grew from
- [Locus Logs](https://antfriend.github.io/index.html?ttdb=companion_arcprize.md&toot=lat-300lon10) — live session logs
- [Kaggle notebook](https://www.kaggle.com/code/danxray/toot-toot-locus/) — competition submission

---

## What you need

- Python 3.12+
- **Anthropic API key** — [console.anthropic.com](https://console.anthropic.com) *(not needed for offline practice)*
- **ARC environment files** — the `environment_files/` directory extracted from the competition dataset (see Step 3 below)

---

## Step 1 — Clone and install

```bash
git clone https://github.com/antfriend/companion_arc.git
cd companion_arc
pip install anthropic arc-agi python-dotenv
```

---

## Step 2 — Create your `.env` file

```bash
cp .env.example .env
```

Edit `.env` and fill in your keys:

```
ANTHROPIC_API_KEY=sk-ant-...
ARC_API_KEY=your-arc-api-key-here
```

`.env` is in `.gitignore` — never commit it.

`ARC_API_KEY` is required for online/competition mode. `ANTHROPIC_API_KEY` is only required when LOCUS is active (training mode). Offline practice needs neither if the game engine accepts unauthenticated local runs.

---

## Step 3 — Get the environment files

Training and offline runs require the ARC-AGI-3 game files. Download the competition dataset from Kaggle and extract it so you have a directory called `environment_files/` containing one subdirectory per game (e.g. `environment_files/ls20/9607627b/ls20.py`).

Place it inside the repo root (`companion_arc/environment_files/`) or pass any path at runtime with `--env-dir`.

---

## Step 4 — Quick offline practice (no API key needed)

The fastest way to test a game locally. No LOCUS calls, no Anthropic key required.

```bash
python practice_offline.py ls20
```

**What happens:**

1. Opens the game in `OFFLINE` mode using local `environment_files/`
2. Takes one probe step to capture the first frame
3. Calls `detector.detect_state()` — prints block position, entity2 ring, cluster, entity1 state
4. Calls `detector.compute_route()` — prints the adaptive action sequence
5. Executes each route step and prints a verification line:

```
[OK  ] step=  3  route[1]=0 UP     block moved UP by 5 rows  (before=(35, 34) after=(30, 34))
[OK  ] step=  4  route[2]=0 UP     block moved UP by 5 rows  (before=(30, 34) after=(25, 34))
[FAIL] step=  5  route[3]=0 UP     block did not move UP — wall or boundary  (before=(25, 34) after=(25, 34))
```

Options:

```bash
python practice_offline.py ls20 --levels 2          # attempt L1 then L2
python practice_offline.py ls20 --max-steps 100     # raise step cap
python practice_offline.py ls20 --env-dir C:\path\to\environment_files
```

---

## Step 5 — Run a LOCUS training session

```bash
python launch_training.py <game_id>
```

Examples:

```bash
python launch_training.py ls20
python launch_training.py cd82
python launch_training.py ls20 --offline-levels 2   # hardcode L1+L2, LOCUS explores from L3
python launch_training.py ls20 --env-dir C:\path\to\environment_files
```

**What happens during a run:**

1. The per-game `companion.md` (e.g. `games/ls20/companion.md`) is loaded as LOCUS's system prompt — only that game's knowledge, keeping context tight
2. LOCUS checks for any open revision cycles (`@LOCUS STATUS`)
3. Hardcoded routes play through the known levels automatically; LOCUS takes over after
4. Every step is verified with `detector.verify_step()` — a `[FAIL]` triggers a recovery prompt to LOCUS
5. After each level win, LOCUS runs a revision cycle (LOG → REVISION → FOCUS)
6. At the end, LOCUS writes a new session record to the per-game companion file

Session exchanges are also saved to `locus_<game-id>_session.txt` in the repo root.

**`--offline-levels` flag:**

Controls how many levels play automatically before LOCUS takes over:
- `0` — LOCUS guides every step from the start
- `1` — hardcoded L1 route plays, then LOCUS explores L2+
- `2` (default) — hardcoded L1 + L2 routes play, LOCUS explores L3+

---

## Step 6 — Find routes for new games

`search_routes.py` does random sampling to discover L1 routes for games with no known route:

```bash
python search_routes.py
```

Edit `ENV_DIR` at the top of the file to point to your environment files. The script tries up to 500 random action sequences per game and prints any winning routes it finds. Add confirmed routes to `_HARDCODED_ROUTES` in `launch_competition.py` and to `_COMPETITION_ROUTES` in `launch_training.py`.

---

## Per-game architecture

Each game lives under `games/<id>/`:

```
games/
  ls20/
    detector.py     ← detect_state, compute_route, verify_step, format_companion_block
    companion.md    ← LOCUS knowledge for this game only
  cd82/
    detector.py
    companion.md
  ...
```

`core/game_registry.py` maps game IDs to their detector and companion file. All three run modes (practice / batch / competition) share the same `core/step_runner.py` loop — mode-specific behavior lives in a **Policy** object:

| Policy | On verify fail | LOCUS? |
|---|---|---|
| `PracticePolicy` | Ask LOCUS for a recovery action | Yes |
| `BatchPolicy` | Retry once, then random | No |
| `CompetitionPolicy` | Retry once, then systematic sweep, then random | No |

**Adding a new game:**

1. Create `games/<id>/detector.py` implementing the four standard functions
2. Create `games/<id>/companion.md` with TTDB header
3. Add one `register()` call at the bottom of `core/game_registry.py`

The detector interface:

```python
def detect_state(grid: np.ndarray) -> GameState          # extract all observable state
def compute_route(state: GameState) -> list[int]          # compute winning action sequence
def verify_step(before, after, action) -> StepResult      # did the frame change as expected?
def format_companion_block(state, route) -> str           # serialize to companion.md format
```

---

## Competition submission flow

The Kaggle notebook (`kaggle_notebook.ipynb`) runs `launch_competition.py` on the Kaggle servers:

- **Offline (batch run):** plays the 25 competition games using hardcoded routes, writes `submission.parquet` with per-game scores
- **Online (competition rerun):** connects to the Kaggle gateway (`http://gateway:8001`) and plays live when `KAGGLE_IS_COMPETITION_RERUN` is set

**Scoring mechanics (confirmed from diagnostics):**

- Games have multiple levels (ls20 = 28, sp80 = 21, cd82 = 21)
- `run.score = (levels_completed / total_levels) × 100` — partial credit
- `run.completed = True` only when ALL levels are done (WIN state)
- `end_of_game` in the parquet must be `True` for Kaggle to count the row
- Completing more levels per game is the main lever for improving the leaderboard score

**To update the submission**, push changes to the `danxray/companion-arc` Kaggle dataset (includes `launch_competition.py` and `companion_arcprize.md`), then rerun the notebook.

---

## Files

| File / Directory | Purpose |
|---|---|
| `practice_offline.py` | **Quick offline practice** — step verification, no API key needed |
| `launch_training.py` | LOCUS-guided training session; writes session record to companion |
| `launch_competition.py` | Kaggle submission runner — offline play + parquet writer |
| `kaggle_agent.py` | LOCUS agent core — action loop, LOCUS query, grid encoder |
| `kaggle_notebook.ipynb` | Kaggle notebook that calls `launch_competition.py` |
| `search_routes.py` | Random-search route finder for games with no known route |
| `agent_framework.py` | Shared `ArcAgent` class used by all run modes |
| `level_scanner.py` | Generic first-frame entity capture and level map I/O |
| `ls20_detector.py` | Re-export shim — all logic now lives in `games/ls20/detector.py` |
| `companion_arcprize.md` | Cross-game LOCUS knowledge index and historical session log |
| `games/ls20/detector.py` | ls20 detector: `detect_state`, `compute_route`, `verify_step` |
| `games/ls20/companion.md` | ls20-specific LOCUS companion (loaded instead of the global file) |
| `core/game_registry.py` | Maps `game_id` → detector module + companion path |
| `core/step_runner.py` | Unified play loop + `PracticePolicy`, `BatchPolicy`, `CompetitionPolicy` |
| `.env.example` | Template for local credentials |

---

## Multi-team training

**Current workflow:**

Each team member runs `launch_training.py` on their assigned game(s). After each session, the per-game `companion.md` grows with a new session record and updated `[ew]` metadata. Commit and push after each session so teammates have your findings.

```bash
git add games/ls20/companion.md
git commit -m "session: ls20 L2 probe DC31"
git push
```

**Splitting work:**

- Assign different game IDs to different team members — the 25 competition games are independent
- Multiple members can train the same game simultaneously (e.g. one on L1 probes, one on L2)
- Discovered routes go into `_HARDCODED_ROUTES` (in `launch_competition.py`) and `_COMPETITION_ROUTES` (in `launch_training.py`) — keep these in sync

**Merging companion files:**

Each `games/<id>/companion.md` is append-only: sessions add new record blocks at the end. Git merges are usually clean. Conflicts only arise if two people edited the same record's `[ew]` block simultaneously.

---

## Troubleshooting

Check that both keys in `.env` are set and that:

```bash
python -c "import anthropic, arc_agi"
```

runs without error. For offline practice only, neither key is strictly required — try:

```bash
python practice_offline.py ls20
```

and check the error message. If training hangs, check that `environment_files/` contains the game you're targeting.
