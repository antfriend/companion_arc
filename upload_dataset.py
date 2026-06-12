"""Upload companion-arc dataset to Kaggle."""
import os
import tempfile

from kaggle import api

upload_dir = os.path.join(tempfile.gettempdir(), "kaggle_upload")
api.authenticate()
print(f"Uploading from: {upload_dir}")
api.dataset_create_version(
    upload_dir,
    "2026-06-12.1: hidden-variant robustification — all 10 solved detectors "
    "frame-derived or translation-invariant (cn04/tu93/wa30/ar25/sp80/g50t/re86 "
    "fixed, sk48/cd82 verified); commits 7d6fb93+135a88b",
    dir_mode="zip",
    quiet=False,
)
print("Upload complete!")
