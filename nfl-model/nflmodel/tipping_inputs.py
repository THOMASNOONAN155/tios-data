"""The tipping INPUTS file: nfl-model/inputs/tipping_inputs.xlsx. You type in it; weekly.py only ever READS it.

Layout (fixed; the reader checks the headers so a moved column is caught instead of silently misread):
  Read me    how to fill it in each week
  Settings   stakes, lock multiplier, leaderboard ranking, Head to Head opponent, Edge Finder week
  Tippers    #, name, outlet (1 = you, then every expert in the order of the expert-pick rows)
  Wk 1..18   GAMES & YOUR PICKS (rows 6-21) · LOCKS (row 25) · ODDS FEED open & close (rows 30-45) · EXPERT PICKS (row 49 on)
Cream cells are the only ones you type in.
"""
import os
import numpy as np, pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter as COL

NAVY, SLATE, ACCENT, GOLD, PAPER, CREAM, GREY, WHITE, INK = '17202B', '243447', '2E4A66', 'C99A2E', 'F4F6F9', 'FBF3DF', '6B7280', 'FFFFFF', '1F2937'
F = lambda size=10, bold=False, color=INK, italic=False: Font(name='Arial', size=size, bold=bold, color=color, italic=italic)
fill = lambda c: PatternFill('solid', fgColor=c)
thin = Side(style='thin', color='D9DEE7'); BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
NG, NW = 16, 18
G0, LOCK_ROW, O0, E0 = 6, 25, 30, 49          # first game row, lock row, first odds row, first expert row
GAME_COLS = ['#', 'Kickoff (UK)', 'Slot', 'Away', 'Home', 'Away pts', 'Home pts', 'Your tip', 'Your spread bet', 'Your over/under', 'Notes']
ODDS_FIELDS = ['Home line', 'Away price', 'Home price', 'Total', 'Over price', 'Under price', 'Away win odds', 'Home win odds']
LOCK_COLS = ['Tip lock (team)', 'Spread lock (team)', 'Over/under lock (a team in that game)']
TEAMS = {'ARI': ('Arizona Cardinals', 'NFC West'), 'ATL': ('Atlanta Falcons', 'NFC South'), 'BAL': ('Baltimore Ravens', 'AFC North'),
         'BUF': ('Buffalo Bills', 'AFC East'), 'CAR': ('Carolina Panthers', 'NFC South'), 'CHI': ('Chicago Bears', 'NFC North'),
         'CIN': ('Cincinnati Bengals', 'AFC North'), 'CLE': ('Cleveland Browns', 'AFC North'), 'DAL': ('Dallas Cowboys', 'NFC East'),
         'DEN': ('Denver Broncos', 'AFC West'), 'DET': ('Detroit Lions', 'NFC North'), 'GB': ('Green Bay Packers', 'NFC North'),
         'HOU': ('Houston Texans', 'AFC South'), 'IND': ('Indianapolis Colts', 'AFC South'), 'JAX': ('Jacksonville Jaguars', 'AFC South'),
         'KC': ('Kansas City Chiefs', 'AFC West'), 'LAC': ('Los Angeles Chargers', 'AFC West'), 'LAR': ('Los Angeles Rams', 'NFC West'),
         'LV': ('Las Vegas Raiders', 'AFC West'), 'MIA': ('Miami Dolphins', 'AFC East'), 'MIN': ('Minnesota Vikings', 'NFC North'),
         'NE': ('New England Patriots', 'AFC East'), 'NO': ('New Orleans Saints', 'NFC South'), 'NYG': ('New York Giants', 'NFC East'),
         'NYJ': ('New York Jets', 'AFC East'), 'PHI': ('Philadelphia Eagles', 'NFC East'), 'PIT': ('Pittsburgh Steelers', 'AFC North'),
         'SEA': ('Seattle Seahawks', 'NFC West'), 'SF': ('San Francisco 49ers', 'NFC West'), 'TB': ('Tampa Bay Buccaneers', 'NFC South'),
         'TEN': ('Tennessee Titans', 'AFC South'), 'WSH': ('Washington Commanders', 'NFC East')}
