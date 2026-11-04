"""ONE COMMAND each week:   python3 weekly.py

  1. updates the data (first run: downloads everything, about 5 minutes; later runs: this season only, about 1 minute)
  2. rebuilds the walk-forward ratings
  3. writes the weekly report to output/: tips with win %, power rankings, strength of schedule, season projections
  4. reads your tipping entries from inputs/tipping_inputs.xlsx (backed up first, never written to) and rebuilds the
     tipping sheets of output/NFL_Model_<season>.xlsx (week tabs, Leaderboard, Money, My Stats, ...)
  5. runs a self-test (model, tipping maths, LibreOffice recalculation of the workbook) and stops if anything looks wrong

Options:  --week N        report for week N (default: the next week with unplayed games)
          --season YYYY   (default: latest season)
          --no-fetch      use the data already downloaded
          --sims N        season simulations (default 20000)
          --no-recalc     skip the LibreOffice recalculation check of the workbook
Before running: type this week's tips, bets, expert picks, odds and last week's scores into inputs/tipping_inputs.xlsx
(see README, "Entering your picks each week"). If a team will start a different QB from last week, add a row to data/qb_overrides.csv.
"""
import argparse, glob, hashlib, json, os, shutil, subprocess, sys, time, warnings
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE)
import numpy as np, pandas as pd
from nflmodel.common import TEAMS, DISPLAY, DIVISIONS, CACHE, OUTPUT, config, load_games
from nflmodel.features import build_features, walk_forward, load_all
from nflmodel.extra import build_extra, adjusted_line
from nflmodel.teamtable import build_team_table
from nflmodel.views import season_views
from nflmodel.season import simulate, game_leverage
from nflmodel import workbook
from nflmodel.tipping_inputs import read_inputs
from nflmodel import tipping_sheets as TSH, tipping_check as TCK
from nflmodel.tipping import MODEL, LINE

CFG = config(); TAU = CFG.get('season_tau', 4.0)
show = lambda t: DISPLAY.get(t, t)
NEEDED = ['games.csv', 'team_games.csv', 'qb_games.csv', 'injury_out.csv', 'team_games_x.csv', 'player_weeks.csv', 'nfelo.csv', 'weather_pbp.csv',
          'starters.csv', 'noise_games.csv']


def update_data(season, fetch):
    missing = [f for f in NEEDED if not os.path.exists(os.path.join(CACHE, f))]
    run = lambda *a: subprocess.run([sys.executable, '-m', *a], check=True)
    if missing:
        print(f'First run (or cache cleared): downloading all seasons from nflverse. Missing: {", ".join(missing)}', flush=True)
        run('nflmodel.fetch_data'); run('nflmodel.fetch_extra'); run('nflmodel.fetch_noise')
    elif fetch:
        print(f'Updating {season} data from nflverse and nfelo ...', flush=True)
        run('nflmodel.fetch_data', '--current', str(season)); run('nflmodel.fetch_extra', '--current', str(season)); run('nflmodel.fetch_noise', '--current', str(season))


TIP_INPUTS = os.path.join(HERE, 'inputs', 'tipping_inputs.xlsx')
TO_TIPPING = {'LA': 'LAR', 'WAS': 'WSH'}           # nflverse team codes -> the codes used in the tipping inputs


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def backup_inputs(keep=30):
    """Copy the inputs file to inputs/backups/ before anything else runs (the run never writes to the inputs file)."""
    if not os.path.exists(TIP_INPUTS): return None
    d = os.path.join(HERE, 'inputs', 'backups'); os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, f'tipping_inputs_{time.strftime("%Y%m%d_%H%M%S")}.xlsx'); shutil.copy2(TIP_INPUTS, dst)
    for old in sorted(glob.glob(os.path.join(d, 'tipping_inputs_*.xlsx')))[:-keep]: os.remove(old)
    return dst


