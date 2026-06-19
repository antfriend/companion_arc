"""Upload companion-arc dataset to Kaggle."""
import os
import tempfile

from kaggle import api

upload_dir = os.path.join(tempfile.gettempdir(), "kaggle_upload")
api.authenticate()
print(f"Uploading from: {upload_dir}")
api.dataset_create_version(
    upload_dir,
    "2026-06-19.1-L2wins: FIRST multi-level dynamics solves on the v1 floor "
    "(LOCUS_MODE=solve, ARC-RFC-0001). tu93 L2 (the turret arms only at EXACT distance-6 on "
    "its facing axis -> one lethal cell + a lower-corridor bypass -> forbidden-cell BFS in "
    "games/tu93/detector.py) and wa30 L2 (the colour-12 sprite is a delivery HELPER, not a "
    "lethal patroller -> COOPERATIVE delivery replacing the hazard-evasion branch in "
    "games/wa30/dynamic.py) now clear L2 (_test_multilevel max level 2 for both). ls20 L4 "
    "attempted + reverted (pushers can't be read cleanly from the frame; still max level 3). "
    "RESYNCED the kaggle_upload mirror to the committed repo: it was MISSING ls20/solver.py + "
    "core/dynamics/hazard_nav.py and had stale ar25/ls20 dynamics (prior uploads may have shipped "
    "a broken ls20 import). de-risk CLEAN (diagonal confusion matrix, 10/10 within-dynamic win, "
    "no off-target regression, SupervisedAgent(empty)==v1 120/120), falsefire floor-hijack 3.4% "
    "unchanged. Runs in both the competition rerun and the offline batch via the shared "
    "_play_game path.",
    dir_mode="zip",
    quiet=False,
)
print("Upload complete!")
