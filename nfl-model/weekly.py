"""ONE COMMAND each week:   python3 weekly.py

  1. updates the data (first run: downloads everything, about 5 minutes; later runs: this season only, about 1 minute)
  2. rebuilds the walk-forward ratings
  3. writes the weekly report to output/: tips with win %, power rankings, strength of schedule, season projections
  4. runs a self-test and stops with an error message if anything looks wrong

Options:  --week N        report for week N (default: the next week with unplayed games)
          --season YYYY   (default: latest season)
          --no-fetch      use the data already downloaded
          --sims N        season simulations (default 20000)
Before running: if a team will start a different QB from last week, add a row to data/qb_overrides.csv.
"""
import argparse, json, os, subprocess, sys, time, warnings
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE)
import numpy as np, pandas as pd
from nflmodel.common import TEAMS, DISPLAY, DIVISIONS, CACHE, OUTPUT, config, load_games
from nflmodel.features import build_features, walk_forward, load_all
from nflmodel.extra import build_extra, adjusted_line
from nflmodel.teamtable import build_team_table
from nflmodel.views import season_views
from nflmodel.season import simulate, game_leverage

CFG = config(); TAU = CFG.get('season_tau', 4.0)
show = lambda t: DISPLAY.get(t, t)
NEEDED = ['games.csv', 'team_games.csv', 'qb_games.csv', 'injury_out.csv', 'team_games_x.csv', 'player_weeks.csv', 'nfelo.csv', 'weather_pbp.csv']


def update_data(season, fetch):
    missing = [f for f in NEEDED if not os.path.exists(os.path.join(CACHE, f))]
    run = lambda *a: subprocess.run([sys.executable, '-m', *a], check=True)
    if missing:
        print(f'First run (or cache cleared): downloading all seasons from nflverse. Missing: {", ".join(missing)}', flush=True)
        run('nflmodel.fetch_data'); run('nflmodel.fetch_extra')
    elif fetch:
        print(f'Updating {season} data from nflverse and nfelo ...', flush=True)
        run('nflmodel.fetch_data', '--current', str(season)); run('nflmodel.fetch_extra', '--current', str(season))


def qb_names(g):
    n = pd.concat([g[['home_qb_id', 'home_qb_name']].set_axis(['i', 'n'], axis=1), g[['away_qb_id', 'away_qb_name']].set_axis(['i', 'n'], axis=1)])
    return n.dropna().drop_duplicates('i', keep='last').set_index('i').n