SETTINGS = [('Stake per tip ($)', 100, 'Every tip is staked this much at your fair win odds.'),
            ('Stake per spread bet ($)', 50, ''), ('Stake per over / under bet ($)', 25, ''),
            ('Lock of the week multiplier', 2, 'Your tip, spread and over/under locks are staked at this many times the normal stake.'),
            ('Rank leaderboard by', 'Wins', 'Wins, Win % or Profit.'),
            ('Head to Head opponent', 'Steve Gardner', 'Any name from the Tippers sheet (or Model / Vegas line).'),
            ('Edge Finder week', None, 'Blank = the latest week with odds entered. Type 1-18 to look at another week.')]


def _band(ws, title, sub, width):
    ws.sheet_view.showGridLines = False
    for c in range(1, width + 1):
        ws.cell(1, c).fill = fill(NAVY); ws.cell(2, c).fill = fill(SLATE)
    ws.cell(1, 1, '  ' + title).font = F(14, True, WHITE); ws.row_dimensions[1].height = 26
    ws.cell(2, 1, '  ' + sub).font = F(9, False, 'D1D5DB', True)


def _hdr(ws, r, c, text, w=None):
    x = ws.cell(r, c, text); x.font = F(9, True, WHITE); x.fill = fill(ACCENT); x.border = BOX
    x.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    if w: ws.column_dimensions[COL(c)].width = w


def _section(ws, r, text):
    x = ws.cell(r, 1, text); x.font = F(10, True, GOLD)


def _cream(c, v=None, fmt=None):
    if v is not None: c.value = v
    c.fill = fill(CREAM); c.border = BOX; c.font = F(10, False, INK); c.alignment = Alignment(horizontal='center')
    if fmt: c.number_format = fmt


def new_workbook(tippers):
    """Empty inputs workbook with the fixed layout. tippers: list of (name, outlet); first must be you."""
    wb = Workbook(); ws = wb.active; ws.title = 'Read me'
    _band(ws, 'TIPPING INPUTS  ·  the only file you type in', 'weekly.py reads this file and never changes it. A dated backup is made before every run (inputs/backups/).', 3)
    text = ['EACH WEEK', '1. Before kickoff: open the week tab. Enter the open and close odds in the ODDS FEED (open as soon as you have it, close before kickoff).',
            '2. Pick your tip, spread bet and over/under for each game from the drop-downs in the cream cells. Add your locks of the week (row 25).',
            '3. Enter each expert\'s pick in EXPERT PICKS (row 49 on). Leave a cell blank if they did not publish one.',
            '4. After the games: type the two scores. Then run python3 weekly.py: everything else is worked out in output/NFL_Model_2026.xlsx.',
            '', 'RULES THE OUTPUT USES', '• Fair price = ROUND(2 / (1/open + 1/close), 2) for every price; fair line / total = midpoint of open and close, quarter points rounded to the .5.',
            '• If only one of open / close is entered, that one is used.', '• A tie: type both scores; every pick on that game is graded wrong (as before).',
            '• Lock of the week: double stake on that tip / spread bet / over-under bet.', '',
            'ADDING AN EXPERT', '• Add the name and outlet at the bottom of Tippers, then use the next empty row in EXPERT PICKS on each week tab (same order as Tippers).',
            '• A tipper whose outlet is exactly "Bot" (like the old Stats model row) is scored and ranked but left out of the panel consensus and the expert-only stats.']
    for i, t in enumerate(text):
        c = ws.cell(4 + i, 1, t); c.font = F(10, t.isupper() and t != '', GOLD if t.isupper() else INK)
    ws.column_dimensions['A'].width = 150
    s = wb.create_sheet('Settings'); _band(s, 'SETTINGS', 'Cream cells only.', 3)
    for j, h in enumerate(['Setting', 'Value', 'Note'], 1): _hdr(s, 4, j, h)
    for i, (k, v, note) in enumerate(SETTINGS):
        s.cell(5 + i, 1, k).font = F(10, True); _cream(s.cell(5 + i, 2), v); s.cell(5 + i, 3, note).font = F(9, False, GREY, True)
    s.column_dimensions['A'].width = 30; s.column_dimensions['B'].width = 18; s.column_dimensions['C'].width = 90
    dv = DataValidation(type='list', formula1='"Wins,Win %,Profit"', allow_blank=False); s.add_data_validation(dv); dv.add('B9')
    t = wb.create_sheet('Tippers'); _band(t, 'TIPPERS', '#1 is you. The expert rows on every week tab follow this order. Rename here and it changes everywhere.', 3)
    for j, h in enumerate(['#', 'Name', 'Outlet'], 1): _hdr(t, 4, j, h)
    for i, (n, o) in enumerate(tippers):
        t.cell(5 + i, 1, i + 1).font = F(10, False, GREY); _cream(t.cell(5 + i, 2), n); _cream(t.cell(5 + i, 3), o)
        t.cell(5 + i, 2).alignment = Alignment(horizontal='left')
    t.column_dimensions['B'].width = 28; t.column_dimensions['C'].width = 22
    lst = wb.create_sheet('Lists'); lst.sheet_state = 'hidden'
    for i, code in enumerate(TEAMS): lst.cell(1 + i, 1, code)
    for wk in range(1, NW + 1): _week_sheet(wb, wk, len(tippers) - 1)
    wb.move_sheet('Read me', -len(wb.sheetnames))
    return wb


