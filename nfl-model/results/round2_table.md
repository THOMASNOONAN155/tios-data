
**Track A: standalone model (no betting line). Each factor added on its own to the round-1 model**

| Group | Factor | Δ RMSE dev | Δ RMSE holdout | Δ tips dev (pts) | Δ tips holdout (pts) | Result |
|---|---|---|---|---|---|---|
| Better EPA | EPA, early downs only (replacing plain EPA) | +0.013 | +0.005 | +0.0 | +0.3 | hurt |
| Better EPA | EPA, red zone only (replacing plain EPA) | +0.004 | +0.016 | +0.3 | +0.5 | hurt |
| Better EPA | EPA, turnovers at half weight (replacing plain EPA) | +0.004 | -0.010 | -0.1 | +0.0 | no clear effect |
| Better EPA | EPA, lost fumbles at half weight (replacing plain EPA) | -0.004 | -0.005 | -0.2 | -0.1 | **helped (kept)** |
| Better EPA | EPA, turnovers removed (replacing plain EPA) | +0.003 | -0.017 | -0.2 | +0.3 | no clear effect |
| Better EPA | EPA, passing plays only (replacing plain EPA) | -0.004 | +0.008 | -0.3 | +0.6 | no clear effect |
| Better EPA | EPA, running plays only (replacing plain EPA) | +0.002 | -0.000 | +0.5 | +0.6 | no clear effect |
| Better EPA | EPA, garbage time removed (replacing plain EPA) | +0.011 | +0.004 | +0.4 | +0.2 | hurt |
| Better EPA | EPA, early downs only (added to plain EPA) | +0.016 | -0.008 | -0.0 | +0.0 | no clear effect |
| Better EPA | EPA, red zone only (added to plain EPA) | +0.001 | +0.002 | -0.2 | +0.0 | hurt |
| Better EPA | EPA, turnovers at half weight (added to plain EPA) | +0.011 | +0.008 | +0.1 | -0.1 | hurt |
| Better EPA | EPA, lost fumbles at half weight (added to plain EPA) | +0.025 | +0.006 | -0.3 | -0.1 | hurt |
| Better EPA | EPA, turnovers removed (added to plain EPA) | +0.012 | +0.007 | +0.1 | -0.1 | hurt |
| Better EPA | EPA, passing plays only (added to plain EPA) | +0.008 | +0.004 | -0.0 | -0.1 | hurt |
| Better EPA | EPA, running plays only (added to plain EPA) | +0.005 | -0.000 | +0.2 | -0.2 | no clear effect |
| Better EPA | EPA, garbage time removed (added to plain EPA) | +0.014 | +0.002 | -0.2 | +0.1 | hurt |
| Better EPA | EPA: not opponent-adjusted (added) | -0.007 | +0.029 | -0.1 | +0.5 | no clear effect |
| Better EPA | EPA: pass and run separately (added together) | +0.036 | -0.006 | +0.0 | +0.2 | no clear effect |
| Players | Players: offensive line out (snap share) | +0.004 | +0.001 | -0.2 | -0.1 | hurt |
| Players | Players: WR/TE out (target share) | +0.009 | -0.019 | +0.1 | -0.3 | no clear effect |
| Players | Players: RB out (snap share) | +0.013 | -0.005 | -0.2 | -0.4 | no clear effect |
| Players | Players: pass rushers out (pressure share) | +0.024 | +0.005 | +0.2 | -0.1 | hurt |
| Players | Players: cornerbacks out (snap share) | +0.008 | -0.026 | +0.4 | +0.3 | no clear effect |
| Players | Players: safeties out (snap share) | +0.001 | -0.000 | +0.0 | -0.1 | no clear effect |
| Players | Players: linebackers out (snap share) | -0.016 | -0.003 | +0.2 | +0.2 | no clear effect |
| Players | Players: count of 60%+ snap starters out | +0.008 | -0.013 | +0.5 | -0.1 | no clear effect |
| Players | Players: all position groups together | +0.044 | -0.045 | +1.0 | +0.0 | no clear effect |
| Play calling | Play calling: pass rate over expected | +0.004 | -0.003 | -0.2 | +0.2 | no clear effect |
| Play calling | Play calling: pace (seconds per play) | +0.007 | +0.003 | -0.1 | +0.1 | hurt |
| Play calling | Play calling: no-huddle rate | +0.006 | +0.003 | +0.0 | +0.2 | hurt |
| Coaching | Coaching: 4th-down aggressiveness | -0.005 | -0.003 | +0.2 | +0.3 | **helped (kept)** |
| Coaching | Coaching: new head coach this season | +0.006 | -0.005 | -0.4 | +0.2 | no clear effect |
| Coaching | Coaching: new head coach x early season | +0.001 | -0.006 | -0.1 | +0.3 | no clear effect |
| Coaching | Coaching: mid-season coaching change | +0.009 | +0.001 | -0.0 | +0.0 | hurt |
| Special teams | Special teams: EPA per game | -0.016 | -0.027 | -0.3 | -0.4 | **helped (kept)** |
| Special teams | Special teams: EPA, opponent-adjusted | -0.014 | -0.024 | -0.3 | -0.6 | **helped (kept)** |
| Penalties | Penalties: penalty yards per game (recent) | +0.000 | +0.004 | +0.1 | +0.0 | hurt |
| Penalties | Penalties: penalty yards per game (long memory) | +0.002 | +0.003 | -0.1 | +0.1 | hurt |
| Luck | Luck: one-score game record (recent) | +0.003 | +0.003 | +0.1 | +0.2 | hurt |
| Luck | Luck: one-score game record (season to date) | +0.004 | +0.001 | +0.0 | -0.1 | hurt |
| Luck | Luck: fumble recoveries above 50/50 | +0.010 | +0.000 | -0.1 | +0.1 | hurt |
| Other data | Other source: nfelo QB-adjusted Elo | -0.017 | +0.001 | +0.3 | +0.3 | no clear effect |
| Other data | Other source: nfelo forecast (as points) | -0.026 | -0.011 | +0.0 | +0.6 | **helped (kept)** |

