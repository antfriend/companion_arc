"""
explore.py — agent-in-the-loop frame-exploration harness for ARC-AGI-3.

PURPOSE
  A reusable instrument for ME (the LLM agent) to READ game frames, PROCEED through
  games one action at a time, VERIFY known level strategies, DISCOVER new dynamics, and
  TEST candidate routes for winning the next level — the empirical front-end whose
  findings get written into games/<g>/companion.md and, once a dynamic is well
  understood + a route reliably wins, promoted into games/<g>/dynamic.py.

WHY REPLAY-FROM-RESET (the key design choice)
  My tool calls are stateless: a Python game object cannot persist between Bash
  invocations. So a session is just a JSON file holding (game, instance, seed, the
  ordered ACTION history, notes). Every command RESETs a fresh game (seeded for
  determinism) and re-applies the whole history, then acts. Consequences:
    * the action log IS the experiment — fully reproducible and inspectable;
    * I can branch and UNDO exploration freely (`back N`);
    * offline environment_files instances are fixed, so replay is deterministic
      (random + numpy seeded). If a game proves non-deterministic, note it and rely on
      the per-step transition reports rather than long replays.
  Games are short (≤600 steps, ~100ms/step), so full replay each call is cheap.

THE METHOD (the loop this tool serves) — see also the module-level METHOD docstring
  printed by `python explore.py method`:
    1 ORIENT     `new <game>`; read the legend (elements) vs the companion file.
    2 MODEL      probe single actions; `diff` to learn each action's effect (move
                 vectors, collisions, triggers). Confirm/refute the action model.
    3 VERIFY     replay the known route; confirm L1 still wins.
    4 ADVANCE    `goto --level N` (plays the registered solver) to reach the next level.
    5 PROBE      single-action experiments on the NEW mechanic; `watch <colors>` +
                 `diff` to map the new element/dynamic.
    6 TEST       form a candidate route; `step` it; binary-search failures with `back`.
    7 RECORD     `note` findings; then write them (confidence-tagged) into companion.md.
    8 PROMOTE    when a dynamic is understood and a route wins across instances/seeds,
                 implement in dynamic.py and pass _test_dynamics.py before staging.

USAGE
  python explore.py method                         # print the method + cheatsheet
  python explore.py games                           # list available games/instances
  python explore.py new <game> [--instance ID] [--seed N] [--session NAME]
  python explore.py show [--full] [--raw] [--legend-only]
  python explore.py step <tokens...>                # apply actions, render result+diff
  python explore.py diff                             # re-show last transition's diff
  python explore.py watch <colors>                  # track colors' bbox/centroid over history
  python explore.py back [N]                         # undo last N actions
  python explore.py goto --level N                   # fast-forward via registered solver
  python explore.py note <text...>                   # append a finding to the session log
  python explore.py status                           # session summary + action log

ACTION TOKENS
  1..7 or a1..a7  -> ACTION1..ACTION7 (canonical, game-agnostic).
  U D L R F       -> ACTION1 2 3 4 5  (NOMINAL directional aliases; the TRUE semantics
                     are game-specific and are exactly what step 2 discovers).
  6@x,y           -> ACTION6 click at frame (x=col, y=row).
  R*4             -> repeat token 4 times.   Tokens are space-separated.
"""
import argparse
import importlib.util
import io
import json
import random
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np
from arcengine import ARCBaseGame, ActionInput, GameAction

ROOT = Path(__file__).parent
ENV = ROOT / "environment_files"
SESS_DIR = ROOT / "_explore_sessions"
SESS_DIR.mkdir(exist_ok=True)

ACT = {1: GameAction.ACTION1, 2: GameAction.ACTION2, 3: GameAction.ACTION3,
       4: GameAction.ACTION4, 5: GameAction.ACTION5, 6: GameAction.ACTION6,
       7: GameAction.ACTION7}
ALIAS = {"U": 1, "D": 2, "L": 3, "R": 4, "F": 5,
         "UP": 1, "DOWN": 2, "LEFT": 3, "RIGHT": 4, "FIRE": 5, "ACT5": 5}
END = ("GameState.GAME_OVER", "game_over", "GameState.WIN", "win")
# Stable color -> single char, so the same colour reads identically across all frames
# and games. Background is rendered '.', transparent/void ' ', regardless of colour id.
HEX = "0123456789abcdef"


