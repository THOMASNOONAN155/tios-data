# Ideas backlog

Ranked by expected value for accuracy or insight versus effort. "Tested" items went through the walk-forward
protocol in `backtest.py`, with the bootstrap significance rule; results are in `reports/EXPERIMENTS.md`. The
rest are untested, with the reason.

| # | Idea | Value | Effort | Status / result |
|---|---|---|---|---|
| 1 | Market-based ratings from past closing odds | High | Low | **Tested – chosen model** (best on tuning seasons) |
| 2 | Blend goals, xG, market and Elo ratings | High | Low | Tested – helps Test B, hurts Test A; dropped |
| 3 | Tune time decay and season-boundary decay (form vs long-term strength) | High | Low | Tested – tuned (market: 90-day half-life, previous seasons ×0.5) |
| 4 | xG vs goals weighting | High | Low | Tested – 70% xG best among goal models; xG beats goals on both test periods |
| 5 | Dixon-Coles correction and explicit draw adjustment | High | Low | Dixon-Coles used; extra draw correction dropped |
| 6 | Recent form (xG difference, last 5) on top of ratings | Medium | Low | Tested – small gain on both periods, within noise; dropped |
| 7 | Promoted-team prior / early-season effects | Medium | Low | Tested – within noise or worse; dropped |
| 8 | Rest days, European congestion | Medium | Medium | Tested – unstable across periods; dropped (UEFA coverage partial) |
| 9 | Manager change | Medium | Low | Tested – within noise; dropped |
| 10 | Starting-XI strength (absences, signings) | High | High | Tested 2022-26 – worse; dropped. Would need a real lineup/injury feed |
| 11 | Finishing luck, penalties, red cards | Medium | Low | Tested – no gain; persistence analysis confirms mostly luck |
| 12 | No-crowd home advantage (2020-21) | Medium | Low | Tested – no change on test periods; dropped |
| 13 | Derbies, end-of-season motivation, set pieces (corners) | Low | Low | Tested – within noise; shown as notes on the Dashboard only |
| 14 | Recalibrate the market-based model's draw rate for 2024-26 (draws under-predicted) | Medium | Low | Untested – watch for one more season before acting |
| 15 | Championship (E1) results and odds to rate promoted clubs before they arrive | Medium | Medium | Untested – the football-data E1 files are in the same mirror |
| 16 | Live injury/availability feed (FPL `chance_of_playing`) | High | Medium | Untested – FPL API blocked here; the vaastav snapshot lags |
| 17 | Shot-level xG (per-shot model, set-piece vs open-play split) | Medium | High | Untested – no reachable shot-level source |
| 18 | Opening-to-closing line movement as an information signal | Medium | Medium | Untested – pre-closing odds exist in football-data files |
| 19 | Domestic cup fixtures for congestion | Low | Medium | Untested – no reachable fixture source |
| 20 | ClubElo ratings as a blend input | Medium | Low | Untested – snapshot timing could leak same-day results |
| 21 | Bivariate Poisson / Weibull count model instead of Dixon-Coles | Low | Medium | Untested |
| 22 | Team-specific home advantage (shrunk) | Low | Low | Untested |
| 23 | Referee tendencies (cards, penalties) | Low | Low | Untested |
| 24 | Squad market value / wage bill as a long-run prior | Medium | Medium | Untested – no free reachable source |
| 25 | Weather, kickoff time, travel distance | Low | Medium | Untested |
| 26 | Betting value / staking vs closing odds | Insight | Low | Not pursued – the model does not beat the close |
