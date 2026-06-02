"""
agent_framework.py — Common ARC-AGI-3 agent framework for all run modes.

Provides a single ArcAgent class used by:
  - Training:    run_training_attempt (kaggle_agent.py)
  - Batch:       _play_game (launch_competition.py)
  - Competition: LucusAgent (kaggle_notebook.ipynb)

All modes share:
  - First-frame capture at level start (on_level_start)
  - Entity/levelmap detection and comparison (via level_scanner)
  - Unified action decision tree (choose_action)

Mode-specific behavior:
  - 'training': writes [levelmap] blocks to companion_arcprize.md; calls LOCUS
  - 'batch':    reads stored levelmaps; uses random fallback (no LOCUS)
  - 'competition': reads stored levelmaps; uses systematic + random fallback
"""

import random
import re
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from level_scanner import (
    LevelSnapshot,
    LevelDiff,
    scan_level,
    diff_snapshots,
    snapshot_to_levelmap_block,
    update_levelmap_in_file,
    parse_all_levelmaps,
)
from ls20_detector import (
    compute_l1_route,
    format_strategy_block,
    update_strategy_in_file,
)

try:
    from core.game_registry import get_detector as _get_detector
except ImportError:
    _get_detector = None


class ArcAgent:
    """
    Unified ARC-AGI-3 agent for training, batch, and competition modes.

    Usage:
        agent = ArcAgent(game_id, 'training', companion_text, companion_path,
                         client=client, routes={1: _L1_SEED, 2: _LEVEL2_ROUTE},
                         locus_fn=_locus, format_state_fn=_format_state,
                         parse_action_fn=parse_action)
        ...
        agent.on_level_start(level_num, first_frame_grid)
        action_idx = agent.choose_action(obs, actions, step, level_step,
                                         prev_frames, last_action_blocked,
                                         last_action_idx)
        agent.on_level_complete(level_num, step_count)
        agent.on_game_end(state, levels_completed, total_steps)
    """

    def __init__(
        self,
        game_id: str,
        mode: str,                                  # 'training' | 'batch' | 'competition'
        companion_text: str = "",
        companion_path: Optional[str] = None,       # local path — training writes only
        routes: Optional[dict] = None,              # {level_num: [action_idx, ...]}
        offline_levels: int = 2,                    # levels using hardcoded route
        locus_fn: Optional[Callable] = None,        # _locus(msg, label) -> reply
        format_state_fn: Optional[Callable] = None, # _format_state(step, actions, ...) -> str
        parse_action_fn: Optional[Callable] = None, # parse_action(text, n) -> int|None
        verbose: bool = True,
    ) -> None:
        self._game_id = game_id
        self._game_prefix = game_id.split("-")[0] if "-" in game_id else game_id
        self._mode = mode
        self._companion_path = companion_path
        self._offline_levels = offline_levels
        self._verbose = verbose

        # Routes — working copy; adaptive updates go here
        self._routes: dict = dict(routes) if routes else {}

        # Stored snapshots from companion (loaded at init)
        self._stored_snapshots: dict = {}
        if companion_text:
            try:
                self._stored_snapshots = parse_all_levelmaps(companion_text, game_id)
                if verbose and self._stored_snapshots:
                    print(
                        f"[agent] levelmap: loaded {len(self._stored_snapshots)} stored "
                        f"snapshot(s) for {self._game_prefix}"
                    )
            except Exception as exc:
                if verbose:
                    print(f"[agent] levelmap load failed: {exc}")

        # LOCUS callables (training only)
        self._locus_fn = locus_fn
        self._format_state_fn = format_state_fn
        self._parse_action_fn = parse_action_fn

        # Per-session state
        self._current_level: int = 1
        self._current_snapshot: Optional[LevelSnapshot] = None
        self._diff: Optional[LevelDiff] = None
        self._locus_entries: list = []
        self._locus_initialized = False

        # Systematic sweep state (competition/training fallback)
        self._systematic_queue: list = []
        self._systematic_step: int = 0

        # Random fallback state
        self._rng = random.Random(hash(game_id) & 0xFFFFFFFF)

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def locus_entries(self) -> list:
        return self._locus_entries

    @property
    def current_snapshot(self) -> Optional[LevelSnapshot]:
        return self._current_snapshot

    @property
    def diff(self) -> Optional[LevelDiff]:
        return self._diff

    @property
    def routes(self) -> dict:
        return self._routes

    # ------------------------------------------------------------------
    # Level lifecycle
    # ------------------------------------------------------------------

    def on_level_start(self, level_num: int, grid: np.ndarray) -> None:
        """
        Call with the first obs.frame[0] grid when a new level begins.

        1. Scan entities from the grid → LevelSnapshot
        2. Compare to stored snapshot (if any)
        3. Write new levelmap block in training on first encounter
        4. Compute adaptive L1 route for ls20
        """
        self._current_level = level_num
        self._diff = None
        self._systematic_queue = []
        self._systematic_step = 0

        # Scan the frame
        try:
            snap = scan_level(grid, self._game_id, level_num)
            self._current_snapshot = snap
        except Exception as exc:
            if self._verbose:
                print(f"[agent] scan_level failed on L{level_num}: {exc}")
            self._current_snapshot = None
            return

        stored = self._stored_snapshots.get(level_num)

        if stored is None:
            # First encounter — record in training
            if self._mode == "training" and self._companion_path:
                try:
                    block = snapshot_to_levelmap_block(snap)
                    update_levelmap_in_file(self._companion_path, block,
                                            self._game_id, level_num)
                    self._stored_snapshots[level_num] = snap
                    if self._verbose:
                        print(f"[agent] levelmap written for L{level_num} "
                              f"({self._game_prefix})")
                except Exception as exc:
                    if self._verbose:
                        print(f"[agent] levelmap write failed: {exc}")
        else:
            # Compare current to stored
            try:
                self._diff = diff_snapshots(stored, snap)
                if self._verbose:
                    if self._diff.match:
                        print(
                            f"[agent] levelmap MATCH L{level_num} "
                            f"(conf={self._diff.confidence:.2f}) → using stored route"
                        )
                    else:
                        print(
                            f"[agent] levelmap MISMATCH L{level_num}: "
                            f"{self._diff.changed_fields} → adaptive strategy"
                        )
                # Update stored record in training on mismatch
                if self._mode == "training" and not self._diff.match and self._companion_path:
                    try:
                        block = snapshot_to_levelmap_block(snap)
                        update_levelmap_in_file(self._companion_path, block,
                                                self._game_id, level_num)
                        self._stored_snapshots[level_num] = snap
                        if self._verbose:
                            print(f"[agent] levelmap updated for L{level_num} (mismatch)")
                    except Exception as exc:
                        if self._verbose:
                            print(f"[agent] levelmap update failed: {exc}")
            except Exception as exc:
                if self._verbose:
                    print(f"[agent] diff_snapshots failed: {exc}")

        # Adaptive route: use per-game detector if available, else ls20 legacy
        detector = _get_detector(self._game_id) if _get_detector else None
        if detector is not None and level_num == 1:
            try:
                state = detector.detect_state(grid)
                adaptive = detector.compute_route(state)
                self._routes[level_num] = adaptive
                if self._verbose:
                    print(f"[agent] adaptive L{level_num} route: "
                          f"{adaptive} ({len(adaptive)} steps)")
            except Exception as exc:
                if self._verbose:
                    print(f"[agent] adaptive route failed: {exc}")
        elif self._game_prefix == "ls20" and level_num == 1:
            # Legacy fallback if games/ package not importable
            try:
                adaptive = compute_l1_route(grid)
                self._routes[1] = adaptive
                if self._verbose:
                    print(f"[agent] adaptive L1 route (legacy): "
                          f"{adaptive} ({len(adaptive)} steps)")
            except Exception as exc:
                if self._verbose:
                    print(f"[agent] adaptive route failed: {exc}")

    def on_level_complete(self, level_num: int, step_count: int) -> None:
        """Call when obs.levels_completed advances."""
        if self._mode == "training" and self._companion_path:
            # Write strategy block on L1 win (ls20 only)
            if (level_num == 1
                    and self._game_prefix == "ls20"
                    and self._current_snapshot is not None):
                try:
                    strategy = format_strategy_block(
                        "ls20", 1,
                        np.zeros((64, 64), dtype=np.int32),  # placeholder grid
                        self._routes.get(1, []),
                    )
                    update_strategy_in_file(self._companion_path, strategy)
                    if self._verbose:
                        print(f"[agent] strategy block written for L1")
                except Exception as exc:
                    if self._verbose:
                        print(f"[agent] strategy write failed: {exc}")

    def on_game_end(self, state: str, levels_completed: int, total_steps: int) -> None:
        """Call on 'win' or 'game_over'."""
        if self._verbose:
            print(
                f"[agent] game ended: {state} | "
                f"levels={levels_completed} | steps={total_steps}"
            )

    # ------------------------------------------------------------------
    # Action selection
    # ------------------------------------------------------------------

    def choose_action(
        self,
        obs,
        actions: list,
        step: int,
        level_step: int,
        prev_frames: Optional[list] = None,
        last_action_blocked: bool = False,
        last_action_idx: Optional[int] = None,
    ) -> int:
        """
        Return action index. Decision tree:

        1. If offline route available AND (match or no stored snapshot):
           → execute route[level_step - 1]
        2. If mode == 'batch':
           → random fallback
        3. If mode in ('training', 'competition'):
           → LOCUS (training) or systematic + random (competition)
        """
        n = max(len(actions), 1)
        route = self._routes.get(self._current_level)
        in_offline = (
            self._current_level <= self._offline_levels
            and obs is not None
            and obs.levels_completed < self._offline_levels
        )

        # Determine whether to use the stored route
        use_route = route is not None and (level_step - 1) < len(route)
        if use_route and self._diff is not None:
            use_route = self._diff.match  # mismatch → skip stored route

        if in_offline and use_route:
            action_idx = route[level_step - 1]
            if self._verbose:
                _names = ["UP", "DOWN", "LEFT", "RIGHT"]
                name = _names[action_idx] if action_idx < 4 else str(action_idx)
                print(f"[agent] step={step} L{self._current_level} "
                      f"route[{level_step-1}]={action_idx} ({name})")
            return action_idx % n

        # Fallback paths
        if self._mode == "batch":
            return self._rng.randrange(n)

        # Training: LOCUS decides
        if self._mode == "training":
            return self._locus_action(obs, actions, step, prev_frames or [],
                                      last_action_blocked, last_action_idx)

        # Competition: systematic sweep then random
        return self._systematic_or_random(n)

    # ------------------------------------------------------------------
    # Internal decision helpers
    # ------------------------------------------------------------------

    def _locus_action(
        self,
        obs,
        actions: list,
        step: int,
        prev_frames: list,
        last_action_blocked: bool,
        last_action_idx: Optional[int],
    ) -> int:
        """LOCUS decides the action. Returns action index."""
        if self._locus_fn is None or self._format_state_fn is None:
            return 0  # no LOCUS available — default

        if not self._locus_initialized:
            self._locus_fn("@LOCUS FOCUS lat-10lon10", "FOCUS game_state")
            self._locus_fn("@LOCUS STATUS", "STATUS")
            self._locus_initialized = True

        state_msg = self._format_state_fn(
            step, actions, obs, prev_frames,
            last_action_blocked=last_action_blocked,
            last_action_idx=last_action_idx,
        )
        reply = self._locus_fn(state_msg, f"ACTION step={step}")

        if self._parse_action_fn:
            action_idx = self._parse_action_fn(reply, len(actions))
            if action_idx is None:
                retry = self._locus_fn(
                    "@LOCUS please respond with only the action number (e.g. 0).",
                    f"ACTION RETRY step={step}",
                )
                action_idx = self._parse_action_fn(retry, len(actions))
            if action_idx is not None:
                return action_idx

        return 0  # fallback

    def _build_systematic(self, n: int) -> list:
        """Each action repeated 1..20 times — covers short repeat patterns."""
        seq = []
        for repeat in range(1, 21):
            for a in range(n):
                seq.extend([a] * repeat)
        return seq

    def _systematic_or_random(self, n: int) -> int:
        """Phase 2 (systematic) then Phase 3 (random)."""
        if not self._systematic_queue:
            self._systematic_queue = self._build_systematic(n)
        if self._systematic_step < len(self._systematic_queue):
            idx = self._systematic_queue[self._systematic_step] % n
            self._systematic_step += 1
            return idx
        return self._rng.randrange(n)

    # ------------------------------------------------------------------
    # LOCUS log accumulation (delegates to caller's closure)
    # ------------------------------------------------------------------

    def set_locus_fn(self, fn: Callable) -> None:
        """Set or replace the LOCUS query callable after construction."""
        self._locus_fn = fn
