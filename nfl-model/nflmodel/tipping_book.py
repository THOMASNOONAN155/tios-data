"""The tipping half of output/NFL_Model_<season>.xlsx: week tabs, Leaderboard, Money, My Stats, Spreads & Totals,
Head to Head, Expert Scout, Edge Finder, Value Report and a read-only Settings sheet.

Everything is rebuilt from inputs/tipping_inputs.xlsx (never written to). Week tabs and the Leaderboard's weekly wins are
live formulas (fair prices, fair lines, winner, ✓/✗, stakes with locks, P/L, every tipper's weekly score), so the workbook
recalculates itself; weekly.py checks those formulas against the Python engine (nflmodel/tipping*.py) after a LibreOffice
recalculation. The analysis sheets are written as values from the same engine.
"""
import numpy as np, pandas as pd
from openpyxl.styles import Alignment, Border, Side, Font
from openpyxl.chart import LineChart, BarChart, Reference, Series
from openpyxl.utils import get_column_letter as COL
from openpyxl.worksheet.hyperlink import Hyperlink
from openpyxl.formatting.rule import CellIsRule, FormulaRule, DataBarRule
from nflmodel.workbook import band, table, section, scale, F, fill, NAVY, SLATE, ACCENT, GOLD, PAPER, GREY, WHITE, INK, RED, GREEN, LEFT, CEN, RIGHT, BOX
from nflmodel.tipping import NW, MODEL, LINE, BOT_CONSENSUS, BOT_FAV, BOT_HOME, BOT_DOG
from nflmodel.tipping_inputs import TEAMS

CREAM = 'FBF3DF'          # cells that come straight from your inputs file
LIGHTGOLD = 'F6EBCB'      # your own row
MON, MON2, STK, PCT, PCT0, ODD, LN, EVF = ('+$#,##0;-$#,##0;$0', '+$#,##0.00;-$#,##0.00;$0.00', '$#,##0', '0.0%', '0%', '0.00',
                                         '+0.0;-0.0;0.0', '+0.0%;-0.0%;0.0%')
TIP_SHEETS = ['Leaderboard', 'Money', 'My Stats', 'Spreads & Totals', 'Head to Head', 'Expert Scout', 'Edge Finder', 'Value Report']
GAME0, BET0 = 10, 30          # week tab: first game row, first bet row
num = lambda v: None if v is None or (isinstance(v, float) and np.isnan(v)) else (v.item() if hasattr(v, 'item') else v)


def link(ws, r, c, text, sheet, cell='A1'):
    x = ws.cell(r, c, text); x.hyperlink = Hyperlink(ref=x.coordinate, location=f"'{sheet}'!{cell}", display=text)
    x.font = Font(name='Arial', size=9, color=ACCENT, underline='single', bold=True); return x


def nav(ws, extra=()):
    """Row 3: links to the main sheets (and any extra (text, sheet) pairs, e.g. previous / next week)."""
    items = [('⌂ Dashboard', 'Dashboard'), ('Leaderboard', 'Leaderboard'), ('Money', 'Money'), ('My Stats', 'My Stats')] + list(extra)
    c = 1
    for text, sheet in items:
        link(ws, 3, c, text, sheet); room = 0
        while room < len(text) * 1.1 + 3:
            room += ws.column_dimensions[COL(c)].width or 8.43; c += 1
    ws.row_dimensions[3].height = 16


def cell(ws, r, c, v, fmt=None, bold=False, color=INK, bg=None, align=CEN, size=10, italic=False):
    x = ws.cell(r, c, num(v)); x.font = F(size, bold, color, italic); x.alignment = align
    if fmt: x.number_format = fmt
    if bg: x.fill = fill(bg)
    return x


def header(ws, r, c0, labels, height=30, bg=ACCENT):
    for j, h in enumerate(labels):
        x = ws.cell(r, c0 + j, h); x.font = F(9, True, WHITE); x.fill = fill(bg)
        x.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    ws.row_dimensions[r].height = height


def tile(ws, r, c, label, value, sub='', fmt=None, color=NAVY):
    """A KPI tile: small caps label, big value, grey note (three rows)."""
    cell(ws, r, c, label.upper(), size=8, bold=True, color=GREY, align=LEFT)
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool) and fmt in (MON, MON2, EVF):
        v = float(value)
        value = (('+' if v > 0 else '-' if v < 0 else '') + f'${abs(v):,.{2 if fmt == MON2 else 0}f}') if fmt != EVF else f'{v * 100:+.1f}%'
        fmt = None
    x = cell(ws, r + 1, c, value, fmt, bold=True, size=16, color=color, align=LEFT)
    if sub: cell(ws, r + 2, c, sub, size=8, color=GREY, align=LEFT, italic=True)
    return x


def widths(ws, w):
    for k, v in w.items(): ws.column_dimensions[k].width = v


def pos_neg(ws, rng):
    ws.conditional_formatting.add(rng, CellIsRule(operator='greaterThan', formula=['0'], font=Font(color='1E7B45')))
    ws.conditional_formatting.add(rng, CellIsRule(operator='lessThan', formula=['0'], font=Font(color='B3261E')))


def ticks(ws, rng):
    ws.conditional_formatting.add(rng, CellIsRule(operator='equal', formula=['"✓"'], font=Font(color='1E7B45', bold=True), fill=fill('E3F2E8')))
    ws.conditional_formatting.add(rng, CellIsRule(operator='equal', formula=['"✗"'], font=Font(color='B3261E', bold=True), fill=fill('FBE6E4')))


def stats_rows(ws, r0, c0, first, rows, note=None):
    """The standard Picks / W / L / Win % / Odds said / +/- wins / P/L / ROI table used by My Stats and Spreads & Totals."""
    header(ws, r0, c0, [first, 'Picks', 'W', 'L', 'Win %', 'Odds said', '+/− wins', 'P/L', 'ROI'])
    for i, (lab, d) in enumerate(rows.items()):
        r = r0 + 1 + i; bg = PAPER if i % 2 else None
        cell(ws, r, c0, lab, align=LEFT, bg=bg)
        for j, (k, fm) in enumerate((('n', '0'), ('w', '0'), ('l', '0'), ('pct', PCT), ('said', PCT), ('plus', '+0.0;-0.0;0.0'), ('pl', MON), ('roi', EVF))):
            v = d[k] if not (k in ('pct', 'said', 'plus', 'roi') and d['n'] == 0) else None
            cell(ws, r, c0 + 1 + j, v, fm, bg=bg).border = BOX
    pos_neg(ws, f'{COL(c0 + 7)}{r0 + 1}:{COL(c0 + 8)}{r0 + len(rows)}')
    return r0 + len(rows)


# ------------------------------------------------------------------ formula fragments (cell references are strings like "H30")
def f_fair(o, c):
    return f'IF(AND({o}="",{c}=""),"",IF({o}="",{c},IF({c}="",{o},ROUND(2/(1/{o}+1/{c}),2))))'


def f_line(o, c):
    s = f'({o}+{c})'
    return f'IF(AND({o}="",{c}=""),"",IF({o}="",{c},IF({c}="",{o},IF(MOD({s},1)<>0,INT({s}/2)+0.5,{s}/2))))'


def f_dec(x):
    return f'IF({x}>=100,1+{x}/100,IF({x}<=-100,1+100/ABS({x}),{x}))'


# ------------------------------------------------------------------ week tabs
def week_layout(ctx, wk):
    """Row numbers on a week tab (shared by the writer, the Leaderboard formulas and the self-test)."""
    n = len(ctx['G'][ctx['G'].week == wk]); tippers = list(ctx['P'].columns)
    e_hdr = BET0 + 16 + 3            # experts header row
    e0 = e_hdr + 2                   # first tipper row (the row above holds the results)
    o_hdr = e0 + len(tippers) + 3    # odds header
    return dict(n=n, e_hdr=e_hdr, res=e_hdr + 1, e0=e0, rows={t: e0 + i for i, t in enumerate(tippers)}, o_hdr=o_hdr, o0=o_hdr + 1)


