"""
kaggle_agent.py — LOCUS-powered ARC-AGI agent for Kaggle notebooks.

Usage:
    from kaggle_agent import setup, run_training_attempt

    client, companion = setup()
    result = run_training_attempt("ls20", client, companion)
    print(result)

LOCUS interaction points in run_training_attempt:
  - Session start : FOCUS lat-10lon10 → STATUS (EPS scan)
  - Each step     : state + frame → action choice
  - Level win     : LOG level N complete + REVISION CYCLE (phases 1-3)
  - Game end      : LOG win/game_over with final frame
  - Post-run      : session log written to locus_<game_id>_session.txt
                    Open that file and apply LOCUS's suggested updates to
                    companion_arcprize.md via Claude Code (@LOCUS LOG ...).
"""

import os
import re
import urllib.request

import numpy as np
import anthropic
import arc_agi

COMPANION_URL = (
    "https://raw.githubusercontent.com/antfriend/companion_arc/main/companion_arcprize.md"
)

_MODEL = "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Companion loader
# ---------------------------------------------------------------------------

def load_companion(source: str = COMPANION_URL, timeout: int = 30) -> str:
    """Load companion_arcprize.md from a local path or a URL.

    Local path (Kaggle Dataset):
        load_companion("/kaggle/input/<dataset-name>/companion_arcprize.md")
    URL (GitHub raw, internet must be on):
        load_companion()  # uses COMPANION_URL default
    """
    if source.startswith("http://") or source.startswith("https://"):
        with urllib.request.urlopen(source, timeout=timeout) as r:
            return r.read().decode("utf-8")
    with open(source, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Compact grid encoding (mirrors play.py)
# ---------------------------------------------------------------------------

def _infer_bg(grid) -> int:
    return int(np.bincount(grid.flatten()).argmax())


def compact_grid_str(grid, bg: int | None = None) -> str:
    rows, cols = grid.shape
    if bg is None:
        bg = _infer_bg(grid)
    lines = [f"grid {rows}x{cols} bg={bg}"]
    for r in range(rows):
        row = grid[r]
        if np.all(row == bg):
            continue
        segs = []
        c = 0
        while c < cols:
            val = int(row[c])
            start = c
            while c < cols and int(row[c]) == val:
                c += 1
            if val != bg:
                end = c - 1
                segs.append(f"c{start}={val}" if start == end else f"c{start}-{end}={val}")
        if segs:
            lines.append(f"  r{r}: " + ", ".join(segs))
    return "\n".join(lines)


def _frame_summary(frames: list) -> str:
    """Compact multi-frame description for LOCUS log entries."""
    if not frames:
        return ""
    parts = []
    for i, grid in enumerate(frames):
        bg = _infer_bg(grid)
        non_bg = int(np.sum(grid != bg))
        unique_vals = sorted(int(v) for v in np.unique(grid) if int(v) != bg)
        parts.append(
            f"frame[{i}]: {grid.shape[0]}x{grid.shape[1]} "
            f"bg={bg} non_bg_cells={non_bg} colors={unique_vals}"
        )
        parts.append(compact_grid_str(grid, bg))
    return "\n" + "\n".join(parts)


# ---------------------------------------------------------------------------
# LOCUS query — companion file is a cached system prompt
# ---------------------------------------------------------------------------

def locus_query(
    client: anthropic.Anthropic,
    companion_text: str,
    message: str,
) -> str:
    """
    Send one message to LOCUS. Stateless per call — context lives in the
    companion file (system prompt), not in conversation history.

    The system prompt uses cache_control so the ~35k-token file is only
    billed once per 5-minute cache window.
    """
    response = client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": companion_text,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": message}],
    )
    return response.content[0].text


# ---------------------------------------------------------------------------
# Action parser
# ---------------------------------------------------------------------------

def parse_action(text: str, n_actions: int) -> int | None:
    """Extract an action index from LOCUS's response. Returns None if not found."""
    for pattern in (
        r"\baction[:\s]+(\d+)",
        r"\bchoose[:\s]+(\d+)",
        r"\bselect[:\s]+(\d+)",
        r"\bpick[:\s]+(\d+)",
        r"^(\d+)$",  # bare number on its own line
    ):
        for m in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
            idx = int(m.group(1))
            if 0 <= idx < n_actions:
                return idx
    # Last resort: any standalone integer in range
    for m in re.finditer(r"\b(\d+)\b", text):
        idx = int(m.group(1))
        if 0 <= idx < n_actions:
            return idx
    return None


