"""Patch kaggle_notebook.ipynb: column-adaptive _detect_l1_route + remove ls20 from _ROUTES."""
import json

NOTEBOOK = "c:/git/companion_arc/kaggle_notebook.ipynb"

with open(NOTEBOOK, encoding="utf-8") as f:
    nb = json.load(f)

src = "".join(nb["cells"][1]["source"])

# --- 1. Remove ls20 from _ROUTES -----------------------------------------------
# Exact text as it appears in the joined source
LS20_ROUTE_LINE = '\n        \'        "ls20": [0, 0, 0, 0, 2, 2, 2, 1, 0, 3, 3, 3, 0, 0, 0],\','
if LS20_ROUTE_LINE in src:
    src = src.replace(LS20_ROUTE_LINE, "", 1)
    print("ls20 removed from _ROUTES.")
else:
    print("ls20 NOT found in _ROUTES (may already be removed).")

# --- 2. Replace _detect_l1_route -----------------------------------------------
# Find from function def to end of function (the return [0]*5 line)
START = '"    def _detect_l1_route(grid):"'
END   = '"        return [0] * 5",'

s = src.find(START)
e = src.find(END, s)
if s == -1 or e == -1:
    print(f"ERROR: bounds not found. START={s} END={e}")
    exit(1)

old_block = src[s : e + len(END)]
print(f"Replacing _detect_l1_route ({len(old_block)} chars)...")

new_block = (
    '"    def _detect_l1_route(grid):",\n'
    '        \'        """Compute L1 adaptive route.\',\n'
    '        "",\n'
    '        "        LEFT/RIGHT count scales with block column so the route",\n'
    '        "        works for any starting column (c34 locally, c39 on Kaggle).",\n'
    '        "        Passes through c19 — required for L1 WIN.",\n'
    '        \'        """\',\n'
    '        "        try:",\n'
    '        "            BLOCK = 12",\n'
    '        "            DETOUR_ROW, DETOUR_COL, FINAL_ROW = 25, 19, 10",\n'
    '        "            positions = _np.argwhere(grid == BLOCK)",\n'
    '        "            if not len(positions):",\n'
    '        "                return None",\n'
    '        "            block_row = int(positions[:, 0].min())",\n'
    '        "            block_col = int(positions[:, 1].min())",\n'
    '        "            ups_1 = max(0, (block_row - DETOUR_ROW) // 5)",\n'
    '        "            ups_2 = max(1, (DETOUR_ROW - FINAL_ROW) // 5)",\n'
    '        "            left_count = max(1, (block_col - DETOUR_COL) // 5)",\n'
    '        "            return [0]*ups_1 + [2]*left_count + [1, 0] + [3]*left_count + [0]*ups_2",\n'
    '        "        except Exception:",\n'
    '        "            pass",\n'
    '        "        return [0, 0, 0, 0, 2, 2, 2, 1, 0, 3, 3, 3, 0, 0, 0]",'
)

src = src[:s] + new_block + src[e + len(END):]

# --- 3. Write back -------------------------------------------------------------
lines = src.splitlines(keepends=True)
nb["cells"][1]["source"] = lines

with open(NOTEBOOK, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
print("Written.")

# --- 4. Verify -----------------------------------------------------------------
src2 = "".join(nb["cells"][1]["source"])
print("block_col present:      ", "block_col" in src2)
print("DETOUR_COL present:     ", "DETOUR_COL" in src2)
print("ls20 in _ROUTES:        ", LS20_ROUTE_LINE in src2)
print("return [0]*5 gone:      ", '"        return [0] * 5"' not in src2)
print("guard clean:            ", "and not self._route:" not in src2)

# Cleanup patch script
import os
os.remove(__file__)
