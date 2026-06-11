"""Upload companion-arc dataset to Kaggle."""
import os
import tempfile

from kaggle import api

upload_dir = os.path.join(tempfile.gettempdir(), "kaggle_upload")
api.authenticate()
print(f"Uploading from: {upload_dir}")
api.dataset_create_version(
    upload_dir,
    "g50t L1 solved: recording/replay maze, ghost holds door open, 17-step route",
    dir_mode="zip",
    quiet=False,
)
print("Upload complete!")