def _week_sheet(wb, wk, n_experts):
    ws = wb.create_sheet(f'Wk {wk}')
    _band(ws, f'WEEK {wk}  ·  YOUR ENTRIES', 'Cream cells only. Scores after the games; odds before kickoff (open and close); expert picks whenever they are published.', 19)
    _section(ws, 4, 'GAMES & YOUR PICKS')
    widths = [4, 17, 11, 8, 8, 8, 8, 10, 10, 11, 24]
    for j, (h, w) in enumerate(zip(GAME_COLS, widths), 1): _hdr(ws, 5, j, h, w)
    team_dv = DataValidation(type='list', formula1='=Lists!$A$1:$A$32', allow_blank=True); ws.add_data_validation(team_dv)
    ou_dv = DataValidation(type='list', formula1='"Over,Under"', allow_blank=True); ws.add_data_validation(ou_dv)
    for i in range(NG):
        r = G0 + i; ws.cell(r, 1, i + 1).font = F(9, False, GREY); ws.cell(r, 1).alignment = Alignment(horizontal='center')
        for c in range(2, 12): _cream(ws.cell(r, c))
        ws.cell(r, 2).alignment = Alignment(horizontal='left'); ws.cell(r, 11).alignment = Alignment(horizontal='left')
        team_dv.add(f'D{r}:E{r}')
        pick = DataValidation(type='list', formula1=f'=$D${r}:$E${r}', allow_blank=True); ws.add_data_validation(pick); pick.add(f'H{r}:I{r}')
        ou_dv.add(f'J{r}')
    _section(ws, LOCK_ROW - 2, 'LOCKS OF THE WEEK  ·  double stake  ·  type the team')
    for j, h in enumerate(LOCK_COLS): _hdr(ws, LOCK_ROW - 1, 2 + j * 3, h); ws.merge_cells(start_row=LOCK_ROW - 1, start_column=2 + j * 3, end_row=LOCK_ROW - 1, end_column=4 + j * 3)
    for j in range(3):
        _cream(ws.cell(LOCK_ROW, 2 + j * 3)); team_dv.add(f'{COL(2 + j * 3)}{LOCK_ROW}')
    _section(ws, O0 - 3, 'ODDS FEED  ·  OPEN & CLOSE  ·  decimal prices; home line: − = home favoured')
    ws.cell(O0 - 2, 3, 'OPEN').font = F(9, True, GOLD); ws.cell(O0 - 2, 11, 'CLOSE').font = F(9, True, GOLD)
    _hdr(ws, O0 - 1, 1, '#'); _hdr(ws, O0 - 1, 2, 'Game')
    for j, h in enumerate(ODDS_FIELDS):
        _hdr(ws, O0 - 1, 3 + j, h); _hdr(ws, O0 - 1, 11 + j, h)
    for i in range(NG):
        r = O0 + i; ws.cell(r, 1, i + 1).font = F(9, False, GREY)
        g = ws.cell(r, 2, f'=IF($D${G0 + i}="","",$D${G0 + i}&" @ "&$E${G0 + i})'); g.font = F(9, False, GREY)
        for c in range(3, 19): _cream(ws.cell(r, c), fmt='0.00' if (c - 3) % 8 not in (0, 3) else '0.0')
    _section(ws, E0 - 2, 'EXPERT PICKS  ·  one row per expert (same order as Tippers), one column per game')
    _hdr(ws, E0 - 1, 1, 'Expert'); _hdr(ws, E0 - 1, 2, 'Outlet')
    for k in range(NG):
        _hdr(ws, E0 - 1, 3 + k, f'=IF($D${G0 + k}="","G{k + 1}",$D${G0 + k}&CHAR(10)&"@ "&$E${G0 + k})')
        ws.column_dimensions[COL(3 + k)].width = max(ws.column_dimensions[COL(3 + k)].width or 8, 8)
    ws.row_dimensions[E0 - 1].height = 30
    for i in range(n_experts):
        r = E0 + i
        ws.cell(r, 1, f'=Tippers!$B${6 + i}').font = F(9, True); ws.cell(r, 2, f'=Tippers!$C${6 + i}').font = F(9, False, GREY)
        for k in range(NG):
            _cream(ws.cell(r, 3 + k))
            if i == 0:
                dvk = DataValidation(type='list', formula1=f'=$D${G0 + k}:$E${G0 + k}', allow_blank=True); ws.add_data_validation(dvk)
                dvk.add(f'{COL(3 + k)}{E0}:{COL(3 + k)}{E0 + n_experts + 20}')
    ws.column_dimensions['A'].width = 24; ws.column_dimensions['B'].width = 17
    ws.freeze_panes = 'C6'