def week_tab(wb, ctx, wk, model):
    G, P, S = ctx['G'], ctx['P'], ctx['S']
    g = G[G.week == wk].sort_values('game'); L = week_layout(ctx, wk); lk = ctx['inp']['weeks'][wk]['locks']
    ws = wb.create_sheet(f'Wk {wk}')
    played = int(g.played.sum())
    band(ws, f'WEEK {wk}  ·  TIPS, BETS & RESULTS', f'{len(g)} games · {played} played. Cream cells come from inputs/tipping_inputs.xlsx (edit them there, '
         'not here). Fair odds and lines = midpoint of open and close; prices = ROUND(2/(1/open+1/close),2).', 21)
    # settings + locks
    cell(ws, 4, 1, f'Stakes: tip ${S["tip"]:,.0f} · spread ${S["spread"]:,.0f} · over/under ${S["ou"]:,.0f} · lock of the week ×{S["lock"]:g}', size=9, color=GREY, align=LEFT, italic=True)
    link(ws, 4, 12, 'Settings ▸', 'Settings')
    cell(ws, 7, 1, 'LOCK OF THE WEEK', size=8, bold=True, color=GOLD, align=LEFT)
    for c, lab, v in ((4, 'Tip', lk.get('tip')), (7, 'Spread', lk.get('spread')), (10, 'O/U game', lk.get('ou'))):
        cell(ws, 7, c, lab, size=9, bold=True, align=RIGHT); cell(ws, 7, c + 1, v or '', bold=True, bg=CREAM)
    TL, SL, OL = '$E$7', '$H$7', '$K$7'
    # tiles (live)
    gl, gr = GAME0, GAME0 + max(len(g), 1) - 1; bl, br = BET0, BET0 + max(len(g), 1) - 1
    tile(ws, 4 + 1, 14, 'Tips', f'=COUNTIF(M{gl}:M{gr},"✓")&"–"&COUNTIF(M{gl}:M{gr},"✗")')
    tile(ws, 4 + 1, 16, 'Tip P/L', f'=SUM(O{gl}:O{gr})', fmt=MON)
    tile(ws, 4 + 1, 18, 'Bets P/L', f'=SUM(L{bl}:L{br})+SUM(S{bl}:S{br})', fmt=MON)
    tile(ws, 4 + 1, 20, 'Week P/L', f'=P6+R6', fmt=MON, color=GOLD)
    for c in (16, 18, 20): pos_neg(ws, f'{COL(c)}6')
    # ---------------- games
    section(ws, 8, 1, 'Games & your tips', 21)
    header(ws, 9, 1, ['#', 'Kickoff (UK)', 'Away', 'Home', 'Away pts', 'Home pts', 'Your tip', 'Away fair odds', 'Home fair odds', 'Fair home line',
                      'Fair total', 'Winner', '✓ / ✗', 'Stake', 'P/L', 'Model tip', 'Model win %', "Line's pick", 'Model ✓ / ✗', 'Panel consensus', 'Notes'], height=32)
    oo = lambda j, k: f'{COL(k)}{L["o0"] + j}'   # odds block cell for game index j, column k (3 = open home line ...)
    for j, r in enumerate(g.itertuples()):
        i = GAME0 + j; b = BET0 + j; bg = PAPER if j % 2 else None
        cell(ws, i, 1, int(r.game), bg=bg); cell(ws, i, 2, r.kickoff, bg=bg, size=9)
        cell(ws, i, 3, r.away, bold=True, bg=CREAM); cell(ws, i, 4, r.home, bold=True, bg=CREAM)
        cell(ws, i, 5, r.away_pts, '0', bg=CREAM); cell(ws, i, 6, r.home_pts, '0', bg=CREAM)
        cell(ws, i, 7, r.tip or None, bold=True, bg=CREAM)
        cell(ws, i, 8, '=' + f_fair(oo(j, 9), oo(j, 17)), ODD, bg=bg); cell(ws, i, 9, '=' + f_fair(oo(j, 10), oo(j, 18)), ODD, bg=bg)
        cell(ws, i, 10, '=' + f_line(oo(j, 3), oo(j, 11)), LN, bg=bg); cell(ws, i, 11, '=' + f_line(oo(j, 6), oo(j, 14)), '0.0', bg=bg)
        cell(ws, i, 12, f'=IF(OR(E{i}="",F{i}=""),"",IF(E{i}>F{i},C{i},IF(F{i}>E{i},D{i},"TIE")))', bold=True, bg=bg)
        cell(ws, i, 13, f'=IF(OR(G{i}="",L{i}=""),"",IF(G{i}=L{i},"✓","✗"))', bg=bg)
        cell(ws, i, 14, f'=IF(G{i}="","",Settings!$B$5*IF(G{i}={TL},Settings!$B$8,1))', STK, bg=bg)
        cell(ws, i, 15, f'=IF(M{i}="","",IFERROR(IF(M{i}="✓",N{i}*(IF(G{i}=C{i},H{i},I{i})-1),-N{i}),""))', MON2, bg=bg)
        mt = model.get(r.gid, {})
        cell(ws, i, 16, mt.get('tip'), bold=True, color=ACCENT, bg=bg); cell(ws, i, 17, mt.get('prob'), PCT0, color=ACCENT, bg=bg)
        cell(ws, i, 18, f'=IF(AND(H{i}="",J{i}=""),"",IF(J{i}="",IF(H{i}<I{i},C{i},D{i}),IF(J{i}<0,D{i},IF(J{i}>0,C{i},IF(H{i}<I{i},C{i},D{i})))))', color=ACCENT, bg=bg)
        cell(ws, i, 19, f'=IF(OR(P{i}="",L{i}=""),"",IF(P{i}=L{i},"✓","✗"))', bg=bg)
        cell(ws, i, 20, P.at[r.Index, BOT_CONSENSUS], bg=bg); note = r.notes if isinstance(r.notes, str) and r.notes else None
        cell(ws, i, 21, note, size=8, align=LEFT, bg=CREAM if note else bg)
        for k in range(1, 22): ws.cell(i, k).border = BOX
        # ---------------- bets (same game order)
        cell(ws, b, 1, int(r.game), bg=bg); cell(ws, b, 2, f'{r.away} @ {r.home}', bg=bg, align=LEFT)
        cell(ws, b, 3, f'=IF(J{i}="","",-J{i})', LN, bg=bg); cell(ws, b, 4, '=' + f_fair(oo(j, 4), oo(j, 12)), ODD, bg=bg)
        cell(ws, b, 5, f'=J{i}', LN, bg=bg); cell(ws, b, 6, '=' + f_fair(oo(j, 5), oo(j, 13)), ODD, bg=bg)
        cell(ws, b, 7, r.spread_bet or None, bold=True, bg=CREAM)
        cell(ws, b, 8, f'=IF(G{b}="","",Settings!$B$6*IF(G{b}={SL},Settings!$B$8,1))', STK, bg=bg)
        cell(ws, b, 9, f'=IF(G{b}="","",IF(G{b}=C{i},C{b},E{b}))', LN, bg=bg)
        cell(ws, b, 10, f'=IF(G{b}="","",IFERROR({f_dec(f"IF(G{b}=C{i},D{b},F{b})")},""))', ODD, bg=bg)
        m = f'(IF(G{b}=C{i},E{i}-F{i},F{i}-E{i})+I{b})'
        cell(ws, b, 11, f'=IF(OR(G{b}="",L{i}="",I{b}=""),"",IF({m}>0,"✓",IF({m}<0,"✗","Push")))', bg=bg)
        cell(ws, b, 12, f'=IF(K{b}="","",IF(K{b}="✓",IFERROR(H{b}*(J{b}-1),0),IF(K{b}="✗",-H{b},0)))', MON2, bg=bg)
        cell(ws, b, 13, '=' + f_line(oo(j, 6), oo(j, 14)), '0.0', bg=bg)
        cell(ws, b, 14, '=' + f_fair(oo(j, 7), oo(j, 15)), ODD, bg=bg); cell(ws, b, 15, '=' + f_fair(oo(j, 8), oo(j, 16)), ODD, bg=bg)
        cell(ws, b, 16, r.ou_bet or None, bold=True, bg=CREAM)
        cell(ws, b, 17, f'=IF(P{b}="","",Settings!$B$7*IF(AND({OL}<>"",OR({OL}=C{i},{OL}=D{i})),Settings!$B$8,1))', STK, bg=bg)
        t = f'(E{i}+F{i})'
        cell(ws, b, 18, f'=IF(OR(P{b}="",L{i}="",M{b}=""),"",IF({t}>M{b},IF(P{b}="Over","✓","✗"),IF({t}<M{b},IF(P{b}="Under","✓","✗"),"Push")))', bg=bg)
        pr = f_dec(f'IF(P{b}="Over",N{b},O{b})')
        cell(ws, b, 19, f'=IF(R{b}="","",IF(R{b}="✓",IFERROR(Q{b}*({pr}-1),0),IF(R{b}="✗",-Q{b},0)))', MON2, bg=bg)
        for k in range(1, 20): ws.cell(b, k).border = BOX
    if len(g) == 0: cell(ws, GAME0, 2, 'No fixtures in the inputs file for this week yet.', align=LEFT, italic=True, color=GREY)
    ticks(ws, f'M{GAME0}:M{GAME0 + 15}'); ticks(ws, f'S{GAME0}:S{GAME0 + 15}'); pos_neg(ws, f'O{GAME0}:O{GAME0 + 15}')
    section(ws, BET0 - 2, 1, 'Spread and over / under bets (fair line and price)', 19)
    header(ws, BET0 - 1, 1, ['#', 'Game', 'Away line', 'Away price', 'Home line', 'Home price', 'Your spread bet', 'Stake', 'Line taken', 'Price', 'Result', 'P/L',
                              'Fair total', 'Over price', 'Under price', 'Your over / under', 'Stake', 'Result', 'P/L'], height=32)
    ticks(ws, f'K{BET0}:K{BET0 + 15}'); ticks(ws, f'R{BET0}:R{BET0 + 15}'); pos_neg(ws, f'L{BET0}:L{BET0 + 15}'); pos_neg(ws, f'S{BET0}:S{BET0 + 15}')
    # ---------------- every tipper's picks
    eh, rr = L['e_hdr'], L['res']
    section(ws, eh - 1, 1, 'Every tipper\'s picks (experts from your inputs file; bots, model and line worked out)', 21)
    header(ws, eh, 1, ['', 'Tipper'] + [f'{r.away}@{r.home}' for r in g.itertuples()] + [''] * (16 - len(g)) + ['Right', 'Graded'], height=30)
    cell(ws, rr, 1, '', bg=SLATE); cell(ws, rr, 2, 'Winner', bold=True, color=WHITE, bg=SLATE, align=LEFT)
    for j in range(16):
        c = cell(ws, rr, 3 + j, f'=L{GAME0 + j}' if j < len(g) else None, bold=True, color=WHITE, bg=SLATE)
    cell(ws, rr, 19, '', bg=SLATE); cell(ws, rr, 20, '', bg=SLATE)
    typed = {n for n, _ in ctx['inp']['tippers']}
    for t, x in L['rows'].items():
        mine = t == ctx['you']; bot = t not in typed or ctx['outlets'][t] == 'Bot'
        bg = LIGHTGOLD if mine else (PAPER if t in (MODEL, LINE) else None)
        cell(ws, x, 1, x - L['e0'] + 1, size=8, color=GREY, bg=bg)
        cell(ws, x, 2, t, bold=mine or t in (MODEL, LINE), align=LEFT, bg=bg, color=ACCENT if t in (MODEL, LINE) else INK, size=9)
        for j, r in enumerate(g.itertuples()):
            if mine: v = f'=IF(G{GAME0 + j}="","",G{GAME0 + j})'
            elif t == LINE: v = f'=R{GAME0 + j}'
            else: v = P.at[r.Index, t]
            cell(ws, x, 3 + j, v, size=9, bg=(CREAM if (t in typed and not bot and not mine) else bg))
        cell(ws, x, 19, f'=SUMPRODUCT((C{x}:R{x}=C${rr}:R${rr})*(C${rr}:R${rr}<>""))', '0', bold=True, bg=bg)
        cell(ws, x, 20, f'=SUMPRODUCT((C{x}:R{x}<>"")*(C${rr}:R${rr}<>""))', '0', bg=bg)
    last = L['e0'] + len(L['rows']) - 1
    for j in range(len(g)):
        c = COL(3 + j)
        ws.conditional_formatting.add(f'{c}{L["e0"]}:{c}{last}', FormulaRule(formula=[f'AND({c}{L["e0"]}<>"",{c}${rr}<>"",{c}{L["e0"]}={c}${rr})'], fill=fill('E3F2E8')))
        ws.conditional_formatting.add(f'{c}{L["e0"]}:{c}{last}', FormulaRule(formula=[f'AND({c}{L["e0"]}<>"",{c}${rr}<>"",{c}{L["e0"]}<>{c}${rr})'], fill=fill('FBE6E4')))
    ws.conditional_formatting.add(f'S{L["e0"]}:S{last}', DataBarRule(start_type='num', start_value=0, end_type='max', color=GOLD))
    # ---------------- odds as typed
    oh = L['o_hdr']
    section(ws, oh - 1, 1, 'Odds as typed in the inputs file (open and close). Every fair number above uses both.', 18)
    fields = ['Home line', 'Away price', 'Home price', 'Total', 'Over price', 'Under price', 'Away win odds', 'Home win odds']
    header(ws, oh, 1, ['#', 'Game'] + [f'OPEN\n{f}' for f in fields] + [f'CLOSE\n{f}' for f in fields], height=40)
    for j, r in enumerate(g.itertuples()):
        x = L['o0'] + j
        cell(ws, x, 1, int(r.game)); cell(ws, x, 2, f'{r.away} @ {r.home}', align=LEFT, size=9)
        for k, fld in enumerate(('hline', 'aprice', 'hprice', 'total', 'oprice', 'uprice', 'aml', 'hml')):
            for side, off in (('open', 0), ('close', 8)):
                cell(ws, x, 3 + k + off, getattr(r, f'{side}_{fld}'), LN if fld == 'hline' else ('0.0' if fld == 'total' else ODD), bg=CREAM, size=9)
    widths(ws, {'A': 5, 'B': 23, 'C': 8, 'D': 8, 'E': 8, 'F': 8, 'G': 9, 'H': 9, 'I': 9, 'J': 9, 'K': 9, 'L': 9, 'M': 8, 'N': 9, 'O': 10,
                'P': 9, 'Q': 9, 'R': 9, 'S': 10, 'T': 10, 'U': 24})
    ws.freeze_panes = 'D10'
    return ws