def model_tips(preds, adj, G, upto):
    """The model's tip (and win % of that team) for every game of the season up to week `upto`, keyed by the tipping gid."""
    p = preds.merge(adj[['game_id', 'pred_adj', 'prob_adj']], on='game_id', how='left')
    key = {(r.week, frozenset((r.away, r.home))): r.gid for r in G.itertuples()}
    out = {}
    for r in p[p.week <= upto].itertuples():
        has = r.spread_line == r.spread_line and r.pred_adj == r.pred_adj
        m, ph = (r.pred_adj, r.prob_adj) if has else (r.pred, r.prob)
        h, a = TO_TIPPING.get(r.home_team, r.home_team), TO_TIPPING.get(r.away_team, r.away_team)
        gid = key.get((r.week, frozenset((a, h))))
        if gid: out[gid] = dict(tip=h if m >= 0 else a, prob=float(max(ph, 1 - ph)))
    return out


def tipping_md(t):
    if t is None: return []
    R, you = t['R'], t['you']; M = t['money'].dropna(subset=['staked'])
    top = R.sort_values('order').head(8)
    tbl = pd.DataFrame({'Rank': top['rank'].astype(int), 'Tipper': top.index, 'W–L': [f'{int(r.W)}–{int(r.L)}' for r in top.itertuples()],
                        'Win %': [f'{r.win_pct * 100:.1f}%' for r in top.itertuples()]})
    L = ['## Tipping', '',
         f"**You:** {int(R.at[you, 'W'])}–{int(R.at[you, 'L'])} ({R.at[you, 'win_pct'] * 100:.1f}%), rank #{int(R.at[you, 'rank'])} of {len(R)}. "
         f"**Model:** {int(R.at[MODEL, 'W'])}–{int(R.at[MODEL, 'L'])}. **Betting line:** {int(R.at[LINE, 'W'])}–{int(R.at[LINE, 'L'])}."]
    if len(M):
        L.append(f"**Money** (tips + spreads + over/unders, locks included): {M.pl.sum():+,.0f} on ${M.staked.sum():,.0f} staked.")
    L += ['', tbl.to_markdown(index=False), '', 'Full detail: the week tabs, Leaderboard, Money, My Stats and the other tipping sheets in the Excel workbook.', '']
    return L


def qb_names(g):
    n = pd.concat([g[['home_qb_id', 'home_qb_name']].set_axis(['i', 'n'], axis=1), g[['away_qb_id', 'away_qb_name']].set_axis(['i', 'n'], axis=1)])
    return n.dropna().drop_duplicates('i', keep='last').set_index('i').n