def import_original(src, dst):
    """One-time: copy every typed entry of the original NFL_Tipping workbook into a new inputs file."""
    wb0 = load_workbook(src, data_only=False)
    setup = wb0['Setup']
    tippers = [(setup.cell(r, 7).value, setup.cell(r, 8).value) for r in range(14, 45)]        # Tom + 30 experts
    tippers.append((setup.cell(49, 7).value, setup.cell(49, 8).value))                         # the old stats model row (typed picks, outlet 'Bot')
    wb = new_workbook(tippers)
    s = wb['Settings']
    s['B5'] = setup['C13'].value; s['B6'] = setup['C16'].value; s['B7'] = setup['C15'].value; s['B8'] = 2
    s['B9'] = setup['C14'].value; s['B10'] = wb0['Head to Head']['D4'].value; s['B11'] = None
    money = wb0['Money']
    raw = lambda c: None if (c.value is None or (isinstance(c.value, str) and c.value.startswith('='))) else c.value
    for wk in range(1, NW + 1):
        o, n = wb0[f'Wk {wk}'], wb[f'Wk {wk}']
        for i in range(NG):
            r0, r = 10 + i, G0 + i
            for src_col, dst_col in ((2, 2), (21, 3), (3, 4), (4, 5), (11, 6), (12, 7), (5, 8), (22, 11)):
                n.cell(r, dst_col).value = raw(o.cell(r0, src_col))
            n.cell(r, 9).value = raw(o.cell(30 + i, 7)); n.cell(r, 10).value = raw(o.cell(30 + i, 15))
            for j in range(16): n.cell(O0 + i, 3 + j).value = raw(o.cell(95 + i, 3 + j))
            for e in range(30): n.cell(E0 + e, 3 + i).value = raw(o.cell(52 + e, 3 + i))
            n.cell(E0 + 30, 3 + i).value = raw(o.cell(86, 3 + i))                                 # old stats model row
        n.cell(LOCK_ROW, 2).value = raw(money.cell(55 + wk, 3)); n.cell(LOCK_ROW, 5).value = raw(money.cell(55 + wk, 8))
        n.cell(LOCK_ROW, 8).value = raw(money.cell(55 + wk, 13))
    os.makedirs(os.path.dirname(dst), exist_ok=True); wb.save(dst)
    return dst


