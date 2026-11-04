# EPL prediction model

A Premier League forecasting model built from real data only. It gives match-by-match expected goals, full
scoreline grids, home/draw/away, over/under 2.5 and both-teams-to-score probabilities, power rankings, a luck
table, strength of schedule and 20,000-run season simulations. It is evaluated honestly against the
bookmakers' closing odds.

**Bottom line: the model does not beat the bookmakers' closing odds.** On both test periods the margin-free
closing market is more accurate. What the model offers is transparency: ratings, xG, scorelines and season odds
that you can inspect, on a forecast that stays close to the market.

## How to run

```bash
pip install -r requirements.txt     # numpy, pandas, xlsxwriter, openpyxl
python3 weekly.py                   # refresh data, self-test, predict the next gameweek (~1-2 min)
```

`weekly.py` re-downloads everything it needs into `cache/` (git-ignored), runs a self-test that ends with
`SELF-TEST PASSED` or `SELF-TEST FAILED`, then writes:

| Output | What it is |
|---|---|
| `output/EPL_Model.xlsx` | The workbook (sheets described below) |
| `output/weekly_report.md` | Readable report: each match's xG, most likely score, top-5 scores, H/D/A, power rankings, season odds, luck, accuracy so far, self-test |
| `output/predictions.csv` | This gameweek's numbers, including the full 0-6+ scoreline grid per match |
| `reports/DATA_CHECKS.md` | Cross-source checks of scores, odds, red cards and xG |

`python3 weekly.py --offline` reuses the cache. `python3 backtest.py` re-runs the full model selection
(about 30 minutes; `--reuse-tuning` skips the tuning stage, `--quick` is a 3-minute smoke test). It rewrites
`config/model_spec.json`, which `weekly.py` uses, plus `reports/BACKTEST.md` and `reports/EXPERIMENTS.md`, and it
appends to `reports/experiment_log.csv`.

### Workbook sheets

- **Dashboard**: this gameweek's matches with expected goals, most likely score and its %, H/D/A, over 2.5, BTTS,
  top-5 scores, recent form and notes (derbies, promoted sides, short rest, European weeks, nothing to play for),
  plus a scoreline grid (0 to 6+) for every match.
- **Power Rankings**: 1-20 by *net rating* (expected goal difference per game against an average schedule),
  with movement since last week, attack and defence ratings, and actual xG difference per game.
- **Ranking History**: rank before each gameweek, with a trend chart.
- **Attack & Defence**: ratings with a scatter chart.
- **Expected Points & Luck**: points vs expected points from each match's xG, plus finishing (goals − xG) and
  goalkeeping (xG against − goals against).
- **Fixture Difficulty**: next five opponents with the model's expected points for each (green = easier), and
  strength of schedule played and remaining.
- **Season Projections**: projected points (10th–90th percentile), title, top 4, top 5, top 7 and relegation
  odds, with charts.
- **Model vs Market**: walk-forward accuracy against closing odds, and this season so far.
- **Factor Tests**: every blend, structural change and factor tested, with its RPS change on each test period,
  the noise bound and the decision. Also shows how far "luck" measures persist from season to season.
- **About**: method, sources, limitations.

## How the model was built and tested

Every prediction is **walk-forward**: the model is refitted before each match date using only matches played
earlier. The self-test proves this by scrambling all later results and checking that predictions do not change.

- **Seasons:** 2015-16 to 2017-18 are burn-in. Tuning uses 2018-19 to 2021-22. **Test A** is 2022-23 and
  2023-24. **Test B** is 2024-25 and 2025-26. Live is 2026-27.
- **Keep rule:** a change is kept only if its gain is clearly bigger than noise on *both* test periods. A paired
  bootstrap over match dates (2,000 resamples) must put the one-sided 95% upper bound of the RPS change below
  zero in each period. All parameters and coefficients are fitted on the tuning seasons only. Every test, kept
  or dropped, is in `reports/EXPERIMENTS.md`.

