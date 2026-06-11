"""Upload companion-arc dataset to Kaggle."""
import os
import tempfile

from kaggle import api

upload_dir = os.path.join(tempfile.gettempdir(), "kaggle_upload")
api.authenticate()
print(f"Uploading from: {upload_dir}")
api.dataset_create_version(
    upload_dir,
    "offline run 2026-06-11.4: fix sk48 route overwritten by empty adaptive scan result",
    dir_mode="zip",
    quiet=False,
)
print("Upload complete!")
