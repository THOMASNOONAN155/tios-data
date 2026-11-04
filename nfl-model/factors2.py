"""Round 2: test every new factor walk-forward, in two tracks, with the same keep rule as round 1.

Track A (standalone): the model that does NOT see this game's betting line. Base = round-1 model.
Track B (beat the line): prediction = closing line + adjustment. Base = the closing line itself.
         A feature is kept only if line + adjustment beats the line on BOTH test periods. This is the direct
         test of "can anything beat the closing line".
Keep rule (both tracks): RMSE lower on development AND holdout, log-loss not worse (tolerance 0.0002) on either.
Development = 2012-19 (2015-19 for injury-report features, whose data start in 2013; fixed before testing).
Holdout = 2020-25. 2026 is not used here.
Also tests gradient boosting and model combinations. Writes results/round2_log.csv, results/round2_selected.json.
"""
import json, sys, warnings
import numpy as np, pandas as pd
from scipy.stats import norm
warnings.filterwarnings('ignore')
from model import build_features, load_all
from extra import build_extra
from metrics import evaluate

P = json.load(open('results/params.json')); SEL = json.load(open('results/selected.json'))
DEV, DEV_INJ, HOLD = list(range(2012, 2020)), list(range(2015, 2020)), list(range(2020, 2026))
BASE_A = SEL['features']


def load():
    data = load_all(); g = data[0]
    f = build_extra(build_features(P, data=data), g, data[1])
    gm = g.set_index('game_id')
    f['gametime'] = gm.gametime.reindex(f.game_id).values; f['weekday'] = gm.weekday.reindex(f.game_id).values
    f['total_line'] = gm.total_line.reindex(f.game_id).values
    nm = pd.read_csv('results/predictions_new.csv')[['game_id', 'pred']].rename(columns={'pred': 'model_pred'})
    f = f.merge(nm, on='game_id', how='left')
    return f


def col(f, k):
    wk = f.week.clip(upper=18).astype(float)
    base = {'const': np.ones(len(f)), 'early': np.exp(-(wk - 1) / 4.0), 'line': f.spread_line.astype(float),
            'absline': f.spread_line.abs().astype(float),
            'bigfav': (f.spread_line.abs() >= 10).astype(float), 'smallline': (f.spread_line.abs() <= 3).astype(float),
            'homedog': (f.spread_line < 0).astype(float),
            'prime': (f.weekday.isin(['Thursday', 'Monday']) | (f.gametime.fillna('13:00') >= '19:00')).astype(float),
            'qbchg': ((f.qb_h.abs() > 0.05) | (f.qb_a.abs() > 0.05)).astype(float),
            'model_edge': (f.model_pred - f.spread_line).astype(float),
            'nfelo_edge': (f.nfelo_pts - f.spread_line).astype(float),
            'highwind': (f.wind.fillna(0) >= 15).astype(float), 'tot45': (f.total_line.fillna(45) / 45.0),
            'late_season': (wk >= 13).astype(float)}
    if k in base: return base[k]
    if '*' in k:
        out = np.ones(len(f))
        for p in k.split('*'): out = out * col(f, p)
        return out
    return f[k].astype(float).fillna(0.0).values


def X_of(f, feats):
    return np.nan_to_num(np.column_stack([col(f, k) for k in feats])) if feats else np.zeros((len(f), 0))


