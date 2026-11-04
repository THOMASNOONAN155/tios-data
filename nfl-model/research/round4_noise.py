"""Round 4, part B: does separating real performance from noise improve rankings or tips?

Each adjustment is built walk-forward and tested in both tracks with the usual keep rule (lower RMSE on development
2012-19 AND holdout 2020-25, log-loss not worse): A = standalone model, B = closing line + adjustment.
  Penalties ......... EPA without penalty plays; penalty EPA as a team trait
  Luck .............. results rating without return/defensive TDs; without field-goal luck; special teams without FG luck;
                      blocked kicks as a trait
  Play impact ....... leverage-weighted EPA (plays at 50/50 count fully, decided games ~0); win-probability added;
                      big plays (20+ yards) vs the rest
  QB left the game .. games where the starting QB had under half the dropbacks count at reduced weight in the ratings
  FTN (2022+ only) .. interceptions that were not 'interception-worthy' at half weight: exploratory (cannot meet the rule)
Writes results/round4_noise.md and .csv.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import warnings; warnings.filterwarnings('ignore')
import numpy as np, pandas as pd
from nflmodel.common import RESULTS, CACHE, TEAMS, TIDX, FRANCHISE, config
from nflmodel.features import load_all
from nflmodel.extra import team_game_frame, rate_ratings, diff
from nflmodel.ratings import ridge_pair, damp, slots, _decay
from factors_round2 import load, compare, DEV, HOLD, score

CFG = config(); A, B = CFG['features'], CFG['line_adjust']; P = CFG['ratings']
FIXT = lambda s: s.replace(FRANCHISE).replace({'LAR': 'LA', 'WSH': 'WAS', 'JAC': 'JAX'})


def results_custom(g, adj_result, game_w, first=2008):
    """Results rating (same settings as the model) on an adjusted margin with per-game weights."""
    m = g.result.notna().values
    h = g.home_team.map(TIDX).values[m]; a = g.away_team.map(TIDX).values[m]
    y = damp(adj_result[m]); neu = g.neutral.values[m]; S = g.season.values[m]; W = g.week.values[m]; gw = game_w[m]
    out = {}
    for s, w in slots(g, first):
        k = ((S < s) | ((S == s) & (W < w))) & (S >= s - 3)
        if k.sum() == 0: continue
        out[(s, w)] = ridge_pair(h[k], a[k], y[k], _decay(s, w, S[k], W[k], P['r_hl'], P['r_off']) * gw[k], neu[k], P['r_lam'])
    return out


def main():
    data = load_all(); g, tg = data[0], data[1]
    f = load()
    t = team_game_frame(g, tg)
    nz = pd.read_csv(os.path.join(CACHE, 'noise_games.csv')); nz['team'] = FIXT(nz.team)
    t = t.merge(nz.drop(columns=['season', 'week', 'n']), on=['game_id', 'team'], how='left').fillna(0)
    opp = t[['game_id', 'team', 'wpa_pos', 'fg_luck', 'ret_td', 'pen_epa']].rename(columns={'team': 'opp', 'wpa_pos': 'o_wpa', 'fg_luck': 'o_fg', 'ret_td': 'o_ret', 'pen_epa': 'o_pen'})
    t = t.merge(opp, on=['game_id', 'opp'], how='left').fillna(0)
    t['wpa_net'] = t.wpa_pos - t.o_wpa; t['st_nofg'] = t.st_epa - t.fg_luck + t.o_fg
    # QB left the game: the first-dropback starter had under half the team's dropbacks
    qb = pd.read_csv(os.path.join(CACHE, 'qb_games.csv')); qb['team'] = FIXT(qb.team)
    st = pd.read_csv(os.path.join(CACHE, 'starters_pending.csv') if os.path.exists(os.path.join(CACHE, 'starters_pending.csv')) else os.path.join(CACHE, 'starters.csv'))
    st['team'] = FIXT(st.team)
    tot = qb.groupby(['game_id', 'team']).dropbacks.sum().rename('tdb')
    sdb = qb.merge(st, left_on=['game_id', 'team', 'player_id'], right_on=['game_id', 'team', 'qb_id']).groupby(['game_id', 'team']).dropbacks.sum().rename('sdb')
    sh = pd.concat([tot, sdb], axis=1).fillna(0); sh['share'] = sh.sdb / sh.tdb
    t = t.join(sh.share, on=['game_id', 'team']); t['qb_left'] = (t.share < 0.5).astype(float)
    nleft = int(t.qb_left.sum())
    E = lambda num, den, **kw: rate_ratings(t, num, den, g, 2008, hl=kw.pop('hl', P['e_hl']), off=kw.pop('off', P['e_off']), lam=kw.pop('lam', P['e_lam']), **kw)
    new = {}
    for nm, num, den in (('nopen', 'epa_nopen', 'n_nopen'), ('lev', 'epa_lev', 'lev'), ('nonexpl', 'epa_nonexpl', 'n_nonexpl'), ('expl', 'epa_expl', 'n_expl')):
        R = E(num, den); new[nm + '_off_d'] = diff(f, R, 1); new[nm + '_def_d'] = diff(f, R, 2)
    new['pen_d'] = diff(f, E('pen_epa', 'one', hl=6.0, lam=3.0), 0)
    new['wpa_d'] = diff(f, E('wpa_net', 'one', opp=False, hl=6.0, lam=3.0), 0)
    new['st_nofg_d'] = diff(f, E('st_nofg', 'one', opp=False, hl=6.0, lam=3.0), 0)
    new['blocked_d'] = diff(f, E('kicks_blocked', 'one', opp=False, hl=20.0, lam=3.0), 0)
    new['expl_share_d'] = diff(f, E('n_expl', 'n', opp=False, hl=6.0, lam=3.0), 0)
    # QB-left games down-weighted in the EPA ratings (offence rows) and in the results rating
    for wgt in (0.0, 0.5):
        t2 = t.copy(); fac = np.where(t2.qb_left == 1, wgt, 1.0)
        t2['epa_w'] = t2.epa * fac; t2['plays_w'] = t2.plays * fac
        R = rate_ratings(t2, 'epa_w', 'plays_w', g, 2008, hl=P['e_hl'], off=P['e_off'], lam=P['e_lam'])
        new[f'qbleft{wgt}_off_d'] = diff(f, R, 1); new[f'qbleft{wgt}_def_d'] = diff(f, R, 2)
        left = t[t.qb_left == 1].groupby('game_id').size()
        gw = np.where(g.game_id.isin(left.index), wgt, 1.0)
        new[f'res_qbleft{wgt}_d'] = diff(f, results_custom(g, g.result.values.astype(float), gw), 0)
    # results without return TDs / FG luck
    gi = t.groupby(['game_id', 'team'])[['ret_td', 'fg_luck']].first()
    def side(col, who):
        return np.array([gi[col].get((gid, tm), 0.0) for gid, tm in zip(g.game_id, g[who])])
    rh, ra, fh, fa = side('ret_td', 'home_team'), side('ret_td', 'away_team'), side('fg_luck', 'home_team'), side('fg_luck', 'away_team')
    res = g.result.values.astype(float); one = np.ones(len(g))
    new['res_noret_d'] = diff(f, results_custom(g, res - 7 * (rh - ra), one), 0)
    new['res_nofg_d'] = diff(f, results_custom(g, res - (fh - fa), one), 0)
    new['res_noluck_d'] = diff(f, results_custom(g, res - 7 * (rh - ra) - (fh - fa), one), 0)
    for k, v in new.items(): f[k] = v
    rep = lambda base, old, newc: [x for x in base if x not in old] + newc
    tests = [
        ('Penalties', 'EPA without penalty plays (replaces EPA)', 'A', rep(A, ['epa_off_d', 'epa_def_d'], ['nopen_off_d', 'nopen_def_d'])),
        ('Penalties', 'Penalty EPA drawn/committed as a team trait', 'A', A + ['pen_d']),
        ('Penalties', 'Penalty EPA vs line', 'B', B + ['pen_d']),
        ('Luck', 'Results rating without return/defensive TDs', 'A', rep(A, ['res_d'], ['res_noret_d'])),
        ('Luck', 'Results rating without field-goal luck', 'A', rep(A, ['res_d'], ['res_nofg_d'])),
        ('Luck', 'Results rating without return TDs and FG luck', 'A', rep(A, ['res_d'], ['res_noluck_d'])),
        ('Luck', 'Results without return TDs and FG luck vs line', 'B', B + ['res_noluck_d']),
        ('Luck', 'Special teams without field-goal luck (replaces special teams)', 'A', rep(A, ['st_d'], ['st_nofg_d'])),
        ('Luck', 'Special teams without FG luck vs line', 'B', rep(B, ['st_opp_d'], ['st_nofg_d'])),
        ('Luck', 'Blocked kicks allowed as a team trait', 'A', A + ['blocked_d']),
        ('Play impact', 'Leverage-weighted EPA (replaces EPA)', 'A', rep(A, ['epa_off_d', 'epa_def_d'], ['lev_off_d', 'lev_def_d'])),
        ('Play impact', 'Win-probability added per game (added)', 'A', A + ['wpa_d']),
        ('Play impact', 'Win-probability added vs line', 'B', B + ['wpa_d']),
        ('Play impact', 'EPA excluding big plays (replaces EPA)', 'A', rep(A, ['epa_off_d', 'epa_def_d'], ['nonexpl_off_d', 'nonexpl_def_d'])),
        ('Play impact', 'Big-play and other EPA weighted separately', 'A', rep(A, ['epa_off_d', 'epa_def_d'], ['nonexpl_off_d', 'nonexpl_def_d', 'expl_off_d', 'expl_def_d'])),
        ('Play impact', 'Big-play dependence (share of plays 20+ yds)', 'A', A + ['expl_share_d']),
        ('Players leaving', 'QB-left games dropped from EPA ratings', 'A', rep(A, ['epa_off_d', 'epa_def_d'], ['qbleft0.0_off_d', 'qbleft0.0_def_d'])),
        ('Players leaving', 'QB-left games at half weight in EPA ratings', 'A', rep(A, ['epa_off_d', 'epa_def_d'], ['qbleft0.5_off_d', 'qbleft0.5_def_d'])),
        ('Players leaving', 'QB-left games at half weight in results rating', 'A', rep(A, ['res_d'], ['res_qbleft0.5_d'])),
        ('Players leaving', 'QB-left games dropped from results rating', 'A', rep(A, ['res_d'], ['res_qbleft0.0_d'])),
        ('Players leaving', 'QB-left games half weight (EPA + results)', 'A', rep(A, ['epa_off_d', 'epa_def_d', 'res_d'], ['qbleft0.5_off_d', 'qbleft0.5_def_d', 'res_qbleft0.5_d'])),
    ]
    L = ['# Round 4: real performance vs noise (generated by research/round4_noise.py)\n',
         f'"QB left the game" = the starting QB (first dropback) had under half his team\'s dropbacks: {nleft} team-games since 2006.\n',
         '| Group | Adjustment | Track | Δ RMSE dev | Δ RMSE holdout | Δ log-loss dev | Δ log-loss holdout | Δ tips dev (pts) | Δ tips holdout (pts) | Result |', '|---|---|---|---|---|---|---|---|---|---|']
    log = []
    for grp, name, track, feats in tests:
        r = compare(f, A if track == 'A' else B, feats, DEV, track); log.append(dict(group=grp, adjustment=name, track=track, **r))
        v = {'HELPED (kept)': '**helped**', 'HURT': 'hurt', 'NO CLEAR EFFECT': 'no clear effect'}[r['verdict']]
        L.append(f"| {grp} | {name} | {'standalone' if track == 'A' else 'vs line'} | {r['dev_dRMSE']:+.3f} | {r['hold_dRMSE']:+.3f} | {r['dev_dLL']:+.4f} | {r['hold_dLL']:+.4f} | {r['dev_dTips']:+.1f} | {r['hold_dTips']:+.1f} | {v} |")
        print(name, track, r['verdict'], flush=True)
    # FTN exploratory: interceptions that were not interception-worthy at half weight (2022+ only)
    q = pd.read_csv(os.path.join(CACHE, 'qb_ftn.csv')); q['team'] = FIXT(q.team)
    qt = q.groupby(['game_id', 'team'])[['ints', 'int_worthy']].sum().rename(columns={'ints': 'ftn_ints'})
    t3 = t.join(qt, on=['game_id', 'team']).fillna({'ftn_ints': 0, 'int_worthy': 0})
    lucky = (t3.ftn_ints - t3.int_worthy.clip(upper=t3.ftn_ints)).clip(lower=0)      # INTs on throws FTN did not chart as interception-worthy
    t3['epa_ftn'] = t3.epa + 0.5 * 4.0 * lucky                                  # ~4 EPA per INT; give half of it back
    R = rate_ratings(t3, 'epa_ftn', 'plays', g, 2008, hl=P['e_hl'], off=P['e_off'], lam=P['e_lam'])
    f['ftn_off_d'] = diff(f, R, 1); f['ftn_def_d'] = diff(f, R, 2)
    ex = [x if x not in ('epa_off_d', 'epa_def_d') else {'epa_off_d': 'ftn_off_d', 'epa_def_d': 'ftn_def_d'}[x] for x in A]
    s0, s1 = score(f, A, range(2023, 2026)), score(f, ex, range(2023, 2026))
    L += ['\n**FTN charting (exploratory, 2022+ only so it cannot meet the two-period rule):** EPA with non-interception-worthy interceptions '
          f'half-forgiven, tested on 2023–25 only: RMSE {s1["RMSE"] - s0["RMSE"]:+.3f}, log-loss {s1["LogLoss"] - s0["LogLoss"]:+.4f}, tips {(s1["SU_acc"] - s0["SU_acc"]) * 100:+.1f} pts. '
          'Not adopted; shown as the "adjusted interception rate" stat instead.\n',
          '**Hail Marys** (40+ air-yard completions in the last 10 seconds of a half): about one touchdown per season league-wide, too rare to test or matter.']
    log.append(dict(group='Turnover blame', adjustment='FTN interception-worthy (exploratory 2023-25)', track='A', hold_dRMSE=s1['RMSE'] - s0['RMSE'], verdict='exploratory only'))
    pd.DataFrame(log).to_csv(os.path.join(RESULTS, 'round4_noise.csv'), index=False)
    open(os.path.join(RESULTS, 'round4_noise.md'), 'w').write('\n'.join(L) + '\n'); print('\n'.join(L))


if __name__ == '__main__':
    main()