# ------------------------------------------------------------------ Leaderboard (two extra tippers: the model and the line)
def leaderboard(wb, ctx):
    R, P, you = ctx['R'], ctx['P'], ctx['you']
    ws = wb.create_sheet('Leaderboard')
    band(ws, 'LEADERBOARD', f'Every tipper, ranked by {ctx["S"].get("rank_by", "Wins")}. Weekly wins are live formulas from the week tabs. '
         'New this season: the model (nfl-model\'s tip) and the betting line (always the line\'s favourite).', 40)
    weeks = list(range(1, NW + 1))
    cols = ['Rank', 'Tipper', 'Outlet'] + [f'Wk {w}' for w in weeks] + ['W', 'L', 'Win %', 'Behind', 'Pace /272', 'Last wk', 'Last 3', 'Best wk', 'Worst wk',
                                                                       '10+ wks', 'Weeks won', 'P/L ($100 flat)', 'ROI', 'ATS', 'ATS %', 'Dog wins', 'Same as you']
    header(ws, 4, 1, cols, height=32)
    order = R.sort_values('order').index
    n = len(order); last = 4 + n
    for i, t in enumerate(order):
        x = 5 + i; r = R.loc[t]; mine = t == you; new = t in (MODEL, LINE)
        bg = LIGHTGOLD if mine else (PAPER if new else (None if i % 2 == 0 else 'FAFBFC'))
        cell(ws, x, 1, int(r['rank']), bg=bg, bold=True); cell(ws, x, 2, t, bg=bg, bold=mine or new, align=LEFT, color=ACCENT if new else INK)
        cell(ws, x, 3, ctx['outlets'][t], bg=bg, size=8, color=GREY, align=LEFT)
        for k, w in enumerate(weeks):
            lay = week_layout(ctx, w); ref = f"'Wk {w}'!S{lay['rows'][t]}"
            v = f'=IF(SUMPRODUCT((\'Wk {w}\'!$L${GAME0}:$L${GAME0 + 15}<>"")*1)=0,"",{ref})'
            cell(ws, x, 4 + k, v, '0', bg=bg, size=9)
        wc, lc = COL(4 + NW), COL(5 + NW)
        cell(ws, x, 4 + NW, f'=SUM(D{x}:{COL(3 + NW)}{x})', '0', bold=True, bg=bg)
        cell(ws, x, 5 + NW, '=' + '+'.join(f"'Wk {w}'!T{week_layout(ctx, w)['rows'][t]}" for w in weeks) + f'-{wc}{x}', '0', bg=bg)
        cell(ws, x, 6 + NW, f'=IF({wc}{x}+{lc}{x}=0,"",{wc}{x}/({wc}{x}+{lc}{x}))', PCT, bg=bg)
        cell(ws, x, 7 + NW, f'=MAX({wc}$5:{wc}${last})-{wc}{x}', '0', bg=bg)
        vals = [r.pace, r.last_wk, r.form3, r.best_wk, r.worst_wk, r.tens, r.weeks_won, r.pl, r.roi, f'{r.ats_w}–{r.ats_l}', r.ats_pct, f'{r.dog_wins} of {r.dog_picks}',
                None if mine else r.same_pct]
        fm = ['0', '0', '0', '0', '0', '0', '0', MON, EVF, None, PCT, None, PCT0]
        for k, (v, f_) in enumerate(zip(vals, fm)): cell(ws, x, 8 + NW + k, v, f_, bg=bg)
    pos_neg(ws, f'{COL(15 + NW)}5:{COL(16 + NW)}{last}')
    ws.conditional_formatting.add(f'{COL(6 + NW)}5:{COL(6 + NW)}{last}', DataBarRule(start_type='num', start_value=0.4, end_type='num', end_value=0.8, color=GOLD))
    scale(ws, f'D5:{COL(3 + NW)}{last}')
    widths(ws, {'A': 6, 'B': 20, 'C': 20})
    for k in range(NW): ws.column_dimensions[COL(4 + k)].width = 5.2
    for k, w_ in enumerate([6, 6, 8, 8, 8, 7, 7, 7, 8, 7, 8, 11, 8, 8, 8, 9, 9]): ws.column_dimensions[COL(4 + NW + k)].width = w_
    ws.freeze_panes = 'D5'
    # the race
    r0 = last + 3
    section(ws, r0, 1, 'The race  ·  cumulative wins after each week', 15)
    cell(ws, r0 + 1, 4, 'CUMULATIVE WINS', size=8, bold=True, color=GOLD, align=LEFT); cell(ws, r0 + 1, 12, 'BEHIND THE LEADER', size=8, bold=True, color=GOLD, align=LEFT)
    r0 += 1
    header(ws, r0 + 1, 1, ['Week', 'Leader', 'Top expert', 'Lead', 'You', 'Gap', 'Rank', 'Panel', 'Favs', 'Model', 'Line', 'You', 'Panel', 'Model', 'Line'], height=22)
    cum = ctx['W'].fillna(0).cumsum(axis=1)
    rows = 0
    for _, rr in ctx['race'].iterrows():
        if not isinstance(rr.get('leader'), str): continue
        x = r0 + 2 + rows; rows += 1; wk = int(rr.week); bg = PAPER if rows % 2 == 0 else None
        cm = lambda t: cum.at[t, wk] if t in cum.index else None
        vals = ((f'Wk {wk}', None), (rr.leader, None), (rr.top_expert, None), (rr.leader_wins, '0'), (rr.you, '0'), (rr.gap, '+0;-0;0'), (f'#{int(rr.your_rank)}', None),
                (rr.consensus, '0'), (rr.favourites, '0'), (cm(MODEL), '0'), (cm(LINE), '0'))
        for k, (v, f_) in enumerate(vals):
            cell(ws, x, 1 + k, v, f_, bg=bg, align=LEFT if k in (1, 2) else CEN, size=9)
        for k, c in enumerate(('E', 'H', 'J', 'K')):
            cell(ws, x, 12 + k, f'=IF({c}{x}="","",{c}{x}-D{x})', '+0;-0;0', bg=bg, size=9)
    if rows:
        ch = LineChart(); ch.title = 'Wins behind the leader after each week'; ch.height = 8; ch.width = 22
        ch.y_axis.title = 'Wins behind'; ch.legend.position = 'b'; ch.x_axis.tickLblPos = 'low'
        for c, t in ((12, 'You'), (13, 'Panel consensus'), (14, 'Model'), (15, 'Betting line')):
            s_ = Series(Reference(ws, min_col=c, min_row=r0 + 2, max_row=r0 + 1 + rows), title=t); s_.smooth = False; ch.series.append(s_)
        ch.set_categories(Reference(ws, min_col=1, min_row=r0 + 2, max_row=r0 + 1 + rows))
        ws.add_chart(ch, f'B{r0 + 3 + rows}')
    return ws