# --------------------------------------------------------------------------- load
def load_game(game, instance=None):
    gdir = ENV / game
    if not gdir.is_dir():
        raise SystemExit(f"no such game dir: {gdir}")
    inst = (gdir / instance) if instance else next(d for d in gdir.iterdir() if d.is_dir() and not d.name.startswith("__"))
    src = inst / f"{game}.py"
    spec = importlib.util.spec_from_file_location(f"ex_{game}", src)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    cls = next(v for v in vars(mod).values()
               if isinstance(v, type) and issubclass(v, ARCBaseGame) and v is not ARCBaseGame)
    return cls, inst.name


def parse_tokens(tokens):
    """Expand action tokens into a flat list of {'id':int,'data':?} dicts."""
    out = []
    for tok in tokens:
        t = tok.strip()
        if not t:
            continue
        rep = 1
        if "*" in t:
            t, r = t.split("*", 1); rep = int(r)
        data = None
        if "@" in t:                                   # click: 6@x,y
            t, xy = t.split("@", 1)
            x, y = xy.split(","); data = {"x": int(x), "y": int(y)}
        t = t.upper().lstrip("A")
        if t in ALIAS:
            aid = ALIAS[t]
        else:
            aid = int(t)
        out.extend([{"id": aid, "data": data} for _ in range(rep)])
    return out


# --------------------------------------------------------------------------- replay
def replay(game, instance, seed, actions):
    """RESET a fresh game (seeded) and apply `actions`; return list of obs frames +
    per-step meta. Frames are np.int arrays (the last sub-frame of each observation)."""
    random.seed(seed); np.random.seed(seed)
    cls, _ = load_game(game, instance)
    g = cls()
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    raw_av = list(getattr(g, "_available_actions", [1, 2, 3, 4, 5]))
    frames = [_frame(obs)]
    meta = [{"act": "RESET", "state": _state(obs), "level": _level(obs), "changed": True}]
    for a in actions:
        prev = frames[-1]
        ai = ActionInput(id=ACT[a["id"]], data=a["data"]) if a["data"] else ActionInput(id=ACT[a["id"]])
        obs = g.perform_action(ai, raw=True)
        f = _frame(obs)
        changed = not (f is not None and prev is not None and f.shape == prev.shape and np.array_equal(f, prev))
        meta.append({"act": _tok(a), "state": _state(obs), "level": _level(obs), "changed": changed})
        frames.append(f)
    return frames, meta, raw_av


def _frame(obs):
    if obs is None or not getattr(obs, "frame", None):
        return None
    return np.asarray(obs.frame[-1])

def _state(obs):
    return str(obs.state) if obs is not None else "None"

def _level(obs):
    return (obs.levels_completed or 0) if obs is not None else 0

def _tok(a):
    s = f"a{a['id']}"
    if a["data"]:
        s += f"@{a['data']['x']},{a['data']['y']}"
    return s


# --------------------------------------------------------------------------- render
def components(frame, bg):
    """Per non-background colour: count, bbox (r0,r1,c0,c1), centroid. Detector-style."""
    info = {}
    for v in np.unique(frame):
        v = int(v)
        if v == bg:
            continue
        pos = np.argwhere(frame == v)
        info[v] = {
            "count": len(pos),
            "bbox": (int(pos[:, 0].min()), int(pos[:, 0].max()),
                     int(pos[:, 1].min()), int(pos[:, 1].max())),
            "centroid": (round(float(pos[:, 0].mean()), 1), round(float(pos[:, 1].mean()), 1)),
        }
    return info


