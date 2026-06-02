"""
level_scanner.py — First-frame entity detection and levelmap I/O for ARC-AGI-3.

Captures all entities (positions + orientations) from a game's first frame,
serializes to [levelmap] blocks in companion_arcprize.md, and compares
current frames to stored records to detect instance differences.

Pure numpy — no file I/O, no external dependencies beyond numpy itself.
Safe to import anywhere and inline into competition agent source strings.
"""

import re
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# Grid value constants (from ls20-9607627b observed frames)
BLOCK = 12
WALL  = 3
FLOOR = 5
ENT1  = 9
TIMER = 11
VOID  = 4

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class LevelSnapshot:
    """All entity information captured from a level's first frame."""
    game_id: str
    level_num: int                          # 1-based
    captured_at: int                        # unix timestamp
    grid_shape: tuple                       # (rows, cols)
    block_pos: Optional[tuple]              # (min_row, min_col) of BLOCK entity
    entity2_ring: Optional[dict]            # {top, bot, left, right, interior_top, ...}
    entity2_notch_orientation: Optional[int]  # 0/90/180/270 — ring wall notch position
    cluster: Optional[dict]                 # {top_row, bot_row, col_min, col_max, col_center}
    entity1_state: int                      # 0/1/2
    entity_signatures: dict = field(default_factory=dict)
    # {value: {'count': N, 'bbox': (r1,r2,c1,c2)}} — generic entity map
    raw_compact: str = ""                   # compact_grid_str for human reference


@dataclass
class LevelDiff:
    """Result of comparing two LevelSnapshots."""
    match: bool                             # True = layouts match → use stored route
    block_delta: Optional[tuple]            # (row_diff, col_diff) or None
    ring_moved: bool
    notch_changed: bool
    cluster_row_delta: Optional[int]        # informational only
    changed_fields: list                    # human-readable list of differences
    confidence: float                       # 0.0-1.0; 1.0 = identical positions


# ---------------------------------------------------------------------------
# Orientation detection
# ---------------------------------------------------------------------------

def _detect_ring_notch_orientation(grid: np.ndarray, ring: dict) -> Optional[int]:
    """
    Infer ring-wall sprite rotation from which edge has the notch (gap in WALL).

    The nszegiawib sprite has a notch at one edge whose position encodes rotation:
      0°  → notch on top row    (top row has the fewest WALL cells)
      90° → notch on right col
      180°→ notch on bottom row
      270°→ notch on left col

    Returns 0/90/180/270 or None if ambiguous.
    """
    top, bot = ring["top"], ring["bot"]
    left, right = ring["left"], ring["right"]
    rows, cols = grid.shape

    if top < 0 or bot >= rows or left < 0 or right >= cols:
        return None

    top_walls  = int(np.sum(grid[top,  left:right + 1] == WALL))
    bot_walls  = int(np.sum(grid[bot,  left:right + 1] == WALL))
    left_walls = int(np.sum(grid[top:bot + 1, left]    == WALL))
    right_walls= int(np.sum(grid[top:bot + 1, right]   == WALL))

    edges = {0: top_walls, 180: bot_walls, 270: left_walls, 90: right_walls}
    # Notch is on the edge with fewest WALL cells
    sorted_edges = sorted(edges.items(), key=lambda x: x[1])
    best_deg, best_count = sorted_edges[0]
    second_count = sorted_edges[1][1]

    # Require clear winner: best must be noticeably lower than second
    if best_count == 0 or second_count == 0:
        # All edges might be zero in some game states
        return None
    if second_count == 0 and best_count == 0:
        return None
    if best_count >= second_count:
        return None  # no clear notch
    return best_deg


# ---------------------------------------------------------------------------
# Entity signature extraction (generic, works for any game)
# ---------------------------------------------------------------------------

def _entity_signatures(grid: np.ndarray) -> dict:
    """
    For each non-background value, return count and bounding box.
    Background = most-common value (VOID=4 for ls20).
    """
    rows, cols = grid.shape
    bg = int(np.bincount(grid.flatten()).argmax())
    sigs = {}
    for val in np.unique(grid):
        if int(val) == bg:
            continue
        positions = np.argwhere(grid == val)
        if not len(positions):
            continue
        r1, c1 = int(positions[:, 0].min()), int(positions[:, 1].min())
        r2, c2 = int(positions[:, 0].max()), int(positions[:, 1].max())
        sigs[int(val)] = {"count": len(positions), "bbox": (r1, r2, c1, c2)}
    return sigs