# ------------------------------------------------------------------ Money
def money_sheet(wb, ctx):
    M, X, S = ctx['money'], ctx['money_x'], ctx['S']
    ws = wb.create_sheet('Money')
    band(ws, 'MONEY', f'Real money: tips ${S["tip"]:,.0f}, spreads ${S["spread"]:,.0f}, over/unders ${S["ou"]:,.0f}, locks at ×{S["lock"]:g}. All at fair (open/close midpoint) prices.', 22)
    p = M.dropna(subset=['staked'])
    if len(p):
        best = p.pl.idxmax(); worst = p.pl.idxmin()
        tile(ws, 5, 2, 'Total profit / loss', float(p.pl.sum()), f'staked ${p.staked.sum():,.0f} · ROI {p.pl.sum() / p.staked.sum() * 100:+.1f}%', MON, GOLD)
        tile(ws, 5, 6, f'Tips (${S["tip"]:,.0f})', float(p.tip_pl.sum()), f'{int(p.tip_w.sum())}–{int(p.tip_l.sum())} · ROI {p.tip_pl.sum() / p.tip_staked.sum() * 100:+.1f}%', MON)
        tile(ws, 5, 10, f'Spreads (${S["spread"]:,.0f})', float(p.sp_pl.sum()), f'{int(p.sp_w.sum())}–{int(p.sp_l.sum())}–{int(p.sp_p.sum())} · ROI {p.sp_pl.sum() / max(1, p.sp_staked.sum()) * 100:+.1f}%', MON)
        tile(ws, 5, 14, f'Over / unders (${S["ou"]:,.0f})', float(p.ou_pl.sum()), f'{int(p.ou_w.sum())}–{int(p.ou_l.sum())}–{int(p.ou_p.sum())} · ROI {p.ou_pl.sum() / max(1, p.ou_staked.sum()) * 100:+.1f}%', MON)
        tile(ws, 5, 18, 'Best week', float(p.pl.max()), f'Wk {best} · worst Wk {worst} ({p.pl.min():+,.0f})', MON)
        tile(ws, 5, 21, 'Bank high point', float(p.high.max()), f'now {p.running.iloc[-1]:+,.0f}', MON)
    section(ws, 9, 2, 'Week by week (locks included)', 20)
    header(ws, 10, 2, ['Week', 'Tips W–L', 'Staked', 'P/L', 'Spreads W–L–P', 'Staked', 'P/L', 'O/U W–L–P', 'Staked', 'P/L', 'Total staked', 'Returned', 'Week P/L',
                       'Bank', 'High point', 'Below high'])
    rows = 0
    for wk, r in M.iterrows():
        x = 11 + rows; rows += 1; bg = PAPER if rows % 2 == 0 else None
        cell(ws, x, 2, f'Wk {wk}', bg=bg)
        if np.isnan(r.get('staked', np.nan)): continue
        from nflmodel.tipping_sheets import wl
        for k, (v, f_) in enumerate(((wl(r.tip_w, r.tip_l), None), (r.tip_staked, STK), (r.tip_pl, MON), (wl(r.sp_w, r.sp_l, r.sp_p), None), (r.sp_staked, STK), (r.sp_pl, MON),
                                     (wl(r.ou_w, r.ou_l, r.ou_p), None), (r.ou_staked, STK), (r.ou_pl, MON), (r.staked, STK), (r.returned, STK), (r.pl, MON),
                                     (r.running, MON), (r.high, MON), (r.below, MON))):
            cell(ws, x, 3 + k, v, f_, bg=bg, bold=k == 11)
    x = 11 + rows
    for k in range(16): cell(ws, x, 2 + k, None, bg=SLATE)
    cell(ws, x, 2, 'Season', bold=True, color=WHITE, bg=SLATE)
    for c in (4, 5, 7, 8, 10, 11, 12, 13, 14):
        cell(ws, x, c, f'=SUM({COL(c)}11:{COL(c)}{x - 1})', STK if c in (4, 7, 10, 12, 13) else MON, bold=True, color=WHITE, bg=SLATE)
    pos_neg(ws, f'E11:E{x - 1}'); pos_neg(ws, f'H11:H{x - 1}'); pos_neg(ws, f'K11:K{x - 1}'); pos_neg(ws, f'N11:Q{x - 1}')
    if len(p):
        ch = LineChart(); ch.title = 'The bank (running profit, locks included)'; ch.height = 7.5; ch.width = 14; ch.legend = None
        s = Series(Reference(ws, min_col=15, min_row=11, max_row=10 + len(p)), title='Bank'); s.graphicalProperties.line.solidFill = GOLD; s.graphicalProperties.line.width = 28000
        ch.series.append(s); ch.set_categories(Reference(ws, min_col=2, min_row=11, max_row=10 + len(p))); ch.y_axis.number_format = '$#,##0'; ch.x_axis.tickLblPos = 'low'
        ws.add_chart(ch, 'S9')
    # where the money comes from
    r0 = x + 3
    section(ws, r0, 2, 'Where the money comes from (locks included)', 9)
    header(ws, r0 + 1, 2, ['Bet type', 'Bets', 'W–L–P', 'Win %', 'Staked', 'P/L', 'ROI', 'Avg price'])
    xx = r0 + 2
    groups = (('TIPS', ['Backed the favourite', 'Backed the underdog', 'Backed the home team', 'Backed the away team']),
              ('SPREADS', ['Laid the points (fav)', 'Took the points (dog)', "Pick'em (0)", 'Home team', 'Away team']), ('OVER / UNDERS', ['Backed the over', 'Backed the under']))
    for title, keys in groups:
        cell(ws, xx, 2, title, bold=True, color=GOLD, align=LEFT, size=9); xx += 1
        for k in keys:
            d = X['where'][k]
            cell(ws, xx, 2, k, align=LEFT)
            for j, (v, f_) in enumerate(((d['bets'], '0'), (d['wlp'], None), (d['pct'], PCT), (d['staked'], STK), (d['pl'], MON), (d['roi'], EVF), (d['price'], ODD))):
                cell(ws, xx, 3 + j, v, f_).border = BOX
            xx += 1
    pos_neg(ws, f'G{r0 + 2}:H{xx}')
    # tips by price
    section(ws, r0, 12, 'Tips by price  ·  are you finding value?', 8)
    header(ws, r0 + 1, 12, ['Odds taken', 'Tips', 'W–L', 'Win %', 'Needed', 'Staked', 'P/L', 'ROI'])
    for i, d in enumerate(X['price']):
        y = r0 + 2 + i
        for j, (v, f_) in enumerate(((d['label'], None), (d['tips'], '0'), (d['wl'], None), (d['pct'], PCT), (d['needed'], PCT), (d['staked'], STK), (d['pl'], MON), (d['roi'], EVF))):
            cell(ws, y, 12 + j, v, f_, align=LEFT if j == 0 else CEN).border = BOX
    pos_neg(ws, f'R{r0 + 2}:S{r0 + 7}')
    cell(ws, r0 + 9, 12, '"Needed" = the win rate the average price needs to break even.', size=8, color=GREY, italic=True, align=LEFT)
    # locks
    r1 = xx + 2
    section(ws, r1, 2, f'Locks of the week (×{S["lock"]:g} stake)', 20)
    header(ws, r1 + 1, 2, ['Week', 'Tip lock', 'Odds', 'Result', 'P/L', 'Game', 'Spread lock', 'Line', 'Result', 'P/L', 'Game', 'O/U lock (team in game)', 'Your bet',
                           'Result', 'P/L', 'Game', 'Lock P/L', 'Extra from locking', 'Check'])
    Lk = X['locks']; tot = [0.0, 0.0, 0.0, 0.0, 0.0]
    for i, (wk, r) in enumerate(Lk.iterrows()):
        y = r1 + 2 + i; bg = PAPER if i % 2 else None
        g_ = lambda k: r[k] if k in r.index else None
        chk = ' · '.join(c for c in (g_('tip_check'), g_('sp_check'), g_('ou_check')) if isinstance(c, str) and c)
        vals = [(f'Wk {wk}', None), (g_('tip'), None), (g_('tip_odds'), ODD), (g_('tip_res'), None), (g_('tip_pl'), MON), (g_('tip_game'), None), (g_('sp'), None),
                (g_('sp_line'), LN), (g_('sp_res'), None), (g_('sp_pl'), MON), (g_('sp_game'), None), (g_('ou'), None), (g_('ou_bet'), None), (g_('ou_res'), None),
                (g_('ou_pl'), MON), (g_('ou_game'), None), (g_('lock_pl'), MON), (g_('extra'), MON), (chk or None, None)]
        for j, (v, f_) in enumerate(vals):
            v = None if isinstance(v, float) and np.isnan(v) else v
            cell(ws, y, 2 + j, v, f_, bg=bg, size=9 if j == 18 else 10, color='B3261E' if j == 18 else INK)
        for k, key in enumerate(('tip_pl', 'sp_pl', 'ou_pl', 'lock_pl', 'extra')):
            v = g_(key); tot[k] += 0 if v is None or np.isnan(v) else v
    y = r1 + 2 + len(Lk)
    for j in range(19): cell(ws, y, 2 + j, None, bg=SLATE)
    cell(ws, y, 2, 'Season', bold=True, color=WHITE, bg=SLATE)
    for c, v in zip((6, 11, 16, 18, 19), tot): cell(ws, y, c, v, MON, bold=True, color=WHITE, bg=SLATE)
    pos_neg(ws, f'F{r1 + 2}:F{y - 1}'); pos_neg(ws, f'K{r1 + 2}:K{y - 1}'); pos_neg(ws, f'P{r1 + 2}:P{y - 1}'); pos_neg(ws, f'R{r1 + 2}:S{y - 1}')
    cell(ws, y + 1, 2, 'Locks are typed on each week of the inputs file (row 25). "Extra from locking" = what the lock added over a normal stake.', size=8, color=GREY, italic=True, align=LEFT)
    widths(ws, {'A': 2, 'B': 22, 'C': 10, 'D': 9, 'E': 9, 'F': 12, 'G': 13, 'H': 11, 'I': 10, 'J': 9, 'K': 10, 'L': 12, 'M': 11, 'N': 10, 'O': 11, 'P': 10,
                'Q': 12, 'R': 11, 'S': 11, 'T': 26, 'U': 10, 'V': 10})
    ws.freeze_panes = 'A5'
    return ws


