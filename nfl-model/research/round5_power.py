"""Round 5, part 2: does the round-5 offence/defence rating (EPA + points blend) also improve the PREDICTION formula?

Candidates, compared with the current model (config.json 'features') by the round-2 walk-forward harness:
  replace  epa_off_d / epa_def_d  with the EPA + points blend (same scale as EPA)
  add      points-rating differences (pts_off_d, pts_def_d) next to the EPA ones
Kept only if RMSE improves on both development (2012-19) and holdout (2020-25) without worse log-loss (round-2 rule).
Writes results/round5_power.md.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import warnings; warnings.filterwarnings('ignore')
import numpy as np, pandas as pd
from nflmodel.common import RESULTS, TIDX, config
from nflmodel.features import load_all
from nflmodel.ratings import epa_ratings
import factors_round2 as F
from round5_offdef import team_table


def main():
    cfg = config(); p = cfg['ratings']
    f = F.load(); data = load_all(); g, tg = data[0], data[1]
    t = team_table(g, tg)
    E = epa_ratings(t, 2010, p['e_hl'], p['e_off'], p['e_lam'], gt=False, metric='epa', schedule=g)
    Pp = epa_ratings(t, 2010, p['e_hl'], p['e_off'], p['e_lam'], gt=False, metric='pts', schedule=g)
    cols = {k: [] for k in ('pts_off_d', 'pts_def_d', 'blend_off_d', 'blend_def_d')}
    for r in f.itertuples():
        k = (r.season, r.week)
        if k not in E or k not in Pp:
            for c in cols: cols[c].append(np.nan)
            continue
        hi, ai = TIDX[r.home_team], TIDX[r.away_team]
        eo, ed = E[k][1], E[k][2]; po, pd_ = Pp[k][1], Pp[k][2]
        bo = 0.5 * eo + 0.5 * po / po.std() * eo.std(); bd = 0.5 * ed + 0.5 * pd_ / pd_.std() * ed.std()
        cols['pts_off_d'].append(po[hi] - po[ai]); cols['pts_def_d'].append(pd_[hi] - pd_[ai])
        cols['blend_off_d'].append(bo[hi] - bo[ai]); cols['blend_def_d'].append(bd[hi] - bd[ai])
    for c, v in cols.items(): f[c] = v
    base = list(cfg['features'])
    rep = [x for x in base if x not in ('epa_off_d', 'epa_def_d')] + ['blend_off_d', 'blend_def_d']
    add = base + ['pts_off_d', 'pts_def_d']
    L = ['# Round 5, part 2: EPA + points blend inside the prediction formula (research/round5_power.py)\n',
         'Walk-forward, current model features vs candidates. Negative dRMSE / dLogLoss = better.\n',
         '| Candidate | dRMSE dev | dRMSE holdout | dLogLoss dev | dLogLoss holdout | Tips dev | Tips holdout | Verdict |', '|---|---|---|---|---|---|---|---|']
    for nm, cand in (('Replace EPA off/def with EPA + points blend', rep), ('Add points ratings next to EPA', add)):
        r = F.compare(f, base, cand, F.DEV, 'A')
        L.append(f"| {nm} | {r['dev_dRMSE']:+.4f} | {r['hold_dRMSE']:+.4f} | {r['dev_dLL']:+.4f} | {r['hold_dLL']:+.4f} | {r['dev_tips']:.2f}% | {r['hold_tips']:.2f}% | {r['verdict']} |")
        print(L[-1], flush=True)
    b = F.score(f, base, F.DEV, track='A'); h = F.score(f, base, F.HOLD, track='A')
    L.append(f"\nCurrent model for reference: tips {b['SU_acc']*100:.2f}% dev, {h['SU_acc']*100:.2f}% holdout.")
    open(os.path.join(RESULTS, 'round5_power.md'), 'w').write('\n'.join(L) + '\n'); print('\n'.join(L))


if __name__ == '__main__':
    main()