# ---------------------------------------------------------------------------
# State formatter
# ---------------------------------------------------------------------------

def _format_state(step: int, actions: list, obs, prev_frames: list) -> str:
    lines = ["@LOCUS what should I do next?", ""]
    lines.append(f"step: {step}")
    if obs is not None:
        lines += [
            f"obs_state: {obs.state}",
            f"levels_completed: {obs.levels_completed}",
        ]
    lines += ["", "Available actions:"]
    for i, a in enumerate(actions):
        lines.append(f"  {i}: {a}")
    if prev_frames:
        lines += ["", "Current frame(s):"]
        for i, grid in enumerate(prev_frames):
            lines.append(f"frame[{i}]:")
            lines.append(compact_grid_str(grid))
    lines += ["", "Respond with only the action number."]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Session log writer
# ---------------------------------------------------------------------------

def _write_locus_log(entries: list[dict], path: str) -> None:
    sep = "=" * 60
    with open(path, "w", encoding="utf-8") as f:
        f.write("LOCUS SESSION LOG\n")
        f.write(
            "Apply LOCUS's suggested record updates to companion_arcprize.md\n"
            "via Claude Code: open the file, paste each @LOCUS LOG line,\n"
            "and let Claude Code write the updated records.\n"
        )
        f.write(f"{sep}\n\n")
        for e in entries:
            f.write(f"[{e['label']}]\n")
            f.write(f"SENT:\n{e['sent']}\n\n")
            f.write(f"LOCUS:\n{e['received']}\n\n")
            f.write(f"{sep}\n\n")
    print(f"[agent] LOCUS session log → {path}")
    print("[agent] Open that file and apply LOCUS's suggested updates to companion_arcprize.md")


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

