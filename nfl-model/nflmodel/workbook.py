"""The weekly Excel workbook (output/NFL_Model_<season>.xlsx), rebuilt by weekly.py every week.

Same colour theme as the original NFL_Tipping workbook (navy #17202B / #243447, gold #C99A2E, paper #F4F6F9, Arial).
All tipping/betting tracking from the original is gone; the stats and model views are kept and extended.
"""
import os
import numpy as np, pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import ColorScaleRule, DataBarRule
from openpyxl.chart import LineChart, ScatterChart, BarChart, Reference, Series
from openpyxl.chart.label import DataLabelList
from openpyxl.utils import get_column_letter as COL
from nflmodel.common import DISPLAY, DIVISIONS, CACHE, RAW, FRANCHISE

NAVY, SLATE, ACCENT, GOLD, PAPER, GREY, WHITE, INK = '17202B', '243447', '2E4A66', 'C99A2E', 'F4F6F9', '6B7280', 'FFFFFF', '1F2937'
RED, MID, GREEN = 'E8A09A', 'FFFFFF', '9FD0B0'
FONT = 'Arial'
show = lambda t: DISPLAY.get(t, t)
FIXT = lambda s: s.replace(FRANCHISE).replace({'LAR': 'LA', 'WSH': 'WAS', 'JAC': 'JAX'})
thin = Side(style='thin', color='D9DEE7'); BOX = Border(bottom=thin)
F = lambda size=10, bold=False, color=INK, italic=False: Font(name=FONT, size=size, bold=bold, color=color, italic=italic)
fill = lambda c: PatternFill('solid', fgColor=c)
LEFT, CEN, RIGHT = Alignment(horizontal='left', vertical='center'), Alignment(horizontal='center', vertical='center'), Alignment(horizontal='right', vertical='center')


def band(ws, title, subtitle, width):
    ws.sheet_view.showGridLines = False
    ws.row_dimensions[1].height = 30
    for c in range(1, width + 1):
        ws.cell(1, c).fill = fill(NAVY); ws.cell(2, c).fill = fill(SLATE)
    ws.cell(1, 1, '  ' + title).font = F(15, True, WHITE)
    ws.cell(2, 1, '  ' + subtitle).font = F(9, False, 'D1D5DB', True)
    ws.cell(1, 1).alignment = Alignment(vertical='center')


def table(ws, df, r0, c0=1, formats=None, widths=None, header_fill=ACCENT, zebra=True):
    """Write a DataFrame as a styled table starting at (r0, c0). Returns (first_data_row, last_row)."""
    formats = formats or {}
    for j, h in enumerate(df.columns):
        x = ws.cell(r0, c0 + j, h); x.font = F(9, True, WHITE); x.fill = fill(header_fill)
        x.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ws.row_dimensions[r0].height = 30
    for i, row in enumerate(df.itertuples(index=False)):
        for j, v in enumerate(row):
            if isinstance(v, (float, np.floating)) and np.isnan(v): v = None
            fm = formats.get(df.columns[j])
            if isinstance(v, (float, np.floating)) and fm:   # round to the shown precision so nothing displays as "-0.0"
                dec = len(fm.split(';')[0].split('.')[1].rstrip('%')) if '.' in fm.split(';')[0] else 0
                v = round(float(v) * (100 if '%' in fm else 1), dec) / (100 if '%' in fm else 1) + 0.0
            x = ws.cell(r0 + 1 + i, c0 + j, v.item() if hasattr(v, 'item') else v)
            x.font = F(10); x.border = BOX
            x.alignment = LEFT if isinstance(v, str) and j < 3 else CEN
            if zebra and i % 2: x.fill = fill(PAPER)
            if fm: x.number_format = fm
    if widths:
        for j, w in enumerate(widths): ws.column_dimensions[COL(c0 + j)].width = w
    return r0 + 1, r0 + len(df)


def scale(ws, rng, reverse=False):
    lo, hi = (GREEN, RED) if reverse else (RED, GREEN)
    ws.conditional_formatting.add(rng, ColorScaleRule(start_type='min', start_color=lo, mid_type='percentile', mid_value=50, mid_color=MID, end_type='max', end_color=hi))


