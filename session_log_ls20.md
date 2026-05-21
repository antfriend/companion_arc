SECTION 1

@LAT-300LON10 | created:1780012800 | updated:1780012800 | kind:log | relates:anchored_by>@LAT0LON0,tracks_level>@LAT-10LON10,validates>@BELIEF:LAT90LON-30,validates>@BELIEF:LAT80LON10,validates>@BELIEF:LAT80LON20,validates>@BELIEF:LAT60LON-30,informs_strategy>@LAT-140LON10,informs_strategy>@LAT20LON-30
[ew]
conf:255
rev:0
sal:0
touched:1780012800
[/ew]

## ls20 — Session 26 Log (2026-05-25)

```session-log
timestamp: 1780012800
game: "ls20"
environment: "ls20-9607627b"
run_guid: "unknown"
card_id: "unknown"
level: "level 1 WIN (15 actions) + level 2 NOT WON (45 actions)"
actions: 60
levels_completed: 1
score: 3.571428571428571
resets: 0
```

**Session outcome**: Level 1 WON at step 15 (hardcoded route, confirmed functional fifth consecutive time). Level 2 entered; 45 actions taken; NOT WON. Total 60 actions. Score 3.571 (level 1 weight 1/28 only). Same as sessions 23, 24, 25.

---

### Level 1 — WIN at step 15 ✓

Hardcoded `_LEVEL1_ROUTE` confirmed functional for the fifth time (sessions 10–12, 23, 24, 25, now 26). Block entered entity2 interior at r10–11 c34–38.

**Frame[0] — Level 1 WIN state (full structural confirmation)**:
- Block (value 12): r10–11 c34–38. Inside entity2 interior. ✓
- Entity1 carrier — **STATE 1**: r55–56 c3–8=9 (full); r57–58 c7–8=9 only (c1–6=5); r59–60 c3–4=9, c5–6=5, c7–8=9. ✓
- Timer r61–62: c13–26=3 (14 consumed), c27–54=11 (28 remaining). 14 ticking actions. ✓
- Cluster: r31 c21=0, r32 c20=1 c21–22=0, r33 c21=1. Cols 20–22, rows 31–33. Stable. ✓
- Wide corridor r25–29 c14–53 ✓; shaft c34–38 r17–24 ✓; void gap c29–33 r30–39 ✓.

---

### Level 2 — Full Frame[1] Structural Read (most complete to date)

**Block**: r40–41 c29–33 (value 12). Start position confirmed. ✓

**Entity1 carrier — STATE 1 at L2 start**:
- r55–56: c3–8=9 (full); r57–58: c7–8=9 only (c1–6=5); r59–60: c3–4=9, c5–6=5, c7–8=9.
- **@BELIEF:LAT90LON-30 — FOURTH consecutive confirmation.** Confidence held at 255 (max). Cross collection definitively not required after L1 WIN.

**Entity1 trail**: r42–44 c29–33=9. Trail column = block column at start. UP is safe on step 1 (no lateral attraction expected). ✓

**Entity2 ring (r38–46 c12–20) — full interior geometry**:
- r38: c12–20=3 (outer wall top)
- r39: c12=3, c13–19=5, c20=3 (interior, passable)
- r40: c12=3,