def render(frame, full=False, prev=None, title=""):
    if frame is None:
        return f"{title}\n  <no frame>"
    bg = int(np.bincount(frame.reshape(-1) - frame.min()).argmax() + frame.min())
    info = components(frame, bg)
    # crop to active region (+1 margin) unless --full
    if full or not info:
        r0, r1, c0, c1 = 0, frame.shape[0] - 1, 0, frame.shape[1] - 1
    else:
        rs = [i["bbox"][0] for i in info.values()] + [i["bbox"][1] for i in info.values()]
        cs = [i["bbox"][2] for i in info.values()] + [i["bbox"][3] for i in info.values()]
        r0, r1 = max(0, min(rs) - 1), min(frame.shape[0] - 1, max(rs) + 1)
        c0, c1 = max(0, min(cs) - 1), min(frame.shape[1] - 1, max(cs) + 1)

    def cell(v):
        if v < 0:
            return " "          # transparent / void
        if v == bg:
            return "·"     # background ·
        return HEX[v] if 0 <= v < 16 else "?"

    lines = [title, f"  (background colour={bg} shown '·'; crop rows {r0}-{r1} cols {c0}-{c1}"
                    f"{' [FULL]' if full else ''})"]
    # column ruler (tens then units)
    tens = "    " + "".join(str((c // 10) % 10) if c % 5 == 0 else " " for c in range(c0, c1 + 1))
    units = "    " + "".join(str(c % 10) for c in range(c0, c1 + 1))
    lines += [tens, units]
    for r in range(r0, r1 + 1):
        row = "".join(cell(int(frame[r, c])) for c in range(c0, c1 + 1))
        lines.append(f"{r:3d} {row}")
    # legend: char = colour, with count / bbox / centroid
    lines.append("  legend (char colour count bbox=r0-r1,c0-c1 centroid):")
    for v in sorted(info):
        i = info[v]
        b = i["bbox"]
        lines.append(f"    {HEX[v] if 0<=v<16 else '?'} = c{v:<2} n={i['count']:<5} "
                     f"bbox={b[0]}-{b[1]},{b[2]}-{b[3]} ctr={i['centroid']}")
    # diff summary vs prev
    if prev is not None and prev.shape == frame.shape:
        dmask = prev != frame
        nd = int(dmask.sum())
        if nd:
            dp = np.argwhere(dmask)
            lines.append(f"  DELTA vs prev: {nd} cells changed, "
                         f"rows {dp[:,0].min()}-{dp[:,0].max()} cols {dp[:,1].min()}-{dp[:,1].max()}")
            # which colours' centroids moved
            pinfo = components(prev, bg)
            moved = []
            for v in sorted(set(info) | set(pinfo)):
                pc = pinfo.get(v, {}).get("centroid")
                cc = info.get(v, {}).get("centroid")
                if pc != cc:
                    moved.append(f"c{v}:{pc}->{cc}")
            if moved:
                lines.append("  moved: " + "  ".join(moved))
        else:
            lines.append("  DELTA vs prev: NO CHANGE (no-op)")
    return "\n".join(lines)


# --------------------------------------------------------------------------- session
def spath(name):
    return SESS_DIR / f"{name}.json"

def load_sess(name):
    p = spath(name)
    if not p.exists():
        raise SystemExit(f"no session '{name}'. Run: python explore.py new <game> --session {name}")
    return json.loads(p.read_text())

def save_sess(s):
    spath(s["session"]).write_text(json.dumps(s, indent=2))

def active_name(arg):
    if arg:
        return arg
    p = SESS_DIR / "_active"
    return p.read_text().strip() if p.exists() else "default"

def set_active(name):
    (SESS_DIR / "_active").write_text(name)


# --------------------------------------------------------------------------- commands
def cmd_new(a):
    cls, inst = load_game(a.game, a.instance)
    s = {"session": a.session, "game": a.game, "instance": inst, "seed": a.seed,
         "actions": [], "notes": []}
    save_sess(s); set_active(a.session)
    frames, meta, av = replay(a.game, inst, a.seed, [])
    print(f"[new] session='{a.session}' game={a.game} instance={inst} seed={a.seed}")
    print(f"  available actions (ids): {[x for x in av]}  (ACTIONn). is_simple movement = the non-6 ids.")
    print(render(frames[-1], full=a.full, title="FRAME 0 (RESET):"))
    print("\nNext: read the legend vs games/%s/companion.md, then `step <action>` and watch the DELTA." % a.game)


def cmd_show(a):
    s = load_sess(active_name(a.session))
    acts = parse_tokens([x for x in _flatten(s["actions"])]) if s["actions"] else []
    frames, meta, av = replay(s["game"], s["instance"], s["seed"], s["actions"])
    if a.legend_only:
        f = frames[-1]; bg = int(np.bincount(f.reshape(-1)-f.min()).argmax()+f.min())
        for v, i in sorted(components(f, bg).items()):
            print(f"  c{v:<2} n={i['count']:<5} bbox={i['bbox']} ctr={i['centroid']}")
        return
    prev = frames[-2] if len(frames) > 1 else None
    print(render(frames[-1], full=a.full, prev=prev,
                 title=f"FRAME after {len(s['actions'])} actions "
                       f"(level={meta[-1]['level']} state={meta[-1]['state']}):"))
    if a.raw:
        print("RAW (cropped numeric):")
        _print_raw(frames[-1])


def cmd_step(a):
    s = load_sess(active_name(a.session))
    new = parse_tokens(a.tokens)
    if not new:
        raise SystemExit("no actions parsed")
    s["actions"].extend(new)
    frames, meta, av = replay(s["game"], s["instance"], s["seed"], s["actions"])
    save_sess(s)
    # report each new step's transition, then render the final frame + diff
    base = len(frames) - 1 - len(new)
    print(f"[step] +{len(new)} action(s) (total {len(s['actions'])}):")
    for k in range(len(new)):
        m = meta[base + 1 + k]
        flag = "chg " if m["changed"] else "NOOP"
        lvlup = "  *** LEVEL UP ***" if meta[base+1+k]["level"] > meta[base+k]["level"] else ""
        end = "  <<< END" if m["state"] in END else ""
        print(f"  {base+1+k:3d} {m['act']:>10s} {flag} level={m['level']} {m['state']}{lvlup}{end}")
    prev = frames[-2] if len(frames) > 1 else None
    print(render(frames[-1], full=a.full, prev=prev,
                 title=f"RESULT FRAME (level={meta[-1]['level']} state={meta[-1]['state']}):"))


def cmd_diff(a):
    s = load_sess(active_name(a.session))
    if len(s["actions"]) < 1:
        raise SystemExit("no transition yet")
    frames, meta, av = replay(s["game"], s["instance"], s["seed"], s["actions"])
    print(render(frames[-1], full=a.full, prev=frames[-2] if len(frames) > 1 else None,
                 title=f"DIFF of last action {meta[-1]['act']}:"))


def cmd_watch(a):
    s = load_sess(active_name(a.session))
    cols = [int(c) for c in a.colors.replace(",", " ").split()]
    frames, meta, av = replay(s["game"], s["instance"], s["seed"], s["actions"])
    print(f"[watch] colours {cols} across {len(frames)} frames (idx act | per-colour count@centroid):")
    for idx, (f, m) in enumerate(zip(frames, meta)):
        parts = []
        for c in cols:
            pos = np.argwhere(f == c) if f is not None else []
            if len(pos):
                parts.append(f"c{c}:n{len(pos)}@({round(pos[:,0].mean(),1)},{round(pos[:,1].mean(),1)})")
            else:
                parts.append(f"c{c}:-")
        chg = "" if m["changed"] else " (noop)"
        print(f"  {idx:3d} {m['act']:>10s} L{m['level']} | " + "  ".join(parts) + chg)


def cmd_back(a):
    s = load_sess(active_name(a.session))
    n = a.n
    if n > len(s["actions"]):
        n = len(s["actions"])
    s["actions"] = s["actions"][:len(s["actions"]) - n]
    save_sess(s)
    frames, meta, av = replay(s["game"], s["instance"], s["seed"], s["actions"])
    print(f"[back] removed {n}; {len(s['actions'])} actions remain.")
    print(render(frames[-1], full=a.full, prev=frames[-2] if len(frames) > 1 else None,
                 title=f"FRAME after back (level={meta[-1]['level']} state={meta[-1]['state']}):"))


def cmd_goto(a):
    """Fast-forward to a target level by playing the registered solver library, recording
    the actions it takes so the level can then be probed manually."""
    s = load_sess(active_name(a.session))
    from core.solve_agent import SupervisedAgent
    from core.dynamics import library  # noqa: F401 — registers dynamics
    random.seed(s["seed"]); np.random.seed(s["seed"])
    cls, _ = load_game(s["game"], s["instance"])
    g = cls()
    obs = g.perform_action(ActionInput(id=GameAction.RESET), raw=True)
    av = [x for x in list(getattr(g, "_available_actions", [1, 2, 3, 4, 5])) if x != 6]
    n = len(av)
    agent = SupervisedAgent(n, seed=s["seed"])
    recorded, prev_lvl = [], 0
    for _ in range(a.budget):
        if obs is None or str(obs.state) in END or not obs.frame:
            break
        a_idx = agent.choose(np.asarray(obs.frame[-1])) % n
        aid = av[a_idx]
        recorded.append({"id": aid, "data": None})
        obs = g.perform_action(ActionInput(id=ACT[aid]), raw=True)
        lvl = _level(obs)
        if lvl > prev_lvl:
            prev_lvl = lvl
            # `--level N` means PARK on level N (= N-1 levels completed), i.e. stop the
            # instant we land on it, BEFORE the (possibly level-blind) solver dies there,
            # leaving the session positioned at the new level for manual probing.
            if lvl >= a.level - 1:
                break
            agent.reset_level()
    s["actions"] = recorded
    save_sess(s)
    frames, meta, _ = replay(s["game"], s["instance"], s["seed"], s["actions"])
    print(f"[goto] solver played {len(recorded)} actions; reached level {prev_lvl} "
          f"(target {a.level}); state={meta[-1]['state']}")
    print(render(frames[-1], full=a.full, prev=frames[-2] if len(frames) > 1 else None,
                 title=f"FRAME at level {meta[-1]['level']}:"))


def cmd_note(a):
    s = load_sess(active_name(a.session))
    note = " ".join(a.text)
    s["notes"].append({"after_actions": len(s["actions"]), "note": note})
    save_sess(s)
    print(f"[note] recorded (after {len(s['actions'])} actions): {note}")


def cmd_status(a):
    s = load_sess(active_name(a.session))
    frames, meta, av = replay(s["game"], s["instance"], s["seed"], s["actions"])
    print(f"session='{s['session']}' game={s['game']} instance={s['instance']} seed={s['seed']}")
    print(f"actions ({len(s['actions'])}): " + " ".join(_tok(x) for x in s["actions"]) or "(none)")
    print(f"current: level={meta[-1]['level']} state={meta[-1]['state']}")
    if s["notes"]:
        print("notes:")
        for nrec in s["notes"]:
            print(f"  @{nrec['after_actions']}: {nrec['note']}")


def cmd_games(a):
    for gdir in sorted(p for p in ENV.iterdir() if p.is_dir()):
        insts = [d.name for d in gdir.iterdir() if d.is_dir() and not d.name.startswith("__")]
        print(f"  {gdir.name:8s} instances: {insts}")


def cmd_method(a):
    print(__doc__)


def _flatten(actions):
    return [_tok(x) for x in actions]

def _print_raw(frame):
    bg = int(np.bincount(frame.reshape(-1)-frame.min()).argmax()+frame.min())
    info = components(frame, bg)
    if not info:
        return
    rs = [i["bbox"][0] for i in info.values()] + [i["bbox"][1] for i in info.values()]
    cs = [i["bbox"][2] for i in info.values()] + [i["bbox"][3] for i in info.values()]
    r0, r1, c0, c1 = min(rs), max(rs), min(cs), max(cs)
    for r in range(r0, r1 + 1):
        print(f"{r:3d} " + " ".join(f"{int(frame[r,c]):2d}" for c in range(c0, c1 + 1)))


# --------------------------------------------------------------------------- cli
def main():
    p = argparse.ArgumentParser(description="agent frame-exploration harness")
    p.add_argument("--session", help="session name (default: last active)")
    p.add_argument("--full", action="store_true", help="render full 64x64 (no crop)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("new"); sp.add_argument("game"); sp.add_argument("--instance")
    sp.add_argument("--seed", type=int, default=0); sp.add_argument("--session", default="default")
    sp.add_argument("--full", action="store_true"); sp.set_defaults(func=cmd_new)

    sp = sub.add_parser("show"); sp.add_argument("--raw", action="store_true")
    sp.add_argument("--legend-only", action="store_true"); sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("step"); sp.add_argument("tokens", nargs="+"); sp.set_defaults(func=cmd_step)
    sp = sub.add_parser("diff"); sp.set_defaults(func=cmd_diff)
    sp = sub.add_parser("watch"); sp.add_argument("colors"); sp.set_defaults(func=cmd_watch)
    sp = sub.add_parser("back"); sp.add_argument("n", type=int, nargs="?", default=1); sp.set_defaults(func=cmd_back)
    sp = sub.add_parser("goto"); sp.add_argument("--level", type=int, required=True)
    sp.add_argument("--budget", type=int, default=600); sp.set_defaults(func=cmd_goto)
    sp = sub.add_parser("note"); sp.add_argument("text", nargs="+"); sp.set_defaults(func=cmd_note)
    sp = sub.add_parser("status"); sp.set_defaults(func=cmd_status)
    sp = sub.add_parser("games"); sp.set_defaults(func=cmd_games)
    sp = sub.add_parser("method"); sp.set_defaults(func=cmd_method)

    a = p.parse_args()
    # let subparser --full/--session override top-level
    a.func(a)


if __name__ == "__main__":
    main()