**Track A: machine learning and combinations, compared with the final round-2 linear model**

| Group | Factor | Δ RMSE dev | Δ RMSE holdout | Δ tips dev (pts) | Δ tips holdout (pts) | Result |
|---|---|---|---|---|---|---|
| Machine learning | Gradient boosting, round-1 features | +0.386 | +0.100 | -0.9 | -0.2 | hurt |
| Machine learning | Gradient boosting, all features | +0.353 | +0.194 | -0.9 | -0.6 | hurt |
| Machine learning | Gradient boosting, all features, heavier regularisation | +0.288 | +0.100 | -1.3 | -0.9 | hurt |
| Machine learning | Average of gradient boosting and linear, all features | +0.132 | -0.010 | +0.4 | +0.9 | no clear effect |
| Machine learning | Linear model with ALL features (overfitting check) | +0.155 | -0.005 | +0.3 | +0.9 | no clear effect |

**Track B: beat the line. Each adjustment added on its own to the closing line**

| Group | Factor | Δ RMSE dev | Δ RMSE holdout | Δ tips dev (pts) | Δ tips holdout (pts) | Result |
|---|---|---|---|---|---|---|
| Situations | Line + constant (bias toward home/away) | +0.003 | +0.001 | +0.1 | +0.0 | hurt |
| Model + line | Line + new model's disagreement with the line | -0.021 | +0.007 | +0.0 | -0.1 | no clear effect |
| Other data | Line + nfelo's disagreement with the line | -0.021 | +0.018 | -0.1 | +0.0 | no clear effect |
| Situations | Big favourites (line 10+): line too big/small | +0.004 | -0.001 | +0.0 | +0.0 | no clear effect |
| Situations | Big underdogs (line 10+): flat bonus for the dog | +0.004 | -0.001 | +0.0 | +0.0 | no clear effect |
| Situations | Close lines (3 or less): flat home bias | +0.003 | +0.001 | +0.0 | +0.0 | hurt |
| Situations | Home underdogs | -0.000 | +0.005 | +0.0 | +0.0 | no clear effect |
| Situations | Early season: line too big/small | +0.001 | +0.001 | +0.0 | +0.0 | hurt |
| Situations | Early season: model disagreement weighted up | +0.010 | -0.001 | +0.0 | +0.0 | no clear effect |
| Situations | Late season (week 13+): line too big/small | -0.002 | -0.011 | +0.0 | +0.0 | **helped (kept)** |
| Situations | After a QB change: line under-reacts | +0.008 | -0.002 | +0.2 | +0.0 | no clear effect |
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
| Players | QB value change vs line | +0.002 | +0.003 | +0.1 | +0.0 | hurt |
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
| Machine learning | Gradient boosting on line residual, all features + line | +0.187 | +0.063 | -0.8 | -0.6 | hurt |
| Machine learning | Gradient boosting on line residual, situations only | +0.159 | +0.092 | +0.2 | -1.2 | hurt |
