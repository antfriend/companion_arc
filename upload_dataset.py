"""Upload companion-arc dataset to Kaggle."""
import os
import tempfile

from kaggle import api

upload_dir = os.path.join(tempfile.gettempdir(), "kaggle_upload")
api.authenticate()
print(f"Uploading from: {upload_dir}")
api.dataset_create_version(
    upload_dir,
    "2026-06-13.2-general: one general count-based explorer (no per-game code) "
    "replaces the detector fleet; LOCUS_MODE=general; beats random on coverage; commit 44cfcda",
    dir_mode="zip",
    quiet=False,
)
print("Upload complete!")