# ------------------------------------------------------------------ My Stats
def my_stats_sheet(wb, ctx):
    ms, W, you, S = ctx['mystats'], ctx['W'], ctx['you'], ctx['S']
    ws = wb.create_sheet('My Stats')
    band(ws, 'MY STATS  ·  YOUR TIPS, EVERY ANGLE', f'Flat ${S["tip"]:,.0f} a tip at fair win odds (no locks), so every split is comparable. "Odds said" = the win rate the prices implied.', 22)
    g = ms['g']; gg = g[g.graded]
    tile(ws, 5, 2, 'Record', f'{int(gg.win.sum())}–{int(len(gg) - gg.win.sum())}', f'{gg.win.mean() * 100:.1f}% · ${S["tip"]:,.0f} flat: {np.nansum(gg.flat_pl):+,.0f}' if len(gg) else '')
    tile(ws, 5, 6, 'Vs the odds', f'{ms["vs_odds"][0]:+.1f} wins', f'the prices expected {ms["vs_odds"][1]:.1f}')
    tile(ws, 5, 10, 'Average price', f'{ms["avg_price"]:.2f}', f'break-even at these prices: {ms["breakeven"] * 100:.0f}%')
    tile(ws, 5, 14, 'Streaks', f'W{ms["streak"][1]} / L{ms["streak"][2]}', 'longest winning / losing run')
    cur = ms['streak'][0]
    tile(ws, 5, 18, 'Bank peak', float(ms['peak']), f'deepest drop {ms["dd"]:,.0f} · current run {"W" if cur >= 0 else "L"}{abs(cur)}', MON)
    r = 9
    section(ws, r, 2, 'By price', 9); section(ws, r, 13, 'Favourite or underdog · home or away', 9)
    stats_rows(ws, r + 1, 2, 'Price band', ms['price'])
    stats_rows(ws, r + 1, 13, 'Who you backed', {**ms['favdog'], **ms['ha']})
    r = 19
    section(ws, r, 2, 'Time slot', 9); section(ws, r, 13, 'Division games', 9)
    stats_rows(ws, r + 1, 2, 'Slot', ms['slot']); stats_rows(ws, r + 1, 13, 'Opponent', ms['div'])
    r = 26
    section(ws, r, 2, 'Lone calls', 9); section(ws, r, 13, 'Against the spread', 9)
    stats_rows(ws, r + 1, 2, 'Experts with you', ms['experts']); stats_rows(ws, r + 1, 13, 'Your tip vs the line', ms['ats'])
    r = 33
    section(ws, r, 2, 'When the crowd agrees · and you went against it', 9)
    header(ws, r + 1, 2, ['Experts on one side', 'Games', 'Majority right', 'You against them', 'P/L going against'])
    for i, d in enumerate(ms['crowd']):
        y = r + 2 + i
        for j, (v, f_) in enumerate(((d['label'], None), (d['games'], '0'), (d['crowd_right'], PCT), (d['against'], None), (d['pl'], MON))):
            cell(ws, y, 2 + j, v, f_, align=LEFT if j == 0 else CEN).border = BOX
    pos_neg(ws, f'F{r + 2}:F{r + 5}')
    section(ws, r, 13, 'Teams that pay you · and cost you (best 4, worst 4)', 9)
    header(ws, r + 1, 13, ['Team', 'Backed', 'W–L', 'P/L', 'Against', 'W–L', 'P/L', 'Net'])
    tm = ms['teams']; sel = pd.concat([tm.head(4), tm.tail(4).iloc[::-1]])
    from nflmodel.tipping_sheets import wl
    for i, (_, t) in enumerate(sel.iterrows()):
        y = r + 2 + i
        vals = ((f'{t.team} · {TEAMS[t.team][0]}' + ('  ▲' if t.key >= 0 else '  ▼'), None), (t.backed, '0'), (wl(t.backed_w, t.backed - t.backed_w), None), (t.backed_pl, MON),
                (t.against, '0'), (wl(t.against_w, t.against - t.against_w), None), (t.against_pl, MON), (t.net, MON))
        for j, (v, f_) in enumerate(vals): cell(ws, y, 13 + j, v, f_, align=LEFT if j == 0 else CEN, size=9 if j == 0 else 10).border = BOX
    pos_neg(ws, f'P{r + 2}:P{r + 9}'); pos_neg(ws, f'S{r + 2}:T{r + 9}')
    # season so far (one row a week) and the full team list
    r = 45
    section(ws, r, 13, 'Week by week', 5)
    header(ws, r + 1, 13, ['Week', 'Wins', 'P/L ($ flat)', 'Your rank'])
    for w in range(1, NW + 1):
        y = r + 1 + w; cell(ws, y, 13, f'Wk {w}', align=LEFT, bg=PAPER if w % 2 == 0 else None)
        if ctx['meta'].played[w] == 0: continue
        x = g[g.week == w]
        for j, (v, f_) in enumerate(((W.at[you, w], '0'), (float(np.nansum(x.flat_pl)), MON), (1 + int((W[w] > W.at[you, w]).sum()), '0'))):
            cell(ws, y, 14 + j, v, f_, bg=PAPER if w % 2 == 0 else None)
    pos_neg(ws, f'O{r + 2}:O{r + 1 + NW}')
    if ctx['last']:
        ch = BarChart(); ch.title = 'Your wins each week'; ch.height = 7; ch.width = 13; ch.legend = None
        ch.add_data(Reference(ws, min_col=14, min_row=r + 2, max_row=r + 1 + ctx['last'])); ch.set_categories(Reference(ws, min_col=13, min_row=r + 2, max_row=r + 1 + ctx['last']))
        ch.series[0].graphicalProperties.solidFill = ACCENT; ch.y_axis.scaling.min = 0; ch.y_axis.majorGridlines = None
        ws.add_chart(ch, f'R{r + 1}')
    section(ws, r, 2, 'Every team', 9)
    header(ws, r + 1, 2, ['Team', 'Backed', 'W–L', 'P/L', 'Against', 'W–L', 'P/L', 'Net'])
    for i, (_, t) in enumerate(tm.iterrows()):
        y = r + 2 + i; bg = PAPER if i % 2 else None
        vals = ((f'{t.team} · {TEAMS[t.team][0]}', None), (t.backed, '0'), (wl(t.backed_w, t.backed - t.backed_w), None), (t.backed_pl, MON),
                (t.against, '0'), (wl(t.against_w, t.against - t.against_w), None), (t.against_pl, MON), (t.net, MON))
        for j, (v, f_) in enumerate(vals): cell(ws, y, 2 + j, v, f_, align=LEFT if j == 0 else CEN, bg=bg, size=9 if j == 0 else 10)
    pos_neg(ws, f'E{r + 2}:E{r + 2 + len(tm)}'); pos_neg(ws, f'H{r + 2}:I{r + 2 + len(tm)}')
    widths(ws, {'A': 2, 'B': 38, 'L': 3, 'M': 30})
    for c in 'CDEFGHIJK': ws.column_dimensions[c].width = 9
    for c in 'NOPQRSTU': ws.column_dimensions[c].width = 9
    ws.column_dimensions['C'].width = 9
    ws.freeze_panes = 'A5'
    return ws


