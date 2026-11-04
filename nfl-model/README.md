# NFL weekly predictor (rebuild of the NFL Power Rankings & Tips model)

Each week this predicts every NFL game, gives a win probability, and produces 1–32 power rankings. It was rebuilt from the original
`nfl_power_rankings` workbook model and tested on 15 seasons of real data, using only information available before each game.
Two rounds of research tested **108 factor variants and model types** (round 1: 24, round 2: 84).

**Bottom line:**

- **Better than your original model:** 65.3% of tips right vs 63.1%, and error of 12.77 vs 13.19 points, on seasons never used for tuning.
- **Nothing beats the Vegas closing line on tips right.** The best version, the line plus two small corrections, ties it at 66.8%. It changes the line's tip in only 7 of 1,610 holdout games.
- **Against the spread there is no reliable edge.** The best was 52.4%, exactly break-even at −110 and within what luck produces.
- **For tipping, use the `TIP (adjusted line)` column** in the weekly output. It is, in effect, the betting line.

---

## Run it each week

```bash
cd nfl-model
pip install -r requirements.txt
python3 weekly.py
```

That one command:

1. downloads this season's latest scores, lines, play-by-play and injury reports from nflverse, plus the latest nfelo QB-Elo file (about 1 minute)
2. rebuilds the ratings
3. writes three files to `output/`:
   - `output/<season>_wk<NN>.md`: readable tables of games and power rankings
   - `output/<season>_wk<NN>_predictions.csv`, with for each game:
     - **TIP (adjusted line)** and its win % (use this for tipping)
     - the model's own tip, win % and margin (made without seeing this week's line)
     - the current line and the model's edge against it
     - the expected starting QBs
   - `output/<season>_wk<NN>_power_rankings.csv`: power score (points better than an average team on a neutral field), split into market, results + Elo, EPA offence, EPA defence, special teams, 4th-down aggressiveness and this week's QB adjustment, plus last week's rank

Options:

- `--week 10` picks a specific week (the default is the first week with unplayed games).
- `--season 2026` picks the season.
- `--no-fetch` skips the download.

**Check the starting QBs before you run it.** nflverse records a game's starting QB only after the game is played. For upcoming games the model assumes each team's most recent starter. If someone else will start, add a row to `data/qb_overrides.csv` in the form `season,week,team,qb_name` (for example `2026,9,BAL,<QB name>`), spelling the name as nflverse does. A QB the data has never seen is treated as replacement level. This adjustment matters a lot: a starter change can be worth 3–7 points.

Run it close to kickoff. Earlier in the week the line isn't final yet, and the injury reports are less complete.

Rebuilding everything from scratch (only needed once, or to re-run the research):

```bash
python3 fetch_data.py    # nflverse 2006–now, about 2 minutes, about 430 MB raw (git-ignored)
python3 fetch_extra.py   # extra per-game tables from play-by-play + nfelo
python3 tune.py          # round 1: rating settings (development seasons only)
python3 factors.py       # round 1: factor tests
python3 factors2.py      # round 2: factor tests, machine learning, beat-the-line tests (about 40 min)
python3 report.py        # before-vs-after report -> results/report.md
```

---

## 1. How the original model worked, and what was wrong with it

**How it worked.** An Excel workbook, rebuilt by Python and recalculated in LibreOffice, combined these parts:

| Part | What it was |
|---|---|
| Market rating | Ridge regression on this season's betting lines (open/close midpoint), half-life 3 weeks |
| Efficiency rating | 75% opponent-adjusted EPA/play (garbage time removed) and 25% FTN DVOA |
| Results rating | Damped margins, minus 50% of fumble luck |
| Elo | K = 20 |
| Trend | Consistency and momentum |
| Hand-entered adjustments | QB absences, other injuries valued by player tier, eye-test tweaks, and "your ranking" blended in at 10% |

The two outputs combined these parts differently:

- **Power score:** 40% market, 40% efficiency, 5% results, 5% Elo and 10% trend.
- **Tips engine:** 50% market and 50% efficiency, plus:
  - 1.5 points home edge
  - 0.3 points per day of rest edge
  - 0.7 points for coming off a bye
  - 0.2 points per 1,000 miles travelled
  - 0.5 points body-clock penalty

  Win probability came from a normal curve with SD 13. In Week 1 the tip was simply the line.

**What was wrong or missing:**

