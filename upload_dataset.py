"""Upload companion-arc dataset to Kaggle."""
import os
import tempfile

from kaggle import api

upload_dir = os.path.join(tempfile.gettempdir(), "kaggle_upload")
api.authenticate()
print(f"Uploading from: {upload_dir}")
api.dataset_create_version(
    upload_dir,
    "offline run 2026-06-11.2: 9 games L1 solved (added sk48 snake+sokoban, 14 actions)",
    dir_mode="zip",
    quiet=False,
)
print("Upload complete!")
