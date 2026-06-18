"""Upload companion-arc dataset to Kaggle."""
import os
import tempfile

from kaggle import api

upload_dir = os.path.join(tempfile.gettempdir(), "kaggle_upload")
api.authenticate()
print(f"Uploading from: {upload_dir}")
api.dataset_create_version(
    upload_dir,
    "2026-06-18.1-recog-hardened: recognizer-precision hardening on the v1 floor "
    "(LOCUS_MODE=solve, ARC-RFC-0001). FIX vs 2026-06-17.1-solve-v1floor, which read 0.10 -- "
    "BELOW the v1 floor (0.18) -- because loose recognizers HIJACKED hidden games with bogus "
    "moves: ls20 fired on any 1-50px of colour-12, sp80 on any stray pixel-9 + pixel-11 (8.85% "
    "of hidden-like frames). Hardened ls20/sp80/cd82 recognizers to gate on real STRUCTURE "
    "(ls20: read_spec+plan must parse a solvable board; sp80: substantial >=20px piece + "
    ">=40px obstacle clusters; cd82: selector-sized 12-50px colour-2). New _test_falsefire.py "
    "hidden-decoy fuzzer cut the floor-hijack rate 10.8%->3.3% (ls20 0%); de-risk still CLEAN "
    "(diagonal confusion matrix, 10/10 within-dynamic win, no off-target regression, "
    "SupervisedAgent(empty)==v1 120/120). Runs in both the competition rerun and the offline "
    "batch via the shared _play_game path.",
    dir_mode="zip",
    quiet=False,
)
print("Upload complete!")
