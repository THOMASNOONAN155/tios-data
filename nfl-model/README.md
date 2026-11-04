# NFL weekly predictor (rebuild of the NFL Power Rankings & Tips model)

Each week this predicts every NFL game, gives a win probability, and produces 1–32 power rankings. It was rebuilt from the original
`nfl_power_rankings` workbook model and tested on 15 seasons of real data, using only information available before each game.

**Bottom line:**

- The new model beats the original on every test period.
- It does **not** beat the Vegas closing line, and nothing I tested did.
- Against the spread, it is a coin flip.
- For tipping winners, the best choice is the **blend** column, which is mostly the line with a small model adjustment. It matches the line, so it doesn't add anything beyond it.

---

## Run it each week

```bash
cd nfl-model
pip install -r requirements.txt
python3 weekly.py
```

That one command:

1. downloads this season's latest scores, lines, play-by-play and injury reports from nflverse (about 15 seconds)
2. rebuilds the ratings
3. writes three files to `output/`:
   - `output/<season>_wk<NN>.md`: readable tables of games and power rankings
   - `output/<season>_wk<NN>_predictions.csv`: per game, the model tip, win %, model margin, current line, edge against the line, blend tip and blend win %, and the expected starting QBs
   - `output/<season>_wk<NN>_power_rankings.csv`: power score (points better than an average team on a neutral field), its parts, the QB adjustment this week, and last week's rank

Options:

- `--week 10` picks a specific week (the default is the first week with unplayed games).
- `--season 2026` picks the season.
- `--no-fetch` skips the download.

**Check the starting QBs before you run it.** nflverse records a game's starting QB only after the game is played. For upcoming games the model assumes each team's most recent starter. If someone else will start, add a row to `data/qb_overrides.csv`, in the form `season,week,team,qb_name` (for example `2026,9,BAL,<QB name>`), spelling the name as nflverse does. A QB the data has never seen is treated as replacement level. This adjustment matters a lot: a starter change can be worth 3–7 points.

Rebuilding everything from scratch (only needed once, or to re-run the research):

