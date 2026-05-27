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

BLOCK_VAL = 12

# Hardcoded routes per level. Key = level number (1-based).
# 0=UP  1=DOWN  2=LEFT  3=RIGHT
_LEVEL1_ROUTE = [0, 0, 0, 0, 2, 2, 2, 1, 0, 3, 3, 3, 0, 0, 0]  # UP×4,LEFT×3,DOWN,UP,RIGHT×3,UP×3 — 17 confirmed wins
# INVALID — session 39 confirmed [1,3,3,3,3] is geometrically impossible:
#   DOWN from c29-33 → void at r45-46 c29-33 (blocked)
#   DOWN from c34-38 → void at r45-46 c34-38 (blocked)
#   RIGHT from c34-38 → void at c39-43 rows 40-41 (blocked)
# Far-right track (c44+) only reachable via wide connector rows 10-14.
# Probe must be redesigned before offline_levels=2 is useful.
_LEVEL2_ROUTE = [
    3,                       # step 1:  RIGHT → r40-41 c34-38
    0, 0, 0, 0, 0, 0,        # steps 2-7:  UP×6 → r10-11 c34-38
    3, 3, 3,                 # steps 8-10: RIGHT×3 → r10-11 c49-53
    1, 1, 1, 1, 1, 1, 1,     # steps 11-17: DOWN×7 → r45-46 c49-53  [CROSS → state 2]
    1, 2, 2,                 # steps 18-20: DOWN+LEFT×2 → r50-51 c39-43  [11-ring B → timer reset]
    3,                       # step 21:  RIGHT → r50-51 c44-48  [void escape]
    0, 0, 0, 0, 0, 0, 0, 0,  # steps 22-29: UP×8 → r10-11 c44-48
    2, 2, 2, 2, 2, 2,        # steps 30-35: LEFT×6 → r10-11 c14-18
    1,                       # step 36:  DOWN → r15-16 c14-18  [11-ring A → timer reset]
    1, 1, 1, 1, 1,           # steps 37-41: DOWN×5 → r40-41 c14-18  [ENTITY2 at state 2]
]  # DC6 41-step route — all collectibles confirmed; entity2 WIN condition unknown until session 49
_HARDCODED_ROUTES: dict[int, list[int]] = {1: _LEVEL1_ROUTE, 2: _LEVEL2_ROUTE}


def _infer_bg(grid) -> int:
    return int(np.bincount(grid.flatten()).argmax())