Models built and compared (all with attack and defence ratings that decay over time):

| Model | RPS tuning | RPS Test A | RPS Test B |
|---|---|---|---|
| Poisson (goals) | 0.1990 | 0.1999 | 0.2059 |
| Dixon-Coles (goals, low-score/draw correction) | 0.1991 | 0.1999 | 0.2059 |
| xG model | 0.1983 | 0.1979 | 0.2024 |
| 70% xG / 30% goals | 0.1981 | 0.1975 | 0.2024 |
| Elo (goal-difference) | 0.2006 | 0.1982 | 0.2073 |
| Market-based rating (fitted to past closing odds) | **0.1979** | **0.1944** | 0.2050 |
| **Closing market (benchmark)** | **0.1959** | **0.1888** | **0.2008** |

**Chosen model:** the market-based rating. It was best on the tuning seasons. Its ratings come from the
expected goals implied by past closing 1X2 and over/under odds, with a 90-day half-life and a Dixon-Coles
draw correction. Blending it with the xG model helped Test B (−0.0017 RPS) but hurt Test A (+0.0007), so no
blend passed the rule. On Test B alone the xG model was better.

No factor passed the significance rule:

- Promoted teams, form, manager changes, derbies and motivation improved both test periods slightly, but
  within noise.
- Rest days helped Test A and hurt Test B.
- European congestion, finishing luck, penalty skill, red-card rate, set pieces (corners as a proxy), lineup
  strength, draw bias and early-season shrinkage did not help.
- Structural tests did not help either: a separate no-crowd home advantage for 2020-21, a prior for promoted
  teams, down-weighting red-card matches, and treating penalties as luck (non-penalty xG). The market had
  already priced most of these in.

Under an earlier, looser rule (any gain on both periods) six factors were kept. They are listed in the log.

**Luck or skill** (correlation of each team measure with the same measure next season, 2019-20 onward):

| Measure | Correlation |
|---|---|
| xG difference per game | 0.67 |
| Goal difference per game | 0.66 |
| Penalties won per game | 0.20 |
| Finishing (goals − xG) | 0.11 |
| Red cards received per game | 0.01 |

Red cards and finishing behave mostly like luck. xG difference is the most repeatable measure.

## Results vs the bookmakers

Closing odds use Pinnacle where available, otherwise Betfair Exchange, otherwise the market average. The margin
is removed with the power method.

| Period | Forecaster | RPS | Log loss | Correct result | Exact score | Over/under 2.5 log loss |
|---|---|---|---|---|---|---|
| Test A 2022-24 | Model | 0.1944 | 0.946 | 55.8% | 12.4% | 0.665 |
| Test A 2022-24 | Closing market | **0.1888** | **0.930** | 57.2% | 11.6% | **0.656** |
| Test B 2024-26 | Model | 0.2051 | 1.004 | 50.0% | 12.8% | **0.678** |
| Test B 2024-26 | Closing market | **0.2008** | **0.991** | 52.2% | 13.8% | 0.680 |
| Live 2026-27 (90 matches) | Model | 0.2016 | 1.006 | 48.9% | 15.6% | 0.692 |
| Live 2026-27 (90 matches) | Closing market | 0.2059 | 1.019 | 47.8% | 13.3% | 0.695 |

- **Overall:** the model loses to the closing market on both test periods. The live-season edge is 90 matches
  and is not evidence of anything.
- **Calibration:** good. On the test periods, events given 40-50% happened 41% of the time and those given
  60-70% happened 62% of the time.
- **Draws:** the model predicts 22-23% against 22-26% actual. It slightly under-predicts draws in 2024-26.
- **Stage of season:** the gap to the market is smallest in rounds 6-12 and largest in rounds 13-19 and 30-38.
- **Season simulation:** calibrated on past seasons from rounds 1, 10, 20 and 30, using only information
  available at each point. Rating uncertainty (sigma 0.15) was chosen on the tuning seasons. On test seasons,
  events given 50-75% happened 64% of the time. The projected-points error is 11.4 points pre-season, 4.9
  from round 20 and 3.6 from round 30.

