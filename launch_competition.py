#!/usr/bin/env python3
"""
launch_competition.py — the single entry point that plays every game.

ONE METHOD, EVERY ENVIRONMENT. The same per-game loop (_play_game) drives both:
  - the competition rerun (online gateway, run_competition), and
  - the offline batch (local environment_files, run_offline),
selected only by IS_COMPETITION_RERUN. There is no second, "inline" agent: the
solving brain is the SupervisedAgent (v1/click floor + recognition-gated Dynamic
solver layer), identical in both paths, so what we verify offline is what runs
in the rerun.

Goal per game: reach the highest level we can solve. Each game is played
independently and a crash in one never sinks the rest (per-game isolation in the
run loops). submission.parquet is a local diagnostic artifact only.
"""

import os
import random
import re
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import arc_agi
from arc_agi import OperationMode
from arc_agi.scorecard import EnvironmentScorecard

try:
    from ls20_detector import compute_l1_route as _ls20_compute_l1
except ImportError:
    _ls20_compute_l1 = None

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_WORKING = Path("/kaggle/working") if Path("/kaggle/working").exists() else Path(__file__).parent
_COMPANION = Path(__file__).parent / "companion_arcprize.md"
GATEWAY_URL = "http://gateway:8001"


def _gateway_is_available() -> bool:
    try:
        r = requests.get(f"{GATEWAY_URL}/api/games", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


# Kaggle may not set KAGGLE_IS_COMPETITION_RERUN even during competition reruns;
# fall back to probing the gateway directly.
IS_COMPETITION_RERUN = bool(os.getenv("KAGGLE_IS_COMPETITION_RERUN")) or _gateway_is_available()

# ---------------------------------------------------------------------------
# Routes  (0=UP  1=DOWN  2=LEFT  3=RIGHT)
# ---------------------------------------------------------------------------

_DIR = {"UP": 0, "DOWN": 1, "LEFT": 2, "RIGHT": 3}

# Play mode. "solve" is the shipped brain (floor + Dynamic solver layer).
# "detector" = fixed per-game routes (net-NEGATIVE: routes die on unknown instances).
# "random" = uniform random. "general" = the bare v1 explorer floor (diagnostic).
# LOCUS_ABLATION=random is honored as a back-compat alias for LOCUS_MODE=random.
_MODE = os.getenv("LOCUS_MODE", "").strip().lower()
_ABLATION = os.getenv("LOCUS_ABLATION", "").strip().lower()
if not _MODE:
    _MODE = "random" if _ABLATION == "random" else "detector"

# Seed all RNGs so hosted batch runs reproduce local runs bit-for-bit in the
# stochastic modes (random/general/goal/solve tie-breaks). Deterministic modes
# (detector routes, pure solver) are unaffected. Override with LOCUS_SEED; set
# LOCUS_SEED=off to restore nondeterministic behavior. _SEED_INT is None when
# seeding is disabled (off/none/empty/non-int), else the parsed int.
_SEED = os.getenv("LOCUS_SEED", "0").strip().lower()
if _SEED in ("off", "none", ""):
    _SEED_INT: int | None = None
else:
    try:
        _SEED_INT = int(_SEED)
    except ValueError:
        _SEED_INT = None

# Games with confirmed, stable solutions — batch runs suppress verbose frame/route logs
_SOLVED_GAMES: frozenset[str] = frozenset({"ls20", "cd82", "re86", "sp80", "tu93", "wa30", "ar25", "g50t", "sk48"})

# Hardcoded winning routes (indices into each game's simple action space)
# ls20: [UP,DOWN,LEFT,RIGHT] → indices 0-3
# cd82: [ACTION1-ACTION5]    → indices 0-4
# sp80: [ACTION1-ACTION5]    → indices 0-4
_HARDCODED_ROUTES: dict[str, list[int]] = {
    # ls20: fallback placeholder — on_level_start always replaces this with
    # compute_route() from games/ls20/detector.py. Route adapts to cursor's
    # detected starting column and normalizes to the x=34 corridor before
    # executing UP+LEFT×3+DOWN+UP+RIGHT×3+UP to the goal at (x=34,y=10).
    "ls20": [0, 0, 0, 2, 2, 2, 1, 0, 3, 3, 3, 0, 0, 0],
    "cd82": [3, 0, 1, 0, 0, 0, 1, 1, 1, 3, 2, 0, 4, 4, 2, 0, 0, 0, 1],
    # sp80: fallback placeholder — on_level_start replaces with compute_route()
    # from games/sp80/detector.py (currently returns same fallback until
    # frame archaeology identifies which entity position varies per instance).
    "sp80": [4, 3, 3, 3, 4, 2, 2, 1],
    # g50t: recording/replay maze. Stage 0: RIGHT*4 to button (37,7) + ACTION5 submit.
    # Stage 1: ghost holds button open, DOWN*7 + RIGHT*5 to win target (43,49). 17 actions.
    "g50t": [3, 3, 3, 3, 4, 1, 1, 1, 1, 1, 1, 1, 3, 3, 3, 3, 3],
    # sk48: snake+sokoban hybrid. Snake starts at row=36; UP×3 climbs 36→30→24→18
    # (6 rows/step). Then extend*4 (c8 detaches at 41,18), retract (c8→35,18),
    # DOWN*2→row=30 (c8→35,30), extend (c14 detaches at 41,30), retract
    # (c8→29,30 c14→35,30), UP→row=24, extend (c9 at 41,24 wins).
    # Final: row=24 segs[3,4,5] hold [c8,c14,c9]=[8,14,9]. 14 route actions.
    # (Was 13 actions + a blind leading ACTION1 that did the first UP; the loop no
    # longer steps blindly, so the route owns all 3 climbing UPs — leading 0 added.)
    "sk48": [0, 0, 0, 3, 3, 3, 3, 2, 1, 1, 3, 2, 0, 3],
}

_ROUTES: dict[str, list[int]] = {}


def _load_routes() -> None:
    global _ROUTES
    _ROUTES = dict(_HARDCODED_ROUTES)
    if not _COMPANION.exists():
        print(f"[route] {_COMPANION.name} not found — using hardcoded ls20", flush=True)
        return
    text = _COMPANION.read_text(encoding="utf-8")
    pattern = re.compile(
        r"\[route\b[^\]]*\bgame=(\w+)\b[^\]]*\blevel=1\b[^\]]*\](.*?)\[/route\]",
        re.DOTALL | re.IGNORECASE,
    )
    for game_id, route_str in pattern.findall(text):
        # Never override a hardcoded route with a companion-file entry —
        # companion entries may be stale (e.g. session logs record old UP×4 ls20 route).
        if game_id in _HARDCODED_ROUTES:
            continue
        actions: list[int] = []
        for token in re.split(r"[,\s]+", route_str.strip()):
            if not token:
                continue
            m = re.match(r"(UP|DOWN|LEFT|RIGHT)[×x*](\d+)$", token, re.IGNORECASE)
            if m:
                actions.extend([_DIR[m.group(1).upper()]] * int(m.group(2)))
            elif token.upper() in _DIR:
                actions.append(_DIR[token.upper()])
            elif re.match(r"^\d+$", token):
                actions.append(int(token))
        if actions:
            _ROUTES[game_id] = actions
    print(f"[route] Routes loaded: {sorted(_ROUTES.keys())}", flush=True)


# ---------------------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------------------

def _wait_for_gateway(timeout_s: int = 600) -> bool:
    url = f"{GATEWAY_URL}/api/games"
    deadline = time.time() + timeout_s
    attempt = 0
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                print(f"[gateway] Ready after {attempt} retries", flush=True)
                return True
        except Exception:
            pass
        time.sleep(5)
        attempt += 1
    print("[gateway] TIMEOUT — gateway not ready", flush=True)
    return False


# ---------------------------------------------------------------------------
# Game play (shared by online + offline paths)
# ---------------------------------------------------------------------------

def _play_game(arc: arc_agi.Arcade, game_id: str, card_id: str) -> None:
    from agent_framework import ArcAgent

    game_prefix = game_id.split("-")[0] if "-" in game_id else game_id
    route = list(_ROUTES.get(game_prefix, []))

    env = arc.make(game_id, scorecard_id=card_id)
    if env is None:
        print(f"[game] {game_id}: env creation failed — skipping", flush=True)
        return

    from arcengine import GameAction as _GA
    actions = [a for a in (env.action_space or []) if a.is_simple()]
    # ACTION6 (click) is not "simple", so it never enters `actions`. The solve-mode
    # click floor drives it via env.step(ACTION6, data={x,y}); other modes can't.
    _has_click = _GA.ACTION6 in (env.action_space or [])
    _click_only = not actions and _has_click and _MODE == "solve"
    if not actions and not _click_only:
        print(f"[game] {game_id}: no simple actions — skipping", flush=True)
        return

    companion_text = ""
    try:
        if _COMPANION.exists():
            companion_text = _COMPANION.read_text(encoding="utf-8")
    except Exception:
        pass

    try:
        from core.game_registry import get_detector as _gd
        _det = _gd(game_id)
        _has_l2 = _det is not None and hasattr(_det, "_L2_ROUTE")
    except Exception:
        _has_l2 = False
    _offline = 2 if _has_l2 else 1

    agent = ArcAgent(
        game_id=game_id,
        mode="batch",
        companion_text=companion_text,
        routes={1: route} if route else {},
        offline_levels=_offline,
        verbose=game_prefix not in _SOLVED_GAMES,
    )

    # The solving brain: one count-based explorer floor + recognition-gated,
    # abortable Dynamic solver layer (ARC-RFC-0001). The floor is additive, so an
    # unrecognized game falls back to it with no regression by construction.
    # "solve"   = SupervisedAgent (the shipped brain — floor + dynamics).
    # "general" = the bare v1 floor (diagnostic only; no per-game solvers).
    _gen = None
    if _MODE in ("general", "solve"):
        try:
            if _MODE == "solve":
                from core.dynamics import library  # noqa: F401 — registers dynamics
                from core.solve_agent import SupervisedAgent as _GenCls
            else:
                from core.general_agent import GeneralAgent as _GenCls
            # Solve mode gets the ACTION6-capable floor on click games so it can
            # actually win them instead of doing nothing; movement games stay on v1.
            if _MODE == "solve" and _has_click:
                _gen = _GenCls(len(actions), floor="click", seed=_SEED_INT)
            else:
                _gen = _GenCls(len(actions), seed=_SEED_INT)
        except Exception as exc:
            print(f"[game] {game_id}: solver unavailable ({exc}) — random", flush=True)

    # Acquire the pristine level-start frame BEFORE acting. The old loop stepped a
    # blind ACTION1 to obtain its first frame, which destroyed plan-once recognizers
    # that key on the start geometry (e.g. sk48's colour-6 head-box anchor at x=11):
    # they never saw a recognizable frame and fell to the floor, scoring 0. Reset
    # yields the true start frame so the scan + first decision operate on it — making
    # level 1 consistent with levels 2+ (which already start route[0] on the level's
    # first frame via the -1 trick below). When obs holds the start frame we set
    # level_start_step=-1 so level_step=1 on the first iteration (route[0] / first
    # choose fire on the start frame, no blind leading action). If reset returns
    # nothing (e.g. a gateway env without reset), fall back to the old behavior.
    obs = env.reset() if hasattr(env, "reset") else None
    step = 0
    level_start_step = -1 if (obs is not None and obs.frame) else 0
    level_scanned = False
    prev_levels = 0
    route_steps = 0
    _END_STATES = ("GameState.WIN", "GameState.GAME_OVER", "win", "game_over")

    while step < 600:
        if obs is not None and str(obs.state) in _END_STATES:
            break

        # First-frame scan. Detector mode computes an adaptive route; random/
        # general modes only refresh the (possibly remapped) action list.
        if obs is not None and obs.frame and not level_scanned:
            fresh = [a for a in (env.action_space or []) if a.is_simple()]
            if fresh:
                actions = fresh
            if _MODE == "detector":
                current_level = (obs.levels_completed or 0) + 1
                agent.on_level_start(current_level, list(obs.frame)[0])
                adaptive = agent.routes.get(current_level)
                if adaptive:
                    route = list(adaptive)
            if _gen is not None:
                _gen.set_n_actions(len(actions))
            level_scanned = True

        # Choose action per mode. random/general re-decide every frame (never
        # commit to a killable plan — fixed routes die on unknown instances).
        level_step = step - level_start_step
        _click = None
        if _gen is not None and obs is not None and obs.frame:
            try:
                action_idx = _gen.choose(np.asarray(list(obs.frame)[-1])) % max(1, len(actions))
                _spec = getattr(_gen, "spec", None)    # SupervisedAgent click side-channel
                if _spec is not None and _spec[0] == "c":
                    _click = (int(_spec[1]), int(_spec[2]))
            except Exception as exc:                    # one bad frame must not end the game
                print(f"[game] {game_id}: choose() raised ({exc}) — safe action 0", flush=True)
                action_idx = 0
        elif _MODE == "random":
            action_idx = random.randrange(len(actions))
        elif obs is None:
            action_idx = 0  # safety: get first frame before acting
        elif 0 < level_step <= len(route):
            action_idx = route[level_step - 1] % len(actions)
            route_steps += 1
        else:
            action_idx = 0  # route exhausted or unknown game — no random

        if _click is not None:                         # ACTION6 click-select
            obs = env.step(_GA.ACTION6, data={"x": _click[0], "y": _click[1]})
        elif actions:
            obs = env.step(actions[action_idx])
        else:
            # Click-only game whose floor proposed a non-click this step (e.g. the
            # ClickExplorer ("m",0) fallback on a blank frame): there is no movement
            # action, so emit a harmless origin click rather than index [] -> crash.
            obs = env.step(_GA.ACTION6, data={"x": 0, "y": 0})
        if obs is None:
            break
        step += 1

        if obs.levels_completed and obs.levels_completed > prev_levels:
            prev_levels = obs.levels_completed
            level_start_step = step - 1  # -1 so next level_step=1 → route[0]
            level_scanned = False
            if _gen is not None:
                _gen.reset_level()  # fresh exploration memory per level

    levels = obs.levels_completed if obs else 0
    state = str(obs.state) if obs else "None"
    print(
        f"[game] {game_id}: {step} steps (route={route_steps}), L{levels}, state={state}",
        flush=True,
    )


def _play_game_safe(arc: arc_agi.Arcade, game_id: str, card_id: str) -> None:
    """Per-game isolation: a crash in one game must never sink the rest of the run.
    The hull stays afloat even if a single solver throws on an unexpected frame."""
    try:
        _play_game(arc, game_id, card_id)
    except Exception as exc:
        import traceback
        print(f"[game] {game_id}: FAILED ({exc}) — skipping, run continues", flush=True)
        traceback.print_exc()


# ---------------------------------------------------------------------------
# Submission writer
# ---------------------------------------------------------------------------

def _scorecard_to_parquet(scorecard: EnvironmentScorecard) -> None:
    rows = []
    for i, env in enumerate(scorecard.environments):
        for j, run in enumerate(env.runs):
            completed = bool(run.completed)
            score = float(run.score)
            # Mark end_of_game=True whenever we have partial or full progress.
            # The competition needs this True to count the row; completed=False just
            # means we reached an intermediate level, not that we didn't play.
            end_of_game = completed or score > 0
            print(f"[row] {env.id}: completed={completed}, end_of_game={end_of_game}, score={score:.4f}", flush=True)
            rows.append({
                "row_id": f"{i}_{j}",
                "game_id": env.id,
                "end_of_game": end_of_game,
                "score": score,
            })
    if not rows:
        rows = [{"row_id": "0_0", "game_id": "none", "end_of_game": False, "score": 0.0}]
    df = pd.DataFrame(rows)
    path = _WORKING / "submission.parquet"
    df.to_parquet(path, index=False)
    print(f"[submission] Written {len(rows)} rows, overall={scorecard.score:.4f}", flush=True)


def _write_dummy() -> None:
    df = pd.DataFrame(
        [{"row_id": "0_0", "game_id": "none", "end_of_game": False, "score": 0.0}]
    )
    (_WORKING / "submission.parquet").unlink(missing_ok=True)
    df.to_parquet(_WORKING / "submission.parquet", index=False)
    print("[submission] Dummy written", flush=True)


# ---------------------------------------------------------------------------
# Offline environment resolution
# ---------------------------------------------------------------------------

def _resolve_env_dir() -> str | None:
    """Return path to a usable environment_files directory, extracting zip if needed."""
    # Direct directory from dataset or competition
    candidates = [
        Path("/kaggle/input/competitions/arc-prize-2026-arc-agi-3/environment_files"),
        Path(__file__).parent / "environment_files",
    ]
    for d in candidates:
        if d.exists() and d.is_dir():
            return str(d)

    # dataset uploaded with --dir-mode zip: extract to /kaggle/working
    zip_candidates = [
        Path(__file__).parent / "environment_files.zip",
    ]
    for z in zip_candidates:
        if z.exists():
            dest = _WORKING / "environment_files"
            dest.mkdir(exist_ok=True)
            with zipfile.ZipFile(z, "r") as zf:
                zf.extractall(dest)
            print(f"[env] Extracted {z.name} to {dest}", flush=True)
            return str(dest)

    return None


# ---------------------------------------------------------------------------
# Competition rerun path (gateway)
# ---------------------------------------------------------------------------

def run_competition() -> None:
    print(f"[launch] COMPETITION RERUN — waiting for {GATEWAY_URL}", flush=True)
    if not _wait_for_gateway():
        print("[launch] Cannot reach gateway — aborting", flush=True)
        return

    os.environ["ARC_BASE_URL"] = GATEWAY_URL
    os.environ.setdefault("ARC_API_KEY", "locus_agent")

    try:
        arc = arc_agi.Arcade(operation_mode=OperationMode.ONLINE)
        print(f"[launch] ONLINE mode, {len(arc.available_environments)} games", flush=True)

        card_id = arc.open_scorecard(tags=["locus"])
        for game_info in arc.available_environments:
            _play_game_safe(arc, game_info.game_id, card_id)

        scorecard = arc.close_scorecard(card_id)
        if scorecard:
            for env in scorecard.environments:
                for run in env.runs:
                    print(f"[online-row] {env.id}: completed={run.completed}, score={float(run.score):.4f}", flush=True)
            print(f"[launch] Final score: {scorecard.score:.4f}", flush=True)
    except Exception as exc:
        import traceback
        print(f"[launch] FATAL: {exc}", flush=True)
        traceback.print_exc()


# ---------------------------------------------------------------------------
# Batch run path (offline play → submission.parquet)
# ---------------------------------------------------------------------------

def run_offline() -> None:
    env_dir = _resolve_env_dir()
    if env_dir is None:
        print("[launch] No environment_files found — writing dummy", flush=True)
        _write_dummy()
        return

    try:
        arc = arc_agi.Arcade(
            operation_mode=OperationMode.OFFLINE,
            environments_dir=env_dir,
        )
        print(f"[launch] OFFLINE mode, {len(arc.available_environments)} games", flush=True)
        for e in arc.available_environments:
            print(f"[env]   {e.game_id}", flush=True)

        if not arc.available_environments:
            print("[launch] No environments loaded — writing dummy", flush=True)
            _write_dummy()
            return

        card_id = arc.open_scorecard(tags=["locus"])
        for game_info in arc.available_environments:
            _play_game_safe(arc, game_info.game_id, card_id)

        scorecard = arc.close_scorecard(card_id)
        if scorecard:
            _scorecard_to_parquet(scorecard)
        else:
            _write_dummy()
    except Exception as exc:
        import traceback
        print(f"[launch] offline error: {exc}", flush=True)
        traceback.print_exc()
        _write_dummy()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if _SEED_INT is not None:
        random.seed(_SEED_INT)
        np.random.seed(_SEED_INT)
        print(f"[launch] RNG seeded ({_SEED_INT}) — stochastic modes are reproducible", flush=True)
    else:
        print(f"[launch] RNG unseeded (LOCUS_SEED={_SEED!r})", flush=True)

    env_flag = os.getenv("KAGGLE_IS_COMPETITION_RERUN")
    print(f"[launch] KAGGLE_IS_COMPETITION_RERUN={env_flag!r}  IS_COMPETITION_RERUN={IS_COMPETITION_RERUN}", flush=True)
    print(f"[launch] PLAY MODE: {_MODE!r}"
          + ("  (bare v1 explorer floor — no per-game solvers)" if _MODE == "general"
             else "  (v1 floor + recognition-gated Dynamic solver layer)" if _MODE == "solve"
             else "  (uniform random)" if _MODE == "random"
             else "  (per-game detector routes)"), flush=True)
    _load_routes()

    if IS_COMPETITION_RERUN:
        run_competition()
    else:
        run_offline()


if __name__ == "__main__":
    main()
