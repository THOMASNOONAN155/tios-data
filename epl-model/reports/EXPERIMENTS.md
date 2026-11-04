# Experiment log

Every test run by `backtest.py`, in order. RPS = ranked probability score (lower is better). Rule: a change is **kept** only if it lowers RPS on both Test A (2022-24) and Test B (2024-26); parameters and coefficients are fitted on the tuning seasons (2018-22) only. Full history across runs: `experiment_log.csv`.

| time | stage | test | description | RPS_TUNE | decision | note | RPS_TEST_A | RPS_TEST_B | RPS_TEST_A(23-24) |
|---|---|---|---|---|---|---|---|---|---|
| 2026-11-04 14:26 | 1-tune | poisson | coordinate-descent tuning over 15 settings | 0.19897 | tuned | {"target": "goals", "dc": false, "half_life": 365} |  |  |  |
| 2026-11-04 14:28 | 1-tune | dixon_coles | coordinate-descent tuning over 15 settings | 0.19913 | tuned | {"target": "goals", "dc": true, "half_life": 365} |  |  |  |
| 2026-11-04 14:30 | 1-tune | xg | coordinate-descent tuning over 20 settings | 0.19834 | tuned | {"target": "xg", "dc": true, "reg": 1} |  |  |  |
| 2026-11-04 14:34 | 1-tune | xg_goals_mix | coordinate-descent tuning over 32 settings | 0.19812 | tuned | {"target": "mix", "dc": true, "reg": 1, "xg_weight": 0.7} |  |  |  |
| 2026-11-04 14:37 | 1-tune | market | coordinate-descent tuning over 23 settings | 0.19786 | tuned | {"target": "market", "dc": true, "half_life": 90, "reg": 0.5, "season_decay": 0.5} |  |  |  |
| 2026-11-04 14:38 | 1-tune | elo | coordinate-descent tuning over 19 settings | 0.20059 | tuned | {"k": 10, "home": 40, "season_regress": 0.15} |  |  |  |
| 2026-11-04 14:38 | 2-compare | poisson | tuned model, walk-forward | 0.19897 |  |  | 0.19987 | 0.20593 |  |
| 2026-11-04 14:38 | 2-compare | dixon_coles | tuned model, walk-forward | 0.19913 |  |  | 0.19986 | 0.20586 |  |
| 2026-11-04 14:38 | 2-compare | xg | tuned model, walk-forward | 0.19834 |  |  | 0.19793 | 0.20238 |  |
| 2026-11-04 14:38 | 2-compare | xg_goals_mix | tuned model, walk-forward | 0.19812 |  |  | 0.19749 | 0.20243 |  |
| 2026-11-04 14:38 | 2-compare | market | tuned model, walk-forward | 0.19786 |  |  | 0.19442 | 0.20503 |  |
| 2026-11-04 14:38 | 2-compare | elo | tuned model, walk-forward | 0.20059 |  |  | 0.19819 | 0.20727 |  |
| 2026-11-04 14:38 | 2-compare | closing_market | margin-free closing odds (benchmark) | 0.19586 |  |  | 0.18875 | 0.20082 |  |
| 2026-11-04 14:38 | 3-blend | best single model (market) | reference for blending | 0.19786 | baseline |  | 0.19442 | 0.20503 |  |
| 2026-11-04 14:38 | 3-blend | xg_goals_mix+market | geometric blend of expected goals {"xg_goals_mix": 0.4, "market": 0.6000000000000001} | 0.19712 | dropped |  | 0.19513 | 0.20338 |  |
| 2026-11-04 14:38 | 3-blend | xg_goals_mix+market+elo | geometric blend of expected goals {"xg_goals_mix": 0.4, "market": 0.6000000000000001, "elo": 0.0} | 0.19712 | dropped |  | 0.19513 | 0.20338 |  |
| 2026-11-04 14:38 | 3-blend | xg+dixon_coles+market | geometric blend of expected goals {"xg": 0.30000000000000004, "dixon_coles": 0.1, "market": 0.6000000000000001} | 0.19713 | dropped |  | 0.19524 | 0.20346 |  |
| 2026-11-04 14:38 | 3-blend | xg+market+elo | geometric blend of expected goals {"xg": 0.4, "market": 0.6000000000000001, "elo": 0.0} | 0.19716 | dropped |  | 0.19517 | 0.20327 |  |
| 2026-11-04 14:38 | 3-blend | xg_goals_mix+dixon_coles+market+elo | geometric blend of expected goals {"xg_goals_mix": 0.4, "dixon_coles": 0.0, "market": 0.6000000000000001, "elo": 0.0} | 0.19712 | dropped |  | 0.19513 | 0.20338 |  |
| 2026-11-04 14:38 | 4-factor | draw_bias | {"draw": ["const"]} | 0.19768 | dropped | {"beta": [], "delta": [-0.1]} | 0.19446 | 0.20553 |  |
| 2026-11-04 14:38 | 4-factor | early_season | {"goals": [["early", "shrink"]]} | 0.19773 | dropped | {"beta": [-0.0077], "delta": []} | 0.19445 | 0.20509 |  |
| 2026-11-04 14:38 | 4-factor | promoted_early | {"goals": [["promoted_early", "own"], ["promoted_early", "opp"]]} | 0.19736 | KEPT | {"beta": [-0.0397, 0.2121], "delta": []} | 0.19402 | 0.20487 |  |
| 2026-11-04 14:38 | 4-factor | rest_days | {"goals": [["short_rest", "own"], ["short_rest", "opp"]]} | 0.19692 | dropped | {"beta": [-0.0588, 0.194, 0.0474, -0.1401], "delta": []} | 0.19286 | 0.20652 |  |
| 2026-11-04 14:38 | 4-factor | rest_diff | {"goals": [["rest_diff_h", "home"]]} | 0.19734 | dropped | {"beta": [-0.0406, 0.2122, 0.0017], "delta": []} | 0.19404 | 0.20483 |  |
| 2026-11-04 14:38 | 4-factor | euro_congestion | {"goals": [["euro_before", "own"], ["euro_before", "opp"], ["euro_after", "own"]]} | 0.19744 | dropped | {"beta": [-0.0405, 0.2096, 0.0222, -0.0705, -0.0106], "delta": []} | 0.19401 | 0.20530 |  |
| 2026-11-04 14:38 | 4-factor | manager_change | {"goals": [["new_mgr", "own"], ["new_mgr", "opp"]]} | 0.19742 | KEPT | {"beta": [-0.0273, 0.2271, -0.0243, -0.0201], "delta": []} | 0.19398 | 0.20486 |  |
| 2026-11-04 14:38 | 4-factor | derby | {"goals": [["derby", "match"]], "draw": ["derby"]} | 0.19740 | KEPT | {"beta": [-0.0291, 0.2264, -0.0225, -0.0183, -0.0218], "delta": [0.05]} | 0.19395 | 0.20483 |  |
| 2026-11-04 14:38 | 4-factor | motivation | {"goals": [["ntp", "own"], ["ntp", "opp"]], "draw": ["both_ntp"]} | 0.19740 | KEPT | {"beta": [-0.0121, 0.2378, -0.0267, -0.0217, -0.0235, 0.0828, 0.1248], "delta": [0.05, -0.5]} | 0.19385 | 0.20479 |  |
| 2026-11-04 14:38 | 4-factor | finishing_luck | {"goals": [["fin_luck", "own"], ["def_luck", "opp"]]} | 0.19742 | dropped | {"beta": [-0.0123, 0.2366, -0.0269, -0.0242, -0.0229, 0.0836, 0.125, -0.0078, 0.0376], "delta": [0.05, -0.5]} | 0.19401 | 0.20493 |  |
| 2026-11-04 14:38 | 4-factor | penalty_skill | {"goals": [["pen_rate", "own"]]} | 0.19736 | dropped | {"beta": [-0.0147, 0.2367, -0.0286, -0.0211, -0.0218, 0.0793, 0.1272, -0.1475], "delta": [0.05, -0.5]} | 0.19398 | 0.20467 |  |
| 2026-11-04 14:38 | 4-factor | red_card_rate | {"goals": [["red_rate", "own"], ["red_rate", "opp"]]} | 0.19742 | dropped | {"beta": [-0.0122, 0.2385, -0.0296, -0.0213, -0.0224, 0.0811, 0.1253, 0.2326, 0.0513], "delta": [0.05, -0.5]} | 0.19398 | 0.20478 |  |
| 2026-11-04 14:38 | 4-factor | set_pieces | {"goals": [["corner_diff", "own"], ["corner_diff", "opp"]]} | 0.19747 | KEPT | {"beta": [-0.0166, 0.2396, -0.0271, -0.0199, -0.0228, 0.0804, 0.1277, -0.0017, 0.0014], "delta": [0.05, -0.5]} | 0.19382 | 0.20469 |  |
| 2026-11-04 14:38 | 4-factor | form | {"goals": [["form_xgd5", "own"], ["form_xgd5", "opp"]]} | 0.19739 | KEPT | {"beta": [-0.016, 0.252, -0.0227, -0.02, -0.0286, 0.0872, 0.1294, -0.0115, -0.0017, 0.0483, 0.0153], "delta": [0.05, -0.5]} | 0.19331 | 0.20432 |  |
| 2026-11-04 14:38 | 4-factor | lineup_strength | starting-XI xG+xA value vs team norm; fitted on 2022-23 (first season with FPL starts) |  | dropped | reference {"TEST_A(23-24)": 0.18337, "TEST_B": 0.20432}; beta=[0.1278, -0.3751] |  | 0.20566 | 0.18362 |
