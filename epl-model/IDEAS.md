# Ideas backlog

Ranked by expected value for accuracy/insight versus effort. "Tested" items were run through the
walk-forward protocol in `backtest.py` (results in `reports/EXPERIMENTS.md`); the rest are untested.

| # | Idea | Value | Effort | Status |
|---|---|---|---|---|
| 1 | Blend goals, xG and market-based ratings | High | Low | Tested (stage 3) |
| 2 | Tune time decay / season-boundary decay (form vs long-term strength) | High | Low | Tested (stage 1) |
| 3 | Dixon-Coles low-score correction and an explicit draw adjustment | High | Low | Tested |
| 4 | Promoted-team prior and early-season shrinkage | Medium | Low | Tested |
| 5 | Rest days, European congestion | Medium | Medium | Tested (UEFA coverage partial) |
| 6 | Manager change ("new manager bounce") | Medium | Low | Tested |
| 7 | Starting-XI strength from player xG+xA (absences, signings) | High | High | Tested on 2022-26 only; needs lineup feed for live use |
| 8 | Finishing luck, penalties, red cards: skill or luck | Medium | Low | Tested (+ persistence analysis) |
| 9 | Derbies and end-of-season motivation | Low | Low | Tested |
| 10 | Set pieces (corner differential as proxy) | Low | Low | Tested |
| 11 | Championship (E1) results/odds to rate promoted clubs before they arrive | Medium | Medium | Untested – football-data E1 files are in the same mirror |
| 12 | Shot-level xG (Poisson-binomial per shot, set-piece vs open play split) | Medium | High | Untested – no reachable shot-level source (Understat/FBref blocked here) |
| 13 | Live injury/availability feed (FPL `chance_of_playing`) for the upcoming gameweek | High | Medium | Untested – FPL API blocked here; vaastav snapshot lags |
| 14 | Domestic cup fixtures (FA Cup, League Cup) for congestion | Low | Medium | Untested – no reachable fixture source |
| 15 | Bivariate Poisson / Weibull count model instead of DC | Low | Medium | Untested |
| 16 | Team-specific home advantage (shrunk) | Low | Low | Untested |
| 17 | ClubElo ratings as an extra blend input | Medium | Low | Untested – snapshot timing could leak same-day results |
| 18 | Referee tendencies (cards, penalties) | Low | Low | Untested |
| 19 | Weather, pitch, kickoff time, travel distance | Low | Medium | Untested |
| 20 | Betting value / Kelly staking vs closing odds | Insight | Low | Not pursued – model does not beat the close |
| 21 | Opening-to-closing line movement as information signal | Medium | Medium | Untested – needs opening odds (football-data pre-closing columns exist) |
| 22 | Squad market value / wage bill as long-run prior | Medium | Medium | Untested – no free reachable source |
