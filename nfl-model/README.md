# NFL weekly predictor

Each week this produces three things:

- **game tips with win %**
- **power rankings**
- **season projections:** playoff, division and #1-seed odds

It's a rebuild of the original `nfl_power_rankings` workbook. Every number was tested walk-forward on 15 seasons of real data: each prediction uses only games played before it.

**Bottom line:**

- It picks winners better than the original model, by about 2 percentage points on seasons it was never tuned on.
- **It does not beat the Vegas closing line.** The tip it gives (the line plus two small tested corrections) ties the line. After more than 130 tested ideas, nothing beat it.

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

**Options:**

- `--week 10` picks a specific week.
- `--season 2026` picks the season.
- `--no-fetch` skips the download.
- `--sims 50000` sets the number of season simulations.

## What the outputs mean

`output/<season>_wk<NN>.md` is the full weekly report:

| Section | What it shows |
|---|---|
| **Tips** | **TIP** and its **Win %**: the betting line plus small corrections for special teams and market drift. It's the most accurate option, and it ties the line. **Model only** is the model's pick without seeing the line. The section also lists the starting QBs assumed. |
| **Biggest games** | The games whose result swings the teams' playoff chances most |
| **Power rankings** | **Power**: points better than an average team on a neutral field, with this week's QB. Also offence and defence rank, expected wins and **luck** (wins minus expected), strength of schedule played and still to play (rank 1 = hardest), the 4-week trend and the QB adjustment. |
| **Season projections** | Projected wins and likely range, and chances to win the division, make the playoffs and get the #1 seed, from 20,000 simulations |
| **Strength of schedule** | Whose record an easy or hard schedule has flattered or hurt, in wins, and the hardest and easiest schedules left |
| **Rest and travel to come** | For information only: tested, with no measurable effect |

There are also two CSV files:

- `_tips.csv`: the tips table, with margins
- `_teams.csv`: every team stat and projection

## Results, all rounds

**Holdout seasons 2020–25** (1,615 games), never used to choose anything. "ATS" is the record against the closing spread; 52.4% is break-even at −110.

| | Tips right | Error (RMSE, pts) | ATS | Log-loss |
|---|---|---|---|---|
| Original workbook model (re-implemented) | 63.1% | 13.19 | 51.4% | 0.641 |
| After round 1 | 65.2% | 12.82 | 50.2% | 0.622 |
| After round 2: **Model only** | 65.3% | 12.77 | 50.2% | 0.619 |
| **TIP: adjusted line** (round 2) | **66.8%** | **12.62** | 52.3% | **0.607** |
| Vegas closing line | 66.8% | 12.66 | — | 0.608 |

**Live 2026, Weeks 1–8** (121 games, never used for anything):

| | Tips right | Error (pts) |
|---|---|---|
| Original | 63.3% | 12.20 |
| Model only | 65.8% | 12.32 |
| TIP | 65.8% | 12.20 |
| Line | 65.8% | 12.18 |

**How sure we can be** (resampling the holdout weeks, 95% intervals):

- The gain from the original to the new model is real: error 0.37 points lower, tips right 2.1 percentage points higher.
- The TIP against the line is no real difference: error 0.03 points lower (−0.07 to +0.00), tips right +0.1 percentage points (−0.2 to +0.4).
- Model only against the line: **the line is better**.

**Power rankings** (round 3). Accuracy here means: of all remaining games, the share won by the higher-ranked team, using the ranking published before each of Weeks 2–17.

| Ranking | Development 2012–19 | Holdout 2020–25 | Moves per week |
|---|---|---|---|
| **Power score (used)** | **63.1%** | 62.7% | 2.1 places |
| nfelo Elo | 62.3% | **63.2%** | 2.2 |
| Original workbook score | 61.7% | 61.8% | 2.0 |
| Win–loss record | 59.1% | 60.0% | 3.0 |

Nothing beat the current power score on both periods, so it stays. Full table: `results/round3_rankings.md`.

**Season simulation** (round 3). Simulated from before Weeks 1, 5, 9 and 13 of every season:

- **Playoff chances match reality.** Teams given 40–60% made the playoffs 49% of the time, and teams given 80–95% made it 85%.
- **Accuracy (Brier score).** Playoff calls scored 0.16 on holdout, against 0.25 for a no-information guess. Lower is better.
- **Win totals:** off by 1.7 wins on average, 2.3 from Week 1 and 1.1 from Week 13.

Full results: `results/round3_season.md`.

**Luck.** A team's expected wins (the sum of the model's pre-game win chances) predicted its rest-of-season win % better than its actual record did: error 0.22 against 0.26. Pythagorean win % (from points scored and allowed) was also better than the record.

## What was tested (over 130 ideas in 3 rounds)

