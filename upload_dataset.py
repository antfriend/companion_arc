"""Upload companion-arc dataset to Kaggle."""
import os
import tempfile

from kaggle import api

upload_dir = os.path.join(tempfile.gettempdir(), "kaggle_upload")
api.authenticate()
print(f"Uploading from: {upload_dir}")
api.dataset_create_version(
    upload_dir,
    "offline run 2026-06-11.5: ka59 adaptive detector (BFS navigation to target win pos)",
    dir_mode="zip",
    quiet=False,
)
print("Upload complete!")
