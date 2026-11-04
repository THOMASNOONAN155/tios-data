"""Extra per-game tables from the nflverse play-by-play already in data/raw (run fetch_data.py first), plus the
free nfelo QB-Elo file (538-style Elo, maintained publicly at github.com/greerreNFL/nfeloqb).

Outputs (committed, compact):
  data/team_games_x.csv   per (game, offence team): early-down / red-zone / turnover-adjusted EPA, pass rate over
                          expected, pace, no-huddle, 4th-down go decisions, special-teams EPA, penalty yards
  data/player_weeks.csv   per (game, team, player): targets, pressures (sacks + QB hits) -> how much each player matters
  data/nfelo.csv          nfelo pre-game Elo / QB-Elo and win probability per game_id
Usage: python3 fetch_extra.py            (all seasons)   |   python3 fetch_extra.py --current 2026
"""
import argparse, os, urllib.request
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); RAW = os.path.join(HERE, 'data', 'raw'); OUT = os.path.join(HERE, 'data')
NFELO_URL = 'https://raw.githubusercontent.com/greerreNFL/nfeloqb/main/qb_elos.csv'
COLS = ['game_id', 'season', 'week', 'season_type', 'posteam', 'defteam', 'play_type', 'epa', 'wp', 'down', 'ydstogo',
        'yardline_100', 'qtr', 'pass_oe', 'no_huddle', 'game_seconds_remaining', 'interception', 'fumble_lost', 'qb_dropback',
        'special_teams_play', 'penalty', 'penalty_team', 'penalty_yards', 'receiver_player_id', 'sack_player_id',
        'half_sack_1_player_id', 'half_sack_2_player_id', 'qb_hit_1_player_id', 'qb_hit_2_player_id', 'drive', 'score_differential']


def team_table(p):
    k = ['game_id', 'season', 'week', 'posteam']
    sc = p[p.play_type.isin(['pass', 'run']) & p.epa.notna() & p.posteam.notna()].copy()
    sc['early'] = sc.down.isin([1, 2]).astype(int)
    sc['rz'] = (sc.yardline_100 <= 20).astype(int)
    to = ((sc.interception == 1) | (sc.fumble_lost == 1))
    fl = (sc.fumble_lost == 1)
    sc['epa_early'] = sc.epa * sc.early; sc['epa_rz'] = sc.epa * sc.rz
    sc['epa_to50'] = np.where(to, 0.5 * sc.epa, sc.epa)          # turnovers counted at half weight (partly luck)
    sc['epa_fl50'] = np.where(fl, 0.5 * sc.epa, sc.epa)          # only lost fumbles discounted (recovery is ~50/50)
    sc['epa_noto'] = np.where(to, 0.0, sc.epa)
    sc['rush'] = (sc.qb_dropback != 1).astype(int)
    sc['rush_epa'] = sc.epa * sc.rush
    neu = sc[(sc.wp.between(0.2, 0.8)) & (sc.down.isin([1, 2, 3])) & (sc.qtr <= 3)]
    a = sc.groupby(k).agg(n=('epa', 'size'), n_early=('early', 'sum'), epa_early=('epa_early', 'sum'), n_rz=('rz', 'sum'),
                          epa_rz=('epa_rz', 'sum'), epa_to50=('epa_to50', 'sum'), epa_fl50=('epa_fl50', 'sum'),
                          epa_noto=('epa_noto', 'sum'), n_rush=('rush', 'sum'), rush_epa=('rush_epa', 'sum'),
                          no_huddle=('no_huddle', 'sum'))
    b = neu.groupby(k).agg(n_neu=('epa', 'size'), proe=('pass_oe', 'sum'))
    # pace: offensive game seconds used per neutral-situation play (lower = faster)
    q = neu.sort_values(['game_id', 'game_seconds_remaining'], ascending=[True, False]).copy()
    q['dt'] = -q.groupby(['game_id', 'drive']).game_seconds_remaining.diff()
    c = q[q.dt.between(1, 60)].groupby(k).agg(n_pace=('dt', 'size'), secs=('dt', 'sum'))
    # 4th down: go-for-it rate in 'decision' spots (4th & <=3 between own 30 and opp 30, not 4th qtr)
    f4 = p[(p.down == 4) & (p.ydstogo <= 3) & p.yardline_100.between(30, 70) & (p.qtr <= 3) & p.posteam.notna()
           & p.play_type.isin(['pass', 'run', 'punt', 'field_goal'])].copy()
    f4['go'] = f4.play_type.isin(['pass', 'run']).astype(int)
    d = f4.groupby(k).agg(n4=('go', 'size'), go4=('go', 'sum'))
    # special teams: EPA on kicking plays from the possessing team's side, credited to both teams
    st = p[(p.special_teams_play == 1) & p.epa.notna() & p.posteam.notna()]
    s1 = st.groupby(k).epa.sum().rename('st_epa_pos')
    s2 = st.groupby(['game_id', 'season', 'week', 'defteam']).epa.sum().rename('st_epa_def')
    s2.index = s2.index.set_names(k)
    pen = p[(p.penalty == 1) & p.penalty_team.notna()].groupby(['game_id', 'season', 'week', 'penalty_team']).penalty_yards.sum().rename('pen_yds')
    pen.index = pen.index.set_names(k)
    out = a.join([b, c, d, s1, s2, pen], how='left').fillna(0).reset_index()
    out['st_epa'] = out.st_epa_pos - out.st_epa_def
    return out.rename(columns={'posteam': 'team'})