def wf(f, feats, seasons, track='A', model='linear', gbm_params=None):
    """Walk-forward predictions. track B: target = result - line, prediction = line + fitted adjustment."""
    out = []
    for S in seasons:
        tr = f[(f.season >= (2010 if track == 'B' else 2009)) & (f.season < S) & f.result.notna() & (f.game_type == 'REG')]   # B needs model preds (2010+)
        te = f[(f.season == S) & (f.game_type == 'REG')].copy()
        if track == 'B':
            tr = tr[tr.spread_line.notna()]; te = te[te.spread_line.notna()]
        y = tr.result.values - (tr.spread_line.values if track == 'B' else 0)
        off_tr = tr.spread_line.values if track == 'B' else 0; off_te = te.spread_line.values if track == 'B' else 0
        if not feats and model == 'linear':
            p_tr = np.zeros(len(tr)); p_te = np.zeros(len(te))
        elif model == 'linear':
            Xt, Xe = X_of(tr, feats), X_of(te, feats)
            b = np.linalg.lstsq(Xt, y, rcond=None)[0]; p_tr, p_te = Xt @ b, Xe @ b
        else:
            from sklearn.ensemble import HistGradientBoostingRegressor
            Xt, Xe = X_of(tr, feats), X_of(te, feats)
            m = HistGradientBoostingRegressor(random_state=0, **(gbm_params or {})).fit(Xt, y)
            p_tr, p_te = m.predict(Xt), m.predict(Xe)
            if model == 'gbm+linear':   # average with the linear fit on the same features
                b = np.linalg.lstsq(Xt, y, rcond=None)[0]; p_tr, p_te = (p_tr + Xt @ b) / 2, (p_te + Xe @ b) / 2
        # sigma from honest in-training residuals for linear; for GBM, in-sample residuals are too small, so use
        # the residual SD of a linear fit on the same data (conservative and comparable)
        if model == 'linear':
            sig = np.sqrt(np.mean((y - p_tr) ** 2))
        else:
            Xt = X_of(tr, feats); bl = np.linalg.lstsq(Xt, y, rcond=None)[0]; sig = np.sqrt(np.mean((y - Xt @ bl) ** 2))
        te['pred'] = off_te + p_te; te['prob'] = norm.cdf(te.pred / sig)
        out.append(te)
    return pd.concat(out)


def score(f, feats, seasons, **kw):
    return evaluate(wf(f, feats, seasons, **kw))


def compare(f, base, cand, dev, track, **kw):
    b_d, b_h = score(f, base, dev, track=track), score(f, base, HOLD, track=track)
    c_d, c_h = score(f, cand, dev, track=track, **kw), score(f, cand, HOLD, track=track, **kw)
    r = dict(dev_dRMSE=c_d['RMSE'] - b_d['RMSE'], hold_dRMSE=c_h['RMSE'] - b_h['RMSE'], dev_dLL=c_d['LogLoss'] - b_d['LogLoss'],
             hold_dLL=c_h['LogLoss'] - b_h['LogLoss'], dev_dTips=(c_d['SU_acc'] - b_d['SU_acc']) * 100,
             hold_dTips=(c_h['SU_acc'] - b_h['SU_acc']) * 100, dev_tips=c_d['SU_acc'] * 100, hold_tips=c_h['SU_acc'] * 100,
             dev_ATS=c_d['ATS_pct'] * 100, hold_ATS=c_h['ATS_pct'] * 100)
    kept = r['dev_dRMSE'] < 0 and r['hold_dRMSE'] < 0 and r['dev_dLL'] <= 2e-4 and r['hold_dLL'] <= 2e-4
    worse = r['dev_dRMSE'] > 0 and r['hold_dRMSE'] > 0
    r['verdict'] = 'HELPED (kept)' if kept else ('HURT' if worse else 'NO CLEAR EFFECT')
    return r


INJ = lambda k: k.startswith('inj_')
EPA_VARIANTS = ['epa_early', 'epa_rz', 'epa_to50', 'epa_fl50', 'epa_noto', 'epa_pass', 'epa_run', 'epa_gt']

