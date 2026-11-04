# NFL weekly predictor

Each week this produces four things:

- **game tips with win %**
- **power rankings**
- **season projections:** playoff, division and #1-seed odds
- **a polished Excel workbook** (`output/NFL_Model_2026.xlsx`)

It's a rebuild of the original `nfl_power_rankings` workbook. Every number was tested walk-forward on 15 seasons of real data: each prediction uses only games played before it.

**Bottom line:**

- It picks winners better than the original model, by about 2 percentage points on seasons it was never tuned on.
- **It does not beat the Vegas closing line.** The tip it gives (the line plus two small tested corrections) ties the line. After more than 160 tested ideas over four rounds, nothing beat it.

## Run it each week

```bash
cd nfl-model
pip install -r requirements.txt    # first time only
python3 weekly.py
```

1. **Check the starting QBs first.** nflverse names a game's starting QB only after the game is played, so for upcoming games the model assumes last week's starter. If a team will start someone else, add a row to `data/qb_overrides.csv` such as `2026,10,BAL,<QB name>`, spelling the name as nflverse does. A starter change can be worth 3–7 points.
2. **Run it close to kickoff.** The line and the injury reports are most complete then.
3. **How long it takes:**
   - **First run:** downloads about 20 seasons of data into `cache/` (git-ignored), about 5 minutes.
   - **Later runs:** refresh only this season, about 1 minute.
4. **It checks itself.** It ends with `SELF-TEST PASSED`, or stops with `SELF-TEST FAILED` and the reason. The checks cover:
   - every game predicted
   - probabilities sensible
   - all 32 teams rated
   - simulation totals adding up: 14 playoff spots, 8 division winners, 2 #1 seeds
   - data up to date
   - the Excel workbook written

**Options:**

- `--week 10` picks a specific week.
- `--season 2026` picks the season.
- `--no-fetch` skips the download.
- `--sims 50000` sets the number of season simulations.

## What the outputs mean

**`output/NFL_Model_2026.xlsx`** is rebuilt every week. It uses the original workbook's navy-and-gold theme, has frozen headers and colour scales, and has no tipping or betting tracking.