def section(ws, r, c, text, width=8):
    x = ws.cell(r, c, text.upper()); x.font = F(10, True, GOLD)
    for k in range(c, c + width): ws.cell(r, k).border = Border(bottom=Side(style='medium', color=GOLD))


def col_of(df, name, c0=1):
    return COL(c0 + list(df.columns).index(name))


# ------------------------------------------------------------------ season stats from the cached per-game tables
def team_season_stats(g, season, week):
    tg = pd.read_csv(os.path.join(CACHE, 'team_games.csv')); tx = pd.read_csv(os.path.join(CACHE, 'team_games_x.csv'))
    nz = pd.read_csv(os.path.join(CACHE, 'noise_games.csv')) if os.path.exists(os.path.join(CACHE, 'noise_games.csv')) else None
    for d in (tg, tx) + ((nz,) if nz is not None else ()):
        d['team'] = FIXT(d.team)
    tg['opp'] = FIXT(tg.opp)
    reg = set(g[(g.season == season) & (g.game_type == 'REG') & (g.week < week)].game_id)
    t = tg[tg.game_id.isin(reg)].merge(tx.drop(columns=['season', 'week']), on=['game_id', 'team'], how='left', suffixes=('', '_x'))
    if nz is not None: t = t.merge(nz.drop(columns=['season', 'week', 'n']), on=['game_id', 'team'], how='left')
    o = t.add_prefix('o_').rename(columns={'o_game_id': 'game_id', 'o_team': 'opp'})
    t = t.merge(o, on=['game_id', 'opp'], how='left')
    s = t.groupby('team').sum(numeric_only=True); n = t.groupby('team').size()
    out = pd.DataFrame(index=s.index)
    out['Games'] = n
    out['Off EPA/play'] = s.epa / s.plays; out['Def EPA/play allowed'] = s.o_epa / s.o_plays
    out['Net EPA/play'] = out['Off EPA/play'] - out['Def EPA/play allowed']
    out['Off success'] = s.succ / s.plays; out['Def success allowed'] = s.o_succ / s.o_plays
    out['Pass EPA/play'] = s.pass_epa / s.pass_plays; out['Rush EPA/play'] = s.rush_epa / (s.plays - s.pass_plays)
    out['Early-down EPA'] = s.epa_early / s.n_early
    out['Pass rate over exp.'] = s.proe / s.n_neu / 100.0
    out['Secs/play (pace)'] = s.secs / s.n_pace
    out['4th-down go rate'] = s.go4 / s.n4.replace(0, np.nan)
    out['Special teams EPA/g'] = s.st_epa / n
    out['Penalty yds/g'] = s.pen_yds / n
    out['Takeaways'] = s.o_ints + s.o_fumbles_lost; out['Giveaways'] = s.ints + s.fumbles_lost
    out['Turnover margin'] = out.Takeaways - out.Giveaways
    if nz is not None:
        out['Big-play rate'] = s.n_expl / s.n; out['Penalty EPA/g'] = (s.pen_epa - s.o_pen_epa) / n
        out['FG luck (pts)'] = s.fg_luck; out['Return/def TDs'] = s.ret_td; out['Kicks blocked'] = s.o_kicks_blocked
        out['WPA/g'] = (s.wpa_pos - s.o_wpa_pos) / n
    out['Fumble luck'] = (0.5 * s.fumbles - s.fumbles_lost) + (s.o_fumbles_lost - 0.5 * s.o_fumbles)
    return out


