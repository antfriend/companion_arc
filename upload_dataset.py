"""Upload companion-arc dataset to Kaggle."""
import os
import tempfile

from kaggle import api

upload_dir = os.path.join(tempfile.gettempdir(), "kaggle_upload")
api.authenticate()
print(f"Uploading from: {upload_dir}")
api.dataset_create_version(
    upload_dir,
    "wa30 L1 solved: adaptive delivery BFS, 30 steps (commit 7d2b5e8)",
    dir_mode="zip",
    quiet=False,
)
print("Upload complete!")
