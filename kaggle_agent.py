"""
kaggle_agent.py — LOCUS-powered ARC-AGI agent for Kaggle notebooks.

Usage:
    from kaggle_agent import setup, run_training_attempt

    client, companion = setup()
    result = run_training_attempt("ls20", client, companion)
    print(result)
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

def load_companion(url: str = COMPANION_URL, timeout: int = 30) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8")


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
    # Explicit patterns first
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

def _format_state(
    step: int,
    actions: list,
    obs,
    prev_frames: list,
) -> str:
    lines = [f"@LOCUS — game step {step}"]
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
    lines += ["", "Which action should I take? Respond with only the action number."]
    return "\n".join(lines)


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

    Returns dict with: game_id, steps, levels_completed, final_state, scorecard.
    Set competition_mode=True only when ready for leaderboard submission.
    """
    from arc_agi import OperationMode

    if competition_mode:
        arc = arc_agi.Arcade(operation_mode=OperationMode.COMPETITION)
    else:
        try:
            arc = arc_agi.Arcade()
        except TypeError:
            # Fallback if Arcade requires operation_mode
            arc = arc_agi.Arcade(operation_mode=OperationMode.PRACTICE)

    env = arc.make(game_id)

    obs = None
    prev_frames: list = []
    step = 0

    mode_label = "COMPETITION" if competition_mode else "practice"
    if verbose:
        print(f"[agent] '{game_id}' started ({mode_label} mode)")

    # Give LOCUS session context before the first action
    status = locus_query(client, companion_text, "@LOCUS STATUS")
    if verbose:
        print(f"[LOCUS STATUS]\n{status}\n")

    while step < max_steps:
        actions = env.action_space
        if not actions:
            if verbose:
                print("[agent] No actions available — episode complete.")
            break

        state_msg = _format_state(step, actions, obs, prev_frames)
        reply = locus_query(client, companion_text, state_msg)

        if verbose:
            print(f"[LOCUS step={step}]\n{reply}\n")

        action_idx = parse_action(reply, len(actions))

        # One retry if parse failed
        if action_idx is None:
            retry = locus_query(
                client,
                companion_text,
                "Please respond with only the action number (e.g. 0).",
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

        if obs.state in ("win", "game_over"):
            if verbose:
                print(f"[agent] Episode ended: {obs.state}")
            break

    scorecard = None
    try:
        scorecard = str(arc.get_scorecard())
    except Exception:
        pass

    return {
        "game_id": game_id,
        "steps": step,
        "levels_completed": obs.levels_completed if obs else 0,
        "final_state": obs.state if obs else "not_started",
        "scorecard": scorecard,
    }


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup(
    companion_url: str = COMPANION_URL,
    model: str = _MODEL,
) -> tuple[anthropic.Anthropic, str]:
    """
    Validate env vars, fetch companion file, return (client, companion_text).
    Call once at the top of your notebook.

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

    print(f"[setup] Fetching companion from {companion_url} ...")
    companion_text = load_companion(companion_url)
    print(f"[setup] Loaded {len(companion_text):,} chars")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    print(f"[setup] Anthropic client ready (model: {model})")

    return client, companion_text
