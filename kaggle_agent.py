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
from pathlib import Path

import numpy as np
import anthropic
import arc_agi

from ls20_detector import compute_l1_route, format_strategy_block, update_strategy_in_file
from agent_framework import ArcAgent

try:
    from core.game_registry import get_detector as _get_detector
except ImportError:
    _get_detector = None

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
# L1 is now computed adaptively from the first frame via ls20_detector.compute_l1_route.
# A safe initial [0] seed is used for level_step 1 (UP is always valid from start).
# DC31 (session 67): extends DC30 with post-reset ring A approach (steps 60-75).
# DC30 sessions 64-66: micro-oscillation (steps 54-59) expires timer; block resets to
# r40-41 c29-33. DC30 steps 60-64 (DOWN x5) were void-blocked at reset position.
# DC31 replaces them: RIGHT + UP×6 + LEFT×4 + DOWN (ring A x2) + DOWN×4 (probe).
# Wide-connector rule: c14-18 unreachable from c29-38 at rows 15-38 by direct LEFT;
# must go UP to rows 10-14 first (confirmed sessions 64-66, DC31 Dream Cycle).
# max_steps=125 → L2 budget=110; 75 hardcoded (route[0-74]) + 35 LOCUS = 110
_LEVEL2_ROUTE = [
    # First ring B probe (20 steps) — state 2 trigger + timer reset
    3,                              # L2 step 1:  RIGHT → r40-41 c34-38
    0, 0, 0, 0, 0, 0,               # L2 steps 2-7:  UP×6 → r10-11 c34-38
    3, 3, 3,                        # L2 steps 8-10: RIGHT×3 → r10-11 c49-53
    1, 1, 1, 1, 1, 1,               # L2 steps 11-16: DOWN×6 → r40-41 c49-53
    2, 1, 1, 2,                     # L2 steps 17-20: L,D,D,L → r50-51 c39-43 [ring B; STATE 2; timer reset 21]
    # Navigate ring B → cross at r45-46 c49-53 (3 steps; timer: 42-6=36 cols=18 steps)
    3, 3,                           # L2 steps 21-22: RIGHT×2 → r50-51 c49-53
    0,                              # L2 step 23: UP → r45-46 c49-53 [cross; second collectible; no timer reset]
    # Ascend c49-53 to wide connector (7 steps; timer: 36-14=22 cols=11 steps)
    0, 0, 0, 0, 0, 0, 0,            # L2 steps 24-30: UP×7 → r10-11 c49-53
    # Traverse wide connector to c14-18 (7 steps; timer: 22-14=8 cols=4 steps)
    2, 2, 2, 2, 2, 2, 2,            # L2 steps 31-37: LEFT×7 → r10-11 c14-18
    # Collect ring A (third collectible; timer reset 21=42 cols)
    1,                              # L2 step 38: DOWN → r15-16 c14-18 [ring A; timer reset]
    # Descend to deadlock (timer: 42-8=34 cols=17 steps at handoff)
    1, 1, 1, 1,                     # L2 steps 39-42: DOWN×4 → r35-36 c14-18 [deadlock; timer=17]
    # Ring A second cycle: UP×5 + LEFT/RIGHT micro-oscillation ×6 (17 steps; timer expiry at step ~59)
    0, 0, 0, 0,                     # L2 steps 43-46: UP×4 → r15-16 c14-18 (timer: 17→13)
    0,                              # L2 step 47: UP×1 → r10-11 c14-18 (timer: 13→12; wide connector)
    2, 3, 2, 3, 2, 3,               # L2 steps 48-53: LEFT-RIGHT×3 oscillate c9-13↔c14-18 (timer: 12→6)
    2, 3, 2, 3, 2, 3,               # L2 steps 54-59: LEFT-RIGHT×3 oscillate c9-13↔c14-18 (timer: 6→0; ring A+B RESPAWN; block resets to r40-41 c29-33)
    # DC31 post-reset: wide-connector approach to ring A second collection + entity1 probe (16 steps)
    3,                              # L2 step 60: RIGHT → r40-41 c34-38 [post-reset; timer=21 fresh]
    0, 0, 0, 0, 0, 0,               # L2 steps 61-66: UP×6 → r10-11 c34-38
    2, 2, 2, 2,                     # L2 steps 67-70: LEFT×4 → r10-11 c14-18
    1,                              # L2 step 71: DOWN → r15-16 c14-18 [ring A x2; timer reset 21]
    1, 1, 1, 1,                     # L2 steps 72-75: DOWN×4 → r35-36 c14-18 [10A probe; timer=17]
]  # 75-step DC31 probe; LOCUS gets 20 L2 steps (max_steps=110; 75+20=95)
# L1 seed: a single UP so the loop has something to execute on step 1.
# This is replaced by the adaptive route after the first frame is received.
_L1_SEED = [0]
_HARDCODED_ROUTES: dict[int, list[int]] = {1: _L1_SEED, 2: _LEVEL2_ROUTE}


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

    DC18 fix: strip surrounding backtick/quote characters before bare-number
    check. LOCUS sometimes formats its answer as `3` (code span); the original
    regex r"^\\d+$" rejects this, causing the fallback to extract the wrong digit
    from earlier in the response (e.g. "0" from "Frames [0]-[4]").
    """
    # Priority: last non-empty line bare number (handles `3`, '3', "3" wrapping)
    for line in reversed(text.strip().splitlines()):
        stripped = line.strip().strip("`'\"‘’“”")
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
    environments_dir: str | None = None,
    game_routes: dict[int, list[int]] | None = None,
    companion_path: "str | None" = None,
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

    if environments_dir is not None:
        arc = arc_agi.Arcade(
            operation_mode=OperationMode.OFFLINE,
            environments_dir=environments_dir,
        )
    elif competition_mode:
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
    _prev_frame_for_verify: "np.ndarray | None" = None
    _detector = _get_detector(game_id) if _get_detector else None

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

    # Use caller-supplied routes if provided, otherwise fall back to ls20 defaults
    _routes = dict(game_routes if game_routes is not None else _HARDCODED_ROUTES)
    _l1_adaptive_done = False  # track whether adaptive L1 route has been computed

    # -- ArcAgent (first-frame recording, levelmap comparison) ---------------
    _agent = ArcAgent(
        game_id=game_id,
        mode="training",
        companion_text=companion_text or "",
        companion_path=companion_path,
        routes=_routes,
        offline_levels=offline_levels,
        locus_fn=_locus,
        format_state_fn=_format_state,
        parse_action_fn=parse_action,
        verbose=verbose,
    )
    _level_scanned = False   # reset each level; triggers on_level_start

    # -- Main loop -----------------------------------------------------------
    while step < max_steps:
        all_actions = env.action_space
        # Filter to simple (non-click) actions only to avoid crashes on games
        # that require x/y coordinate data (e.g. bp35)
        actions = [a for a in (all_actions or []) if a.is_simple()]
        if not actions:
            if verbose:
                print("[agent] No simple actions available — episode complete.")
            break

        current_level = (obs.levels_completed if obs is not None else 0) + 1
        level_step = step - level_start_step
        route = _routes.get(current_level)
        in_offline = offline_levels > 0 and (obs is None or obs.levels_completed < offline_levels)

        if in_offline and route is not None and level_step - 1 < len(route):
            # Offline phase: hardcoded route for this level, no LOCUS
            action_idx = route[level_step - 1]
            if verbose:
                _names = ["UP", "DOWN", "LEFT", "RIGHT", "ACTION5", "ACTION6"]
                _name = _names[action_idx] if action_idx < len(_names) else str(action_idx)
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
            cur_frame = prev_frames[0]

            # Step verification — replaces the simple last_action_blocked check
            if _prev_frame_for_verify is not None and _detector is not None:
                try:
                    _vr = _detector.verify_step(
                        _prev_frame_for_verify, cur_frame, last_action_idx
                        if last_action_idx is not None else 0
                    )
                    last_action_blocked = not _vr.success
                    if verbose:
                        _vs = "OK" if _vr.success else "FAIL"
                        print(f"[verify] step={step} "
                              f"{['UP','DOWN','LEFT','RIGHT'][last_action_idx] if last_action_idx is not None and last_action_idx < 4 else last_action_idx} "
                              f"→ {_vs}: {_vr.reason}")
                except Exception:
                    # Fall back to legacy block-position comparison
                    cur_block_pos = _find_block_pos(cur_frame)
                    last_action_blocked = (
                        prev_block_pos is not None
                        and cur_block_pos is not None
                        and cur_block_pos == prev_block_pos
                    )
                    prev_block_pos = cur_block_pos
            else:
                cur_block_pos = _find_block_pos(cur_frame)
                last_action_blocked = (
                    prev_block_pos is not None
                    and cur_block_pos is not None
                    and cur_block_pos == prev_block_pos
                )
                prev_block_pos = cur_block_pos

            _prev_frame_for_verify = cur_frame

            # First-frame capture: trigger on_level_start once per level
            if not _level_scanned:
                _current_level = (obs.levels_completed if obs is not None else 0) + 1
                _agent.on_level_start(_current_level, cur_frame)
                # Sync adaptive route back from agent
                _routes.update(_agent.routes)
                _level_scanned = True

            # Legacy adaptive route flag (kept for compatibility)
            if (not _l1_adaptive_done
                    and obs.levels_completed == 0
                    and game_id.startswith("ls20")
                    and offline_levels >= 1):
                _l1_adaptive_done = True  # compute_l1_route already called in agent
        else:
            last_action_blocked = False
            _prev_frame_for_verify = None

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
                _agent.on_level_complete(obs.levels_completed, level_steps)
                # Reset level scan flag for next level
                _level_scanned = False
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

            _agent.on_game_end(obs.state, obs.levels_completed, step)
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