def pct(x):
    return f'{100 * x:.0f}%' if x >= 0.005 else ('<1%' if x > 0 else '–')


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--season', type=int); ap.add_argument('--week', type=int)
    ap.add_argument('--no-fetch', action='store_true'); ap.add_argument('--sims', type=int, default=20000); a = ap.parse_args()
    t0 = time.time()
    season = a.season or (int(load_games().season.max()) if os.path.exists(os.path.join(CACHE, 'games.csv')) else int(time.strftime('%Y')))
    update_data(season, not a.no_fetch)
    data = load_all(); g = data[0]
    reg = g[(g.season == season) & (g.game_type == 'REG')]
    if reg.result.isna().sum() == 0 and not a.week:
        sys.exit(f'The {season} regular season is complete; use --week to pick a week.')
    week = a.week or int(reg[reg.result.isna()].week.min())
    f = build_extra(build_features(CFG['ratings'], data=data, force=True), g, data[1], cache=False)
    preds = walk_forward(f, CFG['features'], [season], **CFG.get('opts', {}))
    adj, adj_sig, adj_coef = adjusted_line(f, season, CFG['line_adjust'])
    T = build_team_table(f, data, [season])
    names = qb_names(g); gi = g.set_index('game_id')

    # ---------------- tips
    cur = preds[preds.week == week].merge(adj[['game_id', 'pred_adj', 'prob_adj']], on='game_id', how='left')
    qn = lambda i: names.get(i, str(i).replace('override:', '')) if isinstance(i, str) else '?'
    tips = []
    for r in cur.itertuples():
        x = gi.loc[r.game_id]; has_line = r.spread_line == r.spread_line
        p_tip = r.prob_adj if has_line else r.prob; m_tip = r.pred_adj if has_line else r.pred
        tip = r.home_team if m_tip >= 0 else r.away_team
        hq = x.home_qb_id if isinstance(x.home_qb_id, str) else r.qbid_h
        aq = x.away_qb_id if isinstance(x.away_qb_id, str) else r.qbid_a
        if has_line:
            line = f'{show(r.home_team)} -{r.spread_line:g}' if r.spread_line > 0 else (f'{show(r.away_team)} -{-r.spread_line:g}' if r.spread_line < 0 else 'pick em')
        else:
            line = 'no line yet'
        tips.append({'Kickoff (ET)': f'{x.weekday[:3]} {pd.Timestamp(x.gameday).strftime("%d %b")} {x.gametime}',
                     'Game': f'{show(r.away_team)} @ {show(r.home_team)}' + (' (neutral)' if x.neutral else ''),
                     'TIP': show(tip), 'Win %': round(100 * max(p_tip, 1 - p_tip)), 'Line': line,
                     'Model only': f'{show(r.home_team) if r.pred >= 0 else show(r.away_team)} {round(100 * max(r.prob, 1 - r.prob))}%',
                     'QBs (away / home)': f'{qn(aq)} / {qn(hq)}',
                     '_p': p_tip, '_pm': r.prob, '_line': r.spread_line, '_model': r.pred, '_adj': r.pred_adj})
    tips = pd.DataFrame(tips)

    # ---------------- power rankings and season views
    now = T[T.week == week].set_index('team'); prev = T[T.week == week - 1].set_index('team') if week > 1 else None
    v = season_views(g, T, preds, season, week)
    rk = now.power_qb.rank(ascending=False, method='first').astype(int)
    prk = prev.power_qb.rank(ascending=False, method='first').astype(int) if prev is not None and not prev.empty else None

    # ---------------- season simulation
    proj, sims = simulate(g, season, week, dict(zip(now.index, now.power_qb)), now.hfa.iloc[0], now.sigma.iloc[0],
                          tau=TAU, n=a.sims, seed=season * 100 + week, return_sims=True)
    proj = proj.set_index('team'); lev = game_leverage(sims)

    # ---------------- tables
    def rec(t):
        w, l = v.wins[t], v.losses[t]; ties = int(round((w % 1) * 2))
        return f'{int(w)}-{int(l)}' + (f'-{ties}' if ties else '')
    def mv(t):
        if prk is None: return ''
        d = int(prk[t] - rk[t]); return f'▲{d}' if d > 0 else (f'▼{-d}' if d < 0 else '–')
    nn = lambda x: int(x) if x == x else '–'
    order = rk.sort_values().index
    rank_tbl = pd.DataFrame([{'Rank': rk[t], 'Move': mv(t), 'Team': show(t), 'Record': rec(t), 'Power': f'{now.power_qb[t]:+.1f}',
                              'Off rank': v.off_rank[t], 'Def rank': v.def_rank[t], 'Exp. wins': f'{v.exp_wins[t]:.1f}', 'Luck': f'{v.luck[t]:+.1f}',
                              'SOS played': nn(v.sos_past_rank[t]), 'SOS left': nn(v.sos_left_rank[t]),
                              '4-wk trend': f'{v.trend4[t]:+.1f}' if v.trend4[t] == v.trend4[t] else '–',
                              'QB now': f'{now.qb_now[t]:+.1f}' if abs(now.qb_now[t]) >= 0.5 else ''} for t in order])
    proj_rows = []
    for d in sorted(DIVISIONS):
        for t in sorted(DIVISIONS[d].split(), key=lambda t: -proj.exp_wins[t]):
            proj_rows.append({'Division': d, 'Team': show(t), 'Now': rec(t), 'Projected wins': f'{proj.exp_wins[t]:.1f}',
                              'Likely range': f'{proj.wins_p10[t]:.0f}–{proj.wins_p90[t]:.0f}', 'Win division': pct(proj.p_division[t]),
                              'Make playoffs': pct(proj.p_playoffs[t]), '#1 seed': pct(proj.p_seed1[t])})
    proj_tbl = pd.DataFrame(proj_rows)
    sched = v.sort_values('schedule_wins'); hurt = sched.head(5); helped = sched.tail(5).iloc[::-1]
    fmt_s = lambda d: ', '.join(f'{show(t)} ({x:+.1f} wins)' for t, x in d.schedule_wins.items())
    left = v.sort_values('sos_left', ascending=False)
    travel = v.assign(score=v.rest_deficit_left + v.short_weeks_left * 2 + v.miles_left / 2000 + v.body_clock_left).sort_values('score', ascending=False).head(6)
    travel_tbl = pd.DataFrame([{'Team': show(t), 'Rest days given up': int(r.rest_deficit_left), 'Short weeks': r.short_weeks_left,
                                'Travel miles': f'{r.miles_left:,.0f}', 'Early body-clock games': r.body_clock_left} for t, r in travel.iterrows()])

    # ---------------- self-test: a broken run should be obvious
    checks = []
    def chk(ok, msg, fatal=True): checks.append(('PASS' if ok else ('FAIL' if fatal else 'WARN'), msg))
    n_sched = len(reg[reg.week == week])
    chk(len(tips) == n_sched and n_sched > 0, f'{len(tips)} of {n_sched} scheduled week-{week} games have predictions')
    chk(bool(tips._p.between(0.01, 0.99).all() and tips._pm.between(0.01, 0.99).all()), 'all win probabilities are between 1% and 99%')
    chk(bool(tips._line.notna().all()), f'{tips._line.notna().sum()} of {len(tips)} games have a betting line (games without one are tipped by the model)', fatal=False)
    chk(bool(cur.nfelo_pts.notna().all()), 'nfelo has a forecast for every game this week (missing ones use 0 for that input)', fatal=False)
    chk(bool(now.power_qb.notna().all() and len(now) == 32), '32 teams ranked, no missing ratings')
    last_done = int(reg[reg.result.notna()].week.max()) if reg.result.notna().any() else 0
    chk(last_done == week - 1 or week == 1, f'latest completed week in the data is {last_done} (report is for week {week})', fatal=False)
    npo = 14 if season >= 2020 else 12
    chk(abs(proj.p_playoffs.sum() - npo) < 0.01 and abs(proj.p_division.sum() - 8) < 0.01 and abs(proj.p_seed1.sum() - 2) < 0.01,
        f'simulation: playoff spots {proj.p_playoffs.sum():.2f}/{npo}, division winners {proj.p_division.sum():.2f}/8, #1 seeds {proj.p_seed1.sum():.2f}/2')
    chk(abs(proj.exp_wins.sum() - len(reg)) < 1.0, f'projected wins add up to games played ({proj.exp_wins.sum():.1f} vs {len(reg)})')
    man_p = os.path.join(CACHE, 'manifest.json')
    fetched = json.load(open(man_p)).get('games.csv', {}).get('fetched', 'unknown') if os.path.exists(man_p) else 'unknown'
    done = preds[(preds.week < week) & preds.result.notna() & (preds.result != 0)]
    acc = (np.sign(done.pred) == np.sign(done.result)).mean() if len(done) else np.nan

    # ---------------- report
    show_tips = tips[[c for c in tips.columns if not c.startswith('_')]]
    L = [f'# NFL {season}, Week {week}', '',
         f'Data downloaded {fetched}. Every number uses only games played before this week.', '',
         '## Tips', '',
         '**TIP** = the betting line plus two small tested corrections (special teams, market drift). It was the most accurate method in '
         '15 seasons of testing, but it ties the line rather than beating it. **Model only** ignores the betting line (about 1.5 percentage '
         f'points fewer tips right historically). Win % assumes results spread around the expected margin by about {adj_sig:.0f} points.', '',
         show_tips.to_markdown(index=False), '']
    if not lev.empty:
        L += ["**Biggest games for the playoff race** (how much each team's playoff chance swings between winning and losing):", '']
        L += [f'- {show(r.away)} @ {show(r.home)}: {show(r.home)} playoff chance swings {r.swing_home * 100:.0f} points, {show(r.away)} {r.swing_away * 100:.0f} points' for r in lev.itertuples()]
        L.append('')
    L += ['## Power rankings', '',
          "**Power** = expected margin against an average team on a neutral field, in points, with this week's starting QB. "
          '**Off/Def rank** = opponent-adjusted EPA per play. **Exp. wins** = sum of the model\'s pre-game win chances in games played; '
          '**Luck** = actual wins minus expected (+ = record flattered; in testing expected wins predicted the rest of the season better than the record). '
          '**SOS** rank 1 = hardest schedule played / still to play, adjusted for opponent strength and the QB each opponent had. '
          '**4-wk trend** = change in power over 4 weeks (for interest only: trend did not predict the rest of the season). '
          "**QB now** = this week's starting-QB adjustment, shown when 0.5 pts or more.", '',
          rank_tbl.to_markdown(index=False), '',
          '## Season projections', '',
          f'{a.sims:,} simulations of the remaining schedule. Each run gives every team a season-long strength error (SD {TAU:.0f} pts) on top of '
          'game-to-game randomness. That setting was chosen on 2012–19 and checked on 2020–25, where simulated playoff chances matched reality '
          '(teams given 40–60% made it 49% of the time). "Likely range" = 10th–90th percentile of wins; in testing it held the final total about 86% '
          'of the time. Tiebreakers are simplified (wins, then division record, then conference record).', '',
          proj_tbl.to_markdown(index=False), '',
          '## Strength of schedule', '',
          '"Schedule effect" = wins an average team would have gained (+) or lost (−) from the schedule played, compared with a league-average one.', '',
          f'- **Records flattered by an easy schedule:** {fmt_s(helped)}',
          f'- **Records hurt by a hard schedule:** {fmt_s(hurt)}',
          '- **Hardest remaining schedules:** ' + ', '.join(f'{show(t)} ({x:+.1f} pts/game)' for t, x in left.sos_left.head(5).items()),
          '- **Easiest remaining schedules:** ' + ', '.join(f'{show(t)} ({x:+.1f} pts/game)' for t, x in left.sos_left.tail(5).iloc[::-1].items()), '',
          '## Rest and travel still to come', '',
          'For information only: in testing, rest, byes, travel and time zones did not measurably change results once team strength was known.', '',
          travel_tbl.to_markdown(index=False), '',
          '## Self-test', ''] + [f'- {s}: {m}' for s, m in checks]
    if len(done):
        L += ['', f'Model-only tips so far this season (walk-forward): {acc * 100:.1f}% of {len(done)} games.']
    os.makedirs(OUTPUT, exist_ok=True); tag = f'{season}_wk{week:02d}'
    open(os.path.join(OUTPUT, f'{tag}.md'), 'w').write('\n'.join(L) + '\n')
    show_tips.assign(**{'TIP margin (home)': tips._adj.round(1), 'Model margin (home)': tips._model.round(1)}).to_csv(os.path.join(OUTPUT, f'{tag}_tips.csv'), index=False)
    full = v.join(now[['power_qb', 'market', 'results', 'epa_off', 'epa_def', 'special_teams', 'fourth_down', 'nfelo', 'qb_now']]).join(proj, rsuffix='_sim')
    full.insert(0, 'rank', rk); full.index = [show(t) for t in full.index]
    full.sort_values('rank').round(3).to_csv(os.path.join(OUTPUT, f'{tag}_teams.csv'), index_label='team')
    print(f'\nNFL {season} WEEK {week} TIPS'); print(show_tips.to_string(index=False))
    print('\nSELF-TEST'); [print(f'  {s}: {m}') for s, m in checks]
    print(f'\nWritten in {time.time() - t0:.0f}s: output/{tag}.md (full report), output/{tag}_tips.csv, output/{tag}_teams.csv')
    if any(s == 'FAIL' for s, _ in checks):
        sys.exit("SELF-TEST FAILED: see the FAIL lines above. Don't use this week's output until it's fixed.")
    print('SELF-TEST PASSED' + (' (with warnings)' if any(s == 'WARN' for s, _ in checks) else ''))


if __name__ == '__main__':
    main()