# ------------------------------------------------------------------ Spreads & Totals
def spreads_sheet(wb, ctx):
    st, S = ctx['spreads'], ctx['S']
    ws = wb.create_sheet('Spreads & Totals')
    band(ws, 'SPREADS & TOTALS', f'Every spread and over/under bet at flat stakes (${S["spread"]:,.0f} / ${S["ou"]:,.0f}, no locks). Fair line and price = midpoint of open and close.', 22)
    sp, ou = st['sp'], st['ou']
    spw, spl, spp = (sp.sp_res == '✓').sum(), (sp.sp_res == '✗').sum(), (sp.sp_res == 'Push').sum()
    ow, ol, op = (ou.ou_res == '✓').sum(), (ou.ou_res == '✗').sum(), (ou.ou_res == 'Push').sum()
    from nflmodel.tipping_sheets import wl
    tile(ws, 5, 2, 'Spreads', wl(spw, spl, spp), f'{spw / max(1, spw + spl) * 100:.1f}% · need 52.4% at 1.91')
    tile(ws, 5, 5, 'Spread P/L', float(sp.sp_pl.sum()), f'ROI {sp.sp_pl.sum() / max(1, (spw + spl) * S["spread"]) * 100:+.1f}%', MON2)
    tile(ws, 5, 8, 'Over / unders', wl(ow, ol, op), f'{ow / max(1, ow + ol) * 100:.1f}% correct')
    tile(ws, 5, 11, 'O/U P/L', float(ou.ou_pl.sum()), f'ROI {ou.ou_pl.sum() / max(1, (ow + ol) * S["ou"]) * 100:+.1f}%', MON2)
    tile(ws, 5, 14, 'Combined', float(sp.sp_pl.sum() + ou.ou_pl.sum()), f'{spw + spl + ow + ol} bets', MON2, GOLD)
    cur = lambda t: (f'W{t[0]}' if t[0] >= 0 else f'L{-t[0]}')
    tile(ws, 5, 17, 'Streaks now', f'Spread {cur(st["sp_streak"])} · O/U {cur(st["ou_streak"])}', f'peak +${st["peak"]:,.0f} · deepest drop -${abs(st["dd"]):,.0f}')
    sr, orr = st['sp_rows'], st['ou_rows']; ks, ko = list(sr), list(orr)
    r = 9
    section(ws, r, 2, 'Spread bets', 9); section(ws, r, 13, 'Over / under bets', 9)
    y1 = y2 = r + 1
    for title, keys in (('Side', ks[0:3]), ('Line size', ks[3:7]), ('Home / away', ks[7:9]), ('Vs your tip', ks[9:11])):
        y1 = stats_rows(ws, y1, 2, title, {k: sr[k] for k in keys}) + 2
    for title, keys in (('Over / under', ko[0:2]), ('Total size', ko[2:6]), ('Time slot', ko[6:9]), ('Division', ko[9:11])):
        y2 = stats_rows(ws, y2, 13, title, {k: orr[k] for k in keys}) + 2
    r = max(y1, y2) + 1
    section(ws, r, 2, 'Week by week (flat stakes)', 7)
    header(ws, r + 1, 2, ['Week', 'Spreads W–L–P', 'Spread P/L', 'Over / unders', 'O/U P/L', 'Both'])
    for w, row in st['weeks'].iterrows():
        y = r + 1 + w; bg = PAPER if w % 2 == 0 else None
        cell(ws, y, 2, f'Wk {w}', align=LEFT, bg=bg)
        for j, (key, f_) in enumerate((('sp', None), ('sp_pl', MON2), ('ou', None), ('ou_pl', MON2), ('both', MON2))):
            v = row[key] if key in row.index else None
            cell(ws, y, 3 + j, None if (isinstance(v, float) and np.isnan(v)) else v, f_, bg=bg)
    pos_neg(ws, f'D{r + 2}:D{r + 1 + NW}'); pos_neg(ws, f'F{r + 2}:G{r + 1 + NW}')
    widths(ws, {'A': 2, 'B': 30, 'L': 3, 'M': 18})
    for c in 'CDEFGHIJKNOPQRSTU': ws.column_dimensions[c].width = 9
    ws.freeze_panes = 'A5'
    return ws


# ------------------------------------------------------------------ Head to Head
def h2h_sheet(wb, ctx):
    h, S = ctx['h2h'], ctx['S']
    ws = wb.create_sheet('Head to Head')
    band(ws, f'HEAD TO HEAD  ·  YOU vs {h["opp"].upper()}', 'Change the opponent in inputs/tipping_inputs.xlsx → Settings (B10). P/L = $%d flat tips at fair odds.' % S['tip'], 20)
    tile(ws, 5, 2, 'Your record', h['you_rec'], f'{h["you_pl"]:+,.0f} profit')
    tile(ws, 5, 5, f'{h["opp"]}', h['them_rec'], f'{h["them_pl"]:+,.0f} profit')
    tile(ws, 5, 8, 'When you disagreed', h['dis_rec'], f'you–them, over {h["dis_n"]} games')
    tile(ws, 5, 12, 'Same pick', f'{h["same"] * 100:.0f}%', 'of games')
    section(ws, 9, 2, 'Week by week', 7)
    header(ws, 10, 2, ['Week', 'You', h['opp'], 'Edge', 'Running', 'Your P/L', 'Their P/L'])
    for i, (wk, r) in enumerate(h['weeks'].iterrows()):
        y = 11 + i; cell(ws, y, 2, f'Wk {wk}')
        if 'you' in r.index and not np.isnan(r.you):
            for j, (k, f_) in enumerate((('you', '0'), ('them', '0'), ('edge', '+0;-0;0'), ('running', '+0;-0;0'), ('your_pl', MON), ('their_pl', MON))):
                cell(ws, y, 3 + j, r[k], f_)
    pos_neg(ws, f'E11:H{10 + NW}')
    section(ws, 9, 11, 'Every game you disagreed on', 7)
    header(ws, 10, 11, ['Week', 'Game', 'You', 'Them', 'Winner', 'Who was right'])
    for i, r in h['games'].iterrows():
        y = 11 + i; bg = PAPER if i % 2 else None
        for j, v in enumerate((f'Wk {r.week}', r.game, r.you, r.them, r.winner or 'to play', r.right)):
            cell(ws, y, 11 + j, v, bg=bg, align=LEFT if j == 1 else CEN, size=9)
    ws.conditional_formatting.add(f'P11:P{11 + len(h["games"])}', CellIsRule(operator='equal', formula=['"You"'], font=Font(color='1E7B45', bold=True)))
    ws.conditional_formatting.add(f'P11:P{11 + len(h["games"])}', CellIsRule(operator='equal', formula=['"Them"'], font=Font(color='B3261E', bold=True)))
    r0 = 12 + NW
    section(ws, r0, 2, 'You vs every expert (only games where you split)', 7)
    header(ws, r0 + 1, 2, ['Rank', 'Expert', 'Split games', 'You won', 'They won', 'Net'])
    for i, r in enumerate(h['every'].itertuples()):
        y = r0 + 2 + i; bg = PAPER if i % 2 else None
        for j, (v, f_) in enumerate(((i + 1, '0'), (r.expert, None), (r.split, '0'), (r.you, '0'), (r.them, '0'), (r.net, '+0;-0;0'))):
            cell(ws, y, 2 + j, v, f_, bg=bg, align=LEFT if j == 1 else CEN)
    pos_neg(ws, f'G{r0 + 2}:G{r0 + 1 + len(h["every"])}')
    widths(ws, {'A': 2, 'B': 8, 'C': 20, 'D': 14, 'E': 9, 'F': 9, 'G': 10, 'H': 10, 'I': 3, 'J': 3, 'K': 8, 'L': 22, 'M': 8, 'N': 8, 'O': 10, 'P': 14})
    ws.freeze_panes = 'A5'
    return ws