```bash
python3 fetch_data.py   # all seasons 2006–now, about 2 minutes, about 430 MB of raw files in data/raw (git-ignored)
python3 tune.py         # rating settings, chosen on development seasons only
python3 factors.py      # factor tests (results/factors.csv, results/selected.json)
python3 report.py       # before-vs-after report (results/report.md)
python3 baseline.py     # the original model, re-implemented (results/baseline_predictions.csv)
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

## 2. Data collected, all real, with sources

| Data | Seasons | Source |
|---|---|---|
| Schedule, final scores, **closing spread**, total, moneylines, rest days, roof, surface, temperature/wind, divisional flag, **starting QB** for each game | 2006–2026 | nflverse `games.csv`: https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv |
| Play-by-play with EPA, success, win probability, dropbacks, fumbles (about 1M plays) | 2006–2026 | nflverse: `https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet` |
| Official injury reports (Out / Doubtful) | 2013–2026 | nflverse: `.../releases/download/injuries/injuries_{season}.csv` |
| Snap counts (to weight injured players by playing time) | 2012–2026 | nflverse / Pro-Football-Reference: `.../releases/download/snap_counts/snap_counts_{season}.csv` |
| Player ID map (gsis ↔ PFR) | — | nflverse: `.../releases/download/players/players.csv` |
| Weather where `games.csv` has none | 2006–2026 | Parsed from the NFL gamebook weather text inside the play-by-play |
| Stadium latitude/longitude and time zone | — | **Hand-entered** in `common.py` from public stadium locations (accurate to about 0.05°). Used for travel miles and body clock. |
| International venue corrections | 2025–26 | **Hand-entered** in `common.py` (`VENUE_FIX`). nflverse lists 8 international games (e.g. 2025 Week 1 KC–LAC in São Paulo) at the home team's US stadium. |
| Your workbook's actual 2026 picks | 2026 Weeks 1–8 | Your `modelpicks.json`, copied to `data/original_workbook_picks_2026.json` |

**How the lines were checked.** nflverse doesn't say which sportsbook or which moment its `spread_line` comes from. I compared it with the 5-source consensus closing line in your `base8.xlsx` for all 121 games of 2026 Weeks 1–8:

- It matched exactly in 81% of games.
- The average difference was 0.16 points.
- All 121 scores matched.

So I treat it as the closing line.

**What I couldn't get:**

- **FTN DVOA history.** It's paywalled, so DVOA isn't used. EPA covers the same ground.
- **Historical opening lines.** nflverse has one line per game, so open against close couldn't be tested.
- **Historical weather forecasts.** Recorded game-day conditions stand in for the forecast.

Committed in `data/`: compact per-game tables built from the above (`games.csv`, `team_games.csv`, `qb_games.csv`, `injury_out.csv`, `weather_pbp.csv`) plus `manifest.json` with URLs and checksums. The raw play-by-play stays out of git; `fetch_data.py` re-downloads it.

## 3. How it was tested (walk-forward, no peeking)

- **Ratings.** Ratings for week *w* are fitted only to games from weeks before *w*. A Thursday game isn't used even for that weekend's Sunday games. QB values are updated after each week.
- **Weights.** The weights that combine the ratings are re-fitted before every test season, using only earlier seasons.
- **Probabilities.** The win-probability spread and the model–line blend weight are also fitted only on earlier seasons.
- **Three separate periods:**
  - **Development, 2012–2019 (2,048 games):** used to choose the rating settings and to test factors.
  - **Holdout, 2020–2025 (1,615 games):** a factor was kept only if it also improved results here.
  - **Live 2026, Weeks 1–8 (121 games):** not used for any decision.
- **Keep rule.** A factor stayed only if it lowered RMSE on *both* development and holdout seasons without worsening log-loss.

## 4. Before vs after

All numbers come from `results/report.md`. "Tips right" means the straight-up winner was picked correctly. "ATS" is the model's side against the closing spread.

**Holdout seasons 2020–2025 (never used for tuning):**

| Model | Tips right | RMSE (pts) | ATS vs close | Brier | Log-loss |
|---|---|---|---|---|---|
| Original tips engine | 63.1% | 13.19 | 51.4% | 0.2250 | 0.6410 |
| Original power score | 64.4% | 13.23 | 50.7% | 0.2247 | 0.6406 |
| **New model** | **65.2%** | **12.82** | 50.2% | 0.2165 | 0.6219 |
| New model blended with line | 66.8% | 12.66 | — | 0.2117 | 0.6112 |
| **Vegas closing line** | **66.8%** | **12.66** | — | **0.2102** | **0.6076** |

**Development seasons 2012–2019:**

| Model | Tips right | RMSE (pts) | ATS vs close |
|---|---|---|---|
| Original tips engine | 65.0% | 13.59 | 50.5% |
| New model | 66.0% | 13.22 | 52.5% |
| Vegas closing line | 66.2% | 13.18 | — |

**Live 2026, Weeks 1–8 (121 games):**

| Model | Tips right | RMSE (pts) | ATS vs close |
|---|---|---|---|
| Original tips engine | 63.3% | 12.20 | 54.0% |
| New model | 65.8% | 12.44 | 48.7% |
| Vegas closing line | 65.8% | 12.18 | — |

**How much of this is real.** I resampled weeks 2,000 times on the holdout seasons (`results/significance.txt`, 95% intervals):

- **New model against original:** RMSE is 0.37 points lower (interval −0.53 to −0.21). The new model gets 2.1 percentage points more tips right (+0.3 to +3.7). Both are real improvements.
- **New model against the closing line:** RMSE is 0.17 points higher (+0.04 to +0.29), and the model gets 1.6 percentage points fewer tips right (−3.1 to −0.1). **The line is better.**
- **Against the spread:** the model is 50.2% over 1,577 games. With no skill at all, 95% of results would fall between 47.5% and 52.5%. You need 52.4% to break even at −110, so the model has **no betting edge**. The 52.5% on development seasons didn't hold up on the holdout.

**About the 2026 window in the original README.** On 2026 Weeks 3–8, your workbook's real picks (with DVOA, hand-valued injuries and the eye test) covered 76 of the 89 games. On those 76 games they went 68.0%, against 61.3% for the closing line and 64.0% for the new model. That's about 5 more correct tips than the line, which is within normal luck over 76 games. It can't be tested further, because those hand inputs don't exist for earlier seasons.

**Win probabilities** (holdout calibration table in `results/report.md`):

- When the model says 70–80%, the home team won 74.6% of the time. When it says 80%+, the home team won 86%.
- Near 50/50 it leans slightly too far toward the home team: at 50–60% predicted, the home team won 49.7%. It learned a 2.0-point home edge from 2009 onward, and home edge has shrunk in recent seasons. A version that adapts home edge by era was tested and didn't pass the keep rule.

**Week-to-week consistency** (holdout):

| Model | SD of weekly tip % | Worst 10% of weeks | Weeks at 50% or better |
|---|---|---|---|
| Original tips engine | 12.0 points | 48.7% | 90% |
| New model | 11.9 points | 50.0% | 92% |
| Closing line | 11.8 points | 50.0% | 93% |

Against the line week by week, the model was ahead in 26 weeks, level in 40 and behind in 41.

**By part of the season** (holdout, tips right):

| Weeks | Original | New | Line |
|---|---|---|---|
| 1–4 | 61.8% | 61.6% | 63.4% |
| 5–9 | 62.2% | 65.2% | 66.8% |
| 10–18 | 64.2% | 66.8% | 68.3% |

The new model's biggest error improvement comes early in the season (RMSE 12.61 against 13.25 in Weeks 1–4), thanks to the carry-over from last season.

## 5. Which factors actually helped

Each factor was added on its own to a market-only model. A negative change in RMSE is better.

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

Full results are in `results/factors.csv`. It also shows later selection rounds, where each factor was tested on top of the ones already kept.

**What this means:**

- **What matters** is team strength measured three ways: betting lines, results and play-by-play efficiency. On top of that, which QB is actually starting matters.
- **Offence carries more weight than defence.** With the market rating held fixed, offensive EPA is weighted about 3.5 times as heavily as defensive EPA. Offence is the more repeatable side.
- **Situational factors didn't help.** Rest, byes, travel, time zones, weather and divisional games are each worth well under a point, and the changes they produced were noise in opposite directions on the two test periods. They are left out instead of being given made-up values. (The original's 0.3 points per day of rest, 0.7 for a bye, 0.2 per 1,000 miles and 0.5 body clock all fall in this group.)
- **Borderline factors.** Defensive injuries, rest and bye each improved both 2015–2019 and the holdout by tiny amounts (0.001–0.02 RMSE). They failed the full development window, partly because injury data only starts in 2013. Under the keep rule fixed before testing, they are not kept.

Rating settings came from `tune.py` on development seasons only. The results surface is flat: neighbouring settings differ by about 0.01 RMSE.

| Rating | Half-life | Extra off-season decay | Ridge |
|---|---|---|---|
| Market | 2.5 weeks | none | 0.5 |
| Results | 4 weeks | 2 weeks | 4 |
| EPA | 3 weeks | 2 weeks | 3 (all plays; removing garbage time did slightly worse) |

QB value is EPA per dropback with a time decay (half-life 40 weeks), pulled toward −0.05 with the weight of 250 dropbacks.

## 6. The new model

```
home margin = 2.05 * home field (0 at neutral sites)
            + 0.91 * market rating difference         (points; from past closing lines, carried across seasons)
            + 0.72 * results rating difference        (points; damped margins)
            + 32.8 * QB value change difference        (EPA/dropback: today's starter minus the team's recent starters)
            + 12.2 * offensive EPA/play difference
            + 3.5  * defensive EPA-allowed difference  (with the market fixed, a "bad defence" rating partly regresses back)