def player_table(p):
    k = ['game_id', 'season', 'week']
    t = p[p.receiver_player_id.notna() & (p.play_type == 'pass')].groupby(k + ['posteam', 'receiver_player_id']).size().rename('targets').reset_index()
    t = t.rename(columns={'posteam': 'team', 'receiver_player_id': 'gsis_id'})
    pr = []
    for c, w in (('sack_player_id', 1.0), ('half_sack_1_player_id', 0.5), ('half_sack_2_player_id', 0.5), ('qb_hit_1_player_id', 1.0), ('qb_hit_2_player_id', 1.0)):
        x = p[p[c].notna()][k + ['defteam', c]].rename(columns={c: 'gsis_id', 'defteam': 'team'}); x['pressures'] = w; pr.append(x)
    pr = pd.concat(pr).groupby(k + ['team', 'gsis_id']).pressures.sum().reset_index()
    return t.merge(pr, on=k + ['team', 'gsis_id'], how='outer').fillna({'targets': 0, 'pressures': 0})


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--current', type=int); a = ap.parse_args()
    seasons = [a.current] if a.current else sorted(int(f[4:8]) for f in os.listdir(RAW) if f.startswith('pbp_') and f.endswith('.parquet'))
    T, P = [], []
    for s in seasons:
        p = pd.read_parquet(f'{RAW}/pbp_{s}.parquet', columns=COLS)
        T.append(team_table(p)); P.append(player_table(p)); print('season', s, flush=True)
    T, P = pd.concat(T), pd.concat(P)
    if a.current:
        old_t = pd.read_csv(f'{OUT}/team_games_x.csv'); old_p = pd.read_csv(f'{OUT}/player_weeks.csv')
        T = pd.concat([old_t[old_t.season != a.current], T]); P = pd.concat([old_p[old_p.season != a.current], P])
    T.round(4).to_csv(f'{OUT}/team_games_x.csv', index=False); P.to_csv(f'{OUT}/player_weeks.csv', index=False)
    try:
        urllib.request.urlretrieve(NFELO_URL, f'{RAW}/nfelo_qb_elos.csv')
    except Exception as e:
        print('nfelo download failed (kept old copy if any):', e)
    if os.path.exists(f'{RAW}/nfelo_qb_elos.csv'):
        n = pd.read_csv(f'{RAW}/nfelo_qb_elos.csv', low_memory=False)
        n = n[n.season >= 2006][['game_id', 'season', 'team1', 'team2', 'elo1_pre', 'elo2_pre', 'qbelo1_pre', 'qbelo2_pre', 'qb1_adj', 'qb2_adj',
                                  'elo_prob1', 'qbelo_prob1']].dropna(subset=['game_id'])
        n.to_csv(f'{OUT}/nfelo.csv', index=False)
    print('done', len(T), len(P))


if __name__ == '__main__':
    main()