# ------------------------------------------------------------------ Expert Scout
def scout_sheet(wb, ctx):
    X = ctx['scout']
    ws = wb.create_sheet('Expert Scout')
    band(ws, 'EXPERT SCOUT  ·  WHO TO TRUST, AND WHEN', 'Win rate in every situation (blank = fewer than 5 games). Green = better than the field. Use it for close games, upsets and big favourites.', 13)
    cols = ['Rank', 'Tipper', 'Outlet', 'Overall', 'Last 3 weeks', 'Close games\n(line ≤ 3)', 'Big favourites\n(line ≥ 7)', 'Underdog calls', 'Against the\nconsensus',
            'Vs the spread', 'Agrees with you', 'Strongest at']
    header(ws, 4, 1, cols, height=34)
    for i, (t, r) in enumerate(X.iterrows()):
        y = 5 + i; mine = t == ctx['you']; new = t in (MODEL, LINE)
        bg = LIGHTGOLD if mine else (PAPER if new else None)
        for j, (v, f_) in enumerate(((i + 1, '0'), (t, None), (ctx['outlets'][t], None), (r.overall, PCT), (r.last3, PCT), (r.close, PCT), (r.bigfav, PCT), (r.dogs, None),
                                     (r.against, PCT), (r.ats, PCT), (r.agrees, PCT), (r.strongest, None))):
            cell(ws, y, 1 + j, v, f_, bg=bg, align=LEFT if j in (1, 2, 11) else CEN, bold=j == 1 and (mine or new), size=8 if j == 2 else 10,
                 color=ACCENT if (new and j == 1) else (GREY if j == 2 else INK))
    last = 4 + len(X)
    for c in 'DEFGIJ': scale(ws, f'{c}5:{c}{last}')
    widths(ws, {'A': 6, 'B': 20, 'C': 12, 'D': 9, 'E': 10, 'F': 11, 'G': 12, 'H': 11, 'I': 11, 'J': 10, 'K': 10, 'L': 17})
    ws.freeze_panes = 'C5'
    return ws


# ------------------------------------------------------------------ Edge Finder
def edge_sheet(wb, ctx):
    e, S = ctx['edge'], ctx['S']; g = e['g']
    ws = wb.create_sheet('Edge Finder')
    band(ws, f'EDGE FINDER  ·  WEEK {e["week"]}', 'True % = the closing market, vig removed. EV = true % × your fair price − 1. Positive EV = the price beats the market. '
         'Pick the week in inputs → Settings (B11); blank = the next week you have tips and odds for.', 34)
    ev_tips = g.best_tip_ev.notna().sum()
    tile(ws, 5, 2, 'Value tips on offer', f'{int((g[["ev_a", "ev_h"]].max(axis=1) > 0).sum())} of {int(ev_tips)}', 'games where one side has EV > 0')
    for c, lab, k in ((7, 'Your tips · average EV', 'my_tip_ev'), (12, 'Your spread bets · average EV', 'my_sp_ev'), (17, 'Your total bets · average EV', 'my_ou_ev')):
        tile(ws, 5, c, lab, num(g[k].mean()) if g[k].notna().any() else '–', f'{int(g[k].notna().sum())} picks', EVF)
    if e['top_tip']:
        t = e['top_tip'][0]; tile(ws, 5, 22, 'Biggest edge this week', f'{t["ev"] * 100:+.0f}%', f'{t["play"]} · {t["game"]}')
    section(ws, 9, 1, 'Game by game', 34)
    groups = [(2, 'TIP · win odds'), (11, 'SPREAD · your fair line'), (20, 'OVER / UNDER'), (30, 'WHO BACKS THE HOME TEAM')]
    for c, lab in groups: cell(ws, 10, c, lab, size=8, bold=True, color=GOLD, align=LEFT)
    cols = [('Game', None, None), ('Kickoff', 'kickoff', None), ('Away fair odds', 'aodds', ODD), ('Home fair odds', 'hodds', ODD), ('Away true %', 'true_a', PCT), ('Home true %', 'true_h', PCT),
            ('Away EV', 'ev_a', EVF), ('Home EV', 'ev_h', EVF), ('Best tip', 'best_tip', None), ('Your tip', 'tip', None), ('Your EV', 'my_tip_ev', EVF),
            ('Close home line', 'c_hline', LN), ('Fair home line', 'hline', LN), ('Home covers %', 'cov_h', PCT), ('Away covers %', 'cov_a', PCT), ('Home EV', 'ev_hs', EVF),
            ('Away EV', 'ev_as', EVF), ('Best spread', 'best_sp', None), ('Your spread', 'spread_bet', None), ('Your EV', 'my_sp_ev', EVF),
            ('Close total', 'c_total', '0.0'), ('Fair total', 'total', '0.0'), ('Over %', 'p_over', PCT), ('Under %', 'p_under', PCT), ('Over EV', 'ev_o', EVF), ('Under EV', 'ev_u', EVF),
            ('Best total', 'best_tot', None), ('Your total', 'ou_bet', None), ('Your EV', 'my_ou_ev', EVF),
            ('Experts', 'exp_home', PCT0), ('Skill-weighted', 'skill_home', PCT0), ('Market (close)', 'true_h', PCT0), ('Lean', 'lean', None)]
    header(ws, 11, 1, [c[0] for c in cols], height=32)
    for i, r in enumerate(g.itertuples()):
        y = 12 + i; bg = PAPER if i % 2 else None
        for j, (lab, k, f_) in enumerate(cols):
            v = f'{r.away} @ {r.home}' if k is None else getattr(r, k)
            cell(ws, y, 1 + j, v, f_, bg=bg, size=9, align=LEFT if j in (0, 1) else CEN)
    last = 11 + len(g)
    for k in ('ev_a', 'ev_h', 'my_tip_ev', 'ev_hs', 'ev_as', 'my_sp_ev', 'ev_o', 'ev_u', 'my_ou_ev'):
        c = COL(1 + [x[1] for x in cols].index(k)); pos_neg(ws, f'{c}12:{c}{last}')
    r0 = last + 3
    section(ws, r0, 1, 'Top value plays this week', 34)
    for c0, title, lst in ((1, 'TIPS', e['top_tip']), (9, 'SPREAD BETS', e['top_sp']), (17, 'OVER / UNDER BETS', e['top_ou'])):
        cell(ws, r0 + 1, c0, title, size=8, bold=True, color=GOLD, align=LEFT)
        header(ws, r0 + 2, c0, ['Play', 'Price', 'True %', 'EV', 'Exp. $', 'Game'])
        for i, d in enumerate(lst):
            for j, (k, f_) in enumerate((('play', None), ('price', ODD), ('true', PCT), ('ev', EVF), ('exp', MON2), ('game', None))):
                cell(ws, r0 + 3 + i, c0 + j, d[k], f_, align=LEFT if j in (0, 5) else CEN, size=9)
        pos_neg(ws, f'{COL(c0 + 3)}{r0 + 3}:{COL(c0 + 4)}{r0 + 8}')
    widths(ws, {'A': 13, 'B': 15})
    for k in range(3, 35): ws.column_dimensions[COL(k)].width = 8.5
    for c in ('A', 'I', 'Q'): ws.column_dimensions[c].width = 13
    ws.column_dimensions['N'].width = 9; ws.column_dimensions['V'].width = 11; ws.column_dimensions['AG'].width = 14
    ws.freeze_panes = 'B12'
    return ws


