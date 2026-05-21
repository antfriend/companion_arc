# ARC-AGI-3 LOCUS Companion — Getting Started

Welcome to the team. This repo contains the LOCUS competition agent and the tools to run training attempts against ARC-AGI-3 games. Get through these four steps and you'll have a working training run.


---

## What you need

- Python 3.12+
- Your own **Anthropic API key** — [console.anthropic.com](https://console.anthropic.com)
- The team **ARC API key** — get this from the team lead
- Git clone of this repo

---

## Step 1 — Install dependencies

```bash
pip install anthropic arc-agi python-dotenv
```

---

## Step 2 — Create your `.env` file

Copy the example and fill in both keys:

```bash
cp .env.example .env
```

```
ARC_API_KEY=<team key — get from team lead>
ANTHROPIC_API_KEY=<your personal key from console.anthropic.com>
```

`.env` is in `.gitignore` — do not commit it.

---

## Step 3 — Get your game ID

Each team member works a different game. Your game ID looks like `ls20` or similar — get it from the team lead alongside the ARC API key.

Browse all available games at [arcprize.org/tasks](https://arcprize.org/tasks).

---

## Step 4 — Run a training attempt

```bash
python launch_training.py <your-game-id>
```

This starts a practice-mode run. LOCUS picks actions, logs outcomes, and writes a new session record to `companion_arcprize.md` when the run completes.

---

## What happens during a run

`launch_training.py` runs the full agent loop:

1. Loads `companion_arcprize.md` as LOCUS's knowledge base
2. Calls `@LOCUS STATUS` to check for any open revision cycles
3. At each game step, asks `@LOCUS what should I do next?` and executes the chosen action
4. After each level win, logs the outcome and runs the revision cycle
5. At the end, LOCUS writes a new session record back to `companion_arcprize.md`

All LOCUS exchanges are also saved to `locus_<game-id>_session.txt`.

---

## Files

| File | Purpose |
|---|---|
| `launch_training.py` | Run a training attempt locally |
| `kaggle_agent.py` | The LOCUS agent and API client — imported by both launch scripts |
| `kaggle_notebook.ipynb` | Kaggle notebook version of the same training loop |
| `companion_arcprize.md` | LOCUS's knowledge graph — do not delete or reset |
| `play.py` | Manual / server-mode game runner (for step-by-step play with Claude Code) |

---

## Switching to competition mode

When the team is ready to submit to the leaderboard, edit `launch_training.py` and set:

```python
competition_mode=True
```

Competition mode is final — no resets, score locks on `get_scorecard()`.

---

## Questions

Ask the team lead. If something is broken, check that both keys in `.env` are correct and that `python -c "import anthropic, arc_agi"` runs without error.
