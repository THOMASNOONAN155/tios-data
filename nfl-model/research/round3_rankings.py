"""Round 3, part A1 + A4: what makes a power ranking accurate, and which method is best.

Accuracy of the ranking published before week w (walk-forward, weeks 2-17), measured on seasons it was not tuned on:
  ros_acc      share of ALL remaining regular-season games won by the higher-ranked team   (main measure)
  next_acc     same, next week's games only (a lagging ranking does worse here)
  ros_corr     rank correlation of team score with each team's remaining-season average margin
  stability    average number of places a team moves per week (lower = steadier)
Keep rule: a method replaces the current one only if ros_acc is higher on BOTH development (2012-19) and holdout (2020-25).
Also tests luck-adjusted records, offence/defence rankings and recent trend (A4). Writes results/round3_rankings.md + csv.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import warnings; warnings.filterwarnings('ignore')
import numpy as np, pandas as pd
from scipy.stats import spearmanr, norm
from nflmodel.common import RESULTS, CACHE, TEAMS, config
from nflmodel.features import build_features, load_all
from nflmodel.extra import build_extra
from nflmodel.teamtable import build_team_table
import baseline

DEV, HOLD = range(2012, 2020), range(2020, 2026)


def team_game_results(g):
    x = g[(g.game_type == 'REG') & g.result.notna()]
    a = x[['season', 'week', 'home_team', 'away_team', 'result', 'home_score', 'away_score']].copy()
    h = a.rename(columns={'home_team': 'team', 'away_team': 'opp', 'home_score': 'pf', 'away_score': 'pa'}); h['margin'] = h.result
    v = a.rename(columns={'away_team': 'team', 'home_team': 'opp', 'away_score': 'pf', 'home_score': 'pa'}); v['margin'] = -v.result
    t = pd.concat([h, v])[['season', 'week', 'team', 'opp', 'pf', 'pa', 'margin']]
    t['win'] = np.where(t.margin > 0, 1.0, np.where(t.margin < 0, 0.0, 0.5))
    return t


def methods(T, g, tg, data, f):
    """Score per (season, week, team) for each ranking method (higher = better), all known before that week."""
    X = T[['season', 'week', 'team']].copy()
    X['Model power (current, incl. QB)'] = T.power_qb
    X['Model power without QB adjustment'] = T.power
    X['Market rating only'] = T.mkt_raw; X['Results rating only'] = T.res_raw; X['EPA rating only'] = T.epa_raw
    X['nfelo QB-adjusted Elo'] = T.nfelo_raw
    # smoothed: average with previous week's score
    X = X.sort_values(['season', 'team', 'week'])
    X['Model power, 2-week average'] = X.groupby(['season', 'team'])['Model power (current, incl. QB)'].transform(lambda s: s.rolling(2, min_periods=1).mean())
    X['Model power, 3-week average'] = X.groupby(['season', 'team'])['Model power (current, incl. QB)'].transform(lambda s: s.rolling(3, min_periods=1).mean())
    # record-based (season to date)
    tr = team_game_results(g)
    cum = []
    for (s, tm), grp in tr.groupby(['season', 'team']):
        grp = grp.sort_values('week')
        for w in range(1, 19):
            p = grp[grp.week < w]
            n = len(p)
            pf, pa = p.pf.sum(), p.pa.sum()
            cum.append(dict(season=s, week=w, team=tm, wp=(p.win.sum() / n) if n else 0.5, pdg=(p.margin.sum() / n) if n else 0.0,
                            pyth=(pf ** 2.37 / (pf ** 2.37 + pa ** 2.37)) if n and pf + pa > 0 else 0.5, games=n))
    C = pd.DataFrame(cum)
    X = X.merge(C, on=['season', 'week', 'team'], how='left')
    X['Win % (record), point diff breaks ties'] = X.wp + X.pdg / 1000
    X['Point differential per game'] = X.pdg
    X['Pythagorean win %'] = X.pyth
    # original workbook power score (rebuilt per season, before week w = after week w-1)
    orig = []
    for s in sorted(T.season.unique()):
        R = baseline.season_ratings(g, tg, s)
        for w in range(2, 19):
            if (w - 1) in R:
                for i, tm in enumerate(TEAMS): orig.append((s, w, tm, R[w - 1]['PRE'][i]))
    O = pd.DataFrame(orig, columns=['season', 'week', 'team', 'Original workbook PR score'])
    X = X.merge(O, on=['season', 'week', 'team'], how='left')
    return X.drop(columns=['wp', 'pdg', 'pyth', 'games']), C, tr


def score_methods(X, tr, names, seasons, weeks=range(2, 18)):
    games = tr[tr.margin > 0]   # one row per decided game (winner's side)
    out = {n: dict(ros_hits=0, ros_n=0, next_hits=0, next_n=0, corr=[], stab=[]) for n in names}
    for s in seasons:
        xs = X[X.season == s]; gs = games[games.season == s]
        for w in weeks:
            cur = xs[xs.week == w].set_index('team'); prev = xs[xs.week == w - 1].set_index('team')
            if cur.empty: continue
            ros = gs[gs.week >= w]; nxt = gs[gs.week == w]
            rm = tr[(tr.season == s) & (tr.week >= w)].groupby('team').margin.mean()
            for n in names:
                sc = cur[n]
                if sc.isna().all(): continue
                hw = (sc.reindex(ros.team).values > sc.reindex(ros.opp).values)
                out[n]['ros_hits'] += hw.sum(); out[n]['ros_n'] += len(ros)
                hn = (sc.reindex(nxt.team).values > sc.reindex(nxt.opp).values)
                out[n]['next_hits'] += hn.sum(); out[n]['next_n'] += len(nxt)
                if len(rm) > 10: out[n]['corr'].append(spearmanr(sc.reindex(rm.index), rm).correlation)
                if not prev.empty and not prev[n].isna().all():
                    out[n]['stab'].append(np.mean(np.abs(sc.rank(ascending=False) - prev[n].reindex(sc.index).rank(ascending=False))))
    return pd.DataFrame({n: dict(ros_acc=v['ros_hits'] / max(1, v['ros_n']), next_acc=v['next_hits'] / max(1, v['next_n']),
                                 ros_corr=np.nanmean(v['corr']), stability=np.mean(v['stab']) if v['stab'] else np.nan)
                         for n, v in out.items()}).T


def main():
    cfg = config(); data = load_all(); g, tg = data[0], data[1]
    f = build_extra(build_features(cfg['ratings'], data=data), g, tg)
    T = build_team_table(f, data, list(range(2010, 2027)))
    T.to_pickle(os.path.join(CACHE, 'features', 'team_table.pkl'))
    X, C, tr = methods(T, g, tg, data, f)
    names = [c for c in X.columns if c not in ('season', 'week', 'team')]
    res = {}
    for lab, S in (('dev', DEV), ('hold', HOLD), ('2026', [2026])):
        res[lab] = score_methods(X, tr, names, S, range(2, 18) if lab != '2026' else range(2, 9))
    cur = 'Model power (current, incl. QB)'
    L = ['# Round 3: power-ranking accuracy (generated by research/round3_rankings.py)\n',
         'Ranking published before each week (weeks 2-17). **Remaining-season accuracy** = share of all remaining regular-season games won by the '
         'higher-ranked team (home field ignored, so every method is scored the same way). **Next week** = that week only. '
         '**Correlation** = rank correlation with each team\'s remaining-season average margin. **Stability** = average places moved per week.\n',
         '| Method | Remaining-season accuracy, dev | holdout | 2026 (wks 2-8) | Next-week accuracy, dev | holdout | Correlation, dev | holdout | Stability (places/wk), holdout | Verdict |',
         '|---|---|---|---|---|---|---|---|---|---|']
    rows = []
    for n in names:
        d, h, l = res['dev'].loc[n], res['hold'].loc[n], res['2026'].loc[n]
        better = d.ros_acc > res['dev'].loc[cur].ros_acc and h.ros_acc > res['hold'].loc[cur].ros_acc
        v = 'current method' if n == cur else ('**better on both: adopt**' if better else 'not better on both')
        rows.append((h.ros_acc, f"| {n} | {d.ros_acc*100:.1f}% | {h.ros_acc*100:.1f}% | {l.ros_acc*100:.1f}% | {d.next_acc*100:.1f}% | {h.next_acc*100:.1f}% | "
                                f"{d.ros_corr:.3f} | {h.ros_corr:.3f} | {h.stability:.2f} | {v} |"))
    L += [r for _, r in sorted(rows, key=lambda x: -x[0])]
    pd.concat({k: v for k, v in res.items()}).to_csv(os.path.join(RESULTS, 'round3_rankings.csv'))
    # ---------- A4: luck-adjusted record. Which season-to-date number best predicts the rest-of-season win %?
    L += ['\n## Luck: which record best predicts the rest of the season?\n',
          'For each team and each week 4-14: season-to-date win %, Pythagorean win % (from points scored/allowed), and the model\'s '
          'expected win % (average pre-game win probability in games played). Error = RMSE against the team\'s remaining-season win %.\n',
          '| Predictor | RMSE dev | RMSE holdout | Verdict |', '|---|---|---|---|']
    pre = pd.read_csv(os.path.join(RESULTS, 'predictions_new.csv'))
    gp = pd.concat([pre[['season', 'week', 'home_team', 'prob']].rename(columns={'home_team': 'team', 'prob': 'p'}),
                    pre[['season', 'week', 'away_team', 'prob']].assign(prob=lambda d: 1 - d.prob).rename(columns={'away_team': 'team', 'prob': 'p'})])
    rows = []
    for (s, tm), grp in tr.groupby(['season', 'team']):
        gpp = gp[(gp.season == s) & (gp.team == tm)]
        for w in range(4, 15):
            p, r = grp[grp.week < w], grp[grp.week >= w]
            if len(p) < 3 or len(r) < 3: continue
            pf, pa = p.pf.sum(), p.pa.sum()
            rows.append(dict(season=s, team=tm, week=w, actual=p.win.mean(), pyth=pf ** 2.37 / (pf ** 2.37 + pa ** 2.37),
                             expw=gpp[gpp.week < w].p.mean(), ros=r.win.mean()))
    Lk = pd.DataFrame(rows)
    def rm(d, c): return np.sqrt(np.mean((d[c] - d.ros) ** 2))
    for c, nm in (('actual', 'Actual win % so far'), ('pyth', 'Pythagorean win % (points for/against)'), ('expw', 'Model expected win % (pre-game probabilities)')):
        a, b = rm(Lk[Lk.season.isin(DEV)], c), rm(Lk[Lk.season.isin(HOLD)], c)
        L.append(f'| {nm} | {a:.4f} | {b:.4f} | ' + ('baseline' if c == 'actual' else ('**better than record on both**' if a < rm(Lk[Lk.season.isin(DEV)], 'actual') and b < rm(Lk[Lk.season.isin(HOLD)], 'actual') else 'not better')) + ' |')
    # ---------- offence / defence rankings vs naive points per game
    L += ['\n## Offence and defence rankings\n', 'Rank correlation, before week w (weeks 4-14), with remaining-season points scored / allowed per game.\n',
          '| Ranking | Predicts | Corr dev | Corr holdout |', '|---|---|---|---|']
    T2 = T.merge(C, on=['season', 'week', 'team'])
    acc = {k: {'dev': [], 'hold': []} for k in ('off_epa', 'off_ppg', 'def_epa', 'def_ppg')}
    for s in list(DEV) + list(HOLD):
        lab = 'dev' if s in DEV else 'hold'; ts = tr[tr.season == s]
        for w in range(4, 15):
            cur_ = T2[(T2.season == s) & (T2.week == w)].set_index('team'); p = ts[ts.week < w]; r = ts[ts.week >= w]
            if cur_.empty or r.empty: continue
            ros_pf = r.groupby('team').pf.mean(); ros_pa = r.groupby('team').pa.mean(); ppg = p.groupby('team').pf.mean(); papg = p.groupby('team').pa.mean()
            idx = ros_pf.index
            acc['off_epa'][lab].append(spearmanr(cur_.epa_off_raw.reindex(idx), ros_pf).correlation)
            acc['off_ppg'][lab].append(spearmanr(ppg.reindex(idx), ros_pf).correlation)
            acc['def_epa'][lab].append(spearmanr(cur_.epa_def_raw.reindex(idx), ros_pa).correlation)
            acc['def_ppg'][lab].append(spearmanr(papg.reindex(idx), ros_pa).correlation)
    for k, nm, what in (('off_epa', 'Offence: opponent-adjusted EPA rating', 'points scored'), ('off_ppg', 'Offence: points per game so far', 'points scored'),
                        ('def_epa', 'Defence: opponent-adjusted EPA allowed', 'points allowed'), ('def_ppg', 'Defence: points allowed per game so far', 'points allowed')):
        L.append(f"| {nm} | {what} | {np.nanmean(acc[k]['dev']):.3f} | {np.nanmean(acc[k]['hold']):.3f} |")
    # ---------- trend: does recent movement predict the rest of the season beyond the current rating?
    rows = []
    for s in list(DEV) + list(HOLD):
        ts = tr[tr.season == s]; xs = T[T.season == s]
        for w in range(6, 15):
            cur_ = xs[xs.week == w].set_index('team'); old = xs[xs.week == w - 4].set_index('team')
            r = ts[ts.week >= w]
            if cur_.empty or old.empty: continue
            exp = r.assign(e=cur_.power_qb.reindex(r.team).values - cur_.power_qb.reindex(r.opp).values).groupby('team').e.mean()
            act = r.groupby('team').margin.mean()
            for tm in act.index:
                rows.append(dict(season=s, resid=act[tm] - exp[tm], trend=cur_.power_qb[tm] - old.power_qb[tm]))
    Tr = pd.DataFrame(rows)
    L += ['\n## Trend: last 4 weeks vs season-long\n', 'Does a team\'s rating change over the last 4 weeks predict how it does over the rest of the season, beyond its current rating? '
          'Slope of remaining-season margin (above what the current rating expects) on the 4-week trend. A positive slope would mean "hot" teams keep beating expectations.\n',
          '| Period | Slope (pts of future margin per pt of trend) | Correlation |', '|---|---|---|']
    for lab, S in (('Development', DEV), ('Holdout', HOLD)):
        d = Tr[Tr.season.isin(S)]; sl = np.polyfit(d.trend, d.resid, 1)[0]
        L.append(f'| {lab} | {sl:+.3f} | {np.corrcoef(d.trend, d.resid)[0, 1]:+.3f} |')
    open(os.path.join(RESULTS, 'round3_rankings.md'), 'w').write('\n'.join(L) + '\n')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
