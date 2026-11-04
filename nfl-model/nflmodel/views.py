"""Season views for the weekly report: strength of schedule, luck (expected vs actual wins), offence/defence ranks,
trend, and rest/travel still to come. Everything uses information available before `week`."""
import numpy as np, pandas as pd
from scipy.stats import norm
from nflmodel.common import TEAMS


def team_games(g, season):
    x = g[(g.season == season) & (g.game_type == 'REG')]
    rows = []
    for r in x.itertuples():
        for side, t, o, home in (('h', r.home_team, r.away_team, 1), ('a', r.away_team, r.home_team, -1)):
            rows.append(dict(game_id=r.game_id, week=r.week, team=t, opp=o, venue=0 if r.neutral else home,
                             margin=(r.result if side == 'h' else -r.result) if r.result == r.result else np.nan,
                             pf=r.home_score if side == 'h' else r.away_score, pa=r.away_score if side == 'h' else r.home_score,
                             rest=r.home_rest if side == 'h' else r.away_rest, opp_rest=r.away_rest if side == 'h' else r.home_rest,
                             miles=r.miles_h if side == 'h' else r.miles_a, tz=r.tz_h if side == 'h' else r.tz_a, ko=r.ko_local))
    return pd.DataFrame(rows)


def season_views(g, T, preds, season, week):
    """T: team table (teamtable.build_team_table). preds: walk-forward game predictions with home win 'prob'.
    Returns one row per team."""
    tg = team_games(g, season)
    cur = T[(T.season == season) & (T.week == week)].set_index('team')
    hfa, sig = cur.hfa.iloc[0], cur.sigma.iloc[0]
    played = tg[(tg.week < week) & tg.margin.notna()]; todo = tg[tg.week >= week]
    Ts = T[T.season == season].set_index(['week', 'team'])
    # difficulty of each game for an AVERAGE team, in points: opponent's rating (with the QB they actually had) + venue
    def opp_strength(r, now):
        if now: return cur.power_qb[r.opp]
        try: return Ts.loc[(r.week, r.opp)].power_qb
        except KeyError: return cur.power_qb[r.opp]
    played = played.assign(diff=[opp_strength(r, False) - r.venue * hfa for r in played.itertuples()])
    todo = todo.assign(diff=[opp_strength(r, True) - r.venue * hfa for r in todo.itertuples()])
    pr = preds[(preds.season == season) & (preds.week < week)]
    pp = pd.concat([pr[['home_team', 'prob']].set_axis(['team', 'p'], axis=1), pr[['away_team', 'prob']].assign(prob=lambda d: 1 - d.prob).set_axis(['team', 'p'], axis=1)])
    out = []
    for t in TEAMS:
        p, r = played[played.team == t], todo[todo.team == t]
        wins = float(((p.margin > 0) + 0.5 * (p.margin == 0)).sum()); n = len(p)
        avg_team_wins_past = float(norm.cdf(-p['diff'] / sig).sum())
        pf, pa = p.pf.sum(), p.pa.sum()
        tr = T[(T.season == season) & (T.team == t) & (T.week.isin([week - 4, week]))].set_index('week').power_qb
        out.append(dict(
            team=t, games=n, wins=wins, losses=float(n - wins),
            sos_past=float(p['diff'].mean()) if n else np.nan,                 # + = harder than average (pts)
            schedule_wins=avg_team_wins_past - n / 2,                          # + = easy schedule added this many wins
            sos_left=float(r['diff'].mean()) if len(r) else np.nan, games_left=len(r),
            exp_wins=float(pp[pp.team == t].p.sum()), pyth_wins=float(n * pf ** 2.37 / (pf ** 2.37 + pa ** 2.37)) if n and pf + pa else np.nan,
            off_pts=float(cur.epa_off[t]), def_pts=float(cur.epa_def[t]),
            ppg=float(p.pf.mean()) if n else np.nan, papg=float(p.pa.mean()) if n else np.nan,
            trend4=float(tr.get(week, np.nan) - tr.get(week - 4, np.nan)) if week > 4 else np.nan,
            rest_deficit_left=float(np.clip(r.opp_rest - r.rest, 0, None).sum()),
            short_weeks_left=int((r.rest <= 5).sum()), miles_left=float(r.miles.sum()),
            body_clock_left=int(((r.tz >= 2) & (r.ko <= 13.6)).sum())))
    v = pd.DataFrame(out).set_index('team')
    v['luck'] = v.wins - v.exp_wins
    v['off_rank'] = v.off_pts.rank(ascending=False, method='min').astype(int)
    v['def_rank'] = v.def_pts.rank(ascending=False, method='min').astype(int)
    v['sos_past_rank'] = v.sos_past.rank(ascending=False, method='min')       # 1 = hardest so far
    v['sos_left_rank'] = v.sos_left.rank(ascending=False, method='min')       # 1 = hardest remaining
    return v
