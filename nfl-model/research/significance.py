"""Paired bootstrap significance tests quoted in the README (resampling whole weeks of the holdout seasons 2020-25).
Writes results/significance.txt (round 1) and results/significance_round2.txt (round 2)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import warnings; warnings.filterwarnings('ignore')
import numpy as np, pandas as pd
from nflmodel.common import RESULTS, config
from factors_round2 import load, wf, X_of
import baseline

CFG = config(); HOLD = range(2020, 2026)


def boot(x, stat, seed, n=2000):
    G = x.groupby(['season', 'week']); keys = list(G.groups); rng = np.random.default_rng(seed)
    o = stat(x); B = pd.DataFrame([stat(pd.concat([G.get_group(keys[i]) for i in rng.choice(len(keys), len(keys))])) for _ in range(n)])
    return [f'  {k:26s} {o[k]:+.3f}   [{B[k].quantile(.025):+.3f}, {B[k].quantile(.975):+.3f}]' for k in o]


se = lambda d, c: np.sqrt(((d[c] - d.result) ** 2).mean())
su = lambda d, c: (np.sign(d[c]) == np.sign(d.result)).mean() * 100


def ats(x, c):
    e = x[c] - x.spread_line; v = x.result - x.spread_line; m = (e != 0) & (v != 0); w = (np.sign(e[m]) == np.sign(v[m])).mean()
    return f'  ATS {w*100:.1f}% of {m.sum()}; 95% range if no skill: {50-196*np.sqrt(.25/m.sum()):.1f}%..{50+196*np.sqrt(.25/m.sum()):.1f}%; break-even at -110 is 52.4%'


def main():
    f = load()
    r1 = wf(f, CFG['round1_features'], HOLD); r2 = wf(f, CFG['features'], HOLD); adj = wf(f, CFG['line_adjust'], HOLD, track='B')
    orig = baseline.predict(HOLD)[['game_id', 'pred']].rename(columns={'pred': 'orig'})
    x = r1[['game_id', 'season', 'week', 'result', 'spread_line', 'pred']].rename(columns={'pred': 'r1'})
    x = x.merge(r2[['game_id', 'pred']].rename(columns={'pred': 'r2'}), on='game_id').merge(adj[['game_id', 'pred']].rename(columns={'pred': 'adj'}), on='game_id').merge(orig, on='game_id')
    x = x[x.result.notna() & (x.result != 0)]
    L = ['Holdout 2020-25, paired bootstrap over weeks (2000 resamples), 95% intervals:']
    L += boot(x, lambda d: dict(rmse_new_orig=se(d, 'r1') - se(d, 'orig'), rmse_new_line=se(d, 'r1') - se(d, 'spread_line'),
                               su_new_orig=su(d, 'r1') - su(d, 'orig'), su_new_line=su(d, 'r1') - su(d, 'spread_line')), 0)
    L.append(ats(x, 'r1'))
    open(os.path.join(RESULTS, 'significance.txt'), 'w').write('\n'.join(L) + '\n'); print('\n'.join(L))
    tr = f[(f.season >= 2010) & (f.season < 2026) & f.result.notna() & (f.game_type == 'REG') & f.spread_line.notna()]
    b = np.linalg.lstsq(X_of(tr, CFG['line_adjust']), tr.result - tr.spread_line, rcond=None)[0]
    M = ['Adjusted-line coefficients (fit 2010-25): ' + str(dict(zip(CFG['line_adjust'], b.round(3)))),
         'typical size of adjustment (holdout): mean |adj| = %.2f pts, games where tip differs from line: %d of %d' % ((x.adj - x.spread_line).abs().mean(), (np.sign(x.adj) != np.sign(x.spread_line)).sum(), len(x))]
    d = x[np.sign(x.adj) != np.sign(x.spread_line)]
    M.append('  in those games: adjusted line right %d, line right %d' % ((np.sign(d.adj) == np.sign(d.result)).sum(), (np.sign(d.spread_line) == np.sign(d.result)).sum()))
    M.append('Holdout 2020-25, paired bootstrap over weeks, 95% intervals:')
    M += boot(x, lambda d: dict(rmse_adj_minus_line=se(d, 'adj') - se(d, 'spread_line'), tips_adj_minus_line=su(d, 'adj') - su(d, 'spread_line'),
                               rmse_newA_minus_line=se(d, 'r2') - se(d, 'spread_line'), tips_newA_minus_line=su(d, 'r2') - su(d, 'spread_line'),
                               rmse_round2_minus_round1=se(d, 'r2') - se(d, 'r1'), tips_round2_minus_round1=su(d, 'r2') - su(d, 'r1')), 1)
    M.append(ats(x, 'adj').replace('ATS', 'ATS of adjusted line:'))
    open(os.path.join(RESULTS, 'significance_round2.txt'), 'w').write('\n'.join(M) + '\n'); print('\n'.join(M))


if __name__ == '__main__':
    main()
