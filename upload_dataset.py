"""Upload companion-arc dataset to Kaggle."""
import os
import tempfile

from kaggle import api

upload_dir = os.path.join(tempfile.gettempdir(), "kaggle_upload")
api.authenticate()
print(f"Uploading from: {upload_dir}")
api.dataset_create_version(
    upload_dir,
    "2026-06-14.2-dynsig: general explorer + HUD-immune DynamicSignature "
    "(LOCUS_MODE=general_dyn). general-v1 scored 0.18 (beat random 0.15); this "
    "masks in-grid HUD that defeats the signature; verified no-regression on canonical.",
    dir_mode="zip",
    quiet=False,
)
print("Upload complete!")
