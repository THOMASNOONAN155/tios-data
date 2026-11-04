"""ONE COMMAND each week:   python3 weekly.py
  1. downloads the latest nflverse data for the current season (scores, lines, play-by-play, injury reports)
  2. rebuilds the walk-forward ratings
  3. writes this week's power rankings and game predictions (with win probabilities) to output/

Options: --season 2026 --week 9   (default: the first week with unplayed games)
         --no-fetch               (use data already downloaded)
Starting QBs for upcoming games: the model assumes each team's last starter. If a different QB will start,
add a row to data/qb_overrides.csv before running.
"""
import argparse, json, os, subprocess, sys, warnings
import numpy as np, pandas as pd
from scipy.stats import norm
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
from common import TEAMS, TIDX, DISPLAY, load_games
from model import build_features, walk_forward, load_all
from ratings import market_ratings, results_ratings, epa_ratings
from report import blend_with_line

P = json.load(open('results/params.json')); SEL = json.load(open('results/selected.json'))
show = lambda t: DISPLAY.get(t, t)


def team_scores(data, season, week, betas):
    """Power score = predicted margin vs an average team on a neutral field, from ratings before `week`."""
    g, tg, _, _ = data
    M = market_ratings(g, season, P['m_hl'], P['m_off'], P['m_lam'])
    R = results_ratings(g, season, P['r_hl'], P['r_off'], P['r_lam'])
    E = epa_ratings(tg, season, P['e_hl'], P['e_off'], P['e_lam'], gt=P['e_gt'], schedule=g)
    def at(w):
        k = (season, w)
        if k not in M: return None
        comp = pd.DataFrame({'market': betas['mkt_d'] * M[k][0], 'results': betas['res_d'] * R[k][0],
                             'epa_off': betas['epa_off_d'] * E[k][1], 'epa_def': betas['epa_def_d'] * E[k][2]}, index=TEAMS)
        comp['score'] = comp.sum(1); return comp
    return at(week), at(week - 1) if week > 1 else None


