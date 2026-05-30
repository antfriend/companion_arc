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
- **Anthropic API key** — [console.anthropic.com](https://console.anthropic.com)
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

Edit `.env` and fill in your Anthropic key:

```
ANTHROPIC_API_KEY=sk-ant-...
ARC_API_KEY=your-arc-api-key-here
```

`.env` is in `.gitignore` — never commit it.

The `ARC_API_KEY` is only required for online/competition mode. Local training runs work with just `ANTHROPIC_API_KEY`.

---

## Step 3 — Get the environment files

Training and offline competition runs require the ARC-AGI-3 game files. Download the competition dataset from Kaggle and extract it so you have a directory called `environment_files/` containing one subdirectory per game (e.g. `environment_files/ls20/9607627b/ls20.py`).

The default expected path in `search_routes.py` is `C:\Temp\arc3\extracted\environment_files`. You can pass any path at runtime with `--env-dir`.

---

## Step 4 — Run a training session

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

1. `companion_arcprize.md` is loaded as LOCUS's knowledge base (cached system prompt)
2. LOCUS checks for any open revision cycles (`@LOCUS STATUS`)
3. For each step, LOCUS receives the current game frame and picks an action
4. Hardcoded routes (if any) play through the known levels automatically; LOCUS takes over after
5. After each level win, LOCUS runs a revision cycle (3-phase LOG → REVISION → FOCUS)
6. At the end, LOCUS writes a new session record to `companion_arcprize.md`

Session exchanges are also saved to `locus_<game-id>_session.txt` in the repo root.

**`--offline-levels` flag:**

Controls how many levels play automatically before LOCUS takes over:
- `0` — LOCUS guides every step from the start
- `1` — hardcoded L1 route plays, then LOCUS explores L2+
- `2` (default) — hardcoded L1 + L2 routes play, LOCUS explores L3+

Use `0` when training on a game with no known routes yet. Use `2` when you have confirmed L1 and L2 routes and want LOCUS to push deeper.

---

## Step 5 — Find routes for new games

`search_routes.py` does random sampling to discover L1 routes for games that have no known route:

```bash
python search_routes.py
```

Edit `ENV_DIR` at the top of the file to point to your environment files. The script tries up to 500 random action sequences per game and prints any winning routes it finds. Add confirmed routes to `_HARDCODED_ROUTES` in `launch_competition.py` and to `_COMPETITION_ROUTES` in `launch_training.py`.

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

| File | Purpose |
|---|---|
| `launch_training.py` | Run a local training session; writes session record to `companion_arcprize.md` |
| `kaggle_agent.py` | LOCUS agent core — action loop, LOCUS query, grid encoder |
| `launch_competition.py` | Kaggle submission runner — offline play + parquet writer |
| `kaggle_notebook.ipynb` | Kaggle notebook that calls `launch_competition.py` |
| `companion_arcprize.md` | LOCUS knowledge graph and session log — the shared brain |
| `search_routes.py` | Random-search route finder for games with no known route |
| `.env.example` | Template for local credentials |

---

## Multi-team training

**Current workflow:**

Each team member runs `launch_training.py` on their assigned game(s). After each session, `companion_arcprize.md` grows with a new session record and updated `[ew]` metadata. Commit and push after each session so teammates have your findings.

```bash
git add companion_arcprize.md
git commit -m "session: ls20 L2 probe DC31"
git push
```

**Splitting work:**

- Assign different game IDs to different team members — the 25 competition games are independent
- Multiple members can train the same game simultaneously (e.g. one on L1 probes, one on L2)
- Discovered routes go into `_HARDCODED_ROUTES` (in `launch_competition.py`) and `_COMPETITION_ROUTES` (in `launch_training.py`) — keep these in sync

**Merging companion files (future):**

`companion_arcprize.md` is append-only: each session adds a new record block after the previous one. This means git merges are usually clean (both sides added records at the end with no overlap). Conflicts only arise if two people edited the same existing record's `[ew]` block simultaneously.

Planned tooling to make this easier:
- A merge script that extracts all `[route]` tags and deduplicates by `game=` + `level=`
- A script to pull the latest confirmed routes from all branches and rebuild `_HARDCODED_ROUTES`
- Per-game branches (e.g. `train/ls20`, `train/cd82`) that merge into `main` once a new level is confirmed

For now: coordinate via Slack/Discord to avoid simultaneous edits to the same game's records.

---

## Questions

Check that both keys in `.env` are set and that:

```bash
python -c "import anthropic, arc_agi"
```

runs without error. If training hangs, check that `environment_files/` contains the game you're targeting. Ask the team lead if something is unclear.
