# sp80 Companion

## Status
ADAPTIVE — detector.py v2 implements piece-position detection.

## Mechanics
- Two phases per level: piece positioning (pixel-9 = selected) then liquid spill.
- ACTION0=UP, ACTION1=DOWN, ACTION2=LEFT, ACTION3=RIGHT, ACTION4=SPILL.
- Frame mapping: frame_col = game_x × 4, frame_row = game_y × 4.
- Selected piece shown as pixel 9 (unselected = 8).
- Canonical winning position for L1: game (3, 4).

## Adaptive route
detect_state() finds the pixel-9 entity → game_x, game_y.
compute_route() prefixes LEFT/RIGHT/UP/DOWN moves to reach (3,4), then appends spill sequence.

## Spill sequence (from canonical position)
[route game=sp80 level=1 steps=8 confirmed=true search_seed=42 search_trial=159]
4,3,3,3,4,2,2,1
[/route]

Action space: 5 simple actions (ACTION1–5, indices 0–4).
Route decoded: SPILL RIGHT×3 SPILL LEFT×2 DOWN