def _find_block_pos(grid) -> tuple[int, int] | None:
    """Return (min_row, min_col) of the block (value BLOCK_VAL), or None."""
    positions = np.argwhere(grid == BLOCK_VAL)
    if len(positions) == 0:
        return None
    return (int(positions[:, 0].min()), int(positions[:, 1].min()))


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
    max_tokens: int = 1024,
) -> str:
    """
    Send one message to LOCUS. Stateless per call — context lives in the
    companion file (system prompt), not in conversation history.

    The system prompt uses cache_control so the ~35k-token file is only
    billed once per 5-minute cache window.
    """
    response = client.messages.create(
        model=_MODEL,
        max_tokens=max_tokens,
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
    """Extract an action index from LOCUS's response. Returns None if not found.

    Checks the last non-empty line first — LOCUS ends with just the number.
    This prevents false matches when LOCUS echoes "action N" in its reasoning
    (e.g. "Last action 0 produced no movement" in blocked-move warnings).
    """
    # Priority: last non-empty line bare number
    for line in reversed(text.strip().splitlines()):
        stripped = line.strip()
        if re.match(r"^\d+$", stripped):
            idx = int(stripped)
            if 0 <= idx < n_actions:
                return idx
    # Secondary: explicit keyword patterns (skipping "action" to avoid warning echo)
    for pattern in (
        r"\bchoose[:\s]+(\d+)",
        r"\bselect[:\s]+(\d+)",
        r"\bpick[:\s]+(\d+)",
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
    last_action_blocked: bool = False,
    last_action_idx: int | None = None,
) -> str:
    lines = ["@LOCUS what should I do next?", ""]
    lines.append(f"step: {step}")
    if obs is not None:
        lines += [
            f"obs_state: {obs.state}",
            f"levels_completed: {obs.levels_completed}",
        ]
    if last_action_blocked and last_action_idx is not None:
        _dir = ["UP", "DOWN", "LEFT", "RIGHT"][last_action_idx] if last_action_idx < 4 else str(last_action_idx)
        lines += [
            "",
            f"WARNING: last move ({_dir}) produced NO movement — "
            "block position unchanged. That direction is blocked by a void. "
            "Choose a different direction.",
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
    client: "anthropic.Anthropic | None",
    companion_text: "str | None",
    max_steps: int = 200,
    competition_mode: bool = False,
    verbose: bool = True,
    offline_levels: int = 1,
    stop_after_offline: bool = False,
) -> dict:
    """
    Run one training attempt on game_id using LOCUS to pick actions in the
    online phase.

    offline_levels: play this many initial levels with the hardcoded route,
        no LOCUS calls. LOCUS initialises at the first online-phase step.
    stop_after_offline: stop the episode once the offline levels complete
        (competition offline mode). client / companion_text may be None.

    Returns dict: game_id, steps, levels_completed, final_state, scorecard,
                  locus_session_log (path or None), locus_entries (list).
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
    prev_block_pos: tuple[int, int] | None = None
    cur_block_pos: tuple[int, int] | None = None
    last_action_blocked = False
    last_action_idx: int | None = None
    locus_initialized = stop_after_offline  # True = never initialize LOCUS

    def _locus(msg: str, label: str) -> str:
        """Send a LOCUS message, accumulate to session log, optionally print."""
        if client is None:
            return ""
        reply = locus_query(client, companion_text, msg)
        locus_entries.append({"label": label, "sent": msg, "received": reply})
        if verbose:
            print(f"\n[LOCUS {label}]\n{reply}\n")
        return reply

    mode_label = "COMPETITION" if competition_mode else "practice"
    if verbose:
        print(f"[agent] '{game_id}' started ({mode_label} mode, offline_levels={offline_levels})")

    # -- Main loop -----------------------------------------------------------
    while step < max_steps:
        actions = env.action_space
        if not actions:
            if verbose:
                print("[agent] No actions available — episode complete.")
            break

        current_level = (obs.levels_completed if obs is not None else 0) + 1
        level_step = step - level_start_step
        route = _HARDCODED_ROUTES.get(current_level)
        in_offline = offline_levels > 0 and (obs is None or obs.levels_completed < offline_levels)

        if in_offline and route is not None and level_step < len(route):
            # Offline phase: hardcoded route for this level, no LOCUS
            action_idx = route[level_step]
            if verbose:
                _name = ["UP", "DOWN", "LEFT", "RIGHT"][action_idx]
                print(f"[agent] step={step} — L{current_level} hardcode {action_idx} ({_name})")
        elif in_offline and stop_after_offline:
            # Route exhausted within offline level — stop (offline-only mode)
            if verbose:
                print(f"[agent] L{current_level} route exhausted — stopping (offline-only mode)")
            break
        else:
            # Online phase: LOCUS decides (also handles L1 fallback in training mode)
            if not locus_initialized:
                _locus("@LOCUS FOCUS lat-10lon10", "FOCUS game_state")
                _locus("@LOCUS STATUS", "STATUS")
                locus_initialized = True
            state_msg = _format_state(
                step, actions, obs, prev_frames,
                last_action_blocked=last_action_blocked,
                last_action_idx=last_action_idx,
            )
            reply = _locus(state_msg, f"ACTION step={step}")
            action_idx = parse_action(reply, len(actions))
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

        last_action_idx = action_idx
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
            cur_block_pos = _find_block_pos(prev_frames[0])
            last_action_blocked = (
                prev_block_pos is not None
                and cur_block_pos is not None
                and cur_block_pos == prev_block_pos
            )
            prev_block_pos = cur_block_pos
        else:
            last_action_blocked = False

        # -- Level transition ------------------------------------------------
        if obs.levels_completed > prev_levels:
            level_steps = step - level_start_step
            frame_note = _frame_summary(prev_frames)
            completing_offline = obs.levels_completed <= offline_levels

            if completing_offline:
                if verbose:
                    print(
                        f"[agent] Level {obs.levels_completed} complete "
                        f"(offline, {level_steps} actions)"
                    )
            else:
                _locus(
                    f"@LOCUS LOG level {obs.levels_completed} complete — "
                    f"{level_steps} actions{frame_note}",
                    f"LOG level {obs.levels_completed}",
                )
                if obs.state not in ("win", "game_over"):
                    _locus(
                        "@LOCUS what mechanics should I revise before the next level?",
                        f"REVISION after level {obs.levels_completed}",
                    )

            prev_levels = obs.levels_completed
            level_start_step = step

            if stop_after_offline and obs.levels_completed >= offline_levels:
                if verbose:
                    print(f"[agent] Offline phase done after L{offline_levels} — stopping")
                break

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

    # -- Persist session log (only if LOCUS was used) ------------------------
    log_path = None
    if locus_entries:
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
