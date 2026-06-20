"""Upload companion-arc dataset to Kaggle."""
import os
import tempfile

from kaggle import api

upload_dir = os.path.join(tempfile.gettempdir(), "kaggle_upload")
api.authenticate()
print(f"Uploading from: {upload_dir}")
api.dataset_create_version(
    upload_dir,
    "2026-06-20.1-click+additive: (1) ADDITIVE LAW now an ENFORCED invariant - the floor is "
    "frozen while a solver drives (no off-policy commits) so floor+dynamics >= floor on every "
    "game; repairs the warm-keep pollution that had every dynamics build sitting under plain v1 "
    "(core/solve_agent.py + GeneralAgent.mark_discontinuity; proven by _test_pollution.py). "
    "(2) CLICK-SELECT capability: SolverStep.click + SupervisedAgent.spec side-channel + "
    "ClickExplorer as a drop-in floor='click' + spec_to_action_input -> the dynamics layer and "
    "the competition launcher now drive ACTION6 clicks (env.step(ACTION6,{x,y})); click games "
    "get a real attempt instead of scoring 0 (vc33 ~44% via the click floor). Movement path "
    "byte-identical; full fleet unchanged (_test_multilevel: ls20 L3, tu93/re86/wa30/ar25 L2, "
    "sk48 L2); de-risk CLEAN; _test_click_plumbing.py green. (3) sk48 SOLVED L1+L2 as a "
    "frame-derived, geometry-generalized push-model dynamic (games/sk48/{dynamic,detector,bfs_solver}.py). "
    "falsefire floor-hijack 3.3% unchanged (pre-existing baseline, recognizers untouched).",
    dir_mode="zip",
    quiet=False,
)
print("Upload complete!")