def _num(v):
    if v is None or v == '': return np.nan
    try: return float(v)
    except (TypeError, ValueError): return np.nan


def _txt(v):
    return None if v is None or str(v).strip() == '' else str(v).strip()


def read_inputs(path):
    """Read the inputs file (read-only). Returns dict(settings, tippers, weeks{wk: dict(games, odds, locks, experts)})."""
    wb = load_workbook(path, data_only=True, read_only=True)
    s = wb['Settings']; vals = {r[0].value: r[1].value for r in s.iter_rows(min_row=5, max_row=4 + len(SETTINGS)) if r[0].value}
    settings = dict(tip=float(vals.get('Stake per tip ($)') or 100), spread=float(vals.get('Stake per spread bet ($)') or 50),
                    ou=float(vals.get('Stake per over / under bet ($)') or 25), lock=float(vals.get('Lock of the week multiplier') or 2),
                    rank_by=vals.get('Rank leaderboard by') or 'Wins', h2h=vals.get('Head to Head opponent') or '',
                    edge_week=int(vals['Edge Finder week']) if vals.get('Edge Finder week') not in (None, '') else None)
    t = wb['Tippers']; tippers = [(r[1].value, r[2].value) for r in t.iter_rows(min_row=5) if r[1].value]
    weeks = {}
    for wk in range(1, NW + 1):
        ws = wb[f'Wk {wk}']
        rows = list(ws.iter_rows(min_row=1, max_row=E0 + len(tippers) + 25, max_col=19, values_only=True))
        hdr = [rows[4][j] for j in range(len(GAME_COLS))]
        if hdr != GAME_COLS:
            raise ValueError(f'tipping_inputs.xlsx Wk {wk}: the GAMES header row has moved or changed ({hdr}); restore the original layout.')
        g = []
        for i in range(NG):
            r = rows[G0 - 1 + i]
            if not _txt(r[3]) or not _txt(r[4]): continue
            od = rows[O0 - 1 + i]
            g.append(dict(week=wk, game=i + 1, kickoff=_txt(r[1]), slot=_txt(r[2]), away=_txt(r[3]), home=_txt(r[4]),
                          away_pts=_num(r[5]), home_pts=_num(r[6]), tip=_txt(r[7]), spread_bet=_txt(r[8]), ou_bet=_txt(r[9]), notes=_txt(r[10]),
                          **{f'open_{k}': _num(od[2 + j]) for j, k in enumerate(['hline', 'aprice', 'hprice', 'total', 'oprice', 'uprice', 'aml', 'hml'])},
                          **{f'close_{k}': _num(od[10 + j]) for j, k in enumerate(['hline', 'aprice', 'hprice', 'total', 'oprice', 'uprice', 'aml', 'hml'])}))
        lr = rows[LOCK_ROW - 1]
        locks = dict(tip=_txt(lr[1]), spread=_txt(lr[4]), ou=_txt(lr[7]))
        ex = {}
        for e, (name, _) in enumerate(tippers[1:]):
            r = rows[E0 - 1 + e]
            ex[name] = {i + 1: _txt(r[2 + i]) for i in range(NG)}
        weeks[wk] = dict(games=pd.DataFrame(g), locks=locks, experts=ex)
    wb.close()
    return dict(settings=settings, tippers=tippers, weeks=weeks)