CAND_A = (
    [(f'EPA variant: {v} (replaces EPA off/def)', 'replace', [v + '_off_d', v + '_def_d'], 'Better EPA') for v in EPA_VARIANTS] +
    [(f'EPA variant: {v} (added)', 'add', [v + '_off_d', v + '_def_d'], 'Better EPA') for v in EPA_VARIANTS] +
    [('EPA: not opponent-adjusted (added)', 'add', ['epa_raw_d'], 'Better EPA'),
     ('EPA: pass and run separately (added together)', 'add', ['epa_pass_off_d', 'epa_pass_def_d', 'epa_run_off_d', 'epa_run_def_d'], 'Better EPA'),
     ('Players: offensive line out (snap share)', 'add', ['inj_ol_d'], 'Players'),
     ('Players: WR/TE out (target share)', 'add', ['inj_wrte_d'], 'Players'),
     ('Players: RB out (snap share)', 'add', ['inj_rb_d'], 'Players'),
     ('Players: pass rushers out (pressure share)', 'add', ['inj_rush_d'], 'Players'),
     ('Players: cornerbacks out (snap share)', 'add', ['inj_cb_d'], 'Players'),
     ('Players: safeties out (snap share)', 'add', ['inj_s_d'], 'Players'),
     ('Players: linebackers out (snap share)', 'add', ['inj_lb_d'], 'Players'),
     ('Players: count of 60%+ snap starters out', 'add', ['inj_starters_d'], 'Players'),
     ('Players: all position groups together', 'add', ['inj_ol_d', 'inj_wrte_d', 'inj_rb_d', 'inj_rush_d', 'inj_cb_d', 'inj_s_d', 'inj_lb_d'], 'Players'),
     ('Play calling: pass rate over expected', 'add', ['proe_d'], 'Play calling'),
     ('Play calling: pace (seconds per play)', 'add', ['pace_d'], 'Play calling'),
     ('Play calling: no-huddle rate', 'add', ['nohuddle_d'], 'Play calling'),
     ('Coaching: 4th-down aggressiveness', 'add', ['go4_d'], 'Coaching'),
     ('Coaching: new head coach this season', 'add', ['newcoach_d'], 'Coaching'),
     ('Coaching: new head coach x early season', 'add', ['newcoach_d*early'], 'Coaching'),
     ('Coaching: mid-season coaching change', 'add', ['midchange_d'], 'Coaching'),
     ('Special teams: EPA per game', 'add', ['st_d'], 'Special teams'),
     ('Special teams: EPA, opponent-adjusted', 'add', ['st_opp_d'], 'Special teams'),
     ('Penalties: penalty yards per game (recent)', 'add', ['pen_d'], 'Penalties'),
     ('Penalties: penalty yards per game (long memory)', 'add', ['pen_long_d'], 'Penalties'),
     ('Luck: one-score game record (recent)', 'add', ['close_luck_d'], 'Luck'),
     ('Luck: one-score game record (season to date)', 'add', ['close_luck_season_d'], 'Luck'),
     ('Luck: fumble recoveries above 50/50', 'add', ['fum_luck_d'], 'Luck'),
     ('Other source: nfelo QB-adjusted Elo', 'add', ['nfelo_qb_d'], 'Other data'),
     ('Other source: nfelo forecast (as points)', 'add', ['nfelo_pts'], 'Other data')])

