"""Upload companion-arc dataset to Kaggle."""
import os
import tempfile

from kaggle import api

upload_dir = os.path.join(tempfile.gettempdir(), "kaggle_upload")
api.authenticate()
print(f"Uploading from: {upload_dir}")
api.dataset_create_version(
    upload_dir,
    "purge+focus: the dataset carries ONLY the solving hull (launch_competition.py + "
    "agent_framework.py + ls20_detector.py + level_scanner.py + core/ + games/). One solving "
    "brain - SupervisedAgent (v1/click explorer floor + recognition-gated, abortable Dynamic "
    "solver layer) - plays every game the SAME way in the competition rerun and the offline "
    "batch; an unrecognized game falls back to the floor with no regression (additive law, "
    "enforced by tests/_test_pollution.py). Crow's nest (tests/_test_multilevel.py): ls20 L3; "
    "tu93/re86/wa30/ar25/sk48/sp80/g50t L2; cd82/cn04 L1. NEW: wa30 unified to Pattern A - one "
    "gate-less closed-loop cooperative-delivery solver wins L1+L2 (L1 = the no-helper "
    "degenerate case), replacing the old L1-route/L2-branch split. Per-game isolation so one "
    "game's failure never sinks the run.",
    dir_mode="zip",
    quiet=False,
)
print("Upload complete!")
