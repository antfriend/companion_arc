"""A/B/C: random vs GeneralAgent(v1) vs GeneralAgentV2, head-to-head.

Local canonical instances are NOT the scored hidden set, so absolute numbers
don't predict the leaderboard. But the RELATIVE comparison is a property of the
agent logic that should transfer. We care most about COMPLETIONS (the hidden set
rewards finished levels), so this harness reports — beyond coverage/noop — the
two metrics that actually matter:

  win-rate            fraction of seeds that completed >=1 level
  steps-to-first-win  mean steps to the first completion (lower = more efficient)

Regression guard: v2 must not score worse than random on any game (coverage and
win-rate). Any regression is flagged with '!'.

Usage: python _test_agent_ab2.py [--seeds N] [--budget N] [game ...]
"""
import importlib.util
import io
import random
import statistics
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path

import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction

from core.general_agent import GeneralAgent, board_signature
from core.general_agent_v2 import GeneralAgentV2

ROOT = Path(__file__).parent
ENV_DIR = ROOT / "environment_files"
ACTIONS = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3,
           GameAction.ACTION4, GameAction.ACTION5, GameAction.ACTION6, GameAction.ACTION7]
_END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")

SEEDS = 8
BUDGET = 600
if "--seeds" in sys.argv:
    i = sys.argv.index("--seeds"); SEEDS = int(sys.argv[i + 1]); del sys.argv[i:i + 2]
if "--budget" in sys.argv:
    i = sys.argv.index("--budget"); BUDGET = int(sys.argv[i + 1]); del sys.argv[i:i + 2]
GAMES = sys.argv[1:] or ["ls20", "cd82", "sp80", "re86", "tu93", "wa30",
                         "ar25", "g50t", "sk48", "cn04", "ka59"]

_AGENTS = {"random": None, "v1": GeneralAgent, "v2": GeneralAgentV2}


def load(game):
    inst = next((ENV_DIR / game).iterdir())
    spec = importlib.util.spec_from_file_location("ab_" + game, inst / f"{game}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values()
                if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def play(cls, policy, seed, budget):
    """Return (levels, coverage, noop_frac, steps_to_first_win or None)."""
    g = cls()
    rng = random.Random(seed)
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    avail = [a for a in list(getattr(g, "_available_actions", [1, 2, 3, 4, 5])) if a != 6]
    act_objs = [ACTIONS[a - 1] for a in avail]
    n = len(act_objs)
    agent = _AGENTS[policy](n, seed=seed) if _AGENTS[policy] else None
    levels = 0
    seen = set()
    noops = steps = 0
    first_win = None
    prev_sig = None
    for _ in range(budget):
        if obs is None or str(obs.state) in _END or not obs.frame:
            break
        frame = np.asarray(obs.frame[-1])
        sig = board_signature(frame)
        seen.add(sig)
        if prev_sig is not None and sig == prev_sig:
            noops += 1
        prev_sig = sig
        a = rng.randrange(n) if agent is None else agent.choose(frame) % n
        obs = g.perform_action(ActionInput(id=act_objs[a]), raw=True)
        steps += 1
        if obs is not None and obs.levels_completed > levels:
            levels = obs.levels_completed
            if first_win is None:
                first_win = steps
            seen.clear(); prev_sig = None
            if agent is not None:
                agent.reset_level()
    return levels, len(seen), (noops / steps if steps else 0.0), first_win


def summarize(cls, policy):
    lv, cov, noop, fw, wins = [], [], [], [], 0
    for s in range(SEEDS):
        L, C, N, F = play(cls, policy, s, BUDGET)
        lv.append(L); cov.append(C); noop.append(N)
        if F is not None:
            fw.append(F); wins += 1
    return {
        "lvl": statistics.mean(lv),
        "lvl_sd": statistics.pstdev(lv),
        "cov": statistics.mean(cov),
        "noop": statistics.mean(noop),
        "winrate": wins / SEEDS,
        "fw": statistics.mean(fw) if fw else None,
    }


def main():
    print(f"A/B/C  random vs v1 vs v2   seeds={SEEDS} budget={BUDGET}\n")
    hdr = f"{'game':6s} | {'win% r/v1/v2':>16s} | {'cov r/v1/v2':>20s} | {'first-win r/v1/v2':>20s}"
    print(hdr); print("-" * len(hdr))
    agg = {p: {"cov": 0.0, "win": 0.0} for p in _AGENTS}
    regress = []
    for game in GAMES:
        try:
            cls = load(game)
        except Exception as e:
            print(f"{game:6s} load-error {e}"); continue
        r = {p: summarize(cls, p) for p in _AGENTS}
        for p in _AGENTS:
            agg[p]["cov"] += r[p]["cov"]; agg[p]["win"] += r[p]["winrate"]
        # regression: v2 worse than random on coverage or win-rate
        flag = ""
        if r["v2"]["cov"] < r["random"]["cov"] * 0.98 or r["v2"]["winrate"] < r["random"]["winrate"]:
            flag = " !"; regress.append(game)
        fw = lambda d: f"{d['fw']:.0f}" if d["fw"] is not None else "-"
        print(f"{game:6s} | "
              f"{r['random']['winrate']*100:4.0f}/{r['v1']['winrate']*100:4.0f}/{r['v2']['winrate']*100:<4.0f} | "
              f"{r['random']['cov']:5.0f}/{r['v1']['cov']:5.0f}/{r['v2']['cov']:<5.0f} | "
              f"{fw(r['random']):>5s}/{fw(r['v1']):>5s}/{fw(r['v2']):<5s}{flag}")
    G = len(GAMES)
    print("-" * len(hdr))
    print(f"{'TOTAL':6s} | "
          f"{agg['random']['win']/G*100:4.0f}/{agg['v1']['win']/G*100:4.0f}/{agg['v2']['win']/G*100:<4.0f} | "
          f"{agg['random']['cov']:5.0f}/{agg['v1']['cov']:5.0f}/{agg['v2']['cov']:<5.0f} |")
    print(f"\ncoverage gain v2/random = {agg['v2']['cov']/max(1,agg['random']['cov']):.2f}x"
          f"   v2/v1 = {agg['v2']['cov']/max(1,agg['v1']['cov']):.2f}x")
    print(f"win-rate  total  random={agg['random']['win']/G*100:.0f}%  "
          f"v1={agg['v1']['win']/G*100:.0f}%  v2={agg['v2']['win']/G*100:.0f}%")
    if regress:
        print(f"\n*** REGRESSION: v2 < random on {regress} — do NOT ship v2 ***")
    else:
        print("\nNo regressions: v2 >= random on coverage and win-rate for every game.")


if __name__ == "__main__":
    main()