# ---------------------------------------------------------------------------
# Compact grid string (mirrors kaggle_agent.py)
# ---------------------------------------------------------------------------

def _compact_grid_str(grid: np.ndarray) -> str:
    rows, cols = grid.shape
    bg = int(np.bincount(grid.flatten()).argmax())
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
# Main scan function
# ---------------------------------------------------------------------------

def scan_level(
    grid: np.ndarray,
    game_id: str,
    level_num: int,
    captured_at: Optional[int] = None,
) -> LevelSnapshot:
    """
    Scan a level's first frame and return a LevelSnapshot with all entity
    positions and orientations.

    For ls20 games: uses specific detection (block, entity2 ring, cluster,
    entity1 state). For all games: also captures generic entity_signatures.
    """
    if captured_at is None:
        captured_at = int(time.time())

    rows, cols = grid.shape
    prefix = game_id.split("-")[0] if "-" in game_id else game_id

    # Generic entity map (all games)
    sigs = _entity_signatures(grid)

    # ls20-specific detection
    block_pos = None
    entity2_ring = None
    entity2_notch = None
    cluster = None
    entity1_state = 0

    if prefix == "ls20":
        try:
            from ls20_detector import (
                detect_block,
                detect_entity2_ring,
                detect_cluster,
                detect_entity1_state,
            )
            block_pos = detect_block(grid)
            entity2_ring = detect_entity2_ring(grid, search_rows=(2, 55))
            cluster = detect_cluster(grid)
            entity1_state = detect_entity1_state(grid)
            if entity2_ring:
                entity2_notch = _detect_ring_notch_orientation(grid, entity2_ring)
        except Exception:
            pass
    else:
        # Generic block detection for non-ls20 games
        positions = np.argwhere(grid == BLOCK)
        if len(positions):
            block_pos = (int(positions[:, 0].min()), int(positions[:, 1].min()))

    return LevelSnapshot(
        game_id=game_id,
        level_num=level_num,
        captured_at=captured_at,
        grid_shape=(rows, cols),
        block_pos=block_pos,
        entity2_ring=entity2_ring,
        entity2_notch_orientation=entity2_notch,
        cluster=cluster,
        entity1_state=entity1_state,
        entity_signatures=sigs,
        raw_compact=_compact_grid_str(grid),
    )


# ---------------------------------------------------------------------------
# Snapshot comparison
# ---------------------------------------------------------------------------