CAND_B = [
    ('Line + constant (bias toward home/away)', ['const'], 'Situations'),
    ('Line + new model\'s disagreement with the line', ['model_edge'], 'Model + line'),
    ('Line + nfelo\'s disagreement with the line', ['nfelo_edge'], 'Other data'),
    ('Big favourites (line 10+): line too big/small', ['line*bigfav'], 'Situations'),
    ('Big underdogs (line 10+): flat bonus for the dog', ['bigfav*line'], 'Situations'),
    ('Close lines (3 or less): flat home bias', ['smallline'], 'Situations'),
    ('Home underdogs', ['homedog'], 'Situations'),
    ('Early season: line too big/small', ['line*early'], 'Situations'),
    ('Early season: model disagreement weighted up', ['model_edge*early'], 'Situations'),
    ('Late season (week 13+): line too big/small', ['line*late_season'], 'Situations'),
    ('After a QB change: line under-reacts', ['qb_d*qbchg'], 'Situations'),
    ('After a QB change: model disagreement weighted up', ['model_edge*qbchg'], 'Situations'),
    ('Prime-time games: line too big/small', ['line*prime'], 'Situations'),
    ('Prime-time games: home bias', ['prime'], 'Situations'),
    ('Divisional games: line too big/small', ['line*div'], 'Situations'),
    ('High-total games: line scales with total', ['line*tot45'], 'Situations'),
    ('High wind: line too big', ['line*highwind'], 'Situations'),
    ('Rest difference vs line', ['rest_d'], 'Situations'), ('Bye vs line', ['bye_d'], 'Situations'),
    ('Travel miles vs line', ['miles_d'], 'Situations'), ('Time-zone shift vs line', ['tz_d'], 'Situations'),
    ('QB value change vs line', ['qb_d'], 'Players'),
    ('Non-QB injuries (all groups) vs line', ['inj_ol_d', 'inj_wrte_d', 'inj_rb_d', 'inj_rush_d', 'inj_cb_d', 'inj_s_d', 'inj_lb_d'], 'Players'),
    ('Pass rushers out vs line', ['inj_rush_d'], 'Players'), ('Offensive line out vs line', ['inj_ol_d'], 'Players'),
    ('Market rating vs line (recent-weeks drift)', ['mkt_d'], 'Market'),
    ('Results rating vs line', ['res_d'], 'Team strength'), ('EPA off/def vs line', ['epa_off_d', 'epa_def_d'], 'Team strength'),
    ('Luck: one-score record vs line', ['close_luck_season_d'], 'Luck'), ('Luck: fumble luck vs line', ['fum_luck_d'], 'Luck'),
    ('Special teams vs line', ['st_opp_d'], 'Special teams'), ('Penalties vs line', ['pen_long_d'], 'Penalties'),
    ('New coach x early season vs line', ['newcoach_d*early'], 'Coaching'),
    ('Pass rate over expected vs line', ['proe_d'], 'Play calling'),
]

ALL_FEATS = (['home', 'mkt_d', 'res_d', 'qb_d', 'epa_off_d', 'epa_def_d', 'sr_d', 'rest_d', 'bye_d', 'miles_d', 'tz_d', 'div', 'early',
              'inj_off_d', 'inj_def_d'] + [v + s for v in EPA_VARIANTS for s in ('_off_d', '_def_d')] +
             ['inj_ol_d', 'inj_wrte_d', 'inj_rb_d', 'inj_rush_d', 'inj_cb_d', 'inj_s_d', 'inj_lb_d', 'proe_d', 'pace_d', 'go4_d',
              'newcoach_d', 'st_opp_d', 'pen_long_d', 'close_luck_season_d', 'fum_luck_d', 'nfelo_qb_d'])


