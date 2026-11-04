"""Round 4: 'real performance vs noise' measures per team-game, from the play-by-play in cache/raw plus FTN charting (2022+).

Outputs (cache/):
  noise_games.csv   per (game, team): penalty EPA, EPA without penalty plays, big-play vs other EPA, leverage-weighted EPA,
                    win-probability added, return/defensive TDs, field-goal luck, blocked kicks, Hail Marys
  qb_ftn.csv        per (game, passer), 2022+: attempts, interceptions, interception-worthy throws, drops, catchable balls
Usage: python3 -m nflmodel.fetch_noise   |   python3 -m nflmodel.fetch_noise --current 2026
"""
import argparse, os, urllib.request
import numpy as np, pandas as pd
from nflmodel.common import RAW, CACHE

FTN = 'https://github.com/nflverse/nflverse-data/releases/download/ftn_charting/ftn_charting_{}.csv'
COLS = ['game_id', 'play_id', 'season', 'week', 'season_type', 'posteam', 'defteam', 'play_type', 'epa', 'wp', 'wpa', 'penalty',
        'yards_gained', 'touchdown', 'td_team', 'return_touchdown', 'field_goal_attempt', 'field_goal_result', 'fg_prob',
        'punt_blocked', 'extra_point_result', 'qtr', 'half_seconds_remaining', 'air_yards', 'complete_pass', 'pass_attempt',
        'interception', 'passer_player_id', 'qb_dropback', 'sack']


def team_noise(p):
    k = ['game_id', 'season', 'week', 'posteam']
    sc = p[p.play_type.isin(['pass', 'run']) & p.epa.notna() & p.posteam.notna()].copy()
    sc['nopen'] = (sc.penalty != 1).astype(int); sc['expl'] = (sc.yards_gained >= 20).astype(int)
    sc['lev'] = 4 * sc.wp.clip(0, 1) * (1 - sc.wp.clip(0, 1))               # 1 at 50/50, ~0 when the game is decided
    for c, m in (('epa_nopen', 'nopen'), ('epa_expl', 'expl')): sc[c] = sc.epa * sc[m]
    sc['epa_nonexpl'] = sc.epa * (1 - sc.expl); sc['epa_lev'] = sc.epa * sc.lev
    a = sc.groupby(k).agg(n_nopen=('nopen', 'sum'), epa_nopen=('epa_nopen', 'sum'), n_expl=('expl', 'sum'), epa_expl=('epa_expl', 'sum'),
                          epa_nonexpl=('epa_nonexpl', 'sum'), lev=('lev', 'sum'), epa_lev=('epa_lev', 'sum'), n=('epa', 'size'))
    a['n_nonexpl'] = a.n - a.n_expl
    pen = p[(p.penalty == 1) & p.epa.notna() & p.posteam.notna()].groupby(k).agg(pen_epa=('epa', 'sum'), n_pen=('epa', 'size'))
    wpa = p[p.wpa.notna() & p.posteam.notna()].groupby(k).wpa.sum().rename('wpa_pos')
    fg = p[(p.field_goal_attempt == 1) & p.fg_prob.notna() & p.posteam.notna()].copy()
    fg['fg_luck'] = 3 * ((fg.field_goal_result == 'made').astype(float) - fg.fg_prob)
    fgl = fg.groupby(k).agg(fg_luck=('fg_luck', 'sum'), fg_att=('fg_luck', 'size'))
    blk = p[((p.field_goal_result == 'blocked') | (p.punt_blocked == 1) | (p.extra_point_result == 'blocked')) & p.posteam.notna()]
    blk = blk.groupby(k).size().rename('kicks_blocked')                       # kicks this team had blocked
    hm = p[p.qtr.isin([2, 4]) & (p.half_seconds_remaining <= 10) & (p.air_yards >= 40) & (p.complete_pass == 1) & p.posteam.notna()]
    hm = hm.groupby(k).agg(hail_mary=('touchdown', 'size'), hail_mary_td=('touchdown', 'sum'))
    out = a.join([pen, wpa, fgl, blk, hm], how='outer').fillna(0).reset_index().rename(columns={'posteam': 'team'})
    # return / defensive touchdowns scored BY a team (not by its offence)
    rt = p[(p.touchdown == 1) & p.td_team.notna() & ((p.return_touchdown == 1) | (p.td_team != p.posteam))]
    rt = rt.groupby(['game_id', 'td_team']).size().rename('ret_td').reset_index().rename(columns={'td_team': 'team'})
    out = out.merge(rt, on=['game_id', 'team'], how='left').fillna({'ret_td': 0})
    return out


def ftn_qb(p, season):
    path = os.path.join(RAW, f'ftn_{season}.csv')
    if not os.path.exists(path):
        try: urllib.request.urlretrieve(FTN.format(season), path)
        except Exception as e: print('  FTN', season, 'not available:', e); return None
    f = pd.read_csv(path, low_memory=False)
    for c in ('is_interception_worthy', 'is_drop', 'is_catchable_ball', 'is_throw_away'):
        f[c] = f[c].astype(str).str.upper().eq('TRUE').astype(int)
    x = p[(p.pass_attempt == 1) & (p.sack != 1) & p.passer_player_id.notna()].merge(
        f[['nflverse_game_id', 'nflverse_play_id', 'is_interception_worthy', 'is_drop', 'is_catchable_ball', 'is_throw_away']],
        left_on=['game_id', 'play_id'], right_on=['nflverse_game_id', 'nflverse_play_id'], how='inner')
    return x.groupby(['game_id', 'season', 'week', 'posteam', 'passer_player_id']).agg(
        attempts=('pass_attempt', 'size'), ints=('interception', 'sum'), int_worthy=('is_interception_worthy', 'sum'),
        drops=('is_drop', 'sum'), catchable=('is_catchable_ball', 'sum'), throwaways=('is_throw_away', 'sum')).reset_index() \
        .rename(columns={'posteam': 'team', 'passer_player_id': 'player_id'})


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--current', type=int); a = ap.parse_args()
    seasons = [a.current] if a.current else sorted(int(f[4:8]) for f in os.listdir(RAW) if f.startswith('pbp_') and f.endswith('.parquet'))
    N, Q = [], []
    for s in seasons:
        if a.current and os.path.exists(os.path.join(RAW, f'ftn_{s}.csv')): os.remove(os.path.join(RAW, f'ftn_{s}.csv'))
        p = pd.read_parquet(os.path.join(RAW, f'pbp_{s}.parquet'), columns=COLS)
        N.append(team_noise(p))
        if s >= 2022:
            q = ftn_qb(p, s)
            if q is not None: Q.append(q)
        print('season', s, flush=True)
    N = pd.concat(N); Q = pd.concat(Q) if Q else pd.DataFrame()
    np_, qp = os.path.join(CACHE, 'noise_games.csv'), os.path.join(CACHE, 'qb_ftn.csv')
    if a.current:
        if os.path.exists(np_): o = pd.read_csv(np_); N = pd.concat([o[o.season != a.current], N])
        if os.path.exists(qp) and len(Q): o = pd.read_csv(qp); Q = pd.concat([o[o.season != a.current], Q])
    N.round(4).to_csv(np_, index=False)
    if len(Q): Q.to_csv(qp, index=False)
    print('done', len(N), len(Q))


if __name__ == '__main__':
    main()