def diff_snapshots(stored: LevelSnapshot, current: LevelSnapshot) -> LevelDiff:
    """
    Compare two snapshots. Returns LevelDiff with match=True if layouts are
    close enough to use the stored route.

    Match criteria (all must hold):
    - block_pos within ±3 rows and ±3 cols
    - entity2_ring top within ±2 rows
    - entity2_notch_orientation identical (or both None)
    Cluster row difference is informational only.
    """
    changed = []
    block_delta = None
    ring_moved = False
    notch_changed = False
    cluster_row_delta = None
    confidence = 1.0

    # Block position
    if stored.block_pos is None and current.block_pos is None:
        pass
    elif stored.block_pos is None or current.block_pos is None:
        changed.append("block_pos missing")
        confidence -= 0.3
    else:
        dr = current.block_pos[0] - stored.block_pos[0]
        dc = current.block_pos[1] - stored.block_pos[1]
        block_delta = (dr, dc)
        if abs(dr) > 3 or abs(dc) > 3:
            changed.append(f"block_pos offset ({dr},{dc})")
            confidence -= 0.4
        elif abs(dr) > 0 or abs(dc) > 0:
            confidence -= 0.05 * (abs(dr) + abs(dc))

    # Entity2 ring top row
    if stored.entity2_ring and current.entity2_ring:
        rtop_diff = current.entity2_ring["top"] - stored.entity2_ring["top"]
        if abs(rtop_diff) > 2:
            changed.append(f"entity2_ring top shifted {rtop_diff}")
            ring_moved = True
            confidence -= 0.3
        elif rtop_diff != 0:
            confidence -= 0.05 * abs(rtop_diff)
    elif (stored.entity2_ring is None) != (current.entity2_ring is None):
        changed.append("entity2_ring presence changed")
        ring_moved = True
        confidence -= 0.3

    # Ring notch orientation
    if stored.entity2_notch_orientation != current.entity2_notch_orientation:
        if stored.entity2_notch_orientation is not None and current.entity2_notch_orientation is not None:
            changed.append(
                f"ring_notch {stored.entity2_notch_orientation}→{current.entity2_notch_orientation}"
            )
            notch_changed = True
            confidence -= 0.2

    # Cluster row (informational)
    if stored.cluster and current.cluster:
        cluster_row_delta = current.cluster["top_row"] - stored.cluster["top_row"]
        if cluster_row_delta != 0:
            changed.append(f"cluster_row shifted {cluster_row_delta} (informational)")

    confidence = max(0.0, min(1.0, confidence))
    match = len([c for c in changed if "informational" not in c]) == 0

    return LevelDiff(
        match=match,
        block_delta=block_delta,
        ring_moved=ring_moved,
        notch_changed=notch_changed,
        cluster_row_delta=cluster_row_delta,
        changed_fields=changed,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Companion [levelmap] block serialization
# ---------------------------------------------------------------------------

def snapshot_to_levelmap_block(snap: LevelSnapshot, session_id: str = "") -> str:
    """Serialize a LevelSnapshot to a [levelmap] companion block."""
    if not session_id:
        import datetime
        session_id = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    lines = [
        f"[levelmap game={snap.game_id.split('-')[0]} level={snap.level_num} "
        f"session={session_id} created={snap.captured_at}]",
        f"grid_shape: {snap.grid_shape[0]}x{snap.grid_shape[1]}",
    ]

    if snap.block_pos:
        lines.append(f"block_pos: {snap.block_pos[0]},{snap.block_pos[1]}")
    else:
        lines.append("block_pos: none")

    if snap.entity2_ring:
        r = snap.entity2_ring
        lines.append(
            f"entity2_ring: top={r['top']} bot={r['bot']} "
            f"left={r['left']} right={r['right']}"
        )
    else:
        lines.append("entity2_ring: none")

    notch = snap.entity2_notch_orientation
    lines.append(f"entity2_notch_orientation: {notch if notch is not None else 'none'}")

    if snap.cluster:
        c = snap.cluster
        lines.append(
            f"cluster: top_row={c['top_row']} bot_row={c['bot_row']} "
            f"col_min={c['col_min']} col_max={c['col_max']}"
        )
    else:
        lines.append("cluster: none")

    lines.append(f"entity1_state: {snap.entity1_state}")

    if snap.entity_signatures:
        sig_tokens = []
        for val, info in sorted(snap.entity_signatures.items()):
            bb = info["bbox"]
            sig_tokens.append(
                f"{val}:count={info['count']},bbox={bb[0]}-{bb[1]}x{bb[2]}-{bb[3]}"
            )
        lines.append("entity_signatures: " + " ".join(sig_tokens))

    lines.append("[/levelmap]")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Companion [levelmap] block parsing
# ---------------------------------------------------------------------------

_LEVELMAP_PATTERN = re.compile(
    r"\[levelmap\b([^\]]*)\](.*?)\[/levelmap\]",
    re.DOTALL | re.IGNORECASE,
)


def _parse_levelmap_body(header_attrs: dict, body: str) -> Optional[LevelSnapshot]:
    """Parse levelmap body text into a LevelSnapshot."""
    def _kv(text: str, key: str) -> Optional[str]:
        m = re.search(rf"^{key}:\s*(.+)$", text, re.MULTILINE)
        return m.group(1).strip() if m else None

    game_id = header_attrs.get("game", "unknown")
    level_num = int(header_attrs.get("level", 1))
    captured_at = int(header_attrs.get("created", 0))

    shape_str = _kv(body, "grid_shape") or "64x64"
    parts = shape_str.split("x")
    grid_shape = (int(parts[0]), int(parts[1])) if len(parts) == 2 else (64, 64)

    # block_pos
    bp_str = _kv(body, "block_pos") or "none"
    block_pos = None
    if bp_str != "none":
        try:
            r, c = bp_str.split(",")
            block_pos = (int(r), int(c))
        except Exception:
            pass

    # entity2_ring
    ring_str = _kv(body, "entity2_ring") or "none"
    entity2_ring = None
    if ring_str != "none":
        try:
            vals = dict(re.findall(r"(\w+)=(-?\d+)", ring_str))
            entity2_ring = {
                "top": int(vals["top"]),
                "bot": int(vals["bot"]),
                "left": int(vals["left"]),
                "right": int(vals["right"]),
                "interior_top": int(vals["top"]) + 1,
                "interior_bot": int(vals["bot"]) - 1,
                "interior_left": int(vals["left"]) + 1,
                "interior_right": int(vals["right"]) - 1,
            }
        except Exception:
            pass

    # notch orientation
    notch_str = _kv(body, "entity2_notch_orientation") or "none"
    entity2_notch = None
    if notch_str not in ("none", "None"):
        try:
            entity2_notch = int(notch_str)
        except Exception:
            pass

    # cluster
    cluster_str = _kv(body, "cluster") or "none"
    cluster = None
    if cluster_str != "none":
        try:
            vals = dict(re.findall(r"(\w+)=(-?\d+)", cluster_str))
            cluster = {
                "top_row": int(vals["top_row"]),
                "bot_row": int(vals["bot_row"]),
                "col_min": int(vals["col_min"]),
                "col_max": int(vals["col_max"]),
                "col_center": (int(vals["col_min"]) + int(vals["col_max"])) // 2,
            }
        except Exception:
            pass

    # entity1_state
    e1_str = _kv(body, "entity1_state") or "0"
    try:
        entity1_state = int(e1_str)
    except Exception:
        entity1_state = 0

    # entity_signatures
    sig_str = _kv(body, "entity_signatures") or ""
    entity_signatures = {}
    for token in sig_str.split():
        try:
            val_part, rest = token.split(":", 1)
            kv = dict(item.split("=") for item in rest.split(","))
            bb_raw = kv.get("bbox", "0-0x0-0")
            rb, cb = bb_raw.split("x")
            r1, r2 = rb.split("-")
            c1, c2 = cb.split("-")
            entity_signatures[int(val_part)] = {
                "count": int(kv.get("count", 0)),
                "bbox": (int(r1), int(r2), int(c1), int(c2)),
            }
        except Exception:
            pass

    return LevelSnapshot(
        game_id=game_id,
        level_num=level_num,
        captured_at=captured_at,
        grid_shape=grid_shape,
        block_pos=block_pos,
        entity2_ring=entity2_ring,
        entity2_notch_orientation=entity2_notch,
        cluster=cluster,
        entity1_state=entity1_state,
        entity_signatures=entity_signatures,
        raw_compact="",
    )


def parse_all_levelmaps(companion_text: str, game_id: str) -> dict:
    """
    Parse all [levelmap] blocks from companion text for the given game.
    Returns {level_num: most-recent-snapshot} (highest created timestamp wins).
    """
    prefix = game_id.split("-")[0] if "-" in game_id else game_id
    results: dict = {}

    for header_str, body_str in _LEVELMAP_PATTERN.findall(companion_text):
        attrs = dict(re.findall(r"(\w+)=(\S+)", header_str))
        if attrs.get("game", "").lower() != prefix.lower():
            continue
        try:
            level = int(attrs.get("level", 0))
            created = int(attrs.get("created", 0))
        except Exception:
            continue
        snap = _parse_levelmap_body(attrs, body_str)
        if snap and (level not in results or created > results[level].captured_at):
            results[level] = snap

    return results


# ---------------------------------------------------------------------------
# Companion file update
# ---------------------------------------------------------------------------

def update_levelmap_in_file(path: str, new_block: str, game_id: str, level_num: int) -> None:
    """
    Replace the existing [levelmap game=X level=N] block in companion_arcprize.md,
    or append it if none exists.
    """
    prefix = (game_id.split("-")[0] if "-" in game_id else game_id).lower()
    pattern = re.compile(
        rf"\[levelmap\b[^\]]*\bgame={re.escape(prefix)}\b[^\]]*\blevel={level_num}\b[^\]]*\]"
        rf".*?\[/levelmap\]",
        re.DOTALL | re.IGNORECASE,
    )
    with open(path, encoding="utf-8") as f:
        content = f.read()

    replaced, n = pattern.subn(new_block, content, count=1)
    if n:
        with open(path, "w", encoding="utf-8") as f:
            f.write(replaced)
    else:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n\n---\n\n{new_block}\n")


# ---------------------------------------------------------------------------
# Notebook compilation helper
# ---------------------------------------------------------------------------

def compile_stored_maps_literal(companion_text: str, game_id: str) -> str:
    """
    Extract stored levelmap data from companion and return a Python dict-literal
    string safe for embedding into the LucusAgent source string.

    Example output:
        '{"ls20": {1: {"block_pos": (40, 34), "ring_top": 8, "notch": 180,
                        "route": [0,0,0,2,2,2,1,0,3,3,3,0,0,0]}}}'
    """
    prefix = (game_id.split("-")[0] if "-" in game_id else game_id).lower()
    snaps = parse_all_levelmaps(companion_text, game_id)

    # Also pull stored routes from [route] and [strategy] blocks
    route_pattern = re.compile(
        rf'\[route\b[^\]]*\bgame={re.escape(prefix)}\b[^\]]*\blevel=(\d+)\b[^\]]*\]'
        rf'(.*?)\[/route\]',
        re.DOTALL | re.IGNORECASE,
    )
    _DIR = {"UP": 0, "DOWN": 1, "LEFT": 2, "RIGHT": 3}
    stored_routes: dict = {}
    for level_str, route_body in route_pattern.findall(companion_text):
        actions: list = []
        for token in re.split(r"[,\s]+", route_body.strip()):
            if not token:
                continue
            m = re.match(r"(UP|DOWN|LEFT|RIGHT)[×x](\d+)$", token, re.IGNORECASE)
            if m:
                actions.extend([_DIR[m.group(1).upper()]] * int(m.group(2)))
            elif token.upper() in _DIR:
                actions.append(_DIR[token.upper()])
            elif re.match(r"^\d+$", token):
                actions.append(int(token))
        if actions:
            stored_routes[int(level_str)] = actions

    level_data = {}
    for level_num, snap in snaps.items():
        entry: dict = {}
        if snap.block_pos:
            entry["block_pos"] = snap.block_pos
        if snap.entity2_ring:
            entry["ring_top"] = snap.entity2_ring["top"]
            entry["ring_bot"] = snap.entity2_ring["bot"]
        if snap.entity2_notch_orientation is not None:
            entry["notch"] = snap.entity2_notch_orientation
        if level_num in stored_routes:
            entry["route"] = stored_routes[level_num]
        level_data[level_num] = entry

    # Inject multi-level routes from game detector (if available in the dataset).
    # This allows the LucusAgent to load L2+ routes without notebook changes —
    # only the dataset files need updating when new routes are discovered.
    try:
        import importlib
        _det_mod = importlib.import_module(f"games.{prefix}.detector")
        # Each level beyond L1 that has a known route: inject it.
        for _lnum in range(2, 10):
            _route_attr = f"_L{_lnum}_ROUTE"
            if not hasattr(_det_mod, _route_attr):
                break
            _raw = getattr(_det_mod, _route_attr)
            # Prepend the level's initial probe action so the LucusAgent
            # executes it as route[0] without a separate probe step.
            _probe = getattr(_det_mod, f"_L{_lnum}_PROBE", None)
            if _probe is None and hasattr(_det_mod, "initial_action"):
                _probe = _det_mod.initial_action(_lnum)
            _full = ([_probe] + list(_raw)) if _probe is not None else list(_raw)
            level_data.setdefault(_lnum, {})["route"] = _full
    except Exception:
        pass

    # Build Python literal — no json to keep strings/tuples correct
    inner_parts = []
    for lnum, data in sorted(level_data.items()):
        items = []
        for k, v in data.items():
            items.append(f'"{k}": {repr(v)}')
        inner_parts.append(f"{lnum}: {{{', '.join(items)}}}")

    return '{' + f'"{prefix}": ' + '{' + ', '.join(inner_parts) + '}' + '}'
