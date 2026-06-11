"""Upload companion-arc dataset to Kaggle."""
import os
import tempfile

from kaggle import api

upload_dir = os.path.join(tempfile.gettempdir(), "kaggle_upload")
api.authenticate()
print(f"Uploading from: {upload_dir}")
api.dataset_create_version(
    upload_dir,
    "offline run 2026-06-11.3: fix sk48 route missing from dataset (launch_competition.py was stale in upload dir)",
    dir_mode="zip",
    quiet=False,
)
print("Upload complete!")