def pct(x):
    return f'{100 * x:.0f}%' if x >= 0.005 else ('<1%' if x > 0 else '–')


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--season', type=int); ap.add_argument('--week', type=int)
    ap.add_argument('--no-fetch', action='store_true'); ap.add_argument('--sims', type=int, default=20000)
    ap.add_argument('--no-recalc', action='store_true'); a = ap.parse_args()
    t0 = time.time()
    bak = backup_inputs(); inputs_sha = sha(TIP_INPUTS) if bak else None
    if bak: print(f'Backed up your inputs file to inputs/backups/{os.path.basename(bak)}', flush=True)
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
    tips = []; qb_now_ids = []
    for r in cur.itertuples():
        x = gi.loc[r.game_id]; has_line = r.spread_line == r.spread_line
        p_tip = r.prob_adj if has_line else r.prob; m_tip = r.pred_adj if has_line else r.pred
        tip = r.home_team if m_tip >= 0 else r.away_team
        hq = x.home_qb_id if isinstance(x.home_qb_id, str) else r.qbid_h
        aq = x.away_qb_id if isinstance(x.away_qb_id, str) else r.qbid_a
        qb_now_ids += [hq, aq]
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
    # ---------------- tipping: your entries + experts + the model and the line as two extra tippers
    tctx = None
    if os.path.exists(TIP_INPUTS):
        try:
            inp = read_inputs(TIP_INPUTS)
            G0 = TSH.T.game_log(inp)
            mt = model_tips(preds, adj, G0, week)
            tctx = TSH.compute(inp, include_new=True, model_picks=pd.Series({k: v['tip'] for k, v in mt.items()}, dtype=object),
                               model_probs=pd.Series({k: v['prob'] for k, v in mt.items()}, dtype=float))
            tctx['model_tips'] = mt
            n_wk = int((G0.week <= week).sum())
            chk(len(mt) == n_wk, f'tipping: the model has a tip for {len(mt)} of {n_wk} games in weeks 1–{week} of the inputs file', fatal=False)
            checks += [(s_, 'tipping: ' + m_) for s_, m_ in TCK.maths_checks(tctx)]
        except Exception as e:
            chk(False, f'tipping inputs could not be read: {e!r}')
    else:
        chk(False, 'inputs/tipping_inputs.xlsx not found: the tipping sheets were skipped', fatal=False)
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
          '(teams given 40–60% made it 48% of the time). "Likely range" = 10th–90th percentile of wins; in testing it held the final total about 86% '
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
          ] + tipping_md(tctx) + ['## Self-test', '']
    L_self = len(L)
    if len(done):
        L += ['', f'Model-only tips so far this season (walk-forward): {acc * 100:.1f}% of {len(done)} games.']
    os.makedirs(OUTPUT, exist_ok=True); tag = f'{season}_wk{week:02d}'
    open(os.path.join(OUTPUT, f'{tag}.md'), 'w').write('\n'.join(L) + '\n')
    show_tips.assign(**{'TIP margin (home)': tips._adj.round(1), 'Model margin (home)': tips._model.round(1)}).to_csv(os.path.join(OUTPUT, f'{tag}_tips.csv'), index=False)
    full = v.join(now[['power_qb', 'market', 'results', 'epa_off', 'epa_def', 'special_teams', 'fourth_down', 'nfelo', 'qb_now']]).join(proj, rsuffix='_sim')
    full.insert(0, 'rank', rk); full.index = [show(t) for t in full.index]
    full.sort_values('rank').round(3).to_csv(os.path.join(OUTPUT, f'{tag}_teams.csv'), index_label='team')
    xlsx = os.path.join(OUTPUT, f'NFL_Model_{season}.xlsx')
    wctx = dict(season=season, week=week, tips=show_tips, now=now, hist=T[T.week <= week], views=v, proj=proj, lev=lev, g=g,
                checks=checks, fetched=fetched, qb_now_ids=qb_now_ids, sims=a.sims, tipping=tctx)
    try:
        workbook.build(xlsx, wctx)
        chk(os.path.getsize(xlsx) > 20000, f'Excel workbook written ({os.path.basename(xlsx)}, {os.path.getsize(xlsx) // 1024} KB)')
        if tctx is not None and not a.no_recalc:
            rc = TCK.recalc(xlsx)
            if rc is None:
                chk(False, 'LibreOffice not found: workbook formulas not recalculated/checked (install LibreOffice, or use --no-recalc)', fatal=False)
            else:
                bad, wbv = TCK.scan_errors(rc); n, mm = TCK.compare(wbv, tctx); shutil.rmtree(os.path.dirname(rc), ignore_errors=True)
                chk(not bad, f'LibreOffice recalculation: {len(bad)} formula errors (#REF!, #N/A, #DIV/0!, #VALUE!, ...)' + (f': {bad[:5]}' if bad else ''))
                chk(not mm, f'recalculated week-tab and leaderboard formulas match the Python engine ({n:,} cells, {len(mm)} mismatches)' + (f': {mm[:5]}' if mm else ''))
        if tctx is not None:
            chk(sha(TIP_INPUTS) == inputs_sha, 'inputs/tipping_inputs.xlsx unchanged by this run (backed up first)')
        workbook.build(xlsx, wctx)          # rebuilt so the About sheet lists the complete self-test
    except Exception as e:
        chk(False, f'Excel workbook failed: {e!r}')
    L[L_self:L_self] = [f'- {s}: {m}' for s, m in checks]
    open(os.path.join(OUTPUT, f'{tag}.md'), 'w').write('\n'.join(L) + '\n')
    print(f'\nNFL {season} WEEK {week} TIPS'); print(show_tips.to_string(index=False))
    print('\nSELF-TEST'); [print(f'  {s}: {m}') for s, m in checks]
    print(f'\nWritten in {time.time() - t0:.0f}s: output/{tag}.md (full report), output/{tag}_tips.csv, output/{tag}_teams.csv, output/NFL_Model_{season}.xlsx')
    if any(s == 'FAIL' for s, _ in checks):
        sys.exit("SELF-TEST FAILED: see the FAIL lines above. Don't use this week's output until it's fixed.")
    print('SELF-TEST PASSED' + (' (with warnings)' if any(s == 'WARN' for s, _ in checks) else ''))


if __name__ == '__main__':
    main()