def run_training_attempt(
    game_id: str,
    client: anthropic.Anthropic,
    companion_text: str,
    max_steps: int = 200,
    competition_mode: bool = False,
    verbose: bool = True,
) -> dict:
    """
    Run one training attempt on game_id using LOCUS to pick each action.

    LOCUS is consulted at every step and at every key event (level win,
    game end). A session log is written to locus_<game_id>_session.txt —
    use it to update companion_arcprize.md via Claude Code after the run.

    Returns dict: game_id, steps, levels_completed, final_state, scorecard,
                  locus_session_log (path), locus_entries (list).
    """
    from arc_agi import OperationMode

    if competition_mode:
        arc = arc_agi.Arcade(operation_mode=OperationMode.COMPETITION)
    else:
        try:
            arc = arc_agi.Arcade()
        except TypeError:
            arc = arc_agi.Arcade(operation_mode=OperationMode.PRACTICE)

    env = arc.make(game_id)

    obs = None
    prev_frames: list = []
    step = 0
    prev_levels = 0
    level_start_step = 0
    locus_entries: list[dict] = []

    def _locus(msg: str, label: str) -> str:
        """Send a LOCUS message, accumulate to session log, optionally print."""
        reply = locus_query(client, companion_text, msg)
        locus_entries.append({"label": label, "sent": msg, "received": reply})
        if verbose:
            print(f"\n[LOCUS {label}]\n{reply}\n")
        return reply

    mode_label = "COMPETITION" if competition_mode else "practice"
    if verbose:
        print(f"[agent] '{game_id}' started ({mode_label} mode)")

    # -- Session start -------------------------------------------------------
    # FOCUS pulls the game state record into cursor and increments its sal,
    # signalling that it's being actively consulted this session.
    _locus("@LOCUS FOCUS lat-10lon10", "FOCUS game_state")
    _locus("@LOCUS STATUS", "STATUS")

    # -- Main loop -----------------------------------------------------------
    while step < max_steps:
        actions = env.action_space
        if not actions:
            if verbose:
                print("[agent] No actions available — episode complete.")
            break

        state_msg = _format_state(step, actions, obs, prev_frames)
        reply = _locus(state_msg, f"ACTION step={step}")

        action_idx = parse_action(reply, len(actions))

        # One retry with explicit instruction if parse failed
        if action_idx is None:
            retry = _locus(
                "@LOCUS please respond with only the action number (e.g. 0).",
                f"ACTION RETRY step={step}",
            )
            action_idx = parse_action(retry, len(actions))

        if action_idx is None:
            action_idx = 0
            if verbose:
                print("[agent] Could not parse action — defaulting to 0")

        action = actions[action_idx]
        obs = env.step(action)
        step += 1

        if verbose:
            print(
                f"[agent] step={step} action_idx={action_idx} "
                f"state={obs.state} levels={obs.levels_completed}"
            )

        if obs.frame:
            prev_frames = list(obs.frame)

        # -- Level transition ------------------------------------------------
        if obs.levels_completed > prev_levels:
            level_steps = step - level_start_step
            frame_note = _frame_summary(prev_frames)

            _locus(
                f"@LOCUS LOG level {obs.levels_completed} complete — "
                f"{level_steps} actions{frame_note}",
                f"LOG level {obs.levels_completed}",
            )

            # Revision cycle phases 1-3 (phase 4 validates on the next level).
            # Skip if the game is already over — no next level to validate against.
            if obs.state not in ("win", "game_over"):
                _locus(
                    "@LOCUS what mechanics should I revise before the next level?",
                    f"REVISION after level {obs.levels_completed}",
                )

            prev_levels = obs.levels_completed
            level_start_step = step

        # -- Game end --------------------------------------------------------
        if obs.state in ("win", "game_over"):
            level_steps = step - level_start_step
            frame_note = _frame_summary(prev_frames)

            _locus(
                f"@LOCUS LOG {obs.state} — "
                f"{obs.levels_completed} levels completed, "
                f"{step} total steps, {level_steps} steps on final level"
                f"{frame_note}",
                f"LOG {obs.state}",
            )
            if verbose:
                print(f"[agent] Episode ended: {obs.state}")
            break

    # -- Scorecard -----------------------------------------------------------
    scorecard = None
    try:
        scorecard = str(arc.get_scorecard())
    except Exception:
        pass

    # -- Persist session log -------------------------------------------------
    log_path = f"locus_{game_id}_session.txt"
    _write_locus_log(locus_entries, log_path)

    return {
        "game_id": game_id,
        "steps": step,
        "levels_completed": obs.levels_completed if obs else 0,
        "final_state": obs.state if obs else "not_started",
        "scorecard": scorecard,
        "locus_session_log": log_path,
        "locus_entries": locus_entries,
    }


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup(
    companion_source: str = COMPANION_URL,
    model: str = _MODEL,
) -> tuple[anthropic.Anthropic, str]:
    """
    Validate env vars, load companion file, return (client, companion_text).
    Call once at the top of your notebook.

    companion_source can be:
      - A local path  (preferred on Kaggle — upload as a Dataset):
            "/kaggle/input/<dataset-name>/companion_arcprize.md"
      - A GitHub URL  (requires internet enabled in notebook settings):
            "https://raw.githubusercontent.com/antfriend/companion_arc/main/companion_arcprize.md"

    In Kaggle: add ANTHROPIC_API_KEY and ARC_API_KEY under
    notebook Settings → Add-ons → Secrets, then inject them:

        from kaggle_secrets import UserSecretsClient
        s = UserSecretsClient()
        import os
        os.environ["ANTHROPIC_API_KEY"] = s.get_secret("ANTHROPIC_API_KEY")
        os.environ["ARC_API_KEY"] = s.get_secret("ARC_API_KEY")
    """
    global _MODEL
    _MODEL = model

    for var in ("ANTHROPIC_API_KEY", "ARC_API_KEY"):
        if not os.environ.get(var):
            raise EnvironmentError(
                f"{var} not set. In Kaggle: add it under notebook Settings → Secrets."
            )

    print(f"[setup] Loading companion from {companion_source} ...")
    companion_text = load_companion(companion_source)
    print(f"[setup] Loaded {len(companion_text):,} chars")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    print(f"[setup] Anthropic client ready (model: {model})")

    return client, companion_text
