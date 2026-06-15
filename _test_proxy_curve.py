"""Two-sided local proxy via coverage CURVES (dream @LAT34LON53).

The canonical proxy is one-sided (catches regressions, not gains) because FINAL
coverage SATURATES — every policy eventually covers the small reachable set, so
final-coverage A/Bs show v2 == v1 even when one explores better. Fix: measure
the coverage CURVE, not its endpoint. A faster explorer reaches states EARLIER,
so mean-coverage-over-the-episode (area under coverage(t), /T) separates policies
even when their final coverage is identical. This is saturation-independent and
gain-sensitive.

CREDIBILITY TEST: the proxy is only trustworthy if it reproduces the one ordering
we KNOW from the leaderboard — random (0.15) < general-v1 (0.18). If mean-coverage
ranks random < v1, the proxy detects a real, transfer-confirmed gain, and we can
use it to validate v2/dyn/ClickExplorer BEFORE spending a daily submission. If it
does not, the proxy is not valid and we learn that too.

Coverage yardstick: a measurement-only DynamicSignature (HUD-immune "real
states"), separate from each agent's internal logic, so all policies are scored
on the same ruler.

Usage: python _test_proxy_curve.py [--seeds N] [--budget N] [game ...]
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

from core.general_agent import GeneralAgent
from core.general_agent_v2 import GeneralAgentV2
from core.general_agent_dyn import GeneralAgentDyn
from core.click_agent import ClickExplorer
from core.dyn_signature import DynamicSignature

ROOT = Path(__file__).parent
ENV_DIR = ROOT / "environment_files"
ACTIONS = [GameAction.ACTION1, GameAction.ACTION2, GameAction.ACTION3,
           GameAction.ACTION4, GameAction.ACTION5, GameAction.ACTION6, GameAction.ACTION7]
_END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")

SEEDS = 6
BUDGET = 300
if "--seeds" in sys.argv:
    i = sys.argv.index("--seeds"); SEEDS = int(sys.argv[i + 1]); del sys.argv[i:i + 2]
if "--budget" in sys.argv:
    i = sys.argv.index("--budget"); BUDGET = int(sys.argv[i + 1]); del sys.argv[i:i + 2]
GAMES = sys.argv[1:] or ["ls20", "cd82", "sp80", "re86", "tu93", "wa30",
                         "ar25", "g50t", "sk48", "cn04", "ka59"]

_AGENTS = {"random": None, "v1": GeneralAgent, "v2": GeneralAgentV2,
           "dyn": GeneralAgentDyn, "click": "CLICK"}


def load(game):
    inst = next((ENV_DIR / game).iterdir())
    spec = importlib.util.spec_from_file_location("pc_" + game, inst / f"{game}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return next(v for v in vars(mod).values()
                if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)


def play(cls, policy, seed, budget):
    """Return (mean_coverage, final_coverage, won)."""
    g = cls()
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    raw_avail = list(getattr(g, "_available_actions", [1, 2, 3, 4, 5]))
    has_click = 6 in raw_avail
    avail = [a for a in raw_avail if a != 6]
    mo = [ACTIONS[a - 1] for a in avail]
    n = len(mo)
    rng = random.Random(seed)
    spec = _AGENTS[policy]
    is_click = spec == "CLICK"
    if is_click:
        agent = ClickExplorer(n, allow_click=has_click, seed=seed)
    else:
        agent = spec(n, seed=seed) if spec else None
    ruler = DynamicSignature()        # measurement-only, HUD-immune
    seen = set()
    auc = 0
    won = False
    steps = 0
    for _ in range(budget):
        if obs is None or str(obs.state) in _END or not obs.frame:
            break
        full = np.asarray(obs.frame[-1])
        seen.add(ruler.sig(full))     # common yardstick
        auc += len(seen)
        steps += 1
        if is_click:
            k = agent.choose(full)
            ai = (ActionInput(id=mo[k[1] % n]) if k[0] == "m"
                  else ActionInput(id=GameAction.ACTION6, data={"x": k[1], "y": k[2]}))
        else:
            a = rng.randrange(n) if agent is None else agent.choose(full) % n
            ai = ActionInput(id=mo[a])
        obs = g.perform_action(ai, raw=True)
        if obs is not None and obs.levels_completed > 0:
            won = True
            if agent is not None:
                agent.reset_level()
            ruler = DynamicSignature(); seen = set()  # fresh per level
    mean_cov = auc / steps if steps else 0.0
    return mean_cov, len(seen), won


def main():
    print(f"TWO-SIDED PROXY (coverage curves)  seeds={SEEDS} budget={BUDGET}\n")
    agg = {p: {"mc": [], "fc": [], "win": 0, "plays": 0} for p in _AGENTS}
    sp80 = {p: 0 for p in _AGENTS}
    for game in GAMES:
        try:
            cls = load(game)
        except Exception as e:
            print(f"{game} load-error {e}"); continue
        for p in _AGENTS:
            mcs, fcs, wins = [], [], 0
            for s in range(SEEDS):
                mc, fc, won = play(cls, p, s, BUDGET)
                mcs.append(mc); fcs.append(fc); wins += int(won)
            agg[p]["mc"].append(statistics.mean(mcs))
            agg[p]["fc"].append(statistics.mean(fcs))
            agg[p]["win"] += wins; agg[p]["plays"] += SEEDS
            if game == "sp80":
                sp80[p] = wins / SEEDS

    print(f"{'policy':8s} | {'mean-cov (AUC/T)':>16s} | {'final-cov':>10s} | {'sp80 win%':>9s}")
    print("-" * 54)
    order = sorted(_AGENTS, key=lambda p: -statistics.mean(agg[p]["mc"]))
    means = {}
    for p in _AGENTS:
        mc = statistics.mean(agg[p]["mc"]); fc = statistics.mean(agg[p]["fc"])
        means[p] = mc
        print(f"{p:8s} | {mc:16.1f} | {fc:10.1f} | {sp80[p]*100:8.0f}%")
    print("-" * 54)
    print(f"ranking by mean-cov: {' > '.join(order)}")

    # Credibility check against the known leaderboard ordering random < v1.
    print()
    if means["v1"] > means["random"]:
        gain = (means["v1"] - means["random"]) / means["random"] * 100
        print(f"PROXY VALID: mean-cov reproduces random < v1 (+{gain:.1f}%), "
              f"matching leaderboard 0.15 < 0.18.")
        print("-> mean-coverage is a gain-sensitive local proxy. deltas vs v1 below:")
        for p in ("v2", "dyn", "click"):
            d = (means[p] - means["v1"]) / means["v1"] * 100
            print(f"     {p:5s}: {d:+.1f}% vs v1")
        # final-coverage (the OLD one-sided metric) for contrast
        fr, fv = statistics.mean(agg['random']['fc']), statistics.mean(agg['v1']['fc'])
        print(f"   (contrast: FINAL-cov random={fr:.0f} v1={fv:.0f} -> "
              f"{'separates' if fv>fr*1.02 else 'SATURATED, cannot separate'})")
    else:
        print("PROXY INVALID: mean-cov does NOT reproduce random < v1. "
              "Coverage speed is not the transferring signal; need a different proxy.")


if __name__ == "__main__":
    main()
