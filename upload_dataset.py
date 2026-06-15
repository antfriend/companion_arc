"""Upload companion-arc dataset to Kaggle."""
import os
import tempfile

from kaggle import api

upload_dir = os.path.join(tempfile.gettempdir(), "kaggle_upload")
api.authenticate()
print(f"Uploading from: {upload_dir}")
api.dataset_create_version(
    upload_dir,
    "2026-06-15.1-goal: per-instance solving as an additive-safe, stall-gated "
    "goal-seeking tie-break (LOCUS_MODE=goal; GoalSeekAgent subclasses general_dyn). "
    "Re-orders only v1's already-safe top tier; latched stall-gate keeps it coverage-"
    "neutral vs v1 (+0.2% on the coverage proxy) then biases ties toward an inferred "
    "goal. Validated on a new completion proxy (oracle/greedy anchors): +14 affordance, "
    "no trap regression. Includes HUD-immune DynamicSignature; no-regression by construction.",
    dir_mode="zip",
    quiet=False,
)
print("Upload complete!")
