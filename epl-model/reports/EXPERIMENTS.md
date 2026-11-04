# Experiment log

Every test run by `backtest.py`, in order. RPS = ranked probability score (lower is better); dRPS = change versus the current model (negative = better); upper95 = one-sided 95% bootstrap upper bound of dRPS.

**Keep rule:** a blend, structural change or factor is kept only if its gain is clearly bigger than noise on both Test A (2022-24) and Test B (2024-26): a paired bootstrap over match dates (2,000 resamples) must put upper95 below zero in each period. All parameters and coefficients are fitted on the tuning seasons (2018-22) only. `dropped (gain within noise)` = better on both periods but not clearly. Machine-readable history: `experiment_log.csv`.

## Current run (significance rule)

| stage | test | description | decision | RPS_TUNE | RPS_TEST_A | RPS_TEST_B | dRPS_TEST_A | dRPS_TEST_A_upper95 | dRPS_TEST_B | dRPS_TEST_B_upper95 | note |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1-tune | poisson | tuned settings reused from previous run (deterministic) | tuned |  |  |  |  |  |  |  | {"target": "goals", "dc": false, "half_life": 365}; TUNE=0.19897 (coordinate descent over the grid) |
| 1-tune | dixon_coles | tuned settings reused from previous run (deterministic) | tuned |  |  |  |  |  |  |  | {"target": "goals", "dc": true, "half_life": 365}; TUNE=0.19913 (coordinate descent over the grid) |
| 1-tune | xg | tuned settings reused from previous run (deterministic) | tuned |  |  |  |  |  |  |  | {"target": "xg", "dc": true, "reg": 1}; TUNE=0.19834 (coordinate descent over the grid) |
| 1-tune | xg_goals_mix | tuned settings reused from previous run (deterministic) | tuned |  |  |  |  |  |  |  | {"target": "mix", "dc": true, "reg": 1, "xg_weight": 0.7}; TUNE=0.19812 (coordinate descent over the grid) |
| 1-tune | market | tuned settings reused from previous run (deterministic) | tuned |  |  |  |  |  |  |  | {"target": "market", "dc": true, "half_life": 90, "reg": 0.5, "season_decay": 0.5}; TUNE=0.19786 (coordinate descent over the grid) |
| 1-tune | elo | tuned settings reused from previous run (deterministic) | tuned |  |  |  |  |  |  |  | {"k": 10, "home": 40, "season_regress": 0.15}; TUNE=0.20059 (coordinate descent over the grid) |
| 2-compare | poisson | tuned model, walk-forward |  | 0.19897 | 0.19987 | 0.20593 |  |  |  |  |  |
| 2-compare | dixon_coles | tuned model, walk-forward |  | 0.19913 | 0.19986 | 0.20586 |  |  |  |  |  |
| 2-compare | xg | tuned model, walk-forward |  | 0.19834 | 0.19793 | 0.20238 |  |  |  |  |  |
| 2-compare | xg_goals_mix | tuned model, walk-forward |  | 0.19812 | 0.19749 | 0.20243 |  |  |  |  |  |
| 2-compare | market | tuned model, walk-forward |  | 0.19786 | 0.19442 | 0.20503 |  |  |  |  |  |
| 2-compare | elo | tuned model, walk-forward |  | 0.20059 | 0.19819 | 0.20727 |  |  |  |  |  |
| 2-compare | closing_market | margin-free closing odds (benchmark) |  | 0.19586 | 0.18875 | 0.20082 |  |  |  |  |  |
| 3-blend | best single model (market) | reference for blending (best on TUNE) | baseline | 0.19786 | 0.19442 | 0.20503 |  |  |  |  |  |
| 3-blend | xg_goals_mix+market | geometric blend of expected goals {"xg_goals_mix": 0.4, "market": 0.6} | dropped | 0.19712 | 0.19513 | 0.20338 | 0.00070 | 0.00154 | -0.00169 | -0.00075 |  |
| 3-blend | xg_goals_mix+market+elo | geometric blend of expected goals {"xg_goals_mix": 0.4, "market": 0.6, "elo": 0.0} | dropped | 0.19712 | 0.19513 | 0.20338 | 0.00070 | 0.00154 | -0.00169 | -0.00075 |  |
| 3-blend | xg+dixon_coles+market | geometric blend of expected goals {"xg": 0.3, "dixon_coles": 0.1, "market": 0.6} | dropped | 0.19713 | 0.19524 | 0.20346 | 0.00081 | 0.00163 | -0.00161 | -0.00068 |  |
| 3-blend | xg+market+elo | geometric blend of expected goals {"xg": 0.4, "market": 0.6, "elo": 0.0} | dropped | 0.19716 | 0.19517 | 0.20327 | 0.00073 | 0.00164 | -0.00180 | -0.00080 |  |
| 3-blend | xg_goals_mix+dixon_coles+market+elo | geometric blend of expected goals {"xg_goals_mix": 0.4, "dixon_coles": 0.0, "market": 0.6, "elo": 0.0} | dropped | 0.19712 | 0.19513 | 0.20338 | 0.00070 | 0.00154 | -0.00169 | -0.00075 |  |
| 4-structural | no_crowd_home_adv | separate home advantage for matches without crowds (Jun 2020-May 2021) | dropped | 0.19780 | 0.19443 | 0.20506 | -0.00000 | 0.00000 | 0.00000 | 0.00000 |  |
| 4-structural | promoted_prior | promoted clubs' ratings start at the historical promoted-club average | dropped | 0.19735 | 0.19414 | 0.20509 | -0.00030 | 0.00023 | 0.00002 | 0.00057 |  |
| 4-structural | red_card_downweight | matches with a red card count half in the rating fit (red cards as luck) | dropped | 0.19784 | 0.19449 | 0.20524 | 0.00005 | 0.00016 | 0.00017 | 0.00029 |  |
| 4-structural | npxg_plus_avg_penalties | xG model rebuilt on non-penalty xG + average penalty value (penalties treated as luck); compared with the xG model | dropped | 0.19848 | 0.19825 | 0.20247 | 0.00032 | 0.00116 | 0.00010 | 0.00068 | information only: the xG model is not in the selected blend |
| 5-factor | draw_bias | Global draw-rate correction | dropped | 0.19768 | 0.19446 | 0.20553 | 0.00003 | 0.00033 | 0.00046 | 0.00076 | coefficients {"beta": [], "delta": [-0.1]} |
| 5-factor | early_season | Pull both sides towards each other in the first 7 rounds (early-season uncertainty) | dropped | 0.19773 | 0.19445 | 0.20509 | 0.00001 | 0.00004 | 0.00003 | 0.00005 | coefficients {"beta": [-0.0077], "delta": []} |
| 5-factor | promoted_early | Newly promoted side in the first 11 rounds | dropped (gain within noise) | 0.19736 | 0.19402 | 0.20487 | -0.00041 | 0.00012 | -0.00019 | 0.00034 | coefficients {"beta": [-0.0397, 0.2121], "delta": []} |
| 5-factor | rest_days | Short rest (3 days or fewer) for either side | dropped | 0.19729 | 0.19324 | 0.20673 | -0.00120 | -0.00022 | 0.00167 | 0.00274 | coefficients {"beta": [0.0469, -0.1433], "delta": []} |
| 5-factor | rest_diff | Difference in days of rest between the sides | dropped | 0.19771 | 0.19445 | 0.20503 | 0.00002 | 0.00005 | -0.00004 | 0.00000 | coefficients {"beta": [0.0014], "delta": []} |
| 5-factor | euro_congestion | UEFA match within 3 days before or 4 days after | dropped | 0.19781 | 0.19443 | 0.20556 | -0.00000 | 0.00029 | 0.00049 | 0.00097 | coefficients {"beta": [0.0252, -0.0758, -0.0092], "delta": []} |
| 5-factor | manager_change | New manager or caretaker appointed in the last 60 days | dropped (gain within noise) | 0.19780 | 0.19432 | 0.20506 | -0.00011 | 0.00005 | -0.00000 | 0.00016 | coefficients {"beta": [-0.0261, 0.0004], "delta": []} |
| 5-factor | derby | Derby (same city or classic rivalry): goal level and draw rate | dropped (gain within noise) | 0.19771 | 0.19441 | 0.20502 | -0.00002 | 0.00008 | -0.00004 | 0.00006 | coefficients {"beta": [-0.0253], "delta": [0.05]} |
| 5-factor | motivation | End of season (last 10 games): side has nothing left to play for | dropped (gain within noise) | 0.19771 | 0.19435 | 0.20503 | -0.00009 | 0.00008 | -0.00003 | 0.00029 | coefficients {"beta": [0.0762, 0.1178], "delta": [-0.5]} |
| 5-factor | finishing_luck | Recent goals minus xG (finishing / goalkeeping over-performance) | dropped | 0.19773 | 0.19459 | 0.20519 | 0.00015 | 0.00033 | 0.00012 | 0.00031 | coefficients {"beta": [-0.013, 0.0367], "delta": []} |
| 5-factor | penalty_skill | Penalties won per game over the last 38 games | dropped | 0.19767 | 0.19460 | 0.20495 | 0.00016 | 0.00034 | -0.00012 | 0.00010 | coefficients {"beta": [-0.1469], "delta": []} |
| 5-factor | red_card_rate | Red cards per game over the last 38 games (discipline) | dropped | 0.19773 | 0.19454 | 0.20507 | 0.00011 | 0.00020 | 0.00000 | 0.00011 | coefficients {"beta": [0.2115, 0.0817], "delta": []} |
| 5-factor | set_pieces | Corner differential over the last 19 games (set-piece proxy) | dropped | 0.19772 | 0.19444 | 0.20506 | 0.00000 | 0.00002 | -0.00001 | 0.00001 | coefficients {"beta": [-0.0012, -0.0015], "delta": []} |
| 5-factor | form | xG difference over the last 5 games (form beyond long-term rating) | dropped (gain within noise) | 0.19761 | 0.19414 | 0.20495 | -0.00030 | 0.00007 | -0.00011 | 0.00020 | coefficients {"beta": [0.0258, 0.0059], "delta": []} |
| 5-factor | lineup_strength | Starting-XI attacking value vs the team's norm (absences, signings) | dropped | 0.19773 | 0.18566 | 0.20689 | 0.00030 | 0.00226 | 0.00183 | 0.00345 | coefficients [0.1402, -0.4028] |