The rules were the same every time:

- real data only
- walk-forward testing
- a change is **kept only if it improves both** the development seasons (2012–19) and the holdout seasons (2020–25)

Every result is logged.

| Round | Kept | Tested and dropped | Full log |
|---|---|---|---|
| 1 | Market rating from past lines; results rating; **starting-QB value**; EPA split into offence and defence | Rest, byes, short weeks, travel, time zones, body clock, weather, divisional games, home-field variants, recent form, early-season tweaks, success rate, injuries | `results/factors.csv` |
| 2 | Special teams; nfelo forecast; 4th-down aggressiveness. **TIP** = line + special teams + market drift | Player value by position (offensive line, receivers, pass rush, secondary); 8 EPA variants; pace, pass rate over expected, no-huddle, coaching changes; penalties; luck measures; gradient boosting (overfit every time); 30+ "where the line is wrong" situations (big favourites, prime time, after a QB change, …) | `results/round2_log.csv`, `results/round2_table.md` |
| 3 | Season-simulation uncertainty (SD 4 pts) | Other ranking methods; Denver altitude; team-specific home field; referees; grass/turf; moneyline-based, recalibrated and total-scaled win % | `results/round3_*.md` |

The remaining ideas, ranked by value against effort, are in [`IDEAS.md`](IDEAS.md).

## How it works

- **Ratings (before every week):** three ridge-regression ratings, each with time decay that carries across seasons, so Week 1 starts from last season:
  - **market:** from earlier closing lines
  - **results:** damped point margins
  - **EPA:** offence and defence per play, opponent-adjusted
- **Adjustments on top:** the starting QB's value against the team's recent starters, special teams, 4th-down aggressiveness and nfelo's QB-adjusted Elo.
- **Weights:** fitted before each season using only earlier seasons.
- **Win %:** a normal curve around the predicted margin, with SD about 13 points.

| Folder | Contents |
|---|---|
| `weekly.py` | The weekly command |
| `nflmodel/` | The library: data download (`fetch_data.py`, `fetch_extra.py`), ratings, features, season simulation, views |
| `research/` | Everything behind the results: `baseline.py` (original model), `tune.py`, `factors_round1.py`, `factors_round2.py`, `round3_*.py`, `report.py` |
| `config/model.json` | The settings and features the weekly run uses |
| `data/` | Your hand-edited inputs: `qb_overrides.csv`, plus your workbook's 2026 picks for comparison |
| `results/` | Research outputs: `report.md` (main before-vs-after report), factor logs, significance tests |
| `output/` | Weekly reports (2026 Week 9 included as an example) |
| `cache/` | Downloads and rebuilt tables, created automatically and git-ignored |

To re-run the research after the cache exists:

```bash
python3 research/report.py
python3 research/round3_rankings.py
python3 research/round3_season.py
```

## Data sources (all free, all real)

| Data | Source |
|---|---|
| Scores, closing spreads and moneylines, schedules, rest, roof, weather, starting QBs, coaches (2006–) | nflverse `games.csv`: https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv. Its line matched the 5-source closing line in your workbook exactly in 81% of 2026 games (average difference 0.16 pts). |
| Play-by-play with EPA, about 1M plays (2006–) | nflverse: `github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_<season>.parquet` |
| Injury reports (2013–), snap counts (2012–), player IDs | nflverse releases: `injuries`, `snap_counts`, `players` |
| QB-adjusted Elo, in FiveThirtyEight's format | nfelo: https://raw.githubusercontent.com/greerreNFL/nfeloqb/main/qb_elos.csv |
| Stadium locations; 8 international-venue corrections | Hand-entered from public facts (`nflmodel/common.py`) |

**Couldn't get:**

- FTN DVOA (paywalled)
- historical opening lines and weather forecasts
- FiveThirtyEight's site, ESPN, Open-Meteo and Pro-Football-Reference, all blocked from this environment's network

## Limitations

- **No edge against the market.** It doesn't beat the closing line on tips, and it has no betting edge against the spread.
- **The backtest uses the actual starting QB.** That's normally known before kickoff, so the backtest is slightly flattering. In live use, keep `qb_overrides.csv` up to date.
- **nfelo is a third-party file.** If it isn't updated for a week, the self-test warns you and that input is set to 0.
- **The season simulation simplifies tiebreakers** (wins, then division record, then conference record) and assumes today's starting QBs play the rest of the season.
- **Only regular-season games are predicted and scored.** There's no totals (over/under) model.
- **Small samples.** 2026 has 121 games; differences of a few percent there are noise.
- **The research reused the same holdout period.** It decided keep-or-drop in all three rounds, so 2026 is the only fully untouched check.
- **The original workbook is untouched.** This is a separate Python model.