def qb_season_stats(g, season, week, qb_now):
    p = pd.read_parquet(os.path.join(RAW, f'pbp_{season}.parquet'),
                        columns=['game_id', 'week', 'season_type', 'posteam', 'passer_player_id', 'passer_player_name', 'pass_attempt', 'sack',
                                 'complete_pass', 'passing_yards', 'pass_touchdown', 'interception', 'cpoe', 'qb_dropback', 'id', 'qb_epa'])
    p = p[(p.season_type == 'REG') & (p.week < week)]; p['team'] = FIXT(p.posteam)
    a = p[(p.pass_attempt == 1) & (p.sack != 1) & p.passer_player_id.notna()]
    s = a.groupby('passer_player_id').agg(Name=('passer_player_name', 'last'), Team=('team', 'last'), Att=('pass_attempt', 'size'),
                                         Cmp=('complete_pass', 'sum'), Yds=('passing_yards', 'sum'), TD=('pass_touchdown', 'sum'),
                                         INT=('interception', 'sum'), CPOE=('cpoe', 'mean'))
    db = p[(p.qb_dropback == 1) & p.id.notna()].groupby('id').agg(Dropbacks=('qb_epa', 'size'), EPA=('qb_epa', 'sum'), Sacks=('sack', 'sum'))
    s = s.join(db, how='left'); s = s[s.Dropbacks >= 40]
    s['EPA/dropback'] = s.EPA / s.Dropbacks; s['Sack rate'] = s.Sacks / s.Dropbacks; s['INT rate'] = s.INT / s.Att
    s['Comp %'] = s.Cmp / s.Att; s['Y/A'] = s.Yds / s.Att
    qf = os.path.join(CACHE, 'qb_ftn.csv')
    if os.path.exists(qf):
        q = pd.read_csv(qf); q = q[(q.season == season) & (q.week < week)].groupby('player_id')[['attempts', 'int_worthy', 'drops', 'catchable']].sum()
        s = s.join(q, how='left')
        s['Adj. INT rate (INT-worthy)'] = s.int_worthy / s.attempts
        s['Lucky / unlucky INTs'] = s.INT - s.int_worthy
        s['Drops by receivers'] = s.drops
    pl = os.path.join(RAW, 'players.csv')
    if os.path.exists(pl):
        nm = pd.read_csv(pl, low_memory=False, usecols=['gsis_id', 'display_name']).dropna().drop_duplicates('gsis_id').set_index('gsis_id').display_name
        s['Name'] = [nm.get(i, n) for i, n in zip(s.index, s.Name)]
    s['Starter now'] = s.index.isin(qb_now)
    s['Team'] = s.Team.map(show)
    cols = ['Name', 'Team', 'Starter now', 'Dropbacks', 'EPA/dropback', 'CPOE', 'Comp %', 'Y/A', 'TD', 'INT', 'INT rate',
            'Adj. INT rate (INT-worthy)', 'Lucky / unlucky INTs', 'Drops by receivers', 'Sack rate']
    s = s[[c for c in cols if c in s.columns]].sort_values('EPA/dropback', ascending=False)
    s['Starter now'] = np.where(s['Starter now'], 'yes', '')
    return s.reset_index(drop=True)


