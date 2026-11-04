"""Tune rating hyper-parameters on DEVELOPMENT seasons only (2012-2019), walk-forward.
Each candidate is scored by the RMSE of a walk-forward blend (betas fit on earlier seasons) on 2012-2019.
Writes results/tuning.json. The holdout seasons (2020+) are never looked at here."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # nfl-model/ on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nflmodel.common import RESULTS, INPUTS, config
import itertools, json, warnings
import numpy as np, pandas as pd
warnings.filterwarnings('ignore')
from nflmodel.common import TIDX
from nflmodel.features import load_all, FIRST_RATED, walk_forward
from nflmodel.ratings import market_ratings, epa_ratings, results_ratings
from nflmodel.metrics import evaluate

DEV = list(range(2012, 2020))


def col(g, R, idx=0):
    v = []
    for r in g.itertuples():
        x = R.get((r.season, r.week))
        if x is None: v.append(np.nan); continue
        rr = x[idx] if isinstance(x, tuple) else x
        v.append(rr[TIDX[r.home_team]] - rr[TIDX[r.away_team]])
    return np.array(v)


def score(f, feats):
    d = walk_forward(f, feats, DEV)
    e = evaluate(d); return round(e['RMSE'], 4), round(e['LogLoss'], 4)


def main():
    g, tg, qbg, inj = load_all()
    base = g[(g.season >= 2009) & (g.season <= 2019)][['game_id', 'season', 'week', 'game_type', 'home_team', 'away_team', 'result', 'spread_line',
                                                      'home_moneyline', 'away_moneyline', 'neutral']].copy()
    base['home'] = 1.0 - base.neutral
    res = {'market': [], 'epa': [], 'results': []}
    best_m = None
    for hl, off, lam in itertools.product([3, 4, 6, 8], [2, 6, 12, 20], [0.5, 2, 5]):
        f = base.copy(); f['mkt_d'] = col(f, market_ratings(g, FIRST_RATED, hl, off, lam))
        s = score(f.dropna(subset=['mkt_d']), ['home', 'mkt_d']); res['market'].append(((hl, off, lam), s)); print('market', hl, off, lam, s)
        if best_m is None or s[0] < best_m[1][0]: best_m = ((hl, off, lam), s, f['mkt_d'].values)
    base['mkt_d'] = best_m[2]
    best_e = None
    for hl, off, lam, gt in itertools.product([4, 8, 12, 16], [4, 10, 20], [3, 10, 30], [True, False]):
        f = base.copy(); f['epa_d'] = col(f, epa_ratings(tg, FIRST_RATED, hl, off, lam, gt=gt))
        s = score(f.dropna(subset=['epa_d']), ['home', 'mkt_d', 'epa_d']); res['epa'].append(((hl, off, lam, gt), s)); print('epa', hl, off, lam, gt, s)
        if best_e is None or s[0] < best_e[1][0]: best_e = ((hl, off, lam, gt), s)
    for hl, off, lam in itertools.product([4, 6, 10], [6, 15], [4, 8, 16]):
        f = base.copy(); f['res_d'] = col(f, results_ratings(g, FIRST_RATED, hl, off, lam))
        s = score(f.dropna(subset=['res_d']), ['home', 'mkt_d', 'res_d']); res['results'].append(((hl, off, lam), s)); print('results', hl, off, lam, s)
    out = {k: sorted(v, key=lambda x: x[1][0])[:8] for k, v in res.items()}
    out['best_market'] = best_m[:2]; out['best_epa'] = best_e
    json.dump(out, open(os.path.join(RESULTS, 'tuning.json'), 'w'), indent=1, default=str)
    print(json.dumps({k: out[k][:3] for k in ('market', 'epa', 'results')}, default=str, indent=1))


if __name__ == '__main__':
    main()
