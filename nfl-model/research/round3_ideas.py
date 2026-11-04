"""Round 3, part B: test the top brainstormed ideas (see IDEAS.md), same rules as rounds 1-2.

Factor ideas (tested in both tracks, keep rule = lower RMSE on development AND holdout, log-loss not worse):
  Denver altitude, team-specific home edge, referee tendency, grass/turf mismatch.
Probability ideas (keep rule = lower log-loss on development AND holdout):
  win % for the adjusted line from no-vig moneylines; logistic recalibration of the model; result spread that grows with the total.
Writes results/round3_ideas.md and .csv.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import warnings; warnings.filterwarnings('ignore')
import numpy as np, pandas as pd
from scipy.stats import norm
from nflmodel.common import RESULTS, config
from nflmodel.metrics import no_vig_prob
from factors_round2 import load, compare, DEV, HOLD, wf

CFG = config(); A, B = CFG['features'], CFG['line_adjust']


def add_ideas(f, g):
    gm = g.set_index('game_id')
    f['referee'] = gm.referee.reindex(f.game_id).values; f['surface'] = gm.surface.reindex(f.game_id).values
    f['den_home'] = ((f.home_team == 'DEN') & (f.neutral == 0)).astype(float)
    # team / referee tendencies from EARLIER seasons only, shrunk toward 0 (k = games of prior weight)
    pre = f[['game_id', 'season', 'home_team', 'referee', 'result', 'spread_line', 'model_pred', 'neutral', 'game_type']].copy()
    pre = pre[(pre.game_type == 'REG') & pre.result.notna()]
    pre['res_model'] = pre.result - pre.model_pred; pre['res_line'] = pre.result - pre.spread_line
    def tendency(key, col, k):
        out = np.zeros(len(f))
        for S in sorted(f.season.unique()):
            p = pre[(pre.season < S) & (pre.season >= S - 6) & (pre.neutral == 0)]
            st = p.groupby(key)[col].agg(['sum', 'count']); val = st['sum'] / (st['count'] + k)
            m = (f.season == S).values
            out[m] = f.loc[m, key].map(val).fillna(0).values
        return out
    f['team_hfa_model'] = tendency('home_team', 'res_model', 40) * (1 - f.neutral)
    f['team_hfa_line'] = tendency('home_team', 'res_line', 40) * (1 - f.neutral)
    f['ref_line'] = tendency('referee', 'res_line', 60)
    f['ref_model'] = tendency('referee', 'res_model', 60)
    # surface: each team's usual home surface (grass vs artificial) that season
    grass = lambda s: s.fillna('').str.contains('grass').astype(float)
    hs = g[(g.location == 'Home') & (g.game_type == 'REG')].assign(gr=lambda d: grass(d.surface)).groupby(['season', 'home_team']).gr.mean().round()
    gs = grass(f.surface)
    ah = [hs.get((s, t), np.nan) for s, t in zip(f.season, f.away_team)]
    f['surface_mismatch_away'] = (np.array(ah) != gs.values).astype(float) * (~np.isnan(np.array(ah, float)))
    return f


def prob_tests(f):
    """Log-loss / Brier of alternative win-probability methods, walk-forward, dev and holdout."""
    rows = []
    def ll(p, y): p = np.clip(p, 1e-4, 1 - 1e-4); return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    for lab, S in (('dev', DEV), ('hold', HOLD)):
        res = {}
        for s in S:
            adj = wf(f, B, [s], track='B'); mod = wf(f, A, [s], track='A')
            tr = f[(f.season >= 2010) & (f.season < s) & f.result.notna() & (f.game_type == 'REG') & f.spread_line.notna()]
            trA = wf(f, A, list(range(max(2010, s - 6), s)), track='A')   # out-of-sample model preds from earlier seasons
            y = (adj.result > 0).astype(float); keep = adj.result != 0
            mv = no_vig_prob(adj.home_moneyline.values, adj.away_moneyline.values)
            res.setdefault('Adjusted line: normal curve (current)', []).append((adj.prob.values[keep], y[keep]))
            # moneyline: no-vig market probability, shifted by the adjustment through the normal curve
            sig = adj.prob.values; z = norm.ppf(np.clip(mv, 1e-3, 1 - 1e-3)) + (adj.pred - adj.spread_line).values / 13.0
            pm = np.where(np.isnan(mv), adj.prob.values, norm.cdf(z))
            res.setdefault('Adjusted line: from no-vig moneylines + adjustment', []).append((pm[keep], y[keep]))
            # spread grows with total: sigma = a + b * total, fit on training residuals of the line
            t = tr[tr.total_line.notna()]; r2 = (t.result - t.spread_line) ** 2
            b = np.polyfit(t.total_line, np.sqrt(r2), 1)
            sg = np.clip(np.polyval(b, adj.total_line.fillna(45).values) * np.sqrt(np.mean(r2)) / np.mean(np.polyval(b, t.total_line)), 9, 18)
            res.setdefault('Adjusted line: result spread grows with the total', []).append((norm.cdf(adj.pred / sg)[keep], y[keep]))
            # model: normal vs logistic recalibration (fit on earlier seasons' out-of-sample predictions)
            ym = (mod.result > 0).astype(float); km = mod.result != 0
            res.setdefault('Model: normal curve (current)', []).append((mod.prob.values[km], ym[km]))
            from sklearn.linear_model import LogisticRegression
            ta = trA[trA.result.notna() & (trA.result != 0)]
            lr = LogisticRegression(C=1e6).fit(ta[['pred']].values, (ta.result > 0).astype(int))
            res.setdefault('Model: logistic recalibration', []).append((lr.predict_proba(mod[['pred']].values)[:, 1][km], ym[km]))
        for k, v in res.items():
            p = np.concatenate([a for a, _ in v]); y = np.concatenate([b for _, b in v])
            rows.append(dict(method=k, period=lab, logloss=ll(p, y), brier=float(np.mean((p - y) ** 2)), n=len(y)))
    return pd.DataFrame(rows)


def main():
    from nflmodel.features import load_all
    f = load(); g = load_all()[0]; f = add_ideas(f, g)
    tests = [('Denver altitude: extra home edge in Denver', 'A', A + ['den_home']), ('Denver altitude vs line', 'B', B + ['den_home']),
             ('Team-specific home edge (from earlier seasons, shrunk)', 'A', A + ['team_hfa_model']),
             ('Team-specific home edge vs line', 'B', B + ['team_hfa_line']),
             ('Referee tendency (home margin vs model, earlier seasons)', 'A', A + ['ref_model']),
             ('Referee tendency vs line', 'B', B + ['ref_line']),
             ('Grass/turf: road team on unfamiliar surface', 'A', A + ['surface_mismatch_away']),
             ('Grass/turf mismatch vs line', 'B', B + ['surface_mismatch_away'])]
    L = ['# Round 3: top brainstormed ideas (generated by research/round3_ideas.py)\n',
         '| Idea | Track | Δ RMSE dev | Δ RMSE holdout | Δ log-loss dev | Δ log-loss holdout | Δ tips dev (pts) | Δ tips holdout (pts) | Result |', '|---|---|---|---|---|---|---|---|---|']
    log = []
    for name, track, feats in tests:
        base = A if track == 'A' else B
        r = compare(f, base, feats, DEV, track); log.append(dict(idea=name, track=track, **r))
        v = {'HELPED (kept)': '**helped**', 'HURT': 'hurt', 'NO CLEAR EFFECT': 'no clear effect'}[r['verdict']]
        L.append(f"| {name} | {'standalone' if track == 'A' else 'vs line'} | {r['dev_dRMSE']:+.3f} | {r['hold_dRMSE']:+.3f} | {r['dev_dLL']:+.4f} | {r['hold_dLL']:+.4f} | {r['dev_dTips']:+.1f} | {r['hold_dTips']:+.1f} | {v} |")
        print(name, track, r['verdict'], flush=True)
    P = prob_tests(f)
    L += ['\n## Win-probability methods\n', '| Method | Log-loss dev | Log-loss holdout | Brier dev | Brier holdout | Result |', '|---|---|---|---|---|---|']
    for base_name, prefix in (('Adjusted line: normal curve (current)', 'Adjusted line'), ('Model: normal curve (current)', 'Model')):
        bd = P[(P.method == base_name) & (P.period == 'dev')].logloss.iloc[0]; bh = P[(P.method == base_name) & (P.period == 'hold')].logloss.iloc[0]
        for m in P[P.method.str.startswith(prefix)].method.unique():
            d = P[(P.method == m) & (P.period == 'dev')].iloc[0]; h = P[(P.method == m) & (P.period == 'hold')].iloc[0]
            v = 'current' if m == base_name else ('**better on both: adopt**' if d.logloss < bd and h.logloss < bh else 'not better on both')
            L.append(f'| {m} | {d.logloss:.4f} | {h.logloss:.4f} | {d.brier:.4f} | {h.brier:.4f} | {v} |')
            log.append(dict(idea=m, track='prob', dev_logloss=d.logloss, hold_logloss=h.logloss, verdict=v))
    pd.DataFrame(log).to_csv(os.path.join(RESULTS, 'round3_ideas.csv'), index=False)
    open(os.path.join(RESULTS, 'round3_ideas.md'), 'w').write('\n'.join(L) + '\n'); print('\n'.join(L))


if __name__ == '__main__':
    main()
