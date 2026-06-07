# cd82 Companion

## Status
ADAPTIVE — detector.py v1 implements basket-position detection.

## Mechanics
- 8 baskets arranged in a ring; navigation uses a 3×3 grid with center (1,1) forbidden.
- ACTION0=row-1  ACTION1=row+1  ACTION2=col-1  ACTION3=col+1  ACTION4=FIRE
- ActiveBasket sprite uses pixel 2 (border) and pixel 15 (fill).
- Default start: basket 0, grid (0,1). Variable state: random step 0 may move basket.

## Basket ring layout
```
7(0,0)  0(0,1)  1(0,2)
6(1,0)  [ctr]   2(1,2)
5(2,0)  4(2,1)  3(2,2)
```

## Level 1 solution
Target: canvas rows 5-9 = color 15, rows 0-4 = 0.
→ Navigate to basket 4 at grid (2,1), fire (ACTION4).
→ Canvas position: game(x=27, y=34) = frame rows 34-43, cols 27-36.

## Adaptive route
detect_state() finds pixel-2 entity bbox → (r_min, c_min) → basket lookup → grid position.
compute_route() returns minimal navigation to basket 4, avoiding center (1,1), then FIRE.

## Navigation routes to basket 4
- From (0,0) basket 7: [1,1,3,4]    (4 steps)
- From (0,1) basket 0: [3,1,1,2,4]  (5 steps)
- From (0,2) basket 1: [1,1,2,4]    (4 steps)
- From (1,0) basket 6: [1,3,4]      (3 steps)
- From (1,2) basket 2: [1,2,4]      (3 steps)
- From (2,0) basket 5: [3,4]        (2 steps)
- From (2,1) basket 4: [4]          (1 step)
- From (2,2) basket 3: [2,4]        (2 steps)

## Known failure mode
If random step 0 = ACTION4 (fire basket 0), canvas rows 0-4 = 15. L1 target requires 0 there.
→ canvas_dirty=True → win check fails. Probability 1/5; no recovery with simple actions.

## Levels 2-6
Require color selection (ACTION5 = click) to select colors other than 15.
Not achievable with simple actions. Returns empty route for level_num≥2.