# ------------------------------------------------------------------ the workbook
def build(path, ctx):
    """ctx: season, week, tips (DataFrame), rank_tbl, now (team table rows this week), hist (team table all weeks <= week),
    views (season_views), proj (simulate summary), lev (game_leverage), g (games), checks (self-test lines), fetched, qb_now_ids."""
    S, W = ctx['season'], ctx['week']; v, proj, now, g = ctx['views'], ctx['proj'], ctx['now'], ctx['g']
    wb = Workbook()
    rk = now.power_qb.rank(ascending=False, method='first').astype(int)
    hist = ctx['hist']
    prev = hist[hist.week == W - 1].set_index('team').power_qb.rank(ascending=False, method='first').astype(int) if W > 1 else None
    def rec(t):
        w, l = v.wins[t], v.losses[t]; ties = int(round((w % 1) * 2)); return f'{int(w)}-{int(l)}' + (f'-{ties}' if ties else '')
    # =========================== Dashboard
    ws = wb.active; ws.title = 'Dashboard'
    band(ws, f'NFL {S}  ·  WEEK {W}', f'Data downloaded {ctx["fetched"]}  ·  every number uses only games before this week  ·  model: nfl-model (see README)', 14)
    section(ws, 4, 1, f'This week\'s games', 7)
    tips = ctx['tips'][['Kickoff (ET)', 'Game', 'TIP', 'Win %', 'Line', 'Model only']].copy(); tips['Win %'] = tips['Win %'] / 100
    tips = tips.rename(columns={'TIP': 'Predicted winner', 'Model only': 'Model without line'})
    r1, r2 = table(ws, tips, 5, 1, {'Win %': '0%'}, [17, 22, 11, 8, 11, 15])
    ws.conditional_formatting.add(f'D{r1}:D{r2}', DataBarRule(start_type='num', start_value=0.5, end_type='num', end_value=1, color=GOLD))
    # movers
    c0 = 9
    if prev is not None:
        mv = (prev - rk).rename('move')
        up, dn = mv.sort_values(ascending=False).head(5), mv.sort_values().head(5)
        section(ws, 4, c0, 'Top movers in the power rankings', 6)
        m = pd.DataFrame({'Risers': [f'{show(t)}  ▲{int(x)}  (now #{rk[t]})' for t, x in up.items() if x > 0] + [''] * (5 - int((up > 0).sum())),
                          'Fallers': [f'{show(t)}  ▼{int(-x)}  (now #{rk[t]})' for t, x in dn.items() if x < 0] + [''] * (5 - int((dn < 0).sum()))})
        table(ws, m, 5, c0, widths=[24, 24])
    # playoff race
    section(ws, 12, c0, 'Playoff race', 6)
    r = 13
    lev = ctx['lev']
    ws.cell(r, c0, 'Biggest games this week (swing in playoff chance)').font = F(9, True, ACCENT); r += 1
    for x in lev.itertuples():
        ws.cell(r, c0, f'{show(x.away)} @ {show(x.home)}').font = F(10)
        ws.cell(r, c0 + 1, f'{show(x.home)} ±{x.swing_home*100:.0f} pts · {show(x.away)} ±{x.swing_away*100:.0f} pts').font = F(10, False, GREY); r += 1
    r += 1
    for conf in ('AFC', 'NFC'):
        teams = [t for d, s in DIVISIONS.items() if d.startswith(conf) for t in s.split()]
        top = proj.loc[teams].sort_values('p_seed1', ascending=False).head(3)
        bub = proj.loc[teams][(proj.loc[teams].p_playoffs > 0.25) & (proj.loc[teams].p_playoffs < 0.75)].sort_values('p_playoffs', ascending=False)
        ws.cell(r, c0, f'{conf} #1 seed race').font = F(9, True, ACCENT)
        ws.cell(r, c0 + 1, ' · '.join(f'{show(t)} {p*100:.0f}%' for t, p in top.p_seed1.items())).font = F(10); r += 1
        ws.cell(r, c0, f'{conf} on the bubble').font = F(9, True, ACCENT)
        ws.cell(r, c0 + 1, ' · '.join(f'{show(t)} {p*100:.0f}%' for t, p in bub.p_playoffs.items()) or 'none between 25% and 75%').font = F(10); r += 1
    ws.cell(r + 1, c0, 'Predicted winner = betting line + small tested corrections (ties the line in testing; no betting edge).').font = F(8, False, GREY, True)
    ws.freeze_panes = 'A4'
    # =========================== Power Rankings
    ws = wb.create_sheet('Power Rankings')
    band(ws, 'POWER RANKINGS', 'Power = expected margin vs an average team on a neutral field (pts), with this week\'s starting QB. Parts add up to Power.', 20)
    rows = []
    for t in rk.sort_values().index:
        mvv = (prev[t] - rk[t]) if prev is not None else 0
        rows.append({'Rank': int(rk[t]), 'Move': ('▲' + str(int(mvv))) if mvv > 0 else (('▼' + str(int(-mvv))) if mvv < 0 else '–'), 'Team': show(t), 'Record': rec(t),
                     'Power': now.power_qb[t], 'Market': now.market[t], 'Results + Elo': now.results[t] + now.nfelo[t], 'EPA offence': now.epa_off[t],
                     'EPA defence': now.epa_def[t], 'Special teams': now.special_teams[t], '4th-down': now.fourth_down[t], 'QB now': now.qb_now[t],
                     'Off rank': int(v.off_rank[t]), 'Def rank': int(v.def_rank[t]), 'Exp. wins': v.exp_wins[t], 'Luck': v.luck[t],
                     'SOS played rank': v.sos_past_rank[t], 'SOS left rank': v.sos_left_rank[t], '4-wk trend': v.trend4[t]})
    pr = pd.DataFrame(rows)
    fm = {k: '+0.0;-0.0;0.0' for k in ('Power', 'Market', 'Results + Elo', 'EPA offence', 'EPA defence', 'Special teams', '4th-down', 'QB now', 'Luck', '4-wk trend')}
    fm.update({'Exp. wins': '0.0', 'SOS played rank': '0', 'SOS left rank': '0'})
    r1, r2 = table(ws, pr, 4, 1, fm, [6, 6, 7, 8, 8, 8, 10, 9, 9, 9, 8, 8, 7, 7, 8, 7, 9, 9, 9])
    for c in ('Power', 'Market', 'Results + Elo', 'EPA offence', 'EPA defence', 'Special teams', 'Luck', '4-wk trend'):
        L = col_of(pr, c); scale(ws, f'{L}{r1}:{L}{r2}')
    for c in ('Off rank', 'Def rank', 'SOS played rank', 'SOS left rank'):
        L = col_of(pr, c); scale(ws, f'{L}{r1}:{L}{r2}', reverse=True)
    for i in range(r1, r2 + 1): ws.cell(i, 5).font = F(10, True)
    ws.cell(r2 + 2, 1, 'Off/Def rank from opponent-adjusted EPA per play. Luck = wins minus expected wins. SOS rank 1 = hardest. '
            '4-wk trend is for interest only: in testing it did not predict the rest of the season.').font = F(8, False, GREY, True)
    ws.freeze_panes = 'D5'
    # =========================== Ranking History (+ trend chart)
    ws = wb.create_sheet('Ranking History')
    band(ws, 'RANKING HISTORY', 'Power rank before each week (1 = best). Chart: the current top 8.', 22)
    H = hist.pivot(index='team', columns='week', values='power_qb').rank(ascending=False, method='first').astype(int)
    order = rk.sort_values().index
    H = H.reindex(order); H.columns = [f'Wk {c}' for c in H.columns]
    Hd = H.reset_index().rename(columns={'team': 'Team'}); Hd['Team'] = Hd.Team.map(show)
    r1, r2 = table(ws, Hd, 4, 1, widths=[8] + [6] * (Hd.shape[1] - 1))
    scale(ws, f'B{r1}:{COL(Hd.shape[1])}{r2}', reverse=True)
    ch = LineChart(); ch.title = 'Power rank over the season (current top 8)'; ch.y_axis.title = 'Rank'; ch.x_axis.title = 'Week'
    ch.y_axis.scaling.orientation = 'maxMin'; ch.y_axis.scaling.min = 1; ch.height = 9; ch.width = 22
    for i in range(min(8, len(Hd))):
        s = Series(Reference(ws, min_col=2, max_col=Hd.shape[1], min_row=r1 + i), title=Hd.Team.iloc[i]); s.smooth = False; ch.series.append(s)
    ch.set_categories(Reference(ws, min_col=2, max_col=Hd.shape[1], min_row=4))
    ws.add_chart(ch, f'{COL(Hd.shape[1] + 2)}4'); ws.freeze_panes = 'B5'
    # =========================== Team Efficiency (+ offence vs defence scatter)
    ws = wb.create_sheet('Team Efficiency')
    band(ws, 'TEAM EFFICIENCY', f'Season to date (Weeks 1–{W - 1}). Raw per-play numbers; the rankings use opponent-adjusted versions. Defence: lower EPA allowed is better.', 26)
    ts = team_season_stats(g, S, W)
    ts.insert(0, 'Adj. off EPA', now.epa_off_raw.reindex(ts.index)); ts.insert(1, 'Adj. def EPA allowed', now.epa_def_raw.reindex(ts.index))
    ts = ts.loc[[t for t in order if t in ts.index]]
    te = ts.reset_index().rename(columns={'team': 'Team'}); te['Team'] = te.Team.map(show)
    pct_cols = ('Off success', 'Def success allowed', 'Pass rate over exp.', '4th-down go rate', 'Big-play rate')
    fm = {c: ('0.0%' if c in pct_cols else '+0.000;-0.000;0.000') for c in te.columns if c not in ('Team', 'Games')}
    for c in ('Secs/play (pace)', 'Penalty yds/g', 'Special teams EPA/g', 'Penalty EPA/g', 'FG luck (pts)', 'WPA/g', 'Fumble luck'): fm[c] = '+0.0;-0.0;0.0' if c not in ('Secs/play (pace)', 'Penalty yds/g') else '0.0'
    for c in ('Takeaways', 'Giveaways', 'Turnover margin', 'Return/def TDs', 'Kicks blocked'): fm[c] = '0'
    r1, r2 = table(ws, te, 4, 1, fm, [8] + [10] * (te.shape[1] - 1))
    for c in te.columns[1:]:
        if c in ('Games',): continue
        rev = c in ('Def EPA/play allowed', 'Def success allowed', 'Adj. def EPA allowed', 'Giveaways', 'Penalty yds/g', 'Secs/play (pace)', 'Kicks blocked')
        L = col_of(te, c); scale(ws, f'{L}{r1}:{L}{r2}', reverse=rev)
    ws.freeze_panes = 'B5'
    sc = ScatterChart(); sc.title = 'Offence vs defence (opponent-adjusted EPA/play; up-right = better)'; sc.style = 13
    sc.x_axis.title = 'Offence EPA/play'; sc.y_axis.title = 'Defence (EPA allowed, reversed)'; sc.height = 12; sc.width = 18
    sc.y_axis.scaling.orientation = 'maxMin'; sc.legend = None
    xo, yo = col_of(te, 'Adj. off EPA'), col_of(te, 'Adj. def EPA allowed')
    for i in range(len(te)):
        s = Series(Reference(ws, range_string=f"'Team Efficiency'!{yo}{r1 + i}"), Reference(ws, range_string=f"'Team Efficiency'!{xo}{r1 + i}"), title=te.Team.iloc[i])
        s.marker.symbol = 'circle'; s.marker.size = 7; s.graphicalProperties.line.noFill = True
        s.dLbls = DataLabelList(); s.dLbls.showSerName = True; s.dLbls.showVal = False; s.dLbls.position = 't'
        sc.series.append(s)
    ws.add_chart(sc, f'A{r2 + 3}')
    # =========================== QBs
    ws = wb.create_sheet('QBs')
    band(ws, 'QUARTERBACKS', f'Season to date, 40+ dropbacks. Adj. INT rate = interception-worthy throws per attempt (FTN charting): it strips out tipped and dropped picks.', 16)
    qs = qb_season_stats(g, S, W, ctx['qb_now_ids'])
    fm = {'EPA/dropback': '+0.00;-0.00;0.00', 'CPOE': '+0.0;-0.0;0.0', 'Comp %': '0.0%', 'Y/A': '0.0', 'INT rate': '0.0%',
          'Adj. INT rate (INT-worthy)': '0.0%', 'Sack rate': '0.0%', 'Lucky / unlucky INTs': '+0;-0;0', 'Dropbacks': '0', 'TD': '0', 'INT': '0', 'Drops by receivers': '0'}
    r1, r2 = table(ws, qs, 4, 1, fm, [20, 7, 8, 10, 10, 8, 8, 7, 6, 6, 8, 11, 10, 10, 8])
    for c, rev in (('EPA/dropback', False), ('CPOE', False), ('INT rate', True), ('Adj. INT rate (INT-worthy)', True), ('Sack rate', True)):
        if c in qs.columns: L = col_of(qs, c); scale(ws, f'{L}{r1}:{L}{r2}', reverse=rev)
    ws.cell(r2 + 2, 1, 'Lucky / unlucky INTs = interceptions minus interception-worthy throws (positive = more picks than the throws deserved).').font = F(8, False, GREY, True)
    ws.freeze_panes = 'B5'
    # =========================== Luck & Expected Wins (+ scatter)
    ws = wb.create_sheet('Luck & Expected Wins')
    band(ws, 'LUCK & EXPECTED WINS', 'Expected wins = sum of the model\'s pre-game win chances. In testing it predicted the rest of the season better than the actual record.', 12)
    ts2 = team_season_stats(g, S, W)
    lk = pd.DataFrame({'Team': [show(t) for t in order], 'Record': [rec(t) for t in order], 'Wins': [v.wins[t] for t in order],
                       'Expected wins': [v.exp_wins[t] for t in order], 'Luck (wins)': [v.luck[t] for t in order],
                       'Pythagorean wins': [v.pyth_wins[t] for t in order],
                       'Fumble luck': [ts2['Fumble luck'].get(t, np.nan) for t in order],
                       'FG luck (pts)': [ts2['FG luck (pts)'].get(t, np.nan) if 'FG luck (pts)' in ts2 else np.nan for t in order],
                       'Return/def TDs': [ts2['Return/def TDs'].get(t, np.nan) if 'Return/def TDs' in ts2 else np.nan for t in order],
                       'Turnover margin': [ts2['Turnover margin'].get(t, np.nan) for t in order]})
    lk = lk.sort_values('Luck (wins)', ascending=False)
    fm = {'Wins': '0.0', 'Expected wins': '0.0', 'Luck (wins)': '+0.0;-0.0;0.0', 'Pythagorean wins': '0.0', 'Fumble luck': '+0.0;-0.0;0.0', 'FG luck (pts)': '+0.0;-0.0;0.0', 'Return/def TDs': '0', 'Turnover margin': '+0;-0;0'}
    r1, r2 = table(ws, lk, 4, 1, fm, [8, 9, 7, 10, 10, 11, 10, 10, 10, 10])
    for c in ('Luck (wins)', 'Fumble luck', 'FG luck (pts)', 'Turnover margin'):
        L = col_of(lk, c); scale(ws, f'{L}{r1}:{L}{r2}')
    ws.cell(r2 + 2, 1, 'Positive luck = record better than the play deserved (expect some regression). Fumble luck = recoveries above a 50/50 coin flip; '
            'FG luck = points above what the kicks\' make probabilities expected.').font = F(8, False, GREY, True)
    sc = ScatterChart(); sc.title = 'Expected vs actual wins (above the diagonal = lucky)'; sc.style = 13; sc.legend = None
    sc.x_axis.title = 'Expected wins'; sc.y_axis.title = 'Actual wins'; sc.height = 12; sc.width = 16
    xe, ya = col_of(lk, 'Expected wins'), col_of(lk, 'Wins')
    for i in range(len(lk)):
        s = Series(Reference(ws, range_string=f"'Luck & Expected Wins'!{ya}{r1 + i}"), Reference(ws, range_string=f"'Luck & Expected Wins'!{xe}{r1 + i}"), title=lk.Team.iloc[i])
        s.marker.symbol = 'circle'; s.marker.size = 7; s.graphicalProperties.line.noFill = True
        s.dLbls = DataLabelList(); s.dLbls.showSerName = True; s.dLbls.showVal = False; s.dLbls.position = 't'; sc.series.append(s)
    ws.add_chart(sc, 'L4'); ws.freeze_panes = 'B5'
    # =========================== Strength of Schedule
    ws = wb.create_sheet('Strength of Schedule')
    band(ws, 'STRENGTH OF SCHEDULE', 'Opponent strength in points (+ = harder than average), adjusted for each opponent\'s QB and home/away. Schedule effect = wins an average team gains (+) or loses (−) from this schedule.', 12)
    ss = pd.DataFrame({'Team': [show(t) for t in order], 'Record': [rec(t) for t in order],
                       'Played: opp. strength': [v.sos_past[t] for t in order], 'Played: rank (1 = hardest)': [v.sos_past_rank[t] for t in order],
                       'Schedule effect (wins)': [v.schedule_wins[t] for t in order],
                       'Left: opp. strength': [v.sos_left[t] for t in order], 'Left: rank (1 = hardest)': [v.sos_left_rank[t] for t in order],
                       'Games left': [v.games_left[t] for t in order], 'Rest days given up': [v.rest_deficit_left[t] for t in order],
                       'Short weeks left': [v.short_weeks_left[t] for t in order], 'Travel miles left': [v.miles_left[t] for t in order]})
    fm = {'Played: opp. strength': '+0.0;-0.0;0.0', 'Left: opp. strength': '+0.0;-0.0;0.0', 'Schedule effect (wins)': '+0.0;-0.0;0.0',
          'Played: rank (1 = hardest)': '0', 'Left: rank (1 = hardest)': '0', 'Travel miles left': '#,##0', 'Rest days given up': '0'}
    r1, r2 = table(ws, ss, 4, 1, fm, [8, 9, 11, 11, 11, 11, 11, 8, 10, 9, 11])
    for c, rev in (('Played: opp. strength', True), ('Left: opp. strength', True), ('Schedule effect (wins)', False)):
        L = col_of(ss, c); scale(ws, f'{L}{r1}:{L}{r2}', reverse=rev)
    ws.cell(r2 + 2, 1, 'Rest and travel are shown for information: in testing they did not measurably change results once team strength was known.').font = F(8, False, GREY, True)
    ws.freeze_panes = 'B5'
    # =========================== Season Projections (+ playoff odds bar chart)
    ws = wb.create_sheet('Season Projections')
    band(ws, 'SEASON PROJECTIONS', f'{ctx["sims"]:,} simulations of the remaining schedule (calibrated on 2012–25). Likely range = 10th–90th percentile of wins.', 12)
    rows = []
    for d in sorted(DIVISIONS):
        for t in sorted(DIVISIONS[d].split(), key=lambda t: -proj.exp_wins[t]):
            rows.append({'Division': d, 'Team': show(t), 'Now': rec(t), 'Projected wins': proj.exp_wins[t], 'Low (10%)': proj.wins_p10[t],
                         'High (90%)': proj.wins_p90[t], 'Win division': proj.p_division[t], 'Make playoffs': proj.p_playoffs[t], '#1 seed': proj.p_seed1[t]})
    pj = pd.DataFrame(rows)
    fm = {'Projected wins': '0.0', 'Low (10%)': '0', 'High (90%)': '0', 'Win division': '0%', 'Make playoffs': '0%', '#1 seed': '0%'}
    r1, r2 = table(ws, pj, 4, 1, fm, [11, 8, 8, 10, 9, 9, 10, 10, 9])
    for c in ('Win division', 'Make playoffs', '#1 seed'):
        L = col_of(pj, c); ws.conditional_formatting.add(f'{L}{r1}:{L}{r2}', DataBarRule(start_type='num', start_value=0, end_type='num', end_value=1, color=GOLD))
    # sorted playoff odds for the chart (helper table to the right)
    po = proj.sort_values('p_playoffs', ascending=False)
    ws.cell(4, 12, 'Team').font = F(9, True, WHITE); ws.cell(4, 12).fill = fill(ACCENT)
    ws.cell(4, 13, 'Playoff odds').font = F(9, True, WHITE); ws.cell(4, 13).fill = fill(ACCENT)
    for i, (t, p) in enumerate(po.p_playoffs.items()):
        ws.cell(5 + i, 12, show(t)).font = F(9); c = ws.cell(5 + i, 13, float(p)); c.number_format = '0%'; c.font = F(9)
    bc = BarChart(); bc.type = 'bar'; bc.title = 'Playoff odds'; bc.style = 10; bc.legend = None; bc.height = 20; bc.width = 13; bc.gapWidth = 40
    bc.add_data(Reference(ws, min_col=13, min_row=4, max_row=36), titles_from_data=True); bc.set_categories(Reference(ws, min_col=12, min_row=5, max_row=36))
    bc.y_axis.scaling.min = 0; bc.y_axis.scaling.max = 1; bc.y_axis.number_format = '0%'; bc.x_axis.scaling.orientation = 'maxMin'
    bc.series[0].graphicalProperties.solidFill = ACCENT
    ws.add_chart(bc, 'O4'); ws.freeze_panes = 'C5'
    # =========================== About
    ws = wb.create_sheet('About')
    band(ws, 'ABOUT THIS WORKBOOK', 'Regenerated every week by `python3 weekly.py` (nfl-model). Do not edit: changes are overwritten.', 6)
    lines = ['How to read it', '• Predicted winner = betting line + small tested corrections. It ties the closing line in 15 seasons of testing; there is no betting edge.',
             '• Power = points better than an average team on a neutral field. Ranks, efficiency and projections use only games before this week.',
             '• Season projections are calibrated: in past seasons, teams given 40–60% playoff chances made it 48% of the time.', '',
             'Self-test for this run'] + [f'• {s}: {m}' for s, m in ctx['checks']] + ['', 'Data: nflverse (scores, lines, play-by-play, injuries, snaps, FTN charting), nfelo QB-Elo. Full sources and test results: README.md.']
    for i, t in enumerate(lines):
        c = ws.cell(4 + i, 1, t); c.font = F(11, True, GOLD) if t in ('How to read it', 'Self-test for this run') else F(10)
    ws.column_dimensions['A'].width = 140
    for w_ in wb.worksheets:
        w_.sheet_properties.tabColor = GOLD if w_.title == 'Dashboard' else ACCENT
        w_.sheet_view.zoomScale = 100
        w_.page_setup.orientation = 'landscape'; w_.page_setup.fitToWidth = 1; w_.page_setup.fitToHeight = 0
        w_.sheet_properties.pageSetUpPr.fitToPage = True; w_.print_options.horizontalCentered = True
    os.makedirs(os.path.dirname(path), exist_ok=True); wb.save(path)
    return path
