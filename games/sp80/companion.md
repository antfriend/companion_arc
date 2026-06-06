# sp80 Companion

## Status
STUB — frame archaeology pending.

## Known route (one instance)
[route game=sp80 level=1 steps=8 confirmed=true search_seed=42 search_trial=159]
4,3,3,3,4,2,2,1
[/route]

Action space: 5 simple actions (ACTION1–5, indices 0–4).
Route decoded: ACTION5 ACTION4×3 ACTION5 ACTION3×2 ACTION2

## Frame analysis needed
Run a batch with [frame] logging to capture entity_signatures for multiple
instances. Identify which entity position varies between winning and losing runs,
then implement adaptive detect_state + compute_route in detector.py.