## Earlier full run (superseded keep rule: any RPS gain on both test periods)

Kept six factors under the old rule (promoted_early, manager_change, derby, motivation, set_pieces, form); all six were later shown to be within noise. Kept here for the record (factor coefficients shown cumulatively).

```
[2-compare] poisson                            TUNE=0.19897 TEST_A=0.19987 TEST_B=0.20593
[2-compare] dixon_coles                        TUNE=0.19913 TEST_A=0.19986 TEST_B=0.20586
[2-compare] xg                                 TUNE=0.19834 TEST_A=0.19793 TEST_B=0.20238
[2-compare] xg_goals_mix                       TUNE=0.19812 TEST_A=0.19749 TEST_B=0.20243
[2-compare] market                             TUNE=0.19786 TEST_A=0.19442 TEST_B=0.20503
[2-compare] elo                                TUNE=0.20059 TEST_A=0.19819 TEST_B=0.20727
[2-compare] closing_market                     TUNE=0.19586 TEST_A=0.18875 TEST_B=0.20082
[3-blend] best single model (market)         TUNE=0.19786 TEST_A=0.19442 TEST_B=0.20503  baseline
[3-blend] xg_goals_mix+market                TUNE=0.19712 TEST_A=0.19513 TEST_B=0.20338  dropped
[3-blend] xg_goals_mix+market+elo            TUNE=0.19712 TEST_A=0.19513 TEST_B=0.20338  dropped
[3-blend] xg+dixon_coles+market              TUNE=0.19713 TEST_A=0.19524 TEST_B=0.20346  dropped
[3-blend] xg+market+elo                      TUNE=0.19716 TEST_A=0.19517 TEST_B=0.20327  dropped
[3-blend] xg_goals_mix+dixon_coles+market+elo TUNE=0.19712 TEST_A=0.19513 TEST_B=0.20338  dropped
[4-factor] draw_bias                          TUNE=0.19768 TEST_A=0.19446 TEST_B=0.20553  dropped {"beta": [], "delta": [-0.1]}
[4-factor] early_season                       TUNE=0.19773 TEST_A=0.19445 TEST_B=0.20509  dropped {"beta": [-0.0077], "delta": []}
[4-factor] promoted_early                     TUNE=0.19736 TEST_A=0.19402 TEST_B=0.20487  KEPT {"beta": [-0.0397, 0.2121], "delta": []}
[4-factor] rest_days                          TUNE=0.19692 TEST_A=0.19286 TEST_B=0.20652  dropped {"beta": [-0.0588, 0.194, 0.0474, -0.1401], "delta": []}
[4-factor] rest_diff                          TUNE=0.19734 TEST_A=0.19404 TEST_B=0.20483  dropped {"beta": [-0.0406, 0.2122, 0.0017], "delta": []}
[4-factor] euro_congestion                    TUNE=0.19744 TEST_A=0.19401 TEST_B=0.20530  dropped {"beta": [-0.0405, 0.2096, 0.0222, -0.0705, -0.0106], "delta": []}
[4-factor] manager_change                     TUNE=0.19742 TEST_A=0.19398 TEST_B=0.20486  KEPT {"beta": [-0.0273, 0.2271, -0.0243, -0.0201], "delta": []}
[4-factor] derby                              TUNE=0.19740 TEST_A=0.19395 TEST_B=0.20483  KEPT {"beta": [-0.0291, 0.2264, -0.0225, -0.0183, -0.0218], "delta": [0.05]}
[4-factor] motivation                         TUNE=0.19740 TEST_A=0.19385 TEST_B=0.20479  KEPT {"beta": [-0.0121, 0.2378, -0.0267, -0.0217, -0.0235, 0.0828, 0.1248], "delta": [0.05, -0.5]}
[4-factor] finishing_luck                     TUNE=0.19742 TEST_A=0.19401 TEST_B=0.20493  dropped {"beta": [-0.0123, 0.2366, -0.0269, -0.0242, -0.0229, 0.0836, 0.125, -0.0078, 0.0376], "delta": [0.05, -0.5]}
[4-factor] penalty_skill                      TUNE=0.19736 TEST_A=0.19398 TEST_B=0.20467  dropped {"beta": [-0.0147, 0.2367, -0.0286, -0.0211, -0.0218, 0.0793, 0.1272, -0.1475], "delta": [0.05, -0.5]}
[4-factor] red_card_rate                      TUNE=0.19742 TEST_A=0.19398 TEST_B=0.20478  dropped {"beta": [-0.0122, 0.2385, -0.0296, -0.0213, -0.0224, 0.0811, 0.1253, 0.2326, 0.0513], "delta": [0.05, -0.5]}
[4-factor] set_pieces                         TUNE=0.19747 TEST_A=0.19382 TEST_B=0.20469  KEPT {"beta": [-0.0166, 0.2396, -0.0271, -0.0199, -0.0228, 0.0804, 0.1277, -0.0017, 0.0014], "delta": [0.05, -0.5]}
[4-factor] form                               TUNE=0.19739 TEST_A=0.19331 TEST_B=0.20432  KEPT {"beta": [-0.016, 0.252, -0.0227, -0.02, -0.0286, 0.0872, 0.1294, -0.0115, -0.0017, 0.0483, 0.0153], "delta": [0.05, -0.5]}
[4-factor] lineup_strength                    TEST_A(23-24)=0.18362 TEST_B=0.20566  dropped reference {"TEST_A(23-24)": 0.18337, "TEST_B": 0.20432}; beta=[0.1278, -0.3751]
```
