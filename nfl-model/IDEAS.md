# Ideas backlog

Every idea considered for improving the tips, the rankings or the weekly report. Ranked by **likely value ÷ effort**.

- **Status** is either *tested* (with the result) or *not tested* (with why, and what it would take).
- All tests used the project rules: real data only, walk-forward, and a change is kept only if it holds up on development (2012–19) **and** holdout (2020–25).
- Full results are in `results/`.

## Tested in round 3 (none kept)

| # | Idea | Value | Effort | Result |
|---|---|---|---|---|
| 1 | Better win % for the tip: use no-vig moneylines instead of a normal curve around the line | medium | low | No: tie on holdout (log-loss 0.6073 vs 0.6074), slightly worse on development |
| 2 | Logistic recalibration of the model's win % | medium | low | No: better on development, worse on holdout |
| 3 | Result spread that grows with the game total (high-scoring games are more random) | low–medium | low | No: no change |
| 4 | Denver altitude: extra home edge | low | low | Hurt (development RMSE +0.015) |
| 5 | Team-specific home field (shrunk, from earlier seasons) | low | low | Hurt in both tracks |
| 6 | Referee tendencies (home margin vs expectation) | low | low | Hurt in both tracks |
| 7 | Grass/turf: road team on an unfamiliar surface | low | low | No clear effect / hurt |
| 8 | Power-ranking alternatives: smoothed scores, nfelo, ranking without the QB adjustment, record, Pythagorean | medium | low | None better on both periods (`results/round3_rankings.md`) |
| 9 | Recent trend (last 4 weeks) as a predictor | low | low | No: hot teams slightly *regress* |

Earlier rounds covered 108 more ideas: README section 5 and `results/factors.csv` / `results/round2_log.csv`.

## Not tested yet: best value first

| # | Idea | Likely value | Effort | Notes |
|---|---|---|---|---|
| 1 | **"Questionable" QBs and late scratches.** Use the injury report's Questionable / game-time status for QBs, and weight the QB adjustment by the chance he plays | medium | medium | The QB adjustment is the most valuable factor. The data is in nflverse injuries (`report_status`). Needs a probability-of-playing estimate by status (e.g. how often Questionable QBs played since 2013). |
| 2 | **Automatic starting-QB check from the depth chart** (`depth_charts_{season}.csv` in nflverse) instead of assuming last week's starter | medium | medium | Would cut the manual `qb_overrides.csv` step. Depth charts are published weekly but lag announcements. |
| 3 | **Totals model (over/under)** using offence/defence EPA, pace and pass rate over expected | medium (new output) | medium | A new output, not a better tip. Expect no edge against the closing total, as with spreads. |
| 4 | **Playoff-game predictions** (currently only the regular season is scored) | low–medium | low | Same model. Needs neutral-site handling for the Super Bowl and a separate small-sample evaluation. |
| 5 | **Head-to-head and common-games tiebreakers** in the season simulation | low | medium | Affects a few percent of division and wildcard odds in tight races. The current simplified tiebreakers are documented in `nflmodel/season.py`. |
| 6 | **Season win totals and futures odds** as a pre-season prior | high for Weeks 1–4 | high | No free historical source found. Week 1 is where the model is weakest. |
| 7 | **Line movement (open to close)** as a signal of sharp money | medium | high | nflverse has only one (closing) line. Historical openers need a paid or scraped source. |
| 8 | **ESPN FPI / other public power ratings** as an extra input or benchmark | low–medium | medium | ESPN's API is blocked from this environment's network. It would also need their historical pre-game values. |
| 9 | **FTN charting data** (play-action, pressure, motion; free via nflverse from 2022) | low–medium | medium | Too short for separate development and holdout tests. Revisit around 2028. |
| 10 | **Weather forecasts** (not recorded game-day conditions) | low | medium | Weather didn't help when tested on actual conditions, so forecasts are unlikely to. Open-Meteo is blocked here. |
| 11 | **Expert-pick consensus** (your `audit/src` files for 2026) | unknown | medium | Only 2026 exists, too short to test. Could be logged weekly from now on to test in a future season. |
| 12 | **Your own ranking / eye test** blended in, as in the original workbook | unknown | low | Can't be tested historically. Could be logged weekly and tested after a season. |
| 13 | **Bet sizing (Kelly)** on edges against the line | none | low | Not recommended: no betting edge was found in 3 rounds. |
| 14 | **Interactive dashboard** (HTML page with filters) for the weekly report | presentation only | medium | The markdown and CSV outputs cover the content. |
| 15 | **Email or Slack delivery** of the weekly report | convenience | low | Needs a connector or credentials; out of scope here. |