| Sheet | What it shows |
|---|---|
| **Dashboard** | This week's games with the predicted winner and win %; the top 5 risers and fallers in the power rankings; playoff-race highlights (the biggest games, the #1-seed race, bubble teams) |
| **Power Rankings** | 1–32 with movement and the parts of the power score: market, results + Elo, EPA offence and defence, special teams, 4th-down, QB. Also offence and defence ranks, expected wins, luck, strength of schedule and trend. |
| **Ranking History** | Rank before every week, plus a chart of the current top 8 over the season |
| **Team Efficiency** | EPA per play (raw and opponent-adjusted), success rate, pass/rush/early-down EPA, pass rate over expected, pace, 4th-down go rate, special teams, penalties, turnovers, big plays, field-goal luck, win-probability added, blocked kicks. Includes an offence-vs-defence scatter. |
| **QBs** | EPA per dropback, completion % over expected, completion %, yards per attempt, TDs and INTs, INT rate, and the **adjusted INT rate**: interception-worthy throws per attempt from FTN charting, which strips out tipped and dropped picks. Also lucky or unlucky INTs, drops by receivers, sack rate. |
| **Luck & Expected Wins** | Wins vs expected wins (the model's pre-game chances), Pythagorean wins, fumble luck, field-goal luck, return TDs, turnover margin. Includes an expected-vs-actual scatter. |
| **Strength of Schedule** | Opponent strength played and remaining, adjusted for each opponent's QB and home/away; schedule effect in wins; rest and travel still to come |
| **Season Projections** | Projected wins with likely range, and division, playoff and #1-seed odds, from 20,000 simulations. Includes a playoff-odds chart. |
| **About** | How to read it, and this run's self-test |

**`output/<season>_wk<NN>.md`** has the same content as a plain-text report.

There are also two CSV files:

- `_tips.csv`: the tips table, with margins
- `_teams.csv`: every team stat and projection

**TIP** is the betting line plus small corrections for special teams and market drift. It's the most accurate option, and it ties the line. **Model only** is the model's pick without seeing the line.

## Results, all rounds

**Holdout seasons 2020–25** (1,615 games), never used to choose anything. "ATS" is the record against the closing spread; 52.4% is break-even at −110.

| | Tips right | Error (RMSE, pts) | ATS | Log-loss |
|---|---|---|---|---|
| Original workbook model (re-implemented) | 63.1% | 13.19 | 51.4% | 0.641 |
| After round 1 | 65.0% | 12.83 | 50.0% | 0.623 |
| After round 2: **Model only** | 65.4% | 12.78 | 50.5% | 0.620 |
| **TIP: adjusted line** | **66.8%** | **12.62** | 52.3% | **0.607** |
| Vegas closing line | 66.8% | 12.66 | — | 0.608 |

**Live 2026, Weeks 1–8** (121 games, never used for anything):

| | Tips right | Error (pts) |
|---|---|---|
| Original | 63.3% | 12.20 |
| Model only | 65.0% | 12.20 |
| TIP | 65.8% | 12.20 |
| Line | 65.8% | 12.18 |

**How sure we can be** (resampling the holdout weeks 2,000 times, 95% intervals; `results/significance*.txt`):

- **New model vs the original:** a real gain. Error is 0.36 points lower (−0.52 to −0.20) and tips right 1.9 percentage points higher (+0.2 to +3.6).
- **TIP vs the line:** no real difference. Error is 0.03 points lower (−0.07 to +0.00) and tips right +0.1 percentage points (−0.2 to +0.4).
- **Model only vs the line:** **the line is better**, by 0.13 points of error and 1.4 percentage points of tips.

**Part of the season** (round 4, `results/round4_early.md`). Weeks 1–4 are weaker for every method, including the line.

| Holdout 2020–25 | Weeks 1–4 | Weeks 5–8 | Weeks 9–18 |
|---|---|---|---|
| Model only | 63.9% | 63.7% | 66.7% |
| TIP | 63.4% | 66.0% | 68.6% |
| Line | 63.4% | 66.0% | 68.5% |
| Power-ranking accuracy (published before Weeks 2–4 / 5–8 / 9–17) | 61.0% | 63.2% | 63.8% |

The model is no weaker than the line early. On holdout it was slightly *better* in Weeks 1–4 (error 12.48 vs 12.59), but slightly worse in that window on 2012–19.

Seven early-season fixes were tested, and none passed on both periods:

- different weights for nfelo, the QB value, the results rating, or the market and nfelo together in early weeks
- separate weights fitted only on Weeks 1–4
- less carry-over of last season's market rating

**Power rankings** (round 3). Accuracy here means: of all remaining games, the share won by the higher-ranked team, using the ranking published before each of Weeks 2–17.

| Ranking | Development 2012–19 | Holdout 2020–25 | Moves per week |
|---|---|---|---|
| **Power score (used)** | **63.1%** | 62.7% | 2.1 places |
| nfelo Elo | 62.3% | **63.2%** | 2.2 |
| Original workbook score | 61.7% | 61.8% | 2.0 |
| Win–loss record | 59.1% | 60.0% | 3.0 |

**Season simulation** (round 3, `results/round3_season.md`):

- **Playoff chances match reality.** Teams given 40–60% made the playoffs 48% of the time, and teams given 80–95% made it 85%.
- **Accuracy (Brier score).** Playoff calls scored 0.16 on holdout, against 0.25 for a no-information guess. Lower is better.
- **Win totals:** off by 1.7 wins on average.

**Luck.** Expected wins predicted a team's rest-of-season win % better than its actual record did: error 0.22 against 0.26.

## What was tested (over 160 ideas in 4 rounds)

The rules were the same every time:

- real data only
- walk-forward testing
- a change is **kept only if it improves both** the development seasons (2012–19) and the holdout seasons (2020–25)

Every result is logged in `results/`.

| Round | Kept | Tested and dropped | Log |
|---|---|---|---|
| 1 | Market rating from past lines; results rating; **starting-QB value**; EPA split into offence and defence | Rest, byes, travel, time zones, weather, divisional games, home-field variants, recent form, early-season tweaks, success rate, injuries | `factors.csv` |
| 2 | Special teams; nfelo forecast; 4th-down aggressiveness. **TIP** = line + special teams + market drift | Player value by position; 8 EPA variants; play-calling and coaching; penalties; luck; gradient boosting (overfit every time); 30+ "where the line is wrong" situations | `round2_log.csv`, `round2_table.md` |
| 3 | Season-simulation uncertainty (SD 4 pts) | Other ranking methods; Denver altitude; team home field; referees; grass/turf; alternative win-% methods | `round3_*.md` |
| 4 | None. The noise measures are shown as stats in the workbook instead. | **Penalties:** EPA without penalty plays, penalty EPA. **Luck:** results without return TDs or field-goal luck, special teams without field-goal luck, blocked kicks. **Play impact:** leverage-weighted EPA, win-probability added, big plays vs the rest, big-play dependence. **QB left the game:** those games down-weighted in the ratings. **FTN interception-worthy throws:** exploratory only, since the data starts in 2022. **Early-season fixes** (7). | `round4_noise.md`, `round4_early.md` |

Remaining ideas, ranked by value against effort: [`IDEAS.md`](IDEAS.md).

## Data audit (round 4, `results/audit_data.md`)

**Scores**

- 0 mismatches between nflverse and nfelo, a separately maintained source, across 5,552 games.
- 0 mismatches between nflverse and play-by-play final scores in sample seasons from 2008 to 2026.
- 0 mismatches between nflverse and your workbook for 2026.

**2026 lines vs your workbook's consensus close**

- **Spreads:** 81% exact, 93% within half a point.
- **Opposite favourites:** two near-pick'em games where the two sources disagree: Week 6 DAL@GB and Week 8 KC@DEN. nflverse's spread agrees with its own moneyline, so it's kept.

**Starting QBs: an error was found and fixed**

- **The error:** nflverse sometimes lists the QB who played most rather than the one who started, mostly in Week 17 rest games. Knowing that is hindsight.
- **The fix:** the model now uses the QB on each team's first dropback (players listed at QB only). This corrects 88 team-games.
- **Effect:** disagreement with nfelo fell from 76 games to 17. The results tables above already include the fix. It moved holdout results by at most 0.2 percentage points; on 2026, model-only tips went from 65.8% to 65.0% (one game).

**Player and team stats vs nflverse's official stats**

- Interceptions: 100% exact.
- Targets: 98–99% exact.
- Lost fumbles: 92–94% exact. The gaps are special-teams fumbles, which we include and the official offensive totals leave out.
- 2026 QB EPA per dropback vs your workbook: correlation 0.94.

**Reproducibility check**

`bash research/run_all.sh` re-runs all the research. Before the QB fix, it reproduced every committed result exactly, with three exceptions:

- the gradient-boosting rows, which vary slightly run to run, with verdicts unchanged
- one significance interval, from a one-off script now saved as `research/significance.py`, with the same estimate
- two round-3 rows that had depended on a file later overwritten, both still "hurt"

`round2_table.md` was hand-made; it's now generated by code.

## How it works

- **Ratings (before every week):** three ridge-regression ratings, each with time decay that carries across seasons:
  - **market:** from earlier closing lines
  - **results:** damped margins
  - **EPA:** offence and defence per play, opponent-adjusted
- **Adjustments on top:** the starting QB's value against the team's recent starters, special teams, 4th-down aggressiveness and nfelo's QB-adjusted Elo.
- **Weights:** fitted before each season using only earlier seasons.
- **Win %:** a normal curve around the predicted margin, with SD about 13 points.

| Folder | Contents |
|---|---|
| `weekly.py` | The weekly command |
| `nflmodel/` | The library: data download (`fetch_data.py`, `fetch_extra.py`, `fetch_noise.py`), ratings, features, season simulation, views, `workbook.py` (the Excel file) |
| `research/` | Everything behind the results. `run_all.sh` re-runs it all in about 15 minutes: `baseline.py`, `tune.py`, `factors_round1.py`, `factors_round2.py`, `significance.py`, `round3_*.py`, `audit_data.py`, `round4_*.py`, `report.py` |
| `config/model.json` | The settings and features the weekly run uses |
| `data/` | Hand-edited inputs (`qb_overrides.csv`) and tables exported from your original workbook for the audit |
| `results/` | Research outputs and logs |
| `output/` | Weekly reports and the Excel workbook |
| `cache/` | Downloads and rebuilt tables, created automatically and git-ignored |

## Data sources (all free, all real)

| Data | Source |
|---|---|
| Scores, closing spreads and moneylines, schedules, rest, roof, weather, coaches (2006–) | nflverse `games.csv`: https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv |
| Play-by-play with EPA, win probability and field-goal make probability, about 1M plays (2006–) | nflverse: `github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_<season>.parquet`. Starting QBs come from here: the first dropback by a listed QB. |
| Injury reports (2013–), snap counts (2012–), player IDs, official player and team stats (audit) | nflverse releases: `injuries`, `snap_counts`, `players`, `stats_player`, `stats_team` |
| FTN charting: interception-worthy throws, drops, catchable balls (2022–) | nflverse release `ftn_charting` |
| QB-adjusted Elo, with its own scores and starters | nfelo: https://raw.githubusercontent.com/greerreNFL/nfeloqb/main/qb_elos.csv |
| Stadium locations; 8 international-venue corrections | Hand-entered from public facts (`nflmodel/common.py`) |

**Couldn't get:**

- FTN DVOA (paywalled)
- historical opening lines and weather forecasts
- FiveThirtyEight's site, ESPN, Open-Meteo and Pro-Football-Reference, all blocked from this environment's network

## Limitations

- **No edge against the market.** It doesn't beat the closing line on tips, and it has no betting edge against the spread.
- **The upcoming week's starting QB is assumed.** It's last week's starter unless `qb_overrides.csv` says otherwise.
- **nfelo is a third-party file.** If it isn't updated for a week, the self-test warns you.
- **The season simulation simplifies tiebreakers** and assumes today's starting QBs play the rest of the season.
- **Only regular-season games are scored.** There's no totals model.
- **FTN-based stats start in 2022.** They're shown, but can't be tested under the two-period rule.
- **2026 is a small sample** (121 games).
- **The research reused the same holdout period.** It decided keep-or-drop in all four rounds, so 2026 is the only fully untouched check.
- **The original workbook is untouched.** The new workbook is generated from scratch each week.