1. **Tested on one season and tuned on the same games.** The backtest covered 89 games (2026 Weeks 3–8). The weights were chosen by grid search on those same 89 games (`tune/grid.py`), so the reported result was in-sample. The claimed 10.92 RMSE against 11.55 for the closing line was mostly noise plus overfitting. Rebuilt and run on 2009–2026 (4,552 games), the same engine gets **RMSE 13.54 against 13.10 for the line, and 64.4% of tips right against 66.6%**.
2. **It started from zero every season.** Week 1 just copied the betting line, and Weeks 2–4 rested on one to three games. There was no carry-over from last season.
3. **The weights were set by hand, not fitted.** Each part was rescaled to the market's spread and mixed at hand-picked percentages. Nothing checked how many points each part is really worth against actual margins.
4. **Several inputs can't be tested or repeated:**
   - DVOA comes from paywalled FTN and was typed in by hand for 2026 only.
   - Injuries and QB absences were valued by judgement.
   - The eye test and "your ranking" are opinion.
   - The Super Bowl simulation was pasted in by hand.

   None of these exist for past seasons, so their value can't be measured.
5. **The situational adjustments were never shown to work.** The rest, bye, travel and body-clock values were chosen on the same 89 games. Tested on 14 seasons (below), they add nothing.
6. **The win probabilities weren't calibrated.** The fixed 13-point SD was never checked against outcomes.
7. **It was fragile.** Week 8 was hard-coded (`nfldata/w8`, `data.py`'s week range), the schedule was typed into `data.py`, and helpers depended on missing files (`base5`, `base6`). It needed LibreOffice to calculate.


## 2. Data, all real and downloaded, with sources

| Data | Seasons | Source |
|---|---|---|
| Schedule, final scores, **closing spread**, total, moneylines, rest days, roof, temperature/wind, divisional flag, **starting QB**, head coaches | 2006–2026 | nflverse `games.csv`: https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv |
| Play-by-play with EPA, success, win probability, pass rate over expected, downs, field position, penalties, special teams, targets, sacks and QB hits (about 1M plays) | 2006–2026 | nflverse: `https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet` |
| Official injury reports (Out / Doubtful) | 2013–2026 | nflverse: `.../releases/download/injuries/injuries_{season}.csv` |
| Snap counts | 2012–2026 | nflverse / Pro-Football-Reference: `.../releases/download/snap_counts/snap_counts_{season}.csv` |
| Player ID map | — | nflverse: `.../releases/download/players/players.csv` |
| **nfelo QB-adjusted Elo** (538-style Elo, pre-game ratings and win probabilities, every game since 1920) | 2006–2026 | https://raw.githubusercontent.com/greerreNFL/nfeloqb/main/qb_elos.csv (public, free; the only usable non-nflverse source) |
| Weather where `games.csv` has none | 2006–2026 | Parsed from the NFL gamebook weather text inside the play-by-play |
| Stadium latitude/longitude and time zone | — | **Hand-entered** in `common.py` from public stadium locations (accurate to about 0.05°) |
| International venue corrections | 2025–26 | **Hand-entered** in `common.py` (`VENUE_FIX`). nflverse lists 8 international games (e.g. 2025 Week 1 KC–LAC in São Paulo) at the home team's US stadium. |
| Your workbook's actual 2026 picks | 2026 Weeks 1–8 | Your `modelpicks.json`, copied to `data/original_workbook_picks_2026.json` |

**How the lines were checked.** nflverse doesn't say which sportsbook or which moment its `spread_line` comes from. I compared it with the 5-source consensus closing line in your `base8.xlsx` for all 121 games of 2026 Weeks 1–8:

- It matched exactly in 81% of games.
- The average difference was 0.16 points.
- All 121 scores matched.

So I treat it as the closing line.

**Built from the downloads** (all committed in `data/`, with URLs and checksums in `manifest.json`):

- `team_games.csv` and `team_games_x.csv`: per-game team aggregates
- `qb_games.csv`: QB dropback EPA
- `player_weeks.csv`: targets and pressures per player
- `injury_out.csv`: players ruled out, with their snap share
- `nfelo.csv`

**What I couldn't get, or left out:**

- **FTN DVOA history:** paywalled. Not used.
- **Historical opening lines:** nflverse has one line per game, so line movement couldn't be tested. ("Market drift" below uses the gap between earlier weeks' lines and this week's line.)
- **Historical weather forecasts:** recorded game-day conditions were used instead.
- **Blocked by this environment's network policy:** FiveThirtyEight's own site, ESPN's API, Open-Meteo's weather archive and Pro-Football-Reference all refused the connection. FiveThirtyEight's GitHub data file was no longer at its old address. nfelo's file continues FiveThirtyEight's QB-Elo, so that's the source used.
- **FTN charting data:** free via nflverse, but it only starts in 2022, too short for separate development and holdout tests. Not tested.
- **Not testable historically:** your hand-valued injuries, eye test and "your ranking" don't exist for past seasons.

## 3. How it was tested (walk-forward, no peeking)

- **Ratings.** Ratings for week *w* use only games from weeks before *w*. A Thursday game isn't used even for that weekend's Sunday games.
- **Weights.** Every weight is re-fitted before each test season, using earlier seasons only. Injury snap and target shares come from earlier weeks.
- **Three separate periods:**
  - **Development, 2012–2019:** rating settings are chosen and factors first tested here. Injury-report features use 2015–2019, because that data starts in 2013 and the model needs a couple of seasons to learn from. That window was fixed before any test was run.
  - **Holdout, 2020–2025:** a factor is kept only if it *also* helps here.
  - **Live 2026, Weeks 1–8:** never used for any decision.
- **Keep rule (same in both rounds).** A factor stays only if it lowers prediction error (RMSE) on *both* development and holdout, and doesn't worsen log-loss on either. Error is used instead of tips right because it is far less noisy, and every tips result is reported too.
- **Two tracks in round 2:**
  - **A, standalone model:** improve the model that doesn't see this week's line.
  - **B, beat the line:** start from the closing line itself and add only corrections that make it better. This is the direct test of whether anything beats the market.
- **Selection.** Factors were added one at a time, best first, re-testing everything else after each addition.

## 4. Before vs after

All numbers come from `results/report.md`.

- "Tips right" means the straight-up winner was picked correctly.
- "ATS" is the model's side against the closing spread. You need 52.4% to break even at −110.

**Holdout seasons 2020–2025 (1,615 games, never used for tuning):**

| Model | Tips right | RMSE (pts) | ATS vs close | Brier | Log-loss |
|---|---|---|---|---|---|
| Original tips engine | 63.1% | 13.19 | 764-722 (51.4%) | 0.2250 | 0.6410 |
| Original power score | 64.4% | 13.23 | 754-732 (50.7%) | 0.2247 | 0.6406 |
| Round-1 model | 65.2% | 12.82 | 794-788 (50.2%) | 0.2165 | 0.6219 |
| **New model (round 2)** | **65.3%** | **12.77** | 794-788 (50.2%) | 0.2156 | 0.6194 |
| **Adjusted line (line + special teams + market drift)** | **66.8%** | **12.62** | 827-755 (52.3%) | **0.2101** | **0.6074** |
| Vegas closing line | 66.8% | 12.66 | — | 0.2102 | 0.6076 |

**Development seasons 2012–2019 (2,048 games):**

| Model | Tips right | RMSE (pts) | ATS vs close |
|---|---|---|---|
| Original tips engine | 65.0% | 13.59 | 50.5% |
| Round-1 model | 66.0% | 13.22 | 52.5% |
| New model (round 2) | 66.1% | 13.18 | 53.1% |
| Adjusted line | 66.5% | 13.15 | 52.4% |
| Vegas closing line | 66.2% | 13.18 | — |

**Live 2026, Weeks 1–8 (121 games):**

| Model | Tips right | RMSE (pts) | ATS vs close |
|---|---|---|---|
| Original tips engine | 63.3% | 12.20 | 54.0% |
| Round-1 model | 65.8% | 12.44 | 48.7% |
| New model (round 2) | 65.8% | 12.32 | 47.0% |
| Adjusted line | 65.8% | 12.20 | 45.2% |
| Vegas closing line | 65.8% | 12.18 | — |

**How much of this is real.** I resampled weeks 2,000 times on the holdout seasons, giving 95% intervals (`results/significance.txt`, `results/significance_round2.txt`):

| Comparison | Error difference (pts) | Tips difference (percentage points) | Verdict |
|---|---|---|---|
| Round-1 model vs original | −0.37 (−0.53 to −0.21) | +2.1 (+0.3 to +3.7) | real improvement |
| Round-2 model vs round-1 | −0.05 (−0.11 to +0.01) | +0.2 (−1.1 to +1.4) | small; may be luck |
| Round-2 model vs closing line | +0.12 (−0.01 to +0.24) | −1.4 (−2.9 to −0.1) | **line is better** |
| Adjusted line vs closing line | −0.03 (−0.07 to +0.00) | +0.1 (−0.2 to +0.4) | **no real difference** |

**Week-to-week consistency** (holdout):

| Model | SD of weekly tip % | Worst 10% of weeks | Weeks at 50% or better |
|---|---|---|---|
| Original tips engine | 12.0 points | 48.7% | 90% |
| New model | 11.4 points | 50.0% | 92% |
| Adjusted line | 11.7 points | 50.0% | 93% |
| Closing line | 11.8 points | 50.0% | 93% |

Against the line week by week, the new model was ahead in 27 weeks, level in 42 and behind in 38.

**By part of the season** (holdout, tips right):

| Weeks | Original | New model | Line |
|---|---|---|---|
| 1–4 | 61.8% | 63.9% | 63.4% |
| 5–9 | 62.2% | 65.4% | 66.8% |
| 10–18 | 64.2% | 66.0% | 68.3% |

In Weeks 1–4 the new model edged the line by 0.5 percentage points (2 more correct tips out of 383), with slightly lower error (12.47 vs 12.59). That's too small a sample to call it beating the line, and its win probabilities were still a little worse there (log-loss 0.6287 vs 0.6267). Later in the season the line pulls clearly ahead.

**Win probabilities.** When the model says 60–70%, the home team won 65.1% of the time. When it says 80%+, the home team won 87.4%. Near 50/50 it leans slightly too far toward the home team (full table in `results/report.md`).

**Your workbook's real 2026 picks.** On the 76 Week 3–8 games they cover, your actual picks (with DVOA, hand injuries and the eye test) went 68.0%, against 65.3% for the new model and 61.3% for the line. That's about 5 more correct tips than the line, which is within normal luck over 76 games, and those hand inputs can't be tested on earlier seasons.

## 5. Every factor tested, and whether it helped

A negative change in RMSE is better. "Helped (kept)" means it beat the keep rule when tested on its own. The final selections are listed after each round.

### Round 1: each factor added on its own to a market-only model


| Factor | Change in RMSE, dev | Change in RMSE, holdout | Change in tips right (pts), dev | Change in tips right (pts), holdout | Kept? |
|---|---|---|---|---|---|
| **Results: opponent-adjusted (damped) margin rating** | −0.104 | −0.076 | +0.4 | +1.3 | **yes** |
| **QB: starter's value against the team's recent starters** | −0.102 | −0.146 | +0.5 | +1.6 | **yes** |
| **Efficiency: EPA split into offence and defence** | −0.094 | −0.068 | +0.5 | +0.7 | **yes** |
| Efficiency: single EPA/play rating | −0.087 | −0.058 | +0.7 | +1.4 | covered by the split version |
| Recent form: short-memory EPA rating | −0.083 | −0.051 | +0.4 | +0.7 | added nothing once the above were in |
| Efficiency: success-rate rating | +0.003 | −0.027 | −0.5 | +0.4 | no |
| Injuries: non-QB snap share ruled out (offence/defence) | +0.011 | −0.038 | +0.0 | +0.3 | no (borderline, see below) |
| Home field: market-estimated home edge (adapts by era) | +0.001 | +0.003 | +0.2 | +0.7 | no |
| Home field: weights favour recent seasons | −0.000 | −0.001 | −0.2 | +0.1 | no (too small; added nothing later) |
| Rest: days-of-rest difference | +0.007 | −0.009 | −0.0 | −0.1 | no |
| Rest: coming off a bye | +0.007 | −0.005 | +0.0 | −0.1 | no |
| Rest: short week (5 days or fewer) | −0.000 | +0.000 | +0.0 | +0.0 | no |
| Travel: miles travelled | +0.003 | −0.001 | +0.2 | +0.0 | no |
| Time zones: hours shifted | +0.002 | −0.008 | +0.0 | +0.2 | no |
| Time zones: body clock (west-coast team, 1pm ET) | +0.006 | +0.004 | +0.0 | +0.1 | no |
| Time zones: east-coast team in a late game out west | +0.012 | +0.006 | +0.2 | +0.1 | no |
| Divisional game: extra home edge | −0.006 | +0.014 | +0.0 | +0.4 | no |
| Divisional game: margins shrink | +0.002 | −0.000 | +0.0 | +0.1 | no |
| Weather: high wind (over 15 mph) shrinks margins | +0.003 | +0.002 | +0.0 | −0.1 | no |
| Weather: dome or warm-weather team in a cold (35°F or below) game | +0.001 | +0.002 | −0.0 | −0.1 | no |
| Recent form: short-memory market rating | +0.001 | −0.005 | +0.1 | +0.0 | no |
| Early season: market weight varies by week | +0.006 | +0.002 | +0.1 | +0.0 | no |
| Early season: EPA weight varies by week | +0.005 | −0.024 | +0.2 | +0.9 | no |
| Early season: wider win-probability spread in Weeks 1–4 | +0.000 | +0.000 | +0.0 | +0.0 | no |

Full round-1 results: `results/factors.csv`.

**Kept in round 1:** results rating, starting-QB value, EPA split into offence and defence.

### Round 2


**Track A: standalone model (no betting line). Each factor added on its own to the round-1 model**

| Group | Factor | Δ RMSE dev | Δ RMSE holdout | Δ tips dev (pts) | Δ tips holdout (pts) | Result |
|---|---|---|---|---|---|---|
| Better EPA | EPA, early downs only (replacing plain EPA) | +0.013 | +0.005 | -0.2 | +0.0 | hurt |
| Better EPA | EPA, red zone only (replacing plain EPA) | +0.004 | +0.016 | +0.1 | +0.4 | hurt |
| Better EPA | EPA, turnovers at half weight (replacing plain EPA) | +0.004 | -0.010 | -0.2 | +0.0 | no clear effect |
| Better EPA | EPA, lost fumbles at half weight (replacing plain EPA) | -0.004 | -0.005 | -0.2 | +0.0 | **helped (kept)** |
| Better EPA | EPA, turnovers removed (replacing plain EPA) | +0.003 | -0.017 | -0.5 | +0.1 | no clear effect |
| Better EPA | EPA, passing plays only (replacing plain EPA) | -0.004 | +0.008 | -0.6 | +0.4 | no clear effect |
| Better EPA | EPA, running plays only (replacing plain EPA) | +0.003 | -0.000 | +0.2 | +0.7 | no clear effect |
| Better EPA | EPA, garbage time removed (replacing plain EPA) | +0.010 | +0.004 | +0.1 | +0.3 | hurt |
| Better EPA | EPA, early downs only (added to plain EPA) | +0.015 | -0.007 | -0.2 | +0.4 | no clear effect |
| Better EPA | EPA, red zone only (added to plain EPA) | +0.001 | +0.002 | -0.3 | -0.4 | hurt |
| Better EPA | EPA, turnovers at half weight (added to plain EPA) | +0.011 | +0.007 | -0.0 | +0.4 | hurt |
| Better EPA | EPA, lost fumbles at half weight (added to plain EPA) | +0.025 | +0.006 | -0.5 | +0.0 | hurt |
| Better EPA | EPA, turnovers removed (added to plain EPA) | +0.012 | +0.007 | -0.1 | +0.4 | hurt |
| Better EPA | EPA, passing plays only (added to plain EPA) | +0.009 | +0.004 | -0.3 | +0.0 | hurt |
| Better EPA | EPA, running plays only (added to plain EPA) | +0.005 | -0.001 | +0.0 | +0.1 | no clear effect |
| Better EPA | EPA, garbage time removed (added to plain EPA) | +0.014 | +0.002 | -0.3 | +0.3 | hurt |
| Better EPA | EPA: not opponent-adjusted (added) | -0.007 | +0.029 | -0.3 | +0.4 | no clear effect |
| Better EPA | EPA: pass and run separately (added together) | +0.036 | -0.006 | -0.3 | +0.2 | no clear effect |
| Players | Players: offensive line out (snap share) | +0.004 | +0.001 | -0.3 | -0.1 | hurt |
| Players | Players: WR/TE out (target share) | +0.009 | -0.019 | +0.0 | +0.1 | no clear effect |
| Players | Players: RB out (snap share) | +0.013 | -0.005 | -0.2 | -0.3 | no clear effect |
| Players | Players: pass rushers out (pressure share) | +0.022 | +0.004 | +0.2 | +0.0 | hurt |
| Players | Players: cornerbacks out (snap share) | +0.008 | -0.025 | +0.4 | +0.2 | no clear effect |
| Players | Players: safeties out (snap share) | +0.001 | -0.000 | -0.2 | -0.1 | no clear effect |
| Players | Players: linebackers out (snap share) | -0.016 | -0.003 | +0.1 | +0.2 | no clear effect |
| Players | Players: count of 60%+ snap starters out | +0.007 | -0.012 | +0.5 | +0.1 | no clear effect |
| Players | Players: all position groups together | +0.043 | -0.042 | +0.7 | +0.5 | no clear effect |
| Play calling | Play calling: pass rate over expected | +0.004 | -0.003 | -0.3 | +0.5 | no clear effect |
| Play calling | Play calling: pace (seconds per play) | +0.008 | +0.003 | -0.2 | +0.0 | hurt |
| Play calling | Play calling: no-huddle rate | +0.006 | +0.003 | -0.0 | +0.1 | hurt |
| Coaching | Coaching: 4th-down aggressiveness | -0.005 | -0.003 | +0.1 | +0.5 | **helped (kept)** |
| Coaching | Coaching: new head coach this season | +0.006 | -0.005 | -0.7 | +0.0 | no clear effect |
| Coaching | Coaching: new head coach x early season | +0.001 | -0.006 | -0.2 | +0.3 | no clear effect |
| Coaching | Coaching: mid-season coaching change | +0.008 | +0.001 | -0.1 | +0.1 | hurt |
| Special teams | Special teams: EPA per game | -0.016 | -0.028 | -0.4 | -0.1 | **helped (kept)** |
| Special teams | Special teams: EPA, opponent-adjusted | -0.014 | -0.024 | -0.4 | -0.4 | **helped (kept)** |
| Penalties | Penalties: penalty yards per game (recent) | +0.000 | +0.004 | -0.1 | +0.1 | hurt |
| Penalties | Penalties: penalty yards per game (long memory) | +0.002 | +0.003 | -0.2 | +0.1 | hurt |
| Luck | Luck: one-score game record (recent) | +0.004 | +0.003 | -0.2 | +0.1 | hurt |
| Luck | Luck: one-score game record (season to date) | +0.004 | +0.002 | -0.1 | +0.1 | hurt |
| Luck | Luck: fumble recoveries above 50/50 | +0.010 | +0.001 | -0.3 | +0.1 | hurt |
| Other data | Other source: nfelo QB-adjusted Elo | -0.014 | +0.001 | -0.0 | +0.6 | no clear effect |
| Other data | Other source: nfelo forecast (as points) | -0.021 | -0.010 | +0.0 | +0.3 | **helped (kept)** |

**Track A: machine learning and combinations, compared with the final round-2 linear model**

| Group | Factor | Δ RMSE dev | Δ RMSE holdout | Δ tips dev (pts) | Δ tips holdout (pts) | Result |
|---|---|---|---|---|---|---|
| Machine learning | Gradient boosting, round-1 features | +0.356 | +0.119 | -0.7 | +0.2 | hurt |
| Machine learning | Gradient boosting, all features | +0.356 | +0.183 | -0.2 | -0.9 | hurt |
| Machine learning | Gradient boosting, all features, heavier regularisation | +0.290 | +0.100 | -1.1 | -0.4 | hurt |
| Machine learning | Average of gradient boosting and linear, all features | +0.131 | -0.010 | +0.2 | +1.1 | no clear effect |
| Machine learning | Linear model with ALL features (overfitting check) | +0.152 | -0.003 | +0.2 | +1.1 | no clear effect |

**Track B: beat the line. Each adjustment added on its own to the closing line**

| Group | Factor | Δ RMSE dev | Δ RMSE holdout | Δ tips dev (pts) | Δ tips holdout (pts) | Result |
|---|---|---|---|---|---|---|
| Situations | Line + constant (bias toward home/away) | +0.003 | +0.001 | +0.1 | +0.0 | hurt |
| Model + line | Line + new model's disagreement with the line | -0.027 | +0.005 | +0.0 | +0.0 | no clear effect |
| Other data | Line + nfelo's disagreement with the line | -0.021 | +0.018 | -0.1 | +0.0 | no clear effect |
| Situations | Big favourites (line 10+): line too big/small | +0.004 | -0.001 | +0.0 | +0.0 | no clear effect |
| Situations | Big underdogs (line 10+): flat bonus for the dog | +0.004 | -0.001 | +0.0 | +0.0 | no clear effect |
| Situations | Close lines (3 or less): flat home bias | +0.003 | +0.001 | +0.0 | +0.0 | hurt |
| Situations | Home underdogs | -0.000 | +0.005 | +0.0 | +0.0 | no clear effect |
| Situations | Early season: line too big/small | +0.001 | +0.001 | +0.0 | +0.0 | hurt |
| Situations | Early season: model disagreement weighted up | +0.010 | -0.002 | +0.0 | +0.0 | no clear effect |
| Situations | Late season (week 13+): line too big/small | -0.002 | -0.011 | +0.0 | +0.0 | **helped (kept)** |
| Situations | After a QB change: line under-reacts | +0.005 | -0.001 | +0.1 | +0.1 | no clear effect |
| Situations | After a QB change: model disagreement weighted up | +0.008 | +0.001 | +0.2 | +0.0 | hurt |
| Situations | Prime-time games: line too big/small | +0.000 | +0.020 | +0.0 | +0.0 | hurt |
| Situations | Prime-time games: home bias | +0.002 | +0.011 | +0.0 | +0.0 | hurt |
| Situations | Divisional games: line too big/small | +0.001 | -0.001 | +0.0 | +0.0 | no clear effect |
| Situations | High-total games: line scales with total | -0.002 | -0.002 | +0.0 | +0.0 | **helped (kept)** |
| Situations | High wind: line too big | +0.012 | -0.002 | +0.0 | +0.0 | no clear effect |
| Situations | Rest difference vs line | +0.009 | +0.001 | +0.0 | +0.0 | hurt |
| Situations | Bye vs line | +0.008 | +0.001 | +0.0 | +0.0 | hurt |
| Situations | Travel miles vs line | +0.004 | +0.001 | +0.1 | +0.0 | hurt |
| Situations | Time-zone shift vs line | +0.005 | -0.005 | +0.1 | +0.0 | no clear effect |
| Players | QB value change vs line | -0.001 | +0.001 | +0.1 | +0.0 | no clear effect |
| Players | Non-QB injuries (all groups) vs line | +0.073 | -0.017 | +0.4 | -0.4 | no clear effect |
| Players | Pass rushers out vs line | +0.017 | +0.008 | +0.4 | -0.2 | hurt |
| Players | Offensive line out vs line | +0.002 | +0.002 | +0.1 | +0.0 | hurt |
| Market | Market rating vs line (recent-weeks drift) | -0.017 | -0.003 | +0.1 | +0.0 | **helped (kept)** |
| Team strength | Results rating vs line | -0.004 | +0.002 | +0.1 | +0.0 | no clear effect |
| Team strength | EPA off/def vs line | +0.006 | +0.005 | +0.4 | +0.0 | hurt |
| Luck | Luck: one-score record vs line | +0.005 | +0.002 | +0.1 | +0.0 | hurt |
| Luck | Luck: fumble luck vs line | +0.014 | -0.001 | +0.1 | +0.0 | no clear effect |
| Special teams | Special teams vs line | -0.013 | -0.028 | +0.2 | -0.1 | **helped (kept)** |
| Penalties | Penalties vs line | +0.001 | +0.003 | +0.0 | +0.0 | hurt |
| Coaching | New coach x early season vs line | +0.006 | -0.005 | +0.0 | +0.0 | no clear effect |
| Play calling | Pass rate over expected vs line | +0.016 | +0.001 | +0.0 | +0.0 | hurt |

**Track B: machine learning on what the line gets wrong, compared with the final adjusted line**

| Group | Factor | Δ RMSE dev | Δ RMSE holdout | Δ tips dev (pts) | Δ tips holdout (pts) | Result |
|---|---|---|---|---|---|---|
| Machine learning | Gradient boosting on line residual, all features + line | +0.180 | +0.060 | -0.5 | -0.9 | hurt |
| Machine learning | Gradient boosting on line residual, situations only | +0.138 | +0.091 | -0.4 | -0.1 | hurt |

**Kept in round 2:**

- **Standalone model:** added special-teams EPA per game, nfelo's forecast and 4th-down aggressiveness, in that order. Each was re-tested after the previous one was added.
- **Adjusted line:** the closing line plus special-teams strength (opponent-adjusted) and the market-drift term.

**Helped on their own but were superseded.** These no longer helped once the selected factors were in:

- half-weighting lost fumbles in EPA
- opponent-adjusted special teams, in the standalone model
- nfelo's QB-adjusted Elo rating, alongside nfelo's forecast
- in the adjusted line, the late-season and high-total adjustments

**Round 2 in plain terms:**

- **EPA versions.** Early-down, red-zone, garbage-time-removed, pass/run-split and turnover-discounted EPA were no better than plain opponent-adjusted EPA. Discounting lost fumbles helped a touch on its own.
- **Player value beyond the QB.** Offensive line, receivers weighted by target share, pass rushers weighted by pressures, and cornerbacks, safeties and linebackers weighted by snaps were all noise. Together they helped the holdout seasons but hurt 2015–2019. The market already prices these injuries, and the remaining signal is too small to measure.
- **Play-calling and coaching.** Pace, no-huddle, pass rate over expected, new head coaches and mid-season changes did nothing. The exception is 4th-down aggressiveness: teams that go for it more do slightly better than their other numbers suggest.
- **Special teams.** This is the one clear new signal. It shows up in both tracks, so the betting line also under-prices it slightly, by about 0.3 points per point of special-teams edge.
- **Penalties and luck.** Penalty yards, one-score record and fumble-recovery luck did nothing or hurt. The ratings already damp blowouts and don't use win/loss record, so there is no luck left to strip out.
- **Machine learning.** Gradient boosting was clearly worse every time, by 0.10–0.36 points of error. It overfits even when heavily regularised. Averaging it with the linear model, or putting every feature into one linear model, didn't pass either. With about 3,000 training games and outcomes this noisy, a simple linear blend wins.
- **Where the line might be wrong.** Big favourites and underdogs, home underdogs, early season, prime time, divisional games, high wind, after a QB change, rest, travel and time zones: none of them showed a repeatable line error. The only one kept is "market drift". When this week's line has moved away from where earlier weeks' lines rated the teams, about 13% of that move reverts, so the line slightly over-reacts to recent news. It is worth about 0.01–0.03 points of error.

## 6. The final models

**New model (standalone, no betting line)**, weights for 2026, fitted on 2009–2025:

```
home margin = 1.06 * home field (0 at neutral sites)
            + 0.72 * market rating difference          (points; from earlier weeks' closing lines)
            - 0.71 * results rating difference         (negative because nfelo below also measures results;
            + 0.39 * nfelo forecast (points)             together they act as one results signal: see Results + Elo)
            + 21.9 * QB value change difference         (today's starter minus the team's recent starters, EPA/dropback)
            + 33.9 * offensive EPA/play difference
            - 22.0 * defensive EPA-allowed difference
            + 0.78 * special-teams EPA per game difference
            + 3.8  * 4th-down go-for-it rate difference
win probability = Normal(margin / 13.15)
```

**Adjusted line (recommended tip):**

```
home margin = closing line + 0.302 * special-teams difference (opponent-adjusted, pts/game)
                           + 0.132 * market rating difference (from earlier weeks' lines)
win probability = Normal(margin / 13.03)
```

## 7. Honest verdict: can it beat the closing line?

**No.**

- **Tips right.** After testing 108 factor variants, the best version only ties the line on the holdout seasons (66.8% vs 66.8%) and on 2026 (65.8% vs 65.8%). It is 0.3 percentage points ahead on development seasons, about 6 games out of 2,048. Its corrections are small, 0.7 points on average, so it changes the line's pick in about 1 game in 230.
- **Error and probabilities.** The adjusted line is very slightly more accurate than the line (0.03 points lower error, better log-loss on both test periods), but that gap is within what chance produces.
- **Betting.** 52.3–52.4% against the spread is break-even after the bookmaker's cut. On 2026 it went 45.2%.
- **The standalone model** (no line) is a genuinely better power-ranking engine than the original, but it trails the line by about 1.4 percentage points of tips.

The closing line already reflects public information like this, plus injury news, team announcements and the money of sharp bettors.

## 8. Known limitations

- **The starting QB in the backtest is the actual starter.** Normally that's known before kickoff, but late scratches make the backtest slightly flattering. In live use, keep `qb_overrides.csv` current.
- **nfelo is a third-party file.** Its pre-game ratings use only earlier games, but its settings were chosen by its author with hindsight, which may flatter its historical value slightly. If it isn't updated for a week, `weekly.py` warns you and that input is set to 0.
- **The weekly line isn't the closing line.** "Line" in the output is whatever nflverse has when you run it, so run close to kickoff.
- **Development-season numbers are slightly optimistic,** because settings were chosen there, and round 2 reused the same holdout for keep decisions. 2026 is the one fully untouched check, but it's small (121 games).
- **Weather is recorded game-day conditions, not forecasts.** It didn't help anyway.
- **Coverage gaps.** Only regular-season games are scored. There's no totals (over/under) model. Injury data starts in 2013.
- **Hand-entered values.** Stadium coordinates and 8 international-venue fixes (see section 2).
- **The original workbook is untouched.** This folder is a separate Python model.

## Files

| File | What it does |
|---|---|
| `weekly.py` | The weekly one-command routine |
| `fetch_data.py` | Downloads nflverse data and builds the core per-game tables (`--current SEASON` refreshes one season) |
| `fetch_extra.py` | Extra per-game tables (EPA variants, pace, pass rate over expected, 4th downs, special teams, penalties, targets, pressures) and nfelo |
| `common.py` | Loads games; franchise moves; stadiums, travel, time zones, weather |
| `ratings.py` | Walk-forward market, results and EPA ratings and QB values |
| `model.py` | Round-1 features and walk-forward fitting |
| `extra.py` | Round-2 features, the adjusted line, and per-team parts for the rankings |
| `baseline.py` | Faithful re-implementation of the original tips engine and power score |
| `tune.py`, `factors.py`, `factors2.py`, `report.py` | Settings search, round-1 and round-2 factor tests, final report |
| `metrics.py` | RMSE, tips, ATS, Brier, log-loss, calibration, weekly consistency |
| `results/` | `report.md`, `factors.csv`, `round2_log.csv`, `round2_table.md`, `selected.json`, `params.json`, significance files, prediction CSVs |
| `output/` | Weekly outputs (2026 Week 9 included as an example) |
