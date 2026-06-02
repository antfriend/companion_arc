"""
core/step_runner.py — Unified step-by-step play loop for all modes.

All three modes (practice / batch / competition) run the same play_game()
loop. Mode-specific behavior lives entirely in the Policy object passed in:

  PracticePolicy   — on verify fail: ask LOCUS for a recovery action
  BatchPolicy      — on verify fail: retry once, then random
  CompetitionPolicy — on verify fail: retry once, then systematic sweep, then random

Usage:
    from core.step_runner import play_game, PracticePolicy, BatchPolicy
    from core.game_registry import get_detector, get_companion_path

    detector = get_detector(game_id)
    policy   = PracticePolicy(locus_fn=..., parse_action_fn=..., n_actions=4)
    result   = play_game(env, game_id, detector, routes, policy, max_steps=200)
"""

import random
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class LevelResult:
    level_num: int
    steps: int
    completed: bool
    verify_log: list   # list of (step_idx, action, StepResult)


@dataclass
class GameResult:
    game_id: str
    total_steps: int
    levels_completed: int
    final_state: str
    level_results: list  # list[LevelResult]
    locus_entries: list  # forwarded from policy


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------

class PracticePolicy:
    """
    Practice mode: on verify fail, ask LOCUS for a recovery action.

    locus_fn(msg, label) → str
    parse_action_fn(text, n) → int | None
    """
    def __init__(
        self,
        locus_fn: Callable,
        parse_action_fn: Callable,
        n_actions: int,
    ) -> None:
        self._locus = locus_fn
        self._parse = parse_action_fn
        self._n = n_actions
        self.locus_entries: list = []

    def on_verify_fail(self, result, step_idx: int, action: int) -> Optional[int]:
        action_name = ["UP", "DOWN", "LEFT", "RIGHT"][action] if action < 4 else str(action)
        msg = (
            f"@LOCUS verify_fail at step {step_idx}: {result.reason}\n"
            f"action was: {action} ({action_name})\n"
            f"before_pos: {result.delta.get('before_pos')}\n"
            f"after_pos:  {result.delta.get('after_pos')}\n"
            f"What action should I take to recover? Respond with only the action number."
        )
        reply = self._locus(msg, f"VERIFY_FAIL step={step_idx}")
        self.locus_entries.append({"label": f"VERIFY_FAIL step={step_idx}",
                                   "sent": msg, "received": reply})
        recovered = self._parse(reply, self._n)
        return recovered

    def on_locus_action(self, obs, actions, step, prev_frames,
                        last_blocked, last_action_idx) -> Optional[int]:
        """Called when no route step is available — LOCUS decides."""
        return None  # caller handles LOCUS directly; this hook is a placeholder


class BatchPolicy:
    """
    Batch mode: retry once on verify fail, then random.
    No LOCUS calls.
    """
    def __init__(self, n_actions: int, seed: int = 0) -> None:
        self._n = n_actions
        self._rng = random.Random(seed)
        self._last_failed: Optional[int] = None
        self.locus_entries: list = []

    def on_verify_fail(self, result, step_idx: int, action: int) -> Optional[int]:
        if self._last_failed == action:
            # Already retried this action — go random
            self._last_failed = None
            return self._rng.randrange(self._n)
        self._last_failed = action
        return action  # retry once


class CompetitionPolicy:
    """
    Competition mode: retry once, then systematic sweep, then random.
    No LOCUS calls.
    """
    def __init__(self, n_actions: int) -> None:
        self._n = n_actions
        self._rng = random.Random()
        self._retry_count: dict = {}  # step_idx → count
        self._sweep: list = []
        self._sweep_pos: int = 0
        self.locus_entries: list = []

    def on_verify_fail(self, result, step_idx: int, action: int) -> Optional[int]:
        count = self._retry_count.get(step_idx, 0)
        self._retry_count[step_idx] = count + 1
        if count == 0:
            return action  # retry once
        # Build sweep queue if needed
        if not self._sweep:
            self._sweep = self._build_sweep()
        if self._sweep_pos < len(self._sweep):
            a = self._sweep[self._sweep_pos] % self._n
            self._sweep_pos += 1
            return a
        return self._rng.randrange(self._n)

    def _build_sweep(self) -> list:
        seq = []
        for repeat in range(1, 6):
            for a in range(self._n):
                seq.extend([a] * repeat)
        return seq


# ---------------------------------------------------------------------------
# Unified play loop
# ---------------------------------------------------------------------------

