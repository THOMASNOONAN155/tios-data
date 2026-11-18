# Round 5, part 2: EPA + points blend inside the prediction formula (research/round5_power.py)

Walk-forward, current model features vs candidates. Negative dRMSE / dLogLoss = better.

| Candidate | dRMSE dev | dRMSE holdout | dLogLoss dev | dLogLoss holdout | Tips dev | Tips holdout | Verdict |
|---|---|---|---|---|---|---|---|
| Replace EPA off/def with EPA + points blend | +0.0358 | +0.0152 | +0.0023 | +0.0005 | 66.03% | 64.47% | HURT |
| Add points ratings next to EPA | +0.0061 | -0.0035 | -0.0000 | +0.0000 | 66.27% | 65.34% | NO CLEAR EFFECT |

Current model for reference: tips 66.03% dev, 65.40% holdout.
