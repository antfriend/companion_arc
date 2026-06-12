"""Local reproduction of the Kaggle competition rerun.

Starts arc_agi.server (the same REST gateway protocol the competition uses,
competition_mode=True) over the local environment_files, then drives
launch_competition.run_competition() against it — the exact ONLINE code path
the hidden rerun executes. Compares per-game outcomes with the offline runs.
"""
import io
import sys
import threading
import time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import arc_agi
from arc_agi import OperationMode
from arc_agi.base import Arcade
from arc_agi.server import create_app

ENV_DIR = str(Path(__file__).parent / "environment_files")
PORT = 8001

# --- Start local gateway (competition mode) --------------------------------
serve_arcade = Arcade(operation_mode=OperationMode.OFFLINE, environments_dir=ENV_DIR)
app, api = create_app(serve_arcade, competition_mode=True)

t = threading.Thread(
    target=lambda: app.run(host="127.0.0.1", port=PORT, threaded=False, use_reloader=False),
    daemon=True,
)
t.start()
time.sleep(2)

# --- Drive the competition rerun path against it ----------------------------
import launch_competition as lc

lc.GATEWAY_URL = f"http://127.0.0.1:{PORT}"
lc.IS_COMPETITION_RERUN = True
lc._load_routes()
lc.run_competition()
