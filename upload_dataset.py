"""Upload companion-arc dataset to Kaggle."""
import os
import tempfile

from kaggle import api

upload_dir = os.path.join(tempfile.gettempdir(), "kaggle_upload")
api.authenticate()
print(f"Uploading from: {upload_dir}")
api.dataset_create_version(
    upload_dir,
    "2026-06-17.1-solve-v1floor: dynamics solver layer on the v1 floor (LOCUS_MODE=solve, "
    "ARC-RFC-0001). FIX vs 2026-06-16.1-solve, which floored on the GOAL explorer (0.10) by "
    "mistake -> 0.13; this floors on v1 (GeneralAgent static signature, leaderboard 0.18 -- "
    "the standing best), so the additive recognition-gated dynamics stack on the measured-best "
    "floor (expected ~0.21). 9/11 game-families ported + de-risked CLEAN (sp80,cd82,tu93,wa30,"
    "re86,ar25,cn04,ls20,g50t): diagonal confusion matrix (each fires only on its own game), "
    "10/10 within-dynamic win, no off-target regression; unrecognized/mismatched games fall "
    "back to the v1 explorer floor (no-regression by construction: SupervisedAgent(empty)==v1, "
    "120/120). Runs in both the competition rerun and the offline batch via the shared "
    "_play_game path.",
    dir_mode="zip",
    quiet=False,
)
print("Upload complete!")