Full tables are in `reports/BACKTEST.md`.

## Data sources

The machine that built this could not reach football-data.co.uk, Understat, FBref or the FPL API (blocked by
its network policy). It used public GitHub mirrors of the same files instead. `weekly.py` tries the original
site first and falls back to the mirror.

| Data | Source | Used for |
|---|---|---|
| Results, shots, cards, corners, referees, closing 1X2, over/under 2.5 and Asian handicap odds (2015-16 to now); match xG 2026-27 | [football-data.co.uk](https://www.football-data.co.uk/englandm.php) `mmz4281/{season}/E0.csv`, via mirror [ValentinMartine/football_predictions](https://github.com/ValentinMartine/football_predictions) (`data/raw/{season}_E0.csv`, updated daily) | Core results and odds |
| Second copy of football-data E0 files 2019-26 | [Mentat-Uran/ScoutFootball_for_World_Cup](https://github.com/Mentat-Uran/ScoutFootball_for_World_Cup) | Checking the mirror's integrity (0 differing odds cells) |
| Understat xG (team-match 2019-22, player-match 2021-25, summed to teams); Opta xG, minutes, starts, red cards and penalties from official Fantasy Premier League data; 2026-27 fixture list | [vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League) | xG, lineups, schedule |
| Results 2000-27, UEFA fixtures | [openfootball/england](https://github.com/openfootball/england), [openfootball/champions-league](https://github.com/openfootball/champions-league) | Score cross-check, European congestion |
| Bet365 / average pre-match odds and scores compiled from football-data, plus ClubElo | [xgabora/Club-Football-Match-Data-2000-2025](https://github.com/xgabora/Club-Football-Match-Data-2000-2025) | Odds and score cross-check |
| Manager spells (to Aug 2026) | [rohanhs568/next_manager_sacked](https://github.com/rohanhs568/next_manager_sacked) `labelled_spells.csv` | Manager-change factor |
| Points deductions (Everton −8, Nottingham Forest −4 in 2023-24) | Premier League statements, Nov 2023 – Apr 2024 | `config/points_adjustments.csv` |

**Cross-checks** (in `reports/DATA_CHECKS.md`):

- Scores agree in every match compared across football-data, the official FPL fixtures and openfootball.
- Closing odds agree in every cell between the two football-data mirrors.
- Pre-match odds agree with the xgabora compilation.
- Red cards differ from FPL in 0.5% of matches.
- Understat and Opta xG correlate at 0.94, with Understat running about 8% higher. The model rescales each
  provider to goal level using past data only.

## Limitations

- **Closing odds:** checked only against a second copy of the same feed. No independent closing-odds source was
  reachable.
- **Player data:** lags. The vaastav FPL mirror ran to gameweek 6 at build time. There is no live injury or
  lineup feed, so lineup effects cannot be used for upcoming games.
- **Not covered:** shot-level xG and set-piece xG; domestic cup fixtures; UEFA fixtures for 2026-27; manager
  changes after Aug 2026.
- **xG providers:** Understat until 2024-25, Opta (FPL and football-data) after.
- **Deductions:** points deductions are applied from the start of the season. Only those listed in the config
  file are included.
- **Mirrors:** if a mirror stops updating, `weekly.py` fails its data checks or uses stale data. It reports the
  last result date in every output.

Further ideas, ranked by value vs effort, are in `IDEAS.md`.

## Layout

```
weekly.py            weekly routine (one command)
backtest.py          full model selection and evaluation
src/eplmodel/        data, checks, features, models, adjust, evaluate, experiments,
                     predictor, simulate, season, report, excel, selftest
config/              team-name map, derbies, London clubs, points deductions, chosen model spec
output/              workbook, weekly report, predictions CSV (regenerated weekly)
reports/             backtest results, experiment log, data checks
cache/               downloaded raw data (git-ignored, re-downloaded by weekly.py)
```