win probability = Normal(margin / 13.2)
```

These are the weights used for 2026, fitted on 2009–2025. The weights are re-fitted each season, and all three ratings carry across seasons with decay, so Week 1 no longer just copies the line. The power score is the same formula for one team against an average team on a neutral field, plus this week's QB adjustment.

**Blend.** Blend = line + 0.29 × (model − line). The 0.29 is re-fitted each season on earlier seasons. On holdout seasons the blend tied the line on tips (66.8%) and RMSE (12.66), with slightly worse log-loss.

## 7. Known limitations

- **It doesn't beat the closing line.** Use it to understand the teams and to tip from the blend. Don't expect it to beat bookmakers.
- **The starting QB in the backtest is the actual starter** from nflverse. That's normally known before kickoff, but late scratches would make the backtest look slightly better than live use. In live use, keep `qb_overrides.csv` current.
- **Weather is the recorded game-day condition, not the forecast.** It didn't help anyway.
- **Development-season numbers are slightly optimistic,** because the rating settings were chosen there. The holdout and 2026 numbers are the honest ones.
- **The line during the week isn't the closing line.** When you run it mid-week, "line" is whatever nflverse has at that moment.
- **2026 is a small sample (121 games).** Differences of a few percent between models there are noise.
- **Coverage gaps.** Only regular-season games are scored; playoffs feed the ratings but aren't evaluated. There's no totals (over/under) model. DVOA, the eye test and "your ranking" aren't included, because they can't be tested historically. Injury data starts in 2013.
- **Hand-entered values.** Stadium coordinates and 8 international-venue fixes are hand-entered (see section 2). Arizona's lack of daylight saving and European clock changes are handled, but some international kickoff body-clock values are approximate.
- **The original workbook is untouched.** This folder is a separate Python model. It doesn't rebuild the Excel tabs.

## Files

| File | What it does |
|---|---|
| `weekly.py` | The weekly one-command routine |
| `fetch_data.py` | Downloads the data and builds the compact tables (`--current SEASON` refreshes one season) |
| `common.py` | Loads games; franchise moves (OAK→LV, SD→LAC, STL→LA); stadiums, travel, time zones, weather |
| `ratings.py` | Walk-forward market, results and EPA ratings and QB values |
| `model.py` | Per-game features and the walk-forward fitting and prediction |
| `baseline.py` | Faithful re-implementation of the original tips engine and power score |
| `tune.py`, `factors.py`, `report.py` | Rating-setting search, factor tests, final report |
| `metrics.py` | RMSE, tips, ATS, Brier, log-loss, calibration, weekly consistency |
| `results/` | `report.md`, `factors.csv`, `selected.json`, `params.json`, `significance.txt`, prediction CSVs |
| `output/` | Weekly outputs (2026 Week 9 included as an example) |