# ------------------------------------------------------------------ Value Report
def value_sheet(wb, ctx):
    v, S, G = ctx['value'], ctx['S'], ctx['G']
    ws = wb.create_sheet('Value Report')
    band(ws, 'VALUE REPORT  ·  SKILL OR LUCK?', 'Expected = what your picks were worth at the closing market (EV × stake). Luck = actual − expected. '
         'The value bot always tips the best-EV side and bets spreads/totals only when EV > 0.', 24)
    W = v['weeks']; gp = G[G.played]
    exp = lambda ev, st: st * gp[ev].sum()
    tile(ws, 5, 2, 'Tips · actual vs expected', float(gp.tip_pl.sum()), f'expected {exp("my_tip_ev", S["tip"]):+,.0f}', MON)
    tile(ws, 5, 6, 'Spreads · actual vs expected', float(gp.sp_pl.sum()), f'expected {exp("my_sp_ev", S["spread"]):+,.0f}', MON)
    tile(ws, 5, 10, 'Totals · actual vs expected', float(gp.ou_pl.sum()), f'expected {exp("my_ou_ev", S["ou"]):+,.0f}', MON)
    tile(ws, 5, 14, 'Your tips vs the market', f'{v["wins_vs_true"]:+.1f} wins', f'{int(((gp.tip == gp.winner) & gp.tip.notna()).sum())} wins vs {v["true_wins"]:.1f} the market expected')
    tile(ws, 5, 18, 'Value bot · tips', float(v['bot_tip']), f'expected {v["bot_tip_exp"]:+,.0f}', MON)
    tile(ws, 5, 22, 'Value bot · spreads + totals', float(v['bot_sb']), f'expected {v["bot_sb_exp"]:+,.0f} · {v["bot_sb_n"]} bets', MON)
    section(ws, 9, 2, 'Week by week', 23)
    for c, lab in ((3, f'TIPS (${S["tip"]:,.0f})'), (8, f'SPREAD BETS (${S["spread"]:,.0f})'), (13, f'OVER / UNDER BETS (${S["ou"]:,.0f})'), (18, 'VALUE BOT'), (21, 'SEASON RUNNING TOTAL')):
        cell(ws, 10, c, lab, size=8, bold=True, color=GOLD, align=LEFT)
    header(ws, 11, 2, ['Week', 'Picks', 'Avg EV', 'Expected', 'Actual', 'Luck', 'Bets', 'Avg EV', 'Expected', 'Actual', 'Luck', 'Bets', 'Avg EV', 'Expected', 'Actual', 'Luck',
                       'Tips', 'Spreads', 'Totals', 'Expected', 'Actual', 'Value bot', 'Luck'])
    nrow = 0
    for wk, r in W.iterrows():
        y = 12 + nrow; nrow += 1; bg = PAPER if nrow % 2 == 0 else None
        cell(ws, y, 2, f'Wk {wk}', bg=bg)
        if np.isnan(r.get('tip_n', np.nan)): continue
        c = 3
        for k in ('tip', 'sp', 'ou'):
            for f, f_ in (('n', '0'), ('ev', EVF), ('exp', MON), ('act', MON), ('luck', MON)):
                cell(ws, y, c, r.get(f'{k}_{f}'), f_, bg=bg, size=9); c += 1
        if not np.isnan(r.get('bot_tip', np.nan)):
            for k in ('bot_tip', 'bot_sp', 'bot_ou', 'run_exp', 'run_act', 'run_bot'):
                cell(ws, y, c, r[k], MON, bg=bg, size=9); c += 1
            cell(ws, y, c, r.run_act - r.run_exp, MON, bg=bg, size=9)
    pos_neg(ws, f'F12:Y{11 + nrow}')
    y = 12 + nrow
    for k in range(24): cell(ws, y, 2 + k, None, bg=SLATE)
    cell(ws, y, 2, 'Season', bold=True, color=WHITE, bg=SLATE)
    for c in (3, 5, 6, 7, 8, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21):
        cell(ws, y, c, f'=SUM({COL(c)}12:{COL(c)}{y - 1})', '0' if c in (3, 8, 13) else MON, bold=True, color=WHITE, bg=SLATE, size=9)
    done = W.dropna(subset=['run_exp'])
    if len(done):
        ch = LineChart(); ch.title = 'Running total: actual, expected, value bot'; ch.height = 7.5; ch.width = 18; ch.legend.position = 'b'
        for c, t in ((22, 'Expected'), (23, 'Actual'), (24, 'Value bot')):
            s = Series(Reference(ws, min_col=c, min_row=12, max_row=11 + len(done)), title=t); s.smooth = False; ch.series.append(s)
        ch.set_categories(Reference(ws, min_col=2, min_row=12, max_row=11 + len(done))); ch.y_axis.number_format = '$#,##0'; ch.x_axis.tickLblPos = 'low'
        ws.add_chart(ch, f'N{y + 3}')
    r0 = y + 3
    section(ws, r0, 2, 'Your tips vs the market\'s chances', 8)
    header(ws, r0 + 1, 2, ['True chance', 'Tips', 'Expected wins', 'Actual wins', '+/− wins', 'Win %', 'P/L'])
    for i, b in enumerate(v['bands']):
        yy = r0 + 2 + i; last = i == len(v['bands']) - 1
        for j, (k, f_) in enumerate((('label', None), ('tips', '0'), ('exp', '0.0'), ('act', '0'), ('plus', '+0.0;-0.0;0.0'), ('pct', PCT), ('pl', MON))):
            cell(ws, yy, 2 + j, b[k], f_, bold=last, bg=PAPER if last else None, align=LEFT if j == 0 else CEN).border = BOX
    pos_neg(ws, f'F{r0 + 2}:H{r0 + 7}')
    r1 = r0 + 10
    section(ws, r1, 2, 'Did you take the value?', 8)
    header(ws, r1 + 1, 2, ['Picks', 'Count', 'Won', 'Win %', 'Actual', 'Expected'])
    for i, b in enumerate(v['took']):
        yy = r1 + 2 + i
        for j, (k, f_) in enumerate((('label', None), ('picks', '0'), ('won', '0'), ('pct', PCT), ('act', MON), ('exp', MON))):
            cell(ws, yy, 2 + j, b[k], f_, align=LEFT if j == 0 else CEN).border = BOX
    pos_neg(ws, f'F{r1 + 2}:G{r1 + 7}')
    widths(ws, {'A': 2, 'B': 24})
    for k in range(3, 26): ws.column_dimensions[COL(k)].width = 9.5
    ws.freeze_panes = 'C12'
    return ws


# ------------------------------------------------------------------ Settings (read-only copy) and the Dashboard block
def settings_sheet(wb, ctx):
    S = ctx['S']; ws = wb.create_sheet('Settings')
    band(ws, 'SETTINGS  (read-only copy)', 'These come from inputs/tipping_inputs.xlsx → Settings. Change them there; the week-tab formulas read these cells.', 6)
    for i, (lab, v, f_) in enumerate((('Tip stake', S['tip'], STK), ('Spread bet stake', S['spread'], STK), ('Over / under stake', S['ou'], STK),
                                      ('Lock of the week multiplier', S['lock'], '0.0"×"'), ('Leaderboard ranked by', S.get('rank_by', 'Wins'), None),
                                      ('Head to Head opponent', ctx['h2h']['opp'], None), ('Edge Finder week', ctx['edge']['week'], '0'))):
        cell(ws, 5 + i, 1, lab, align=LEFT, bold=True); cell(ws, 5 + i, 2, v, f_, bg=CREAM)
    rows = ['', 'Fair-price rule (used everywhere):', '• Lines and totals: midpoint of open and close; a quarter point goes to the .5.',
            '• Prices and win odds: ROUND(2 / (1/open + 1/close), 2). If only one of open / close is typed, that one is used.',
            '• Never the closing number alone. (The Edge Finder and Value Report use the closing market only to estimate the TRUE chance.)']
    for i, t in enumerate(rows): cell(ws, 13 + i, 1, t, align=LEFT, bold=i == 1, color=GOLD if i == 1 else INK)
    widths(ws, {'A': 30, 'B': 18})
    return ws


def dashboard_block(ws, ctx, r0):
    """A 'your tipping season' summary and a contents list with links, added under the model's Dashboard."""
    from nflmodel.workbook import section as sec
    R, you, M = ctx['R'], ctx['you'], ctx['money']
    p = M.dropna(subset=['staked'])
    sec(ws, r0, 1, f'Your tipping season  ·  Weeks 1–{ctx["last"]}', 7)
    rows = [('Your record', f'{int(R.at[you, "W"])}–{int(R.at[you, "L"])} ({R.at[you, "win_pct"] * 100:.1f}%) · rank #{int(R.at[you, "rank"])} of {len(R)}')]
    if MODEL in R.index:
        rows.append(('The model', f'{int(R.at[MODEL, "W"])}–{int(R.at[MODEL, "L"])} ({R.at[MODEL, "win_pct"] * 100:.1f}%) · rank #{int(R.at[MODEL, "rank"])}'))
    if LINE in R.index:
        rows.append(('The betting line', f'{int(R.at[LINE, "W"])}–{int(R.at[LINE, "L"])} ({R.at[LINE, "win_pct"] * 100:.1f}%) · rank #{int(R.at[LINE, "rank"])}'))
    lead = R.sort_values('order').index[0]
    rows.append(('Leader', f'{lead} ({int(R.at[lead, "W"])} wins)'))
    if len(p):
        rows.append(('Money', f'{p.pl.sum():+,.0f} on ${p.staked.sum():,.0f} staked · ROI {p.pl.sum() / p.staked.sum() * 100:+.1f}%'))
    for i, (a, b) in enumerate(rows):
        cell(ws, r0 + 1 + i, 1, a, bold=True, color=ACCENT, align=LEFT, size=9); cell(ws, r0 + 1 + i, 2, b, align=LEFT)
    r = r0 + 2 + len(rows)
    sec(ws, r, 1, 'Contents', 7)
    sheets = [('Leaderboard', 'everyone ranked, plus the model and the line'), ('Money', 'P/L, the bank, locks'), ('My Stats', 'your tips from every angle'),
              ('Spreads & Totals', 'spread and over/under bets'), ('Head to Head', 'you vs one tipper'), ('Expert Scout', 'who to trust, and when'),
              ('Edge Finder', 'this week\'s value'), ('Value Report', 'skill or luck?'), (f'Wk {min(NW, ctx["last"] + 1)}', 'this week\'s tab (all 18 weeks have one)'),
              ('Power Rankings', 'the model\'s team ratings'), ('Season Projections', 'playoff odds'), ('About', 'how it works + self-test'), ('Settings', 'stakes and the fair-price rule')]
    for i, (s, d) in enumerate(sheets):
        link(ws, r + 1 + i, 1, s, s); cell(ws, r + 1 + i, 2, d, size=9, color=GREY, align=LEFT)
    return r + 1 + len(sheets)


def add_tipping(wb, ctx, model):
    """Add every tipping sheet to the model workbook `wb`. model: {gid: {'tip': team, 'prob': win % of that team}}."""
    leaderboard(wb, ctx); money_sheet(wb, ctx); my_stats_sheet(wb, ctx); spreads_sheet(wb, ctx); h2h_sheet(wb, ctx)
    scout_sheet(wb, ctx); edge_sheet(wb, ctx); value_sheet(wb, ctx)
    for wk in range(1, NW + 1): week_tab(wb, ctx, wk, model)
    settings_sheet(wb, ctx)
    for n in TIP_SHEETS + ['Settings']: nav(wb[n])
    for wk in range(1, NW + 1):
        nav(wb[f'Wk {wk}'], ([('◂ Wk %d' % (wk - 1), f'Wk {wk - 1}')] if wk > 1 else []) + ([('Wk %d ▸' % (wk + 1), f'Wk {wk + 1}')] if wk < NW else []))
    names = ['Dashboard'] + TIP_SHEETS + [f'Wk {w}' for w in range(1, NW + 1)]
    wb._sheets = [wb[n] for n in names] + [s for s in wb._sheets if s.title not in names]
