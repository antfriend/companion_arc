"""Upload companion-arc dataset to Kaggle."""
import os
import tempfile

from kaggle import api

upload_dir = os.path.join(tempfile.gettempdir(), "kaggle_upload")
api.authenticate()
print(f"Uploading from: {upload_dir}")
api.dataset_create_version(
    upload_dir,
    "offline run 2026-06-11: overall=1.0667, 8 games scoring L1; frame sigs for 11 unsolved",
    dir_mode="zip",
    quiet=False,
)
print("Upload complete!")
