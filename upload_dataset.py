"""Upload companion-arc dataset to Kaggle."""
import os
import tempfile

from kaggle import api

upload_dir = os.path.join(tempfile.gettempdir(), "kaggle_upload")
api.authenticate()
print(f"Uploading from: {upload_dir}")
api.dataset_create_version(
    upload_dir,
    "2026-06-13.1-ablation: LOCUS_ABLATION=random diagnostic — routes/detectors "
    "disabled, uniformly-random play, to measure the hidden-set floor; commit 00fbc55",
    dir_mode="zip",
    quiet=False,
)
print("Upload complete!")
