"""
_test_pollution.py — the ADDITIVE-LAW guard for the dynamics layer (ARC-RFC-0001 §7).

The leaderboard failure this locks out: a dynamic fires on a game it should not, drives
a few off-policy moves, then aborts — and the explorer FLOOR, kept "warm" by committing
whatever action was executed, LEARNS those off-policy moves. After the abort it runs a
polluted transition model that underperforms clean v1. That is the only way the additive
stack can score BELOW its own floor, and the data fit it: every dynamics build sat under
plain v1 0.18 (@BELIEF:LAT92LON62).

The fix (core/solve_agent.py): while a solver drives, the explorer is FROZEN — no observe,
no commit — and on resume it marks a transition discontinuity. So the floor's model is
byte-identical to one that simply SKIPPED the off-policy frames: floor+dynamics >= floor by
construction, firing or not.

This test proves that invariant deterministically on a synthetic replay tape:
  A. solver-driven frames leave ZERO trace in the floor (not in visit, not as a trans
     origin, not as a trans successor),
  B. NO off-policy edge is learned,
  C. NO bogus cross-gap edge is learned on resume (the last pre-takeover action is not
     wired to the post-abort frame),
  D. non-firing is byte-identical to standalone v1 (the no-regression invariant), and
  E. the resumed floor (actions + model) equals a clean floor that ran the prefix, hit an
     episode boundary, and resumed on the resume frames — zero pollution, zero RNG drift.

Each assertion FAILS on the old "keep warm every step" code and PASSES on the fix, so this
is a real regression guard. Run: python _test_pollution.py
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np

from core.general_agent import GeneralAgent, board_signature
from core.dynamics.base import Dynamic, SolverStep
from core.solve_agent import SupervisedAgent

N_ACTIONS = 6
SEED = 7
TRIG = 9            # marker colour, placed in the dropped UI row (row 0)
A_SOLVER = 5        # the off-policy action the stub forces


def make_frame(core_id: int, trigger: bool = False) -> np.ndarray:
    """8×8 frame with a UNIQUE core (rows 1..-2, cols 0..-2 — what the floor signs) and
    an optional trigger marker in row 0, which board_signature DROPS (so the marker is
    invisible to the floor but visible to the dynamic)."""
    f = np.zeros((8, 8), dtype=np.int64)
    f[1, 1] = core_id          # distinct per frame -> distinct signature
    if trigger:
        f[0, 0] = TRIG
    return f


def _is_trigger(f) -> bool:
    return int(np.asarray(f)[0, 0]) == TRIG


class StubDynamic(Dynamic):
    """Fires on a trigger frame, then drives A_SOLVER every step while expecting the
    frame to STAY a trigger frame — so once the tape leaves the trigger window the
    expectation fails and the supervisor aborts back to the floor."""
    id = "stub"

    def recognize(self, frame):
        return 1.0 if _is_trigger(frame) else 0.0

    def next_action(self, frame, n_actions):
        return SolverStep(action=A_SOLVER, expect=_is_trigger)


# Replay tape: 2 floor-prefix frames, 1 trigger (fires) + 2 non-trigger (solver keeps
# driving until abort), then 2 resume frames. Distinct core ids => distinct signatures.
PREFIX  = [make_frame(11), make_frame(12)]
TRIGGER = [make_frame(13, trigger=True)]
WINDOW  = [make_frame(14), make_frame(15)]          # non-trigger; expect() fails here
RESUME  = [make_frame(16), make_frame(17), make_frame(18)]
TAPE = PREFIX + TRIGGER + WINDOW + RESUME           # 8 frames

# With _ABORT_K=3: F0(fire) F1(div1) F2(div2) drive off-policy; the 3rd failure latches
# the abort on the next frame, which the floor then drives. So:
SOLVER_FRAMES = TRIGGER + WINDOW                     # indices 2,3,4 — floor must NOT see these
FLOOR_FRAMES  = PREFIX + [TAPE[5], TAPE[6], TAPE[7]] # 0,1 then 5,6,7 (abort lands on idx 5)


def _sigset(frames):
    return {board_signature(f) for f in frames}


def _ok(cond, label, fails):
    print(f"    [{'PASS' if cond else 'FAIL'}] {label}")
    if not cond:
        fails.append(label)


def run() -> bool:
    fails = []
    print("additive-law / floor-pollution guard\n")

    # --- Drive the supervised agent over the tape, recording per-frame actions. -----
    sup = SupervisedAgent(N_ACTIONS, seed=SEED, floor="v1", dynamics=[StubDynamic()])
    sup.reset_level(1)
    actions = [sup.choose(f) for f in TAPE]
    floor = sup.explorer

    solver_sigs = _sigset(SOLVER_FRAMES)
    trans_origins = {k[0] for k in floor.trans}
    trans_succ = set(floor.trans.values())

    print("  the solver actually drove the off-policy window:")
    _ok(actions[2] == A_SOLVER and actions[3] == A_SOLVER and actions[4] == A_SOLVER,
        f"frames 2-4 executed A_SOLVER ({A_SOLVER})  got {actions[2:5]}", fails)

    print("\n  A. solver-driven frames left ZERO trace in the floor:")
    _ok(solver_sigs.isdisjoint(floor.visit), "no solver sig was visited", fails)
    _ok(solver_sigs.isdisjoint(trans_origins), "no trans edge ORIGINATES from a solver sig", fails)
    _ok(solver_sigs.isdisjoint(trans_succ), "no trans edge LANDS on a solver sig", fails)

    print("\n  B. no OFF-POLICY edge was learned:")
    offpolicy = [k for k in floor.trans if k[0] in solver_sigs]
    _ok(not offpolicy, f"no trans key keyed on a solver frame  ({len(offpolicy)} found)", fails)

    print("\n  C. no BOGUS cross-gap edge on resume:")
    gap_key = (board_signature(PREFIX[1]), actions[1])   # last pre-takeover (sig, action)
    _ok(gap_key not in floor.trans,
        "last pre-takeover action is NOT wired to the post-abort frame", fails)

    # --- D. non-firing == standalone v1 (the no-regression invariant). --------------
    print("\n  D. empty library is byte-identical to plain v1:")
    sup0 = SupervisedAgent(N_ACTIONS, seed=SEED, floor="v1", dynamics=[])
    sup0.reset_level(1)
    a_sup0 = [sup0.choose(f) for f in TAPE]
    g = GeneralAgent(N_ACTIONS, seed=SEED)
    a_g = [g.choose(f) for f in TAPE]
    _ok(a_sup0 == a_g, f"action sequence matches v1  ({a_sup0} vs {a_g})", fails)
    _ok(sup0.explorer.trans == g.trans and sup0.explorer.visit == g.visit
        and sup0.explorer.noop == g.noop, "floor model matches v1 exactly", fails)

    # --- E. resumed floor == a clean floor that skipped the window at an episode bound.
    print("\n  E. resumed floor == clean floor with an episode boundary at the gap:")
    oracle = GeneralAgent(N_ACTIONS, seed=SEED)
    oracle.choose(PREFIX[0]); oracle.choose(PREFIX[1])
    oracle.mark_discontinuity()
    ora_actions = [oracle.choose(TAPE[5]), oracle.choose(TAPE[6]), oracle.choose(TAPE[7])]
    _ok(actions[5:8] == ora_actions,
        f"resume actions match the clean floor  ({actions[5:8]} vs {ora_actions})", fails)
    _ok(floor.trans == oracle.trans and floor.visit == oracle.visit
        and floor.noop == oracle.noop, "resumed floor model == clean floor model", fails)

    ok = not fails
    print("\nverdict:", "CLEAN — the dynamics layer is additive by construction"
          if ok else f"POLLUTION — {len(fails)} invariant(s) broken: {fails}")
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