def record(g, season, week):
    x = g[(g.season == season) & (g.week < week) & (g.game_type == 'REG') & g.result.notna()]
    rec = {t: [0, 0, 0] for t in TEAMS}
    for r in x.itertuples():
        if r.result > 0: rec[r.home_team][0] += 1; rec[r.away_team][1] += 1
        elif r.result < 0: rec[r.away_team][0] += 1; rec[r.home_team][1] += 1
        else: rec[r.home_team][2] += 1; rec[r.away_team][2] += 1
    return {t: f'{w}-{l}' + (f'-{d}' if d else '') for t, (w, l, d) in rec.items()}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--season', type=int); ap.add_argument('--week', type=int)
    ap.add_argument('--no-fetch', action='store_true'); a = ap.parse_args()
    g0 = load_games(); season = a.season or int(g0.season.max())
    if not a.no_fetch:
        print(f'Updating {season} data from nflverse ...', flush=True)
        subprocess.run([sys.executable, 'fetch_data.py', '--current', str(season)], check=True)
    data = load_all(); g = data[0]
    reg = g[(g.season == season) & (g.game_type == 'REG')]
    week = a.week or int(reg[reg.result.isna()].week.min())
    f = build_features(P, data=data, force=True)
    hist = walk_forward(f, SEL['features'], range(2010, season + 1), **SEL['opts'])
    bl = blend_with_line(hist)
    cur = hist[(hist.season == season) & (hist.week == week)].copy()
    cb = bl[(bl.season == season) & (bl.week == week)].set_index('game_id')
    betas = {k: cur['b_' + k].iloc[0] for k in SEL['features']}
    # ---------- game predictions
    gi = g.set_index('game_id')
    rows = []
    for r in cur.itertuples():
        x = gi.loc[r.game_id]; ln = r.spread_line
        pm = r.pred; ph = r.prob
        b = cb.loc[r.game_id] if r.game_id in cb.index and not np.isnan(ln) else None
        rows.append({'Kickoff (ET)': f'{x.weekday[:3]} {x.gameday} {x.gametime}', 'Away': show(r.away_team), 'Home': show(r.home_team),
                     'Model tip': show(r.home_team) if pm >= 0 else show(r.away_team),
                     'Win %': round(100 * max(ph, 1 - ph), 1), 'Model margin (home)': round(pm, 1),
                     'Line (+ = home fav)': ln, 'Edge vs line': round(pm - ln, 1) if not np.isnan(ln) else None,
                     'Blend tip': (show(r.home_team) if b.pred >= 0 else show(r.away_team)) if b is not None else None,
                     'Blend win %': round(100 * max(b.prob, 1 - b.prob), 1) if b is not None else None,
                     'Home QB adj (pts)': round(betas['qb_d'] * r.qb_h, 1), 'Away QB adj (pts)': round(betas['qb_d'] * r.qb_a, 1),
                     'Home QB': x.home_qb_id if isinstance(x.home_qb_id, str) else r.qbid_h,
                     'Away QB': x.away_qb_id if isinstance(x.away_qb_id, str) else r.qbid_a})
    games = pd.DataFrame(rows)
    # QB ids -> names
    names = pd.concat([g[['home_qb_id', 'home_qb_name']].set_axis(['i', 'n'], axis=1), g[['away_qb_id', 'away_qb_name']].set_axis(['i', 'n'], axis=1)]).dropna().drop_duplicates('i', keep='last').set_index('i').n
    for c in ('Home QB', 'Away QB'):
        games[c] = games[c].map(lambda i: names.get(i, str(i).replace('override:', '')) if isinstance(i, str) else '?')
    # ---------- power rankings
    now, prev = team_scores(data, season, week, betas)
    qb_now = {}
    for r in cur.itertuples():
        qb_now[r.home_team] = betas['qb_d'] * r.qb_h; qb_now[r.away_team] = betas['qb_d'] * r.qb_a
    now['qb_now'] = pd.Series(qb_now).reindex(TEAMS).fillna(0)
    now['power'] = now.score + now.qb_now
    now = now.sort_values('power', ascending=False)
    now['rank'] = range(1, 33)
    if prev is not None:
        pr = prev.score.rank(ascending=False, method='first').astype(int); now['last_wk'] = pr
    rec = record(g, season, week)
    rk = pd.DataFrame({'Rank': now['rank'], 'Team': [show(t) for t in now.index], 'Record': [rec[t] for t in now.index],
                       'Power (pts vs avg)': now.power.round(1), 'Market': now.market.round(1), 'Results': now.results.round(1),
                       'EPA offence': now.epa_off.round(1), 'EPA defence': now.epa_def.round(1), 'QB this week': now.qb_now.round(1),
                       'Last week rank': now.get('last_wk', pd.Series(index=now.index, dtype=float)).values})
    os.makedirs('output', exist_ok=True)
    tag = f'{season}_wk{week:02d}'
    games.to_csv(f'output/{tag}_predictions.csv', index=False); rk.to_csv(f'output/{tag}_power_rankings.csv', index=False)
    blend_a = cb.blend_a.iloc[0] if len(cb) else float('nan')
    md = [f'# {season} Week {week}: predictions and power rankings\n',
          'Built only from games before this week. "Model" ignores this week\'s betting line; "Blend" = line + '
          f'{blend_a:.2f} x (model - line), the mix that worked best on past seasons. Historically the blend (and the line itself) '
          'picks winners slightly better than the model alone; see README.\n',
          f'Win probabilities assume results spread around the predicted margin with SD {cur.sigma.iloc[0]:.1f} pts.\n',
          '## Games\n', games.drop(columns=['Home QB adj (pts)', 'Away QB adj (pts)']).to_markdown(index=False),
          '\n## Power rankings\n', 'Power = expected margin against an average team on a neutral field (points).\n',
          rk.to_markdown(index=False)]
    open(f'output/{tag}.md', 'w').write('\n'.join(md) + '\n')
    pd.set_option('display.width', 200); pd.set_option('display.max_columns', 20)
    print(f'\n{season} WEEK {week} PREDICTIONS'); print(games.drop(columns=['Home QB adj (pts)', 'Away QB adj (pts)']).to_string(index=False))
    print(f'\nPOWER RANKINGS before week {week}'); print(rk.to_string(index=False))
    print(f'\nWritten: output/{tag}.md, output/{tag}_predictions.csv, output/{tag}_power_rankings.csv')


if __name__ == '__main__':
    main()