def play_game(
    env,
    game_id: str,
    detector,
    routes: dict,          # {level_num: list[int]} — pre-computed routes
    policy,                # PracticePolicy | BatchPolicy | CompetitionPolicy
    max_steps: int = 200,
    verbose: bool = True,
) -> GameResult:
    """
    Run one full game episode with step-by-step frame verification.

    detector must implement: detect_state, compute_route, verify_step.
    routes provides pre-computed action sequences per level (1-based keys).
    policy handles recovery when verify_step returns success=False.

    After every action:
      1. read the new frame
      2. call detector.verify_step(prev_frame, new_frame, action)
      3. log the result
      4. if not success: call policy.on_verify_fail → get recovery action

    Returns GameResult with per-level verify logs.
    """
    obs = None
    prev_frame: Optional[np.ndarray] = None
    step = 0
    prev_levels = 0
    level_start_step = 0
    level_results: list = []
    verify_log: list = []   # current level's verify log
    level_scanned = False
    current_snapshot = None

    while step < max_steps:
        all_actions = env.action_space
        actions = [a for a in (all_actions or []) if a.is_simple()]
        if not actions:
            break

        n = len(actions)
        current_level = (obs.levels_completed if obs is not None else 0) + 1
        level_step = step - level_start_step

        # --- Choose action --------------------------------------------------
        route = routes.get(current_level)
        route_idx = level_step - 1  # level_step starts at 1 after first obs

        if route is not None and 0 <= route_idx < len(route):
            action_idx = route[route_idx]
            if verbose:
                name = ["UP", "DOWN", "LEFT", "RIGHT"][action_idx] if action_idx < 4 else str(action_idx)
                print(f"[runner] step={step} L{current_level}[{route_idx}] "
                      f"route={action_idx} ({name})")
        else:
            # No route available — random fallback (override in caller for LOCUS)
            action_idx = random.randrange(n)
            if verbose:
                print(f"[runner] step={step} L{current_level} random={action_idx}")

        action_idx = action_idx % n
        action = actions[action_idx]

        # --- Execute ---------------------------------------------------------
        obs = env.step(action)
        step += 1

        # --- Frame capture + verify -----------------------------------------
        if obs.frame:
            new_frame = obs.frame[0]

            # First frame of this level: detect + (re)compute route
            if not level_scanned:
                if detector is not None:
                    try:
                        state = detector.detect_state(new_frame)
                        adaptive = detector.compute_route(state)
                        routes[current_level] = adaptive
                        if verbose:
                            print(f"[runner] L{current_level} adaptive route: "
                                  f"{adaptive} ({len(adaptive)} steps)")
                    except Exception as exc:
                        if verbose:
                            print(f"[runner] detect/route failed L{current_level}: {exc}")
                level_scanned = True
                current_snapshot = new_frame.copy()

            # Verify this step
            if prev_frame is not None and detector is not None:
                try:
                    vr = detector.verify_step(prev_frame, new_frame, action_idx)
                    verify_log.append((step, action_idx, vr))
                    if verbose:
                        status = "OK" if vr.success else "FAIL"
                        print(f"[verify] step={step} {['UP','DOWN','LEFT','RIGHT'][action_idx] if action_idx < 4 else action_idx} "
                              f"→ {status}: {vr.reason}")

                    if not vr.success:
                        recovery = policy.on_verify_fail(vr, step, action_idx)
                        if recovery is not None:
                            # Execute recovery immediately
                            r_action = actions[recovery % n]
                            obs = env.step(r_action)
                            step += 1
                            if obs.frame:
                                r_frame = obs.frame[0]
                                r_vr = detector.verify_step(new_frame, r_frame, recovery)
                                verify_log.append((step, recovery, r_vr))
                                if verbose:
                                    rs = "OK" if r_vr.success else "FAIL"
                                    print(f"[verify] step={step} RECOVERY "
                                          f"{['UP','DOWN','LEFT','RIGHT'][recovery] if recovery < 4 else recovery} "
                                          f"→ {rs}: {r_vr.reason}")
                                new_frame = r_frame
                except Exception as exc:
                    if verbose:
                        print(f"[verify] error at step={step}: {exc}")

            prev_frame = new_frame

        if verbose:
            print(f"[runner] step={step} state={obs.state} levels={obs.levels_completed}")

        # --- Level transition -----------------------------------------------
        if obs.levels_completed > prev_levels:
            level_steps = step - level_start_step
            level_results.append(LevelResult(
                level_num=obs.levels_completed,
                steps=level_steps,
                completed=True,
                verify_log=list(verify_log),
            ))
            verify_log = []
            prev_levels = obs.levels_completed
            level_start_step = step
            level_scanned = False

        # --- Game end -------------------------------------------------------
        if obs.state in ("win", "game_over"):
            break

    return GameResult(
        game_id=game_id,
        total_steps=step,
        levels_completed=obs.levels_completed if obs else 0,
        final_state=obs.state if obs else "not_started",
        level_results=level_results,
        locus_entries=getattr(policy, "locus_entries", []),
    )
