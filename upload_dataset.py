"""Upload companion-arc dataset to Kaggle."""
import os
import tempfile

from kaggle import api

upload_dir = os.path.join(tempfile.gettempdir(), "kaggle_upload")
api.authenticate()
print(f"Uploading from: {upload_dir}")
api.dataset_create_version(
    upload_dir,
    "ar25 L1 solved: reflection puzzle, piece at (1,15) covers markers via mirror, 16 steps",
    dir_mode="zip",
    quiet=False,
)
print("Upload complete!")
