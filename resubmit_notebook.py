"""Resubmit the Kaggle competition notebook."""
from kaggle import api

api.authenticate()

# Push the notebook for competition
api.kernels_push("c:/git/companion_arc")
print("Notebook submitted!")