def main():
    f = load(); log = []
    def rec(track, stage, name, group, r):
        r = dict(track=track, stage=stage, factor=name, group=group, **r); log.append(r)
        pd.DataFrame(log).to_csv('results/round2_partial.csv', index=False)
        print(track, stage, name, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items() if k not in ('track', 'stage', 'factor', 'group')}, flush=True)
    # ---------------- Track A: greedy forward selection over the new candidates
    base = list(BASE_A); stage = 0
    if 'B' in sys.argv:   # Track A already run: reuse its selection
        base = BASE_A + ['st_d', 'nfelo_pts', 'go4_d']; stage = 99
    while stage < 6:
        stage += 1; res = []
        for name, how, feats, group in CAND_A:
            if how == 'replace':
                cand = [x for x in base if x not in ('epa_off_d', 'epa_def_d')] + feats
            else:
                cand = base + [x for x in feats if x not in base]
            if cand == base or set(feats) <= set(base): continue
            dev = DEV_INJ if any(INJ(x) for x in feats) else DEV
            r = compare(f, base, cand, dev, 'A'); rec('A', stage, name, group, r); res.append((r, cand, name))
        good = [x for x in res if x[0]['verdict'].startswith('HELPED')]
        if not good: break
        best = min(good, key=lambda x: x[0]['dev_dRMSE'] + x[0]['hold_dRMSE'])
        print('>>> A keeps', best[2], flush=True); base = best[1]
        log.append(dict(track='A', stage=stage, factor='>>> SELECTED: ' + best[2], group='selection'))
    sel_A = base
    # ---------------- Track A: machine learning
    for nm, model, feats, gp in (() if 'B' in sys.argv else (
            ('Gradient boosting, round-1 features', 'gbm', BASE_A, dict(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=80)),
            ('Gradient boosting, all features', 'gbm', ALL_FEATS, dict(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=80)),
            ('Gradient boosting, all features, heavier regularisation', 'gbm', ALL_FEATS, dict(max_depth=2, learning_rate=0.03, max_iter=300, min_samples_leaf=200, l2_regularization=5.0)),
            ('Average of gradient boosting and linear, all features', 'gbm+linear', ALL_FEATS, dict(max_depth=2, learning_rate=0.03, max_iter=300, min_samples_leaf=200, l2_regularization=5.0)),
            ('Linear model with ALL features (overfitting check)', 'linear', ALL_FEATS, None))):
        r = compare(f, sel_A, feats, DEV_INJ, 'A', model=model, gbm_params=gp); rec('A', 'ML', nm, 'Machine learning', r)
    # ---------------- Track B: beat the line
    baseB = []; stage = 0
    while stage < 6:
        stage += 1; res = []
        for name, feats, group in CAND_B:
            cand = baseB + [x for x in feats if x not in baseB]
            if cand == baseB: continue
            dev = DEV_INJ if any(INJ(x) for x in feats) else DEV
            r = compare(f, baseB, cand, dev, 'B'); rec('B', stage, name, group, r); res.append((r, cand, name))
        good = [x for x in res if x[0]['verdict'].startswith('HELPED')]
        if not good: break
        best = min(good, key=lambda x: x[0]['dev_dRMSE'] + x[0]['hold_dRMSE'])
        print('>>> B keeps', best[2], flush=True); baseB = best[1]
        log.append(dict(track='B', stage=stage, factor='>>> SELECTED: ' + best[2], group='selection'))
    for nm, model, feats, gp in (
            ('Gradient boosting on line residual, all features + line', 'gbm', ALL_FEATS + ['line', 'model_edge'], dict(max_depth=2, learning_rate=0.03, max_iter=300, min_samples_leaf=200, l2_regularization=5.0)),
            ('Gradient boosting on line residual, situations only', 'gbm', ['line', 'early', 'prime', 'div', 'qbchg', 'rest_d', 'bye_d', 'miles_d', 'tz_d', 'tot45', 'highwind', 'model_edge'], dict(max_depth=2, learning_rate=0.03, max_iter=300, min_samples_leaf=200, l2_regularization=5.0))):
        r = compare(f, baseB, feats, DEV_INJ, 'B', model=model, gbm_params=gp); rec('B', 'ML', nm, 'Machine learning', r)
    L = pd.DataFrame(log)
    if 'B' in sys.argv: L = pd.concat([pd.read_csv('results/round2_log_A.csv'), L])
    L.to_csv('results/round2_log.csv', index=False)
    out = dict(trackA=sel_A, trackB=baseB)
    for k, feats, tr in (('A', sel_A, 'A'), ('B', baseB, 'B')):
        out[k + '_dev'] = score(f, feats, DEV, track=tr); out[k + '_hold'] = score(f, feats, HOLD, track=tr); out[k + '_2026'] = score(f, feats, [2026], track=tr)
    out['line_dev'] = score(f, [], DEV, track='B'); out['line_hold'] = score(f, [], HOLD, track='B'); out['line_2026'] = score(f, [], [2026], track='B')
    json.dump(out, open('results/round2_selected.json', 'w'), indent=1, default=float)
    print('A', sel_A, '\nB', baseB)


if __name__ == '__main__':
    main()